"""Whole-OS S2000 emulator (unicorn, 16-bit) -- boot from 0000:0050 with fake hardware.

  py -3.11 -I s2k_emu.py OS.bin [--steps N] [--trace]

Fake devices (grown as the boot needs them):
  LCD HD44780 on 0x62/0x60, key matrix 0x52 (row out) / 0x50 (cols in, 0xFF = nothing pressed),
  V53 TCU counter at 0xC030 (free-running from the instruction count), everything else: last write / 0xFF.
Prints the LCD and the hottest code blocks when it stops, so a stuck boot shows where it waits.
"""
import collections
import os
import sys

from unicorn import UC_ARCH_X86, UC_HOOK_BLOCK, UC_HOOK_INSN, UC_MODE_16, Uc, UcError
from unicorn.x86_const import (UC_X86_INS_IN, UC_X86_INS_OUT, UC_X86_REG_BX, UC_X86_REG_CS,
                               UC_X86_REG_EFLAGS, UC_X86_REG_IP, UC_X86_REG_SP, UC_X86_REG_SS)

ICU_BASE = 8           # ICW2 = 0x08: IR0 -> int 8 (SCU/MIDI rx, 0FE4:0C66), IR1 -> int 9 (tick, 0FE4:0B92)
TICK_BLOCKS = 1000     # basic blocks between IR1 ticks (~4000 insns, ~1 ms; only relative timing matters)

# reads faked per code site (linear address of the IN instruction) where a device model isn't worth it yet
SITE_READS = {
    0x25088: lambda emu: emu.mu.reg_read(UC_X86_REG_BX),   # 2345:1C38 sample-RAM addr counter == end of DMA
}


class LCD:
    def __init__(self):
        self.ddram = bytearray(b" " * 0x80)
        self.cgram = bytearray(64)
        self.ac, self.cg = 0, False

    def cmd(self, v):
        if 0x08 <= v <= 0x0F:              # display control: bit1 = underline cursor, bit0 = blink
            self.cursor = v & 3
        if v == 0x01:                      # clear display
            self.ddram[:] = b" " * 0x80
            self.ac, self.cg = 0, False
        elif v & 0xFE == 0x02:             # return home
            self.ac, self.cg = 0, False
        elif v & 0x80:
            self.ac, self.cg = v & 0x7F, False
        elif v & 0x40:
            self.ac, self.cg = v & 0x3F, True

    def write(self, v):
        if self.cg:
            self.cgram[self.ac] = v
            self.ac = (self.ac + 1) & 0x3F
        else:
            self.ddram[self.ac] = v
            self.ac = (self.ac + 1) & 0x7F

    def read(self):
        mem = self.cgram if self.cg else self.ddram
        v = mem[self.ac]
        self.ac = (self.ac + 1) & (0x3F if self.cg else 0x7F)
        return v

    def lines(self):
        f = lambda b: "".join(chr(c) if 32 <= c < 127 else f"\\{c:x}" if c < 8 else "?" for c in b)
        return f(self.ddram[0:16]), f(self.ddram[0x40:0x50])


