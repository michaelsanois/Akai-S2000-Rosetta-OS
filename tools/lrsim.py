"""Live reverse (src/rosetta_lrev.asm) in unicorn: the hi code's real lr_len / lr_fill, fed a simulated ADC ring and
DMA pointers, every mode checked against numpy. Run it after any engine change, before hardware:

  py -3.11 -I tools/lrsim.py            (needs a build: build/rosetta_hi.bin, .map, lo_syms.inc; unicorn, numpy)

Each pass the "ADC" writes 200-600 samples into the ring at 0:90D0, lr_fill runs, then "ch3" reads as many frames
from our ring (it starts 512 frames behind our first write, like on hw). L must equal the input 512 frames late;
R must be the previous chunk backwards (at the octave's speed, inside START..END). Half / quarter rate shows
~0.5 % error (the interpolation); full rate is exact. "runaway" = a loop that never ends.
"""
import os
import re
import struct

import numpy as np
from unicorn import UC_ARCH_X86, UC_HOOK_CODE, UC_HOOK_INSN, UC_MODE_16, Uc
from unicorn.x86_const import (UC_X86_INS_IN, UC_X86_INS_OUT, UC_X86_REG_CS, UC_X86_REG_DS, UC_X86_REG_EFLAGS,
                               UC_X86_REG_ES, UC_X86_REG_SP, UC_X86_REG_SS)

B = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "build")
hi = open(os.path.join(B, "rosetta_hi.bin"), "rb").read()
hmap = open(os.path.join(B, "rosetta_hi.map")).read()
lsyms = open(os.path.join(B, "lo_syms.inc")).read()


def hs(n):
    return int(re.search(r"^\s*([0-9A-F]+)\s+[0-9A-F]+\s+" + re.escape(n) + r"\s*$", hmap, re.M).group(1), 16)


def ls(n):
    return int(re.search(r"^LO_" + n + r"\s+equ\s+(\S+)", lsyms, re.M).group(1), 0)


RING, HI, LO, D, SR = 0x90D0, 0x40000, 0x3EA00, 512, 44100
mu = Uc(UC_ARCH_X86, UC_MODE_16)
mu.mem_map(0, 0x100000)
mu.mem_write(HI, hi)
dmau = {"sel": 0, 2: RING, 3: 0}


def port_in(uc, port, size, ud):
    if port == 0xC001:
        return dmau["sel"]
    if port == 0xC004:
        return dmau.get(dmau["sel"], 0) & 0xFFFF
    return 0


def port_out(uc, port, size, value, ud):
    if port == 0xC001:
        dmau["sel"] = value & 3


mu.hook_add(UC_HOOK_INSN, port_in, None, 1, 0, UC_X86_INS_IN)
mu.hook_add(UC_HOOK_INSN, port_out, None, 1, 0, UC_X86_INS_OUT)
steps = {"n": 0}


def count(uc, a, size, ud):
    steps["n"] += 1
    if steps["n"] > 3_000_000:
        raise SystemExit("runaway")


mu.hook_add(UC_HOOK_CODE, count)
RET = len(hi) + 16


def call(label):
    """near call into the hi code (CS = 4000h, DS = ES = 0 as from its tick)"""
    mu.mem_write(0x7FFE, struct.pack("<H", RET))
    mu.reg_write(UC_X86_REG_SS, 0)
    mu.reg_write(UC_X86_REG_SP, 0x7FFE)
    mu.reg_write(UC_X86_REG_CS, 0x4000)
    mu.reg_write(UC_X86_REG_DS, 0)
    mu.reg_write(UC_X86_REG_ES, 0)
    mu.reg_write(UC_X86_REG_EFLAGS, 2)
    steps["n"] = 0
    mu.emu_start(HI + hs(label), HI + RET)


def w8(a, v):
    mu.mem_write(a, bytes([v & 0xFF]))


def w16(a, v):
    mu.mem_write(a, struct.pack("<H", v & 0xFFFF))


def r16(a):
    return struct.unpack("<H", mu.mem_read(a, 2))[0]


