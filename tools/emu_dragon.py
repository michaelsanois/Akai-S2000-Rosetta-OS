"""Emulate the S2000 OS boot from 0000:0050 up to 1F50:0000 (stock init) with a fake HD44780.

  py -3.11 -I emu_dragon.py OS.bin [--frames]

Checks: reaches 1F50:0000; DS=ES=SS=0, SP=0x300, IF=0, DF=0 there; CGRAM chars 1-3 restored;
no memory written outside the dragon segment span; prints the line sequence the LCD showed.
"""
import random
import sys

from unicorn import UC_ARCH_X86, UC_HOOK_CODE, UC_HOOK_INSN, UC_HOOK_MEM_WRITE, UC_MODE_16, Uc
from unicorn.x86_const import (UC_X86_INS_IN, UC_X86_INS_OUT, UC_X86_REG_AL, UC_X86_REG_CS, UC_X86_REG_DS,
                               UC_X86_REG_EFLAGS, UC_X86_REG_ES, UC_X86_REG_IP, UC_X86_REG_SP, UC_X86_REG_SS)

DRAGON_LO, DRAGON_HI = 0x3E200, 0x3EA00
STOP = 0x1F500


class LCD:
    def __init__(self):
        self.ddram = bytearray(b" " * 0x80)
        self.cgram = bytearray(random.randrange(32) for _ in range(64))
        self.cgram_init = bytes(self.cgram)
        self.ac, self.cg = 0, False
        self.rows = []          # snapshots of (line, text) after each full 16-char row write
        self.wcount = 0

    def cmd(self, v):
        if v & 0x80:
            self.ac, self.cg = v & 0x7F, False
            self.wcount = 0
        elif v & 0x40:
            self.ac, self.cg = v & 0x3F, True

    def write(self, v):
        if self.cg:
            self.cgram[self.ac] = v
            self.ac = (self.ac + 1) & 0x3F
        else:
            self.ddram[self.ac] = v
            self.ac = (self.ac + 1) & 0x7F
            self.wcount += 1
            if self.wcount == 16:
                start = self.ac - 16
                self.rows.append((0 if start < 0x40 else 1, self.show(start)))

    def read(self):
        mem = self.cgram if self.cg else self.ddram
        v = mem[self.ac]
        self.ac = (self.ac + 1) & (0x3F if self.cg else 0x7F)
        return v

    def show(self, start):
        return "".join("123"[c - 1] if 1 <= c <= 3 else (chr(c) if 32 <= c < 127 else "?")
                       for c in self.ddram[start:start + 16])

    def glyphs(self):
        rows = []
        for r in range(8):
            rows.append("".join(f"{self.cgram[8 * ch + r] & 0x1F:05b}" for ch in (1, 2, 3)))
        return "\n".join(r.replace("0", " ").replace("1", "#") for r in rows)


def main():
    os_bin = open(sys.argv[1], "rb").read()
    show_frames = "--frames" in sys.argv
    mu = Uc(UC_ARCH_X86, UC_MODE_16)
    mu.mem_map(0, 0x100000)
    mu.mem_write(0, os_bin)
    lcd = LCD()
    frames_seen = []
    bad_writes = []
    state = {"done": False, "insns": 0}

    def hook_in(uc, port, size, ud):
        if port == 0x62:
            return 0x00          # never busy
        if port == 0x60:
            return lcd.read()
        return 0

    def hook_out(uc, port, size, value, ud):
        if port == 0x62:
            if value & 0xC0 == 0x40 and value == 0x48 and show_frames and lcd.rows:
                frames_seen.append(lcd.glyphs())
            lcd.cmd(value)
        elif port == 0x60:
            lcd.write(value)

    def hook_code(uc, address, size, ud):
        state["insns"] += 1
        cs = uc.reg_read(UC_X86_REG_CS)
        ip = uc.reg_read(UC_X86_REG_IP)
        if (cs << 4) + ip == STOP:
            state["done"] = True
            uc.emu_stop()

    def hook_write(uc, access, address, size, value, ud):
        if not (DRAGON_LO <= address < DRAGON_HI):
            bad_writes.append(address)

    mu.hook_add(UC_HOOK_INSN, hook_in, None, 1, 0, UC_X86_INS_IN)
    mu.hook_add(UC_HOOK_INSN, hook_out, None, 1, 0, UC_X86_INS_OUT)
    mu.hook_add(UC_HOOK_CODE, hook_code)
    mu.hook_add(UC_HOOK_MEM_WRITE, hook_write)
    mu.reg_write(UC_X86_REG_CS, 0)
    mu.reg_write(UC_X86_REG_EFLAGS, 0x0202)
    mu.emu_start(0x50, 0xFFFFF, count=200_000_000)

    regs = {n: mu.reg_read(r) for n, r in (("cs", UC_X86_REG_CS), ("ip", UC_X86_REG_IP), ("ds", UC_X86_REG_DS),
                                           ("es", UC_X86_REG_ES), ("ss", UC_X86_REG_SS), ("sp", UC_X86_REG_SP),
                                           ("fl", UC_X86_REG_EFLAGS))}
    print(f"reached 1F50:0000: {state['done']}  insns {state['insns']:,}")
    print("regs at stop:", " ".join(f"{k}={v:04x}" for k, v in regs.items()),
          f"IF={(regs['fl'] >> 9) & 1} DF={(regs['fl'] >> 10) & 1}")
    # the stock 0x50 stub itself writes [1D] and the INT0 vector (0..3) -- allowed
    stray = sorted(set(a for a in bad_writes if a > 0x1F))
    print("writes outside dragon span (excl. stock stub IVT/[1D]):", [hex(a) for a in stray[:10]], len(stray))
    print("CGRAM chars 1-3 restored:", lcd.cgram[8:32] == lcd.cgram_init[8:32])
    print(f"LCD rows drawn: {len(lcd.rows)}")
    seen = []
    for line, txt in lcd.rows:
        s = f"L{line + 1} |{txt}|"
        if not seen or seen[-1] != s:
            seen.append(s)
    for s in seen[:3] + ["..."] + seen[16:20] + ["..."] + seen[-3:]:
        print("  ", s)
    if show_frames:
        for i, g in enumerate(frames_seen[1:9]):
            print(f"-- frame {i}\n{g}")
    ok = state["done"] and not stray and lcd.cgram[8:32] == lcd.cgram_init[8:32] and regs["ds"] == regs["es"] \
        == regs["ss"] == 0 and regs["sp"] == 0x300 and not (regs["fl"] >> 9) & 1 and not (regs["fl"] >> 10) & 1
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