class FDC765:
    """Minimal uPD765 on 0x20 (MSR) / 0x22 (data). Without a disk image, commands complete with 'not ready'.
    With one (raw Akai HD image: 1 KB blocks, block = C*20 + H*10 + R-1), read data moves the sector(s) by
    DMA channel 1 (done by S2K, see `pending_read`) and every seek/recalibrate/read raises IR3."""
    CMDLEN = {0x03: 3, 0x04: 2, 0x07: 2, 0x08: 1, 0x0F: 3, 0x0A: 2, 0x0D: 6, 0x06: 9, 0x05: 9, 0x02: 9,
              0x11: 9, 0x19: 9, 0x1D: 9, 0x09: 9, 0x0C: 9, 0x10: 1, 0x12: 2, 0x13: 4, 0x0E: 1}

    def __init__(self, disk=None):
        self.cmd, self.res = [], []
        self.pcn = 0
        self.int_pending = False
        self.disk = disk
        self.irq = False              # IR3 request for S2K to deliver
        self.pending_read = None      # (C, H, R, N, EOT) for S2K to run through DMA channel 1
        self.reads = 0

    def __getstate__(self):           # snapshots: leave the (big, constant) image out
        d = dict(self.__dict__)
        d["disk"] = None
        return d

    def msr(self):
        return 0xC0 if self.res else 0x80

    def write(self, v):
        self.cmd.append(v)
        op = self.cmd[0] & 0x1F
        need = self.CMDLEN.get(op, 1)
        if len(self.cmd) < need:
            return
        c, self.cmd = self.cmd, []
        drv = (c[1] & 3) if len(c) > 1 else 0
        if op == 0x08:                       # sense interrupt
            if self.int_pending:
                self.res = [0x20 | drv, self.pcn]
            elif self.disk is not None:      # nothing pending: a drive-ready change (the 72065 polls after
                self.res = [0xC0, self.pcn]  # a reset); the OS always reads 2 bytes here (0FE4:A51A)
            else:
                self.res = [0x80]
            self.int_pending = False
        elif op in (0x07, 0x0F):             # recalibrate / seek
            self.pcn = c[2] if op == 0x0F else 0
            self.int_pending = True
            self.irq = self.disk is not None
        elif op == 0x04:                     # sense drive status: ST3 bit 3 = no disk on this board
            if self.disk is not None:
                self.res = [0x20 | (0x10 if self.pcn == 0 else 0) | (c[1] & 7)]
            else:
                self.res = [0x08 | (0x10 if self.pcn == 0 else 0) | drv]
        elif op == 0x03:                     # specify
            pass
        elif op in (0x10, 0x0E):             # version / dumpreg
            self.res = [0x80] if op == 0x10 else [0] * 10
        elif op == 0x06 and self.disk is not None:   # read data: S2K moves the bytes, then results
            self.pending_read = (c[2], c[3], c[4], c[5], c[6], c[1])
        else:                                # read/write/format/read id: abnormal term, not ready
            self.res = [0x48 | drv, 0x00, 0x00, c[2] if len(c) > 2 else 0, 0, 1, 2]

    def read(self):
        return self.res.pop(0) if self.res else 0xFF

    def aux(self, v):
        """uPD72065 auxiliary command written to the MSR address (0x36 = software reset)."""
        self.cmd = []
        self.res = [] if v == 0x36 else [0x00]


class ICU8259:
    """V53 ICU at C010/C012: tracks the ICW sequence so only OCW1 sets the mask (all masked until then)."""

    def __init__(self):
        self.mask, self.expect, self.icw1 = 0xFF, [], 0

    def write(self, port, v):
        if port == 0xC010:
            if v & 0x10:                                  # ICW1
                self.icw1, self.mask = v, 0xFF
                self.expect = ["icw2"] + ([] if v & 2 else ["icw3"]) + (["icw4"] if v & 1 else [])
        elif port == 0xC012:
            if self.expect:
                self.expect.pop(0)
            else:
                self.mask = v                             # OCW1


