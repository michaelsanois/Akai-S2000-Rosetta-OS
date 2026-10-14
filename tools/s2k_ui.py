"""Drive the emulated S2000 UI: boot once, snapshot, then press keys and record the LCD.

  py -3.11 -I s2k_ui.py OS.bin keymap               press each of the 16 matrix keys from the main screen
  py -3.11 -I s2k_ui.py OS.bin seq r,c r,c ...      press a sequence of keys, print the LCD after each

Snapshots are taken at block boundaries (emu_stop from the block hook), which resumes cleanly.
"""
import copy
import pickle
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s2k_emu as E  # noqa: E402
from unicorn import UcError  # noqa: E402
from unicorn.x86_const import UC_X86_REG_CS, UC_X86_REG_IP  # noqa: E402

BOOT_BLOCKS = 20_000_000


class UI:
    def __init__(self, os_bin):
        self.emu = E.S2K(os_bin)
        self.stop_at = None
        orig = self.emu._block

        def blk(uc, address, size, ud):
            orig(uc, address, size, ud)
            if self.stop_at is not None and self.emu.nblocks >= self.stop_at:
                uc.emu_stop()
        # replace the block hook's work: S2K registered its bound method; wrap by monkeypatching the method
        self.emu._block_impl = blk
        self.started = False

    def run_blocks(self, n):
        emu = self.emu
        self.stop_at = emu.nblocks + n
        mu = emu.mu
        if not self.started:
            self.started = True
            mu.reg_write(UC_X86_REG_CS, 0)
            mu.reg_write(E.UC_X86_REG_EFLAGS, 0x0002)
            start = 0x50
        else:
            # unicorn 16-bit: emu_start's begin is LINEAR (it sets IP = begin - CS*16)
            start = (mu.reg_read(UC_X86_REG_CS) << 4) + mu.reg_read(UC_X86_REG_IP)
        try:
            mu.emu_start(start, 0xFFFFFFFF)
        except UcError as e:
            cs, ip = mu.reg_read(UC_X86_REG_CS), mu.reg_read(UC_X86_REG_IP)
            raise RuntimeError(f"emu error {e} at {cs:04x}:{ip:04x}")

    def ticks(self, n):
        self.run_blocks(n * E.TICK_BLOCKS)

    def snapshot(self):
        e = self.emu
        return (e.mu.context_save(), bytes(e.mu.mem_read(0, 0x100000)),
                pickle.dumps((e.lcd, e.fdc, e.icu, e.ports, e.keyrow, e.nblocks, getattr(e, "ticks", 0),
                              getattr(e, "tick_pending", False))))

    def restore(self, snap):
        e = self.emu
        ctx, mem, dev = snap
        e.mu.context_restore(ctx)
        e.mu.mem_write(0, mem)
        (e.lcd, e.fdc, e.icu, e.ports, e.keyrow, e.nblocks, e.ticks, e.tick_pending) = pickle.loads(dev)
        e.pressed = set()

    def press(self, key, hold=60, after=250):
        self.emu.pressed = {key}
        self.ticks(hold)
        self.emu.pressed = set()
        self.ticks(after)

    def screen(self):
        l1, l2 = self.emu.lcd.lines()
        return f"|{l1}|{l2}|"


def patch_hook(emu):
    """S2K registered emu._block directly; route it through _block_impl when present."""
    base = E.S2K._block

    def dispatch(uc, address, size, ud):
        impl = getattr(emu, "_block_impl", None)
        (impl or (lambda *a: base(emu, *a)))(uc, address, size, ud)
    return dispatch