def run(sig, lenms=390, pfb=0, bpm=0, div=1, oct_=0, st=0, en=99, passes=400, seed=1):
    """knobs as on the REV menu; returns (state, input, L, R) as ch3 read them"""
    rng = np.random.default_rng(seed)
    w8(LO + ls("fxon"), 8)                                    # REVERSE
    w16(LO + ls("pfb"), pfb)
    for n, v in (("lr_bpm", bpm), ("lr_div", div), ("lr_oct", oct_), ("lr_st", st), ("lr_en", en)):
        w8(HI + hs(n), v)
    w16(HI + hs("lr_lenms"), lenms)
    mu.mem_write(HI + 0x4000, bytes(0xC000))                 # = lr_start's state, minus the OS / chip calls
    w16(HI + hs("lr_hw"), 0x4000)
    w16(HI + hs("lr_j"), 0xFFFF)
    w16(HI + hs("lr_wb"), 0xE000 + D * 4)
    w16(HI + hs("lr_last"), 0)
    for n in ("lr_hph", "lr_side", "lr_evaon", "lr_evron"):
        w8(HI + hs(n), 0)
    mu.mem_write(HI + hs("lr_c3f"), bytes(4))
    mu.mem_write(HI + hs("lr_wf"), struct.pack("<I", D))
    w16(HI + hs("lr_c3a"), 0xE000)
    w16(HI + hs("lr_pka"), 0)
    w16(HI + hs("lr_cg"), 256)
    w16(HI + hs("lr_cgn"), 256)
    adc = ch3 = 0
    L, R = [], []
    for _ in range(passes):
        k = int(rng.integers(100, 300)) * 2
        for _ in range(k):
            w16(RING + 2 * (adc % 4096), int(sig[adc]))
            adc += 1
        dmau[2] = RING + 2 * (adc % 4096)
        dmau[3] = 0xE000 + 4 * (ch3 % 2048)
        call("lr_len")
        call("lr_fill")
        for _ in range(k):
            o = HI + 0xE000 + 4 * (ch3 % 2048)
            L.append(struct.unpack("<h", mu.mem_read(o, 2))[0])
            R.append(struct.unpack("<h", mu.mem_read(o + 2, 2))[0])
            ch3 += 1
    state = dict(n=r16(HI + hs("lr_n")), rl=mu.mem_read(HI + hs("lr_rl"), 1)[0], f=r16(HI + hs("lr_f")),
                 s=r16(HI + hs("lr_s")), e=struct.unpack("<b", bytes(mu.mem_read(HI + hs("lr_e"), 1)))[0])
    return state, np.array(sig[:adc]), np.array(L), np.array(R)


def check(name, **kw):
    t = np.arange(400000)
    sig = (np.sin(2 * np.pi * 110 * t / SR) * 12000 + np.sin(2 * np.pi * 37 * t / SR) * 8000).astype(int)
    stt, inp, L, R = run(sig, **kw)
    n, f, sl = stt["n"], stt["f"], stt["s"]
    p0 = kw.get("st", 0) * n // 100 & ~1
    sp = 2.0 ** kw.get("oct_", 0)
    errs = []
    for c in range(2, len(inp) // n - 1):
        for j in range(0, n, 11):
            js = j % sl
            if js < f + 32 or js > sl - f - 32 or n - j < f + 32:
                continue
            o = D + c * n + j
            if o >= len(R):
                break
            errs.append(abs(R[o] - np.interp(c * n - 1 - (p0 + js) * sp, np.arange(len(inp)), inp)))
    errs = np.array(errs) if errs else np.zeros(1)
    lok = np.array_equal(L[D + 2000:D + 6000], inp[2000:6000])
    print(f"{name:22s} chunk {n:5d} ({n / SR * 1000:4.0f} ms) slice {sl:5d} 44.1k>>{stt['rl']} e {stt['e']:2d} | "
          f"L ok {lok} | R err median {np.median(errs):5.1f} max {errs.max():5.0f}")


if __name__ == "__main__":
    check("FREE 160 ms", lenms=160)
    check("FREE 390 ms (22k)", lenms=390)
    check("92 bpm 1/8", bpm=92, div=1)
    check("92 bpm 1/4 (11k)", bpm=92, div=3)
    check("160 ms oct +1", lenms=160, oct_=1)
    check("160 ms oct -1", lenms=160, oct_=-1)
    check("92 bpm 1/4 oct -1", bpm=92, div=3, oct_=-1)
    check("START 20 END 39", lenms=160, st=20, en=39)
    check("1/8 START 50 END 59", bpm=92, div=1, st=50, en=59)
    check("160 ms FB 40 (+repeats)", lenms=160, pfb=40)   # feedback adds the repeats: R differs on purpose