class S2K:
    def __init__(self, os_bin, disk=None):
        self.mu = Uc(UC_ARCH_X86, UC_MODE_16)
        self.mu.mem_map(0, 0x100000)
        self.mu.mem_write(0, os_bin)
        self.lcd = LCD()
        if disk is None and os.environ.get("S2K_DISK"):
            disk = open(os.environ["S2K_DISK"], "rb").read()   # raw disk image in the floppy drive
        self.disk = disk
        self.fdc = FDC765(disk)
        self.dma = {}             # DMAU channel -> {"lo": address bits 15-0, "hi": bank, "n": count - 1}
        self.icu = ICU8259()
        self.ports = {}
        self.port_log = collections.Counter()
        self.blocks = collections.Counter()
        self.nblocks = 0
        self.keyrow = 0xFF
        self.pressed = set()      # (row_bit, col_bit) pairs held down
        mu = self.mu
        mu.hook_add(UC_HOOK_INSN, self._in, None, 1, 0, UC_X86_INS_IN)
        mu.hook_add(UC_HOOK_INSN, self._out, None, 1, 0, UC_X86_INS_OUT)
        mu.hook_add(UC_HOOK_BLOCK, self._block)

    def lin(self):
        return (self.mu.reg_read(UC_X86_REG_CS) << 4) + self.mu.reg_read(UC_X86_REG_IP)

    def _block(self, uc, address, size, ud):
        self.nblocks += 1
        self.blocks[address] += 1
        if self.nblocks % TICK_BLOCKS == 0:
            self.tick_pending = True
            self.ticks = getattr(self, "ticks", 0) + 1
            if getattr(self, "on_tick", None):
                self.on_tick(self)
        if getattr(self, "tick_pending", False) and self.irq(1):
            self.tick_pending = False
        if self.fdc.irq and self.irq(3):
            self.fdc.irq = False

    def _in(self, uc, port, size, ud):
        self.port_log[("in", port)] += 1
        site = SITE_READS.get(self.lin())
        if site:
            return site(self)
        if port == 0x62:
            return 0x00
        if port == 0x60:
            return self.lcd.read()
        if port == 0x50:
            v = 0xFF
            for r, c in self.pressed:
                if not (self.keyrow >> r) & 1:
                    v &= ~(1 << c) & 0xFF
            return v
        if port == 0xA0:
            return 0x0000      # L7A1045 data/status: idle (status reg 0x180 bit0 = busy)
        if port == 0x20:
            return self.fdc.msr()
        if port == 0x22:
            return self.fdc.read()
        if port == 0xC004 and self.ports.get(0xC001) == 2 and getattr(self, "rec_dma", False):
            # record DMA (channel 2) current address in the 0:90D0 ring of 0x2000 bytes, moving with time
            # (~180 bytes per tick ~ 88 kB/s mono 44.1 kHz), so takes run in emulation (seq token recdma)
            return 0x90D0 + ((self.nblocks * 180 // TICK_BLOCKS) & 0x1FFE)
        if port == 0xC002:
            return 0xFFFF if size == 2 else 0xFF   # DMA count: transfer finished instantly (no sample data)
        if port == 0xC030:
            return (0x10000 - (self.nblocks * 3)) & 0xFF if size == 1 else (0x10000 - self.nblocks * 3) & 0xFFFF
        return self.ports.get(port, 0xFF if size == 1 else 0xFFFF)

    def _out(self, uc, port, size, value, ud):
        self.port_log[("out", port)] += 1
        if getattr(self, "snd_log", None) is not None and port not in (0x60, 0x62, 0x52, 0x00, 0x02, 0x10):
            self.snd_log.append((port, value, self.lin()))
        if port == 0x62:
            self.lcd.cmd(value)
        elif port == 0x60:
            self.lcd.write(value)
        elif port == 0x52:
            self.keyrow = value
        elif port == 0x22:
            if self.fdc.disk is None and self.disk is not None:
                self.fdc.disk = self.disk         # (restored from a snapshot)
            self.fdc.write(value)
            if self.fdc.pending_read:
                self._fdc_read(*self.fdc.pending_read)
                self.fdc.pending_read = None
        elif port in (0xC002, 0xC004, 0xC006):
            ch = self.ports.get(0xC001, 0) & 3
            self.dma.setdefault(ch, {})[{0xC002: "n", 0xC004: "lo", 0xC006: "hi"}[port]] = value
        elif port == 0x20:
            self.fdc.aux(value)
        elif port in (0xC010, 0xC012):
            self.icu.write(port, value)
        self.ports[port] = value

    def _fdc_read(self, c, h, r, n, eot, hdus):
        """Read data: sectors r.. (of 128 << n bytes) into DMA channel 1's buffer, until its count runs out."""
        d = self.dma.get(1, {})
        addr = ((d.get("hi", 0) & 0x0F) << 16) | (d.get("lo", 0) & 0xFFFF)
        left = (d.get("n", 0) & 0xFFFF) + 1
        size = 128 << n
        while left > 0:
            blk = c * 20 + h * 10 + (r - 1)
            data = self.disk[blk * size:(blk + 1) * size] if size == 1024 else bytes(size)
            take = min(left, size)
            self.mu.mem_write(addr, data[:take])
            addr, left = addr + take, left - take
            r += 1
        self.fdc.reads += 1
        self.fdc.res = [hdus & 7, 0x00, 0x00, c, h, r, n]
        self.fdc.irq = True

    def midi_in(self, data):
        """Inject MIDI bytes into the OS rx ring (consumer 0FE4:6040: ptr [0x73A2] -> [0x73A0], 256 B page)."""
        mu = self.mu
        wp = int.from_bytes(mu.mem_read(0x73A0, 2), "little")
        for b in data:
            mu.mem_write(wp, bytes([b]))
            wp = (wp & 0xFF00) | ((wp + 1) & 0xFF)
        mu.mem_write(0x73A0, wp.to_bytes(2, "little"))

    def irq(self, line):
        """Deliver ICU IR<line> if unmasked and IF=1. Returns True when taken."""
        mu = self.mu
        fl = mu.reg_read(UC_X86_REG_EFLAGS)
        mask = self.icu.mask
        if not (fl >> 9) & 1 or (mask >> line) & 1:
            return False
        ss, sp = mu.reg_read(UC_X86_REG_SS), mu.reg_read(UC_X86_REG_SP)
        cs, ip = mu.reg_read(UC_X86_REG_CS), mu.reg_read(UC_X86_REG_IP)
        for v in (fl & 0xFFFF, cs, ip):
            sp = (sp - 2) & 0xFFFF
            mu.mem_write((ss << 4) + sp, v.to_bytes(2, "little"))
        mu.reg_write(UC_X86_REG_SP, sp)
        mu.reg_write(UC_X86_REG_EFLAGS, fl & ~0x0300)       # clear IF, TF
        vec = ICU_BASE + line
        off, seg = (int.from_bytes(mu.mem_read(4 * vec + k, 2), "little") for k in (0, 2))
        mu.reg_write(UC_X86_REG_CS, seg)
        mu.reg_write(UC_X86_REG_IP, off)
        return True

    def run(self, steps, on_tick=None):
        """One continuous emu_start (note: in 16-bit mode emu_start's begin is LINEAR, IP = begin - CS*16);
        IR1 ticks are injected from the block hook every TICK_BLOCKS blocks."""
        mu = self.mu
        self.on_tick = on_tick
        mu.reg_write(UC_X86_REG_CS, 0)
        mu.reg_write(UC_X86_REG_EFLAGS, 0x0002)
        try:
            mu.emu_start(0x50, 0xFFFFFFFF, count=steps)
        except UcError as e:
            return e
        return None


def main():
    os_bin = open(sys.argv[1], "rb").read()
    steps = int(sys.argv[sys.argv.index("--steps") + 1]) if "--steps" in sys.argv else 5_000_000
    emu = S2K(os_bin)
    err = emu.run(steps)
    cs = emu.mu.reg_read(UC_X86_REG_CS)
    ip = emu.mu.reg_read(UC_X86_REG_IP)
    print(f"stopped at {cs:04x}:{ip:04x} (lin {emu.lin():05x}) after {emu.nblocks:,} blocks, err={err}")
    l1, l2 = emu.lcd.lines()
    print(f"LCD |{l1}|\n    |{l2}|")
    print("hot blocks:", " ".join(f"{a:05x}x{n}" for a, n in emu.blocks.most_common(8)))
    print("ports:", " ".join(f"{d}{p:x}:{n}" for (d, p), n in sorted(emu.port_log.items(), key=lambda x: -x[1])[:24]))


if __name__ == "__main__":
    main()