def main():
    os_bin = open(sys.argv[1], "rb").read()
    cmd = sys.argv[2]
    # make S2K's block hook overridable before construction
    E.S2K._block_orig = E.S2K._block

    def _block(self, uc, address, size, ud):
        impl = getattr(self, "_block_impl", None)
        if impl:
            impl(uc, address, size, ud)
        else:
            E.S2K._block_orig(self, uc, address, size, ud)
    E.S2K._block = _block
    img = os.path.splitext(sys.argv[1])[0] + ".img"
    if "S2K_DISK" not in os.environ and os.path.exists(img):
        os.environ["S2K_DISK"] = img      # the build's own floppy in the drive (hi code); S2K_DISK= for none
    ui = UI(os_bin)
    ui.emu._block_impl = None

    def blk(uc, address, size, ud):
        E.S2K._block_orig(ui.emu, uc, address, size, ud)
        if ui.stop_at is not None and ui.emu.nblocks >= ui.stop_at:
            uc.emu_stop()
    ui.emu._block_impl = blk

    if cmd == "memuse":
        # writes into LO-HI from power-on, through boot and a key tour: which pages ever get written
        from unicorn import UC_HOOK_MEM_WRITE
        lo_, hi_ = (int(x, 16) for x in sys.argv[3].split("-"))
        pages = {}

        def wr(uc, access, address, size, value, ud):
            pg = address & ~0xFF
            if pg not in pages:
                pages[pg] = (uc.reg_read(UC_X86_REG_CS), uc.reg_read(UC_X86_REG_IP))
        ui.emu.mu.hook_add(UC_HOOK_MEM_WRITE, wr, None, lo_, hi_)
    t = time.time()
    # boot until the main screen is up ("prog active" on line 2), then let it settle
    for _ in range(120):
        ui.run_blocks(1_000_000)
        if any(t in ui.emu.lcd.lines()[1] for t in ("prog active", "LOAD ")):   # stock / Rosetta 0.12+ HOME
            ui.run_blocks(2_000_000)
            break
    print(f"booted in {time.time() - t:.0f}s: {ui.screen()}")
    snap = ui.snapshot()
    if cmd == "keymap":
        for r in range(8):
            for c in range(2):
                ui.restore(snap)
                ui.press((r, c))
                print(f"key r{r}c{c}: {ui.screen()}")
    elif cmd == "tree":
        keys = [(r, c) for r in range(8) for c in range(2)]
        for k in keys:
            ui.restore(snap)
            ui.press(k)
            s1 = ui.screen()
            snap1 = ui.snapshot()
            print(f"== r{k[0]}c{k[1]}: {s1}")
            for k2 in keys:
                ui.restore(snap1)
                ui.press(k2)
                s2 = ui.screen()
                if s2 != s1:
                    print(f"   + r{k2[0]}c{k2[1]}: {s2}")
    elif cmd == "note":
        e = ui.emu
        print("rx ring ptrs:", hex(int.from_bytes(e.mu.mem_read(0x73A0, 2), "little")),
              hex(int.from_bytes(e.mu.mem_read(0x73A2, 2), "little")))
        from unicorn import UC_HOOK_CODE
        L = lambda seg, off: (seg << 4) + off
        probes = {L(0x2B9D, 0x0122): "011D: is note-on", L(0x2B9D, 0x0131): "0131: [7A86]&1 capture path",
                  L(0x2B9D, 0x013B): "013B: normal path", L(0x2B9D, 0x0165): "0165: lcall 0FE4:63FB",
                  L(0x2B9D, 0x016B): "016B: call 0354", L(0x2B9D, 0x0354): "0354 note-on entered",
                  L(0x2B9D, 0x0176): "0176: not note-on"}
        hits = []
        for a_ in probes:
            e.mu.hook_add(UC_HOOK_CODE, lambda uc, ad, sz, ud: hits.append(probes[ad]), None, a_, a_)
        e.snd_log = []
        e.midi_in([0x90, 0x3C, 0x64])
        ui.ticks(60)
        on = e.snd_log
        e.snd_log = []
        e.midi_in([0x80, 0x3C, 0x40])
        ui.ticks(60)
        off = e.snd_log
        e.snd_log = None
        print("MIDI path hits:", hits[:20])
        print("rx ring ptrs after:", hex(int.from_bytes(e.mu.mem_read(0x73A0, 2), "little")),
              hex(int.from_bytes(e.mu.mem_read(0x73A2, 2), "little")))
        for name, log in (("NOTE ON", on), ("NOTE OFF", off)):
            print(f"== {name}: {len(log)} writes")
            prev = None
            for port, v, site in log:
                if (port, v) in ((0xA2, 0x0238), (0xA2, 0x0239), (0xA2, 0x023A), (0xA2, 0x023B)) or                         (prev and prev[0] == 0xA2 and prev[1] in (0x0238, 0x0239, 0x023A, 0x023B) and port == 0xA0):
                    prev = (port, v)
                    continue                      # skip the periodic 0x238-0x23B refresh
                prev = (port, v)
                print(f"  out {port:04x} <- {v:04x}  @{site:05x}")
    elif cmd == "notes":
        e = ui.emu
        skip = {0x60, 0x62, 0x52, 0x00, 0x02, 0x10, 0x54}
        for n in (36, 48, 60, 72, 84):
            e.snd_log = []
            e.midi_in([0x90, n, 0x64])
            ui.ticks(40)
            log = [(p_, v, st) for p_, v, st in e.snd_log
                   if p_ not in skip and not (p_ == 0xA2 and 0x238 <= v <= 0x23B)]
            e.midi_in([0x80, n, 0x40])
            ui.ticks(40)
            ports = sorted({f"{p_:x}" for p_, v, st in log})
            print(f"note {n}: {len(log)} writes, ports {ports}, LCD {ui.screen()}")
            for p_, v, st in log[:12]:
                print(f"    out {p_:04x} <- {v:04x} @{st:05x}")
        e.snd_log = None
    elif cmd == "wwatch":
        # wwatch LO-HI r,c ... : code that WRITES the watched range during each key press (value + site)
        from unicorn import UC_HOOK_MEM_WRITE
        lo_, hi_ = (int(x, 16) for x in sys.argv[3].split("-"))
        seen = []
        trail = []

        def blk(uc, address, size, ud):
            trail.append(address)
            del trail[:-4]

        def wr(uc, access, address, size, value, ud):
            seen.append(f"[{address:04x}]={value:#x} blk {trail[-1]:05x}")
        ui.emu.mu.hook_add(UC_HOOK_MEM_WRITE, wr, None, lo_, hi_)
        from unicorn import UC_HOOK_BLOCK as _HB
        ui.emu.mu.hook_add(_HB, blk)
        ui.emu.mu.ctl_flush_tb()
        for tok in sys.argv[4:]:
            seen.clear()
            if tok.startswith("poke:"):
                addr, val = tok[5:].split("=")
                ui.emu.mu.mem_write(int(addr, 16), bytes.fromhex(val))
                print(tok)
                continue
            r, c = map(int, tok.split(","))
            ui.press((r, c))
            uniq = list(dict.fromkeys(seen))
            print(f"{tok}: {ui.screen()}  writes({len(uniq)}): {' | '.join(uniq[:14])}")
    elif cmd == "watch":
        # watch HEXADDR[,HEXADDR..] r,c r,c ... : code that reads the watched bytes during each key press
        from unicorn import UC_HOOK_MEM_READ
        spec = sys.argv[3]
        if "-" in spec:
            lo_, hi_ = (int(x, 16) for x in spec.split("-"))
            ranges = [(lo_, hi_)]
        else:
            ranges = [(int(x, 16), int(x, 16) + 1) for x in spec.split(",")]
        seen = []

        def rd(uc, access, address, size, value, ud):
            cs, ip = uc.reg_read(UC_X86_REG_CS), uc.reg_read(UC_X86_REG_IP)
            seen.append(f"{address:05x}<-{cs:04x}:{ip:04x}")
        for lo_, hi_ in ranges:
            ui.emu.mu.hook_add(UC_HOOK_MEM_READ, rd, None, lo_, hi_)
        ui.emu.mu.ctl_flush_tb()   # mem hooks are baked in at translation time: retranslate
        for tok in sys.argv[4:]:
            seen.clear()
            r, c = map(int, tok.split(","))
            ui.press((r, c))
            uniq = list(dict.fromkeys(seen))
            print(f"{tok}: {ui.screen()}  reads({len(uniq)}): {' '.join(uniq[:16])}")
    elif cmd == "memuse":
        tour = [(2, 0), (2, 1), (1, 1), (6, 1), (2, 1), (1, 1), (7, 1), (0, 0), (0, 1), (1, 1), (4, 1), (0, 0),
                (1, 1), (3, 1), (0, 0), (1, 1), (3, 0), (1, 1), (0, 0), (2, 1), (1, 1)]
        for k in tour:
            ui.press(k)
        e = ui.emu
        for n in (36, 60, 72):
            e.midi_in([0x90, n, 0x64]); ui.ticks(30); e.midi_in([0x80, n, 0]); ui.ticks(30)
        runs = []
        for pg in sorted(pages):
            if runs and pg == runs[-1][1] + 0x100:
                runs[-1][1] = pg
            else:
                runs.append([pg, pg])
        print("written ranges:", " ".join(f"{a:05x}-{b + 0xff:05x}" for a, b in runs))
        for a_, b_ in runs:
            cs, ip = pages[a_]
            print(f"  {a_:05x}: first writer {cs:04x}:{ip:04x}")
    elif cmd == "tracenote":
        # blocks executed inside the note-on call 2B9D:016C -> 0354 (until return to 2B9D:016F)
        from unicorn import UC_HOOK_BLOCK as _HB
        enter, ret = (0x2B9D << 4) + 0x0354, (0x2B9D << 4) + 0x016F
        state = {"in": False}
        trace = []

        def blk(uc, address, size, ud):
            if address == enter:
                state["in"] = True
            if state["in"]:
                cs = uc.reg_read(UC_X86_REG_CS)
                trace.append(f"{cs:04x}:{address - (cs << 4):04x}")
            if address == ret:
                state["in"] = False
        ui.emu.mu.hook_add(_HB, blk)
        ui.emu.mu.ctl_flush_tb()
        note = int(sys.argv[3]) if len(sys.argv) > 3 else 60
        m = ui.emu.mu
        rb = lambda a_: m.mem_read(a_, 1)[0]
        nprog = rb(0x74F4)
        segs = [int.from_bytes(m.mem_read(0xB0D0 + 2 * i, 2), "little") for i in range(nprog)]
        print(f"progs in mem {nprog}, selected [758A]={rb(0x758A)}, active [74FA]={rb(0x74FA)}, "
              f"prog numbers {[m.mem_read((sg << 4) + 0xF, 1)[0] for sg in segs]}")
        for pc in sys.argv[4:]:
            ui.emu.midi_in([0xC0, int(pc)])
            ui.ticks(40)
            print(f"after PC {pc}: [758A]={rb(0x758A)} active={rb(0x74FA)} LCD {ui.screen()}")
        ui.emu.snd_log = []
        ui.emu.midi_in([0x90, note, 0x64])
        ui.ticks(40)
        log = [(p_, v, st) for p_, v, st in ui.emu.snd_log if p_ != 0x54]
        ui.emu.snd_log = None
        # collapse the periodic 0x238-0x23B refresh
        out, skip = [], False
        for p_, v, st in log:
            if p_ == 0xA2 and 0x238 <= v <= 0x23B:
                skip = True
                continue
            if skip and p_ == 0xA0:
                skip = False
                continue
            skip = False
            out.append((p_, v, st))
        print(f"port writes during note-on (refresh removed): {len(out)}")
        for p_, v, st in out[:160]:
            print(f"  out {p_:04x} <- {v:04x} @{st:05x}")
        print(f"{len(trace)} blocks in note-on:")
        print(" ".join(trace[:400]))
    elif cmd == "samples":
        # find Akai-charset sample names in RAM after boot and dump their headers
        cs_ = "0123456789 ABCDEFGHIJKLMNOPQRSTUVWXYZ#+-."
        ak = lambda t: bytes(cs_.index(ch) for ch in t)
        mem = bytes(ui.emu.mu.mem_read(0, 0x100000))
        for nm in ("SINE        ", "SQUARE      ", "SAW         ", "RECT"):
            pat = ak(nm)
            i = mem.find(pat)
            while i >= 0:
                if i > 0x40000 or i < 0x30000 and not (0x1000 <= i < 0x10000):
                    pass
                hdr = mem[i - 3:i + 0x60]
                words = [int.from_bytes(hdr[k:k + 2], "little") for k in range(0, len(hdr) - 1, 2)]
                print(f"{nm.strip():7s} @{i:05x}: " + " ".join(f"{w:04x}" for w in words[:40]))
                i = mem.find(pat, i + 1)
        for pat in (bytes.fromhex("16040100"), bytes.fromhex("01001604"), bytes.fromhex("00000100")):
            hits = [i for i in range(0x40000, 0x100000) if mem[i:i + 4] == pat][:12]
            print(f"pattern {pat.hex()} at:", " ".join(f"{h:05x}" for h in hits))
        nprog = mem[0x74F4]
        print("words at 74f0..:", " ".join(f"{int.from_bytes(mem[a_:a_ + 2], 'little'):04x}" for a_ in range(0x74E8, 0x7500, 2)))
    elif cmd == "fxtest":
        e = ui.emu
        def chip_log(action):
            e.snd_log = []
            action()
            log, e.snd_log = e.snd_log, None
            sel, rega, reg7w1 = None, {}, []
            for p_, v, st in log:
                if p_ == 0x80:
                    sel = v
                elif sel is not None and (sel >> 8) & 0xF == 0xA and p_ in (0x82, 0x84):
                    rega.setdefault(sel & 0x1F, {})[p_] = v
                elif sel is not None and (sel >> 8) & 0xF == 7 and p_ == 0x84:
                    reg7w1.append((sel & 0x1F, hex(v), f"{st:05x}"))
            return rega, reg7w1

        def note():
            e.midi_in([0x90, 60, 0x64]); ui.ticks(30)
            print("      (note-off now)")
            e.midi_in([0x80, 60, 0]); ui.ticks(30)
        e.midi_in([0xC0, 0]); ui.ticks(20)
        ui.press((1, 1))
        for step in ("EFFECTS (on)", "note", "exit", "EFFECTS (off)", "note"):
            if step.startswith("EFFECTS"):
                rega, w = chip_log(lambda: ui.press((3, 0)))
            elif step == "exit":
                rega, w = chip_log(lambda: ui.press((1, 1)))
            else:
                rega, w = chip_log(note)
            fns = sorted(rega)
            print(f"{step:14s} LCD {ui.screen()}  regA fns written: {len(fns)} "
                  f"{[(f, hex(rega[f].get(0x82, 0)), hex(rega[f].get(0x84, 0))) for f in fns[:6]]}  reg7 word1: {w[:4]}")
    elif cmd == "playkey":
        # which front-panel key triggers a voice (key-on write to port 0x88) with TEST PROGRAM active
        e = ui.emu
        e.midi_in([0xC0, 0]); ui.ticks(30)
        ui.press((1, 1))
        base = ui.snapshot()
        for r in range(8):
            for c in range(2):
                ui.restore(base)
                e.snd_log = []
                ui.press((r, c), hold=80, after=80)
                kon = [v for p_, v, st in e.snd_log if p_ == 0x88 and v & 0x100]
                e.snd_log = None
                print(f"r{r}c{c}: key-ons {len(kon)}  LCD {ui.screen()}")
    elif cmd == "playfx":
        e = ui.emu
        e.midi_in([0xC0, 0]); ui.ticks(30)
        ui.press((1, 1))
        for label, key in (("EFFECTS", (3, 0)), ("PLAY on fx page", (6, 0)), ("EXIT", (1, 1)), ("PLAY on main", (6, 0))):
            e.snd_log = []
            ui.press(key, hold=80, after=80)
            log, e.snd_log = e.snd_log, None
            kon = sum(1 for p_, v, st in log if p_ == 0x88 and v & 0x100)
            sel, w1 = None, set()
            for p_, v, st in log:
                if p_ == 0x80:
                    sel = v
                elif sel is not None and (sel >> 8) & 0xF == 7 and p_ == 0x84:
                    w1.add(hex(v))
            print(f"{label:16s} key-ons {kon}  reg7 word1 {sorted(w1)}  LCD {ui.screen()}")
    elif cmd == "cursor":
        # select program 1 via MIDI, then sample the LCD (custom chars shown as backslash+N) + CGRAM char 5
        e = ui.emu
        e.midi_in([0xC0, 0]); ui.ticks(30)
        seen = []
        for _ in range(12):
            ui.ticks(25)
            lc = e.lcd
            cur = getattr(lc, "cursor", 0)
            pos = (lc.ac & 0x3F, 1 if lc.ac >= 0x40 else 0)
            scr = ui.screen() + (f"  cursor {'ON' if cur & 2 else 'off'}{' blink' if cur & 1 else ''} at line {pos[1] + 1} col {pos[0]}" if not lc.cg else "")
            if not seen or seen[-1] != scr:
                seen.append(scr)
        for scr in seen:
            print("  ", scr)
        cg = e.lcd.cgram[40:48]
        print("   CGRAM char5:", " ".join(f"{b_ & 0x1F:05b}" for b_ in cg))
    elif cmd == "auditions":
        # does PLAY trigger a voice on each mode page (no program selected: [758A] stays 35)
        e = ui.emu
        base = ui.snapshot()
        for label, mode_key in (("main", None), ("sample/REC", (7, 1)), ("MULTI", (4, 1)), ("PROG page", (0, 0)), ("TUNE", (3, 1))):
            ui.restore(base)
            if mode_key:
                ui.press(mode_key)
            e.snd_log = []
            ui.press((6, 0), hold=80, after=80)
            kon = sum(1 for p_, v, st in e.snd_log if p_ == 0x88 and v & 0x100)
            e.snd_log = None
            print(f"PLAY on {label:11s}: key-ons {kon}  LCD {ui.screen()}")
    elif cmd == "playtrace":
        # far calls/blocks run between pressing PLAY and the key-on, on the sample page vs main
        from unicorn import UC_HOOK_BLOCK as _HB
        e = ui.emu
        base = ui.snapshot()
        rec = {"on": False, "blocks": []}

        def blk(uc, address, size, ud):
            if rec["on"]:
                cs = uc.reg_read(UC_X86_REG_CS)
                rec["blocks"].append((cs, address - (cs << 4)))

        e.mu.hook_add(_HB, blk)
        e.mu.ctl_flush_tb()
        for label, mode_key in (("sample", (7, 1)), ("main", None)):
            ui.restore(base)
            if mode_key:
                ui.press(mode_key)
            rec["blocks"] = []
            e.pressed = {(6, 0)}
            rec["on"] = True
            ui.ticks(80)
            rec["on"] = False
            e.pressed = set()
            ui.ticks(40)
            # keep only first occurrence, drop the hot tick/key-scan noise in 2345:07xx/0A4x and main loop 0FE4:00xx
            seen, out = set(), []
            for cs, off in rec["blocks"]:
                k = (cs, off)
                if k in seen:
                    continue
                seen.add(k)
                out.append(f"{cs:04x}:{off:04x}")
            print(f"== {label}: {len(out)} unique blocks")
            print(" ".join(out[:260]))
    elif cmd == "playmain":
        # PLAY on the main page with no program active: key-on? which start address? release?
        from unicorn import UC_HOOK_CODE
        e = ui.emu
        rel = []
        e.mu.hook_add(UC_HOOK_CODE, lambda uc, a_, sz, ud: rel.append(1), None, (0x2345 << 4) + 0x5C25, (0x2345 << 4) + 0x5C25)
        e.mu.ctl_flush_tb()
        rb = lambda a_: e.mu.mem_read(a_, 1)[0]
        print(f"[7637]={rb(0x7637):#x} samples [74F6]={rb(0x74F6)} active [74FA]={rb(0x74FA)}")
        if len(sys.argv) > 3 and sys.argv[3] == "samplepage":
            ui.press((7, 1))
        # count voices that are on ([voice+0x10C] != 0) before/after
        def voices_on():
            return sum(1 for n in range(32) if e.mu.mem_read(0x378D0 + n * 0x1BC + 0x10C, 1)[0])
        for k in ((6, 0), (6, 0)):
            e.snd_log = []
            e.pressed = {k}; ui.ticks(60)
            on_log, e.snd_log = e.snd_log, []
            e.pressed = set(); ui.ticks(60)
            off_log, e.snd_log = e.snd_log, None
            sel, start = None, None
            for p_, v, st in on_log:
                if p_ == 0x80: sel = v
                elif sel is not None and (sel >> 8) & 0xF == 0 and p_ == 0x84: start = v
            kon = sum(1 for p_, v, st in on_log if p_ == 0x88 and v & 0x100)
            print(f"PLAY: key-ons {kon} start-addr-word1 {start and hex(start)}  release calls {len(rel)}  voices on after release {voices_on()}  LCD {ui.screen()}")
            rel.clear()
    elif cmd == "sysex":
        e = ui.emu
        m = e.mu
        nib = lambda v, n: [(v >> (4 * (n - 1 - k))) & 0xF for k in range(n)]
        def tx_ring():
            wp = int.from_bytes(m.mem_read(0x3B050 + 0x102, 2), "little")
            cnt = int.from_bytes(m.mem_read(0x3B050 + 0x100, 2), "little")
            return bytes(m.mem_read(0x3B050, 256)), wp, cnt
        def send(body, ticks=20):
            _, wp0, _ = tx_ring()
            e.midi_in([0xF0, 0x7D, 0x53] + body + [0xF7]); ui.ticks(ticks)
            ring, wp, cnt = tx_ring()
            out = bytes(ring[(wp0 + k) & 0xFF] for k in range((wp - wp0) & 0xFF))
            return out.hex(" ")
        print("PING  ->", send([0x05]))
        print("POKE 3F00:0013 = 07 60 ->", send([0x03] + nib(0x3F00, 4) + nib(0x0013, 4) + nib(2, 2) + nib(0x07, 2) + nib(0x60, 2)))
        print("   mem 3F013:", bytes(m.mem_read(0x3F013, 2)).hex(" "))
        print("PEEK 3F00:0012 x3 ->", send([0x04] + nib(0x3F00, 4) + nib(0x0012, 4) + nib(3, 2)))
        e.snd_log = []
        send([0x01] + nib(0x80, 2) + nib(0x0A05, 4))
        print("OUTW 80 <- 0A05 logged:", [(hex(p_), hex(v)) for p_, v, st in e.snd_log if p_ == 0x80][-1:])
        e.snd_log = []
        send([0x06], 40)
        print("FXPROG reg A selects:", len([v for p_, v, st in e.snd_log if p_ == 0x80 and (v >> 8) & 0xF == 0xA]))
        e.snd_log = None
        print("INW 62 ->", send([0x07] + nib(0x62, 2)))
        e.midi_in([0xF0, 0x47, 0x00, 0x00, 0x48, 0xF7]); ui.ticks(20)
        print("Akai SysEx handler [7DE6] =", hex(int.from_bytes(m.mem_read(0x7DE6, 2), "little")), "(stock 0x63cb)")
        print("LCD", ui.screen())
    elif cmd == "akaisx":
        e = ui.emu
        e.midi_in([0xF0, 0x47, 0x00, 0x00, 0x48, 0xF7]); ui.ticks(20)
        print("Akai SysEx handler [7DE6] =", hex(int.from_bytes(e.mu.mem_read(0x7DE6, 2), "little")), " LCD", ui.screen())
    elif cmd == "seq":
        for tok in sys.argv[3:]:
            if tok.startswith("poke:"):                 # poke:LINHEX=BYTEHEX[BYTEHEX..]
                addr, val = tok[5:].split("=")
                ui.emu.mu.mem_write(int(addr, 16), bytes.fromhex(val))
                print(f"{tok}")
                continue
            if tok.startswith("hit:"):                  # hit:SEG:OFF[,SEG:OFF..] count executions from now on
                from unicorn import UC_HOOK_CODE
                if not hasattr(ui, "hits"):
                    ui.hits = {}
                for so in tok[4:].split(","):
                    sg, of = (int(x, 16) for x in so.split(":"))
                    a_ = (sg << 4) + of
                    ui.hits[so] = 0
                    ui.emu.mu.hook_add(UC_HOOK_CODE, lambda uc, ad, sz, k: ui.hits.__setitem__(k, ui.hits[k] + 1),
                                       so, a_, a_)
                ui.emu.mu.ctl_flush_tb()
                continue
            if tok == "recdma":                         # let the record DMA ring move (takes can run)
                ui.emu.rec_dma = True
                continue
            if tok.startswith("hold:"):                 # hold:r,c,TICKS press a key for that long
                r, c, n_ = map(int, tok[5:].split(","))
                ui.press((r, c), hold=n_)
                mp_ = tuple(ui.emu.mu.mem_read(0x762B, 2))
                print(f"{tok}: {mp_[0]:2d}/{mp_[1]:3d} {ui.screen()}", flush=True)
                continue
            if tok == "hits":
                print("hits:", getattr(ui, "hits", {}), flush=True)
                continue
            if tok.startswith("peek:"):                 # peek:LINHEX,NHEX -> hex dump
                a_, n_ = (int(x, 16) for x in tok[5:].split(","))
                b_ = bytes(ui.emu.mu.mem_read(a_, n_))
                for i in range(0, n_, 16):
                    print(f"  {a_ + i:05x}: {b_[i:i + 16].hex(' ')}", flush=True)
                continue
            if tok == "where":                          # where: sample CS:IP over a while (find a busy loop)
                from collections import Counter
                hits = Counter()
                for _ in range(40):
                    ui.run_blocks(3000)
                    hits[f"{ui.emu.mu.reg_read(UC_X86_REG_CS):04x}:{ui.emu.mu.reg_read(UC_X86_REG_IP):04x}"] += 1
                print("where:", hits.most_common(8), flush=True)
                continue
            if tok.startswith("wait:"):                 # wait:N ticks (2 ms each), then show the screen
                ui.ticks(int(tok[5:]))
            else:
                r, c = map(int, tok.split(","))
                ui.press((r, c))
            mp_ = tuple(ui.emu.mu.mem_read(0x762B, 2))
            print(f"{tok}: {mp_[0]:2d}/{mp_[1]:3d} {ui.screen()}", flush=True)
    elif cmd == "pagewalk":
        # pagewalk: per mode key, what each nav key (0x44-0x47 = r1c0 r0c0 r5c0 r4c0) does, then walk the
        # page+ key through the whole mode: (mode, page) + LCD per step -> menu redesign inventory
        e = ui.emu
        mp = lambda: tuple(e.mu.mem_read(0x762B, 2))
        nav = [(1, 0), (0, 0), (5, 0), (4, 0)]
        modes = [(None, "MAIN"), ((0, 1), "r0c1"), ((4, 1), "MULTI"), ((7, 1), "REC"), ((3, 1), "TUNE"),
                 ((2, 0), "LOAD"), ((6, 1), "SAVE")]
        for key, nm in modes:
            ui.restore(snap)
            if key:
                ui.press(key)
            s0 = ui.snapshot()
            m0 = mp()
            print(f"===== {nm}: mode/page {m0} {ui.screen()}")
            fwd = None
            for k in nav:
                ui.restore(s0)
                ui.press(k)
                m1 = mp()
                print(f"   nav r{k[0]}c{k[1]} -> {m1} {ui.screen()}")
                if fwd is None and m1[0] == m0[0] and m1[1] == m0[1] + 1:
                    fwd = k
            if not fwd:
                continue
            ui.restore(s0)
            seen = {m0}
            for _ in range(48):
                ui.press(fwd)
                m1 = mp()
                print(f"      {m1[0]:2d}/{m1[1]:2d} {ui.screen()}")
                if m1 in seen:
                    break
                seen.add(m1)
    elif cmd == "groupwalk":
        # groupwalk: the edit modes in full. Per mode: GROUP+ (r4c0) jumps = group starts, then PAGE+ (r0c0)
        # through every page (up to 200) -> docs/pagewalk_edit.txt (menu M2 page/group map)
        e = ui.emu
        mp = lambda: tuple(e.mu.mem_read(0x762B, 2))
        paths = [([(0, 1)], "EDIT PROGRAM"), ([(4, 1), (0, 1)], "EDIT MULTI"), ([(7, 1), (0, 1)], "EDIT SAMPLE")]
        for path, nm in paths:
            ui.restore(snap)
            for k in path:
                ui.press(k)
            s0 = ui.snapshot()
            m0 = mp()
            print(f"===== {nm}: {m0} {ui.screen()}")
            for label, key, limit in (("GROUP+", (4, 0), 60), ("PAGE+", (0, 0), 200)):
                ui.restore(s0)
                seen = {m0}
                print(f"  -- {label}")
                for _ in range(limit):
                    ui.press(key, hold=40, after=120)
                    m1 = mp()
                    print(f"      {m1[0]:2d}/{m1[1]:3d} {ui.screen()}", flush=True)
                    if m1 in seen:
                        break
                    seen.add(m1)
    elif cmd == "pagekeys":
        # pagekeys N r,c ...: go there via the keys, then on each of N pages (PAGE+ = r0c0 between them)
        # press every panel key from the same state and print what changed (mode/page + LCD)
        e = ui.emu
        mp = lambda: tuple(e.mu.mem_read(0x762B, 2))
        n = int(sys.argv[3])
        for tok in sys.argv[4:]:
            ui.press(tuple(map(int, tok.split(","))))
        keys = [(r, c) for r in range(8) for c in range(2)]
        for _ in range(n):
            s0 = ui.snapshot()
            m0, l0 = mp(), ui.screen()
            print(f"== {m0[0]}/{m0[1]:3d} {l0}", flush=True)
            for k in keys:
                ui.restore(s0)
                ui.press(k)
                m1, l1 = mp(), ui.screen()
                if (m1, l1) != (m0, l0):
                    print(f"   r{k[0]}c{k[1]} -> {m1[0]}/{m1[1]:3d} {l1}", flush=True)
            ui.restore(s0)
            ui.press((0, 0))
    elif cmd == "isrcheck":
        # do any interrupt handlers write the voice chip (0x80-0x8C)? A select+data pair split by an ISR
        # write would corrupt the main loop's (and Rosetta's LFO) chip writes. Notes + chorus for N ticks.
        from unicorn import UC_HOOK_CODE
        e = ui.emu
        depth = [0]
        isr_writes = []
        ivt = e.mu.mem_read(0, 0x400)
        entries = set()
        for v in range(8, 16):
            off, seg = int.from_bytes(ivt[4 * v:4 * v + 2], "little"), int.from_bytes(ivt[4 * v + 2:4 * v + 4], "little")
            entries.add((seg << 4) + off)
        print("ISR entries:", [hex(a) for a in sorted(entries)])

        def on_entry(uc, address, size, ud):
            depth[0] += 1

        def on_insn(uc, address, size, ud):
            if depth[0] and uc.mem_read(address, 1)[0] == 0xCF:      # iret
                depth[0] -= 1
        for a_ in entries:
            e.mu.hook_add(UC_HOOK_CODE, on_entry, None, a_, a_)
        e.mu.hook_add(UC_HOOK_CODE, on_insn, None, 0x0FE40, 0x1FE3F)
        e.mu.ctl_flush_tb()
        orig_out = e._out

        def out(uc, port, size, value, ud):
            if depth[0] and 0x80 <= port <= 0x8C:
                isr_writes.append((port, value, e.lin()))
            orig_out(uc, port, size, value, ud)
        e._out = out
        e.mu.hook_add(__import__("unicorn").UC_HOOK_INSN, out, None, 1, 0, __import__("unicorn").x86_const.UC_X86_INS_OUT)
        for k in range(6):
            ui.press((3, 0))
        print("FX:", ui.screen())
        n = int(sys.argv[3]) if len(sys.argv) > 3 else 600
        for k in range(n // 60):
            e.midi_in([0x90, 48 + k % 24, 0x64])
            ui.ticks(40)
            e.midi_in([0x80, 48 + k % 24, 0x40])
            ui.ticks(20)
        print(f"{n} ticks, ISR-depth chip writes: {len(isr_writes)}")
        for w in isr_writes[:12]:
            print(f"   out {w[0]:02x} <- {w[1]:04x} @{w[2]:05x}")
    elif cmd == "fxcheck":
        # fxcheck [N]: press EFFECTS (r3c0) N times; per preset show the LCD and the reg A (delay engine)
        # writes over 200 ticks: static programming happens once, LFO slots keep rewriting their taps
        e = ui.emu
        for k in range(int(sys.argv[3]) if len(sys.argv) > 3 else 9):
            e.snd_log = []
            ui.press((3, 0))
            log = e.snd_log
            e.snd_log = []
            ui.ticks(200)
            run = e.snd_log
            e.snd_log = None

            def taps(lg):
                sel, out = None, {}
                for p_, v, st in lg:
                    if p_ == 0x80:
                        sel = v
                    elif p_ in (0x82, 0x84) and sel is not None and sel >> 8 == 0x0A:
                        out.setdefault(sel & 0xFF, []).append((p_, v))
                return out
            t0, t1 = taps(log), taps(run)
            live = {fn: (v[-1] if v else None) for fn, v in t0.items()
                    if any(p_ == 0x82 and w & 0xFFFC for p_, w in v)}
            print(f"EFFECTS #{k + 1}: {ui.screen()}  regA fns written {len(t0)}, nonzero gain {len(live)}; "
                  f"next 200 ticks: {sum(len(v) for v in t1.values())} regA writes on fns {sorted(t1)}")
            for fn in sorted(t1)[:4]:
                lens = [(2 - w) & 0xFFFF for p_, w in t1[fn] if p_ == 0x84]
                gains = [w for p_, w in t1[fn] if p_ == 0x82]
                print(f"    fn{fn}: delay {min(lens)}..{max(lens)}  gain {min(gains):#06x}..{max(gains):#06x}")


if __name__ == "__main__":
    main()
