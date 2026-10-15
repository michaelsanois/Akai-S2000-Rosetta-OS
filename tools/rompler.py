"""ROSETTA ROM: a tiny synth rompler on the boot floppy. The S2000 loads a boot floppy's programs and samples
right after the OS, so they're there at power-on: programs 1-9 (RS SAW .. RS PLUCK), pick them on the main screen.

Band-limited single-cycle waves (SAW, SQR, PLS, TRI, SIN), multisampled in 5 key ranges so no range aliases at its
top note, plus ready-made S1000 programs that use them (filter + filter envelope, detuned layers). With the SYNTH
CCs (20-25: drift, detune, filter LFO) they make a small analog-style synth.

Waves: the loop is k whole cycles (>= 256 samples, so the pitch is exact after the cents tune), stored with PRE
samples of the wave before it and GUARD after it (the same periodic wave all through). The chip's interpolator reads
past the loop end and, after the jump back, before the loop start (measured on hw 2026-10-15: a loop with other data
around it clicked once per loop at up to 1.3 x the wave's level = the "crackle"; with the wave on both sides, -34 dB
residual = the noise floor), so both sides must be the wave itself.

  python -I tools/rompler.py                 list what goes on the disk
  (mkbaby.py adds it unless ROMPLER=0)
"""
import math
import os
import struct
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import testkit  # noqa: E402  (finds the akaitool package)
from akaitool.akai import (KG_SIZE, LM_LOOP_REL, PB_AS_SAMPLE, T_PROG1, T_SAMP3, Keygroup, Loop, Program,  # noqa: E402
                           Sample, Zone)
from akaitool.image import program_bytes, sample_bytes  # noqa: E402

SR = 44100
TOP_HZ = 18000                               # harmonics stay below this at a range's top note
RANGES = [(0, 41, 36), (42, 59, 52), (60, 71, 66), (72, 83, 78), (84, 127, 90)]   # lo, hi, root (MIDI)
MIN_LEN = 256
GUARD = 64                                   # the wave continued after the loop end ...
PRE = 32                                     # ... and before the loop start (the chip's interpolator reads both)


def hz(note):
    return 440.0 * 2 ** ((note - 69) / 12)


def wave(kind, nh, k, n):
    """k cycles of `kind` in n samples, harmonics 1..nh (additive, so nothing above nh)"""
    t = np.arange(n) * (2 * np.pi * k / n)
    x = np.zeros(n)
    for h in range(1, nh + 1):
        if kind == "SAW":
            a = 1 / h
        elif kind == "SQR":
            a = 1 / h if h % 2 else 0
        elif kind == "PLS":                  # 25 % pulse
            a = math.sin(math.pi * h * 0.25) / h
        elif kind == "TRI":
            a = (-1) ** ((h - 1) // 2) / h ** 2 if h % 2 else 0
        else:                                # SIN
            a = 1.0 if h == 1 else 0
        if a:
            x += a * (np.cos(h * t) if kind == "PLS" else np.sin(h * t))
    return x


def make_sample(kind, rng_i):
    lo, hi, root = RANGES[rng_i]
    f = hz(root)
    k = max(1, math.ceil(MIN_LEN * f / SR))  # cycles so the buffer is >= MIN_LEN
    n = round(k * SR / f)
    f0 = k * SR / n                          # the pitch the buffer really has
    top = min(hi, 108)                       # (above C8 nobody minds a little aliasing)
    nh = max(1, min(int(TOP_HZ / (f0 * 2 ** ((top - root) / 12))), n // (2 * k) - 1))
    x = wave(kind, nh, k, n)
    x = x - x.mean()
    x = x / np.abs(x).max() * 0.85 * 32767
    pcm = np.round(x).astype(np.int16)
    pcm = pcm[(np.arange(PRE + n + GUARD) - PRE) % n]   # PRE | the loop (n) | GUARD, one periodic wave
    cents = 1200 * math.log2(hz(root) / f0)  # tune so note `root` sounds at its own pitch
    name = f"RS {kind} {rng_i + 1}"
    return Sample(name, pcm, root=root, cents=cents, loops=[Loop(PRE, PRE + n)], loop_mode=LM_LOOP_REL), nh


# programs: (name, zones [(wave, cents, semis, pan, loud)], filter, key>filter, env1 ADSR, env2 ADSR, env2>filter)
PROGS = [
    ("RS SAW", [("SAW", 0, 0, 0, 0)], 80, 12, (0, 99, 99, 30), (0, 60, 70, 40), 15),
    ("RS SQUARE", [("SQR", 0, 0, 0, 0)], 80, 12, (0, 99, 99, 30), (0, 60, 70, 40), 15),
    ("RS PULSE", [("PLS", 0, 0, 0, 0)], 85, 12, (0, 99, 99, 30), (0, 60, 70, 40), 10),
    ("RS TRI", [("TRI", 0, 0, 0, 0)], 99, 0, (0, 99, 99, 30), (0, 99, 99, 99), 0),
    ("RS SINE", [("SIN", 0, 0, 0, 0)], 99, 0, (0, 99, 99, 30), (0, 99, 99, 99), 0),
    ("RS SUPERSAW", [("SAW", -12, 0, -30, -6), ("SAW", 0, 0, 0, -6), ("SAW", 12, 0, 30, -6)],
     85, 12, (0, 99, 99, 45), (0, 99, 99, 99), 0),
    ("RS BASS", [("SQR", 0, 0, 0, 0), ("SAW", 0, -12, 0, -4)], 45, 6, (0, 70, 80, 15), (0, 35, 10, 20), 40),
    ("RS PAD", [("SAW", -7, 0, -25, -4), ("SAW", 7, 0, 25, -4), ("TRI", 0, 12, 0, -10)],
     60, 12, (55, 99, 99, 70), (60, 99, 80, 70), 20),
    ("RS PLUCK", [("PLS", 0, 0, 0, 0)], 55, 12, (0, 45, 0, 35), (0, 30, 0, 30), 45),
]
KG_KEYFILT, KG_VELFILT, KG_ENV2FILT = 8, 9, 11      # S1000 keygroup bytes akaitool's writer leaves at 0


def build():
    """[(name, type, bytes)] for testkit.add_files"""
    files, used = [], set()
    for _, zones, *_ in PROGS:
        used |= {z[0] for z in zones}
    for kind in ("SAW", "SQR", "PLS", "TRI", "SIN"):
        if kind not in used:
            continue
        for r in range(len(RANGES)):
            s, _ = make_sample(kind, r)
            files.append((s.name, T_SAMP3, sample_bytes(s, T_SAMP3, addr=0x10400)))
    for pn, (name, zones, filt, keyf, e1, e2, e2f) in enumerate(PROGS):
        kgs = []
        for r, (lo, hi, _) in enumerate(RANGES):
            env = dict(filter=filt, amp_att=e1[0], amp_dec=e1[1], amp_sus=e1[2], amp_rel=e1[3],
                       fil_att=e2[0], fil_dec=e2[1], fil_sus=e2[2], fil_rel=e2[3])
            zs = [Zone(sample=f"RS {w} {r + 1}", tune=c + 100 * sm, pan=pan, loud=loud, playback=PB_AS_SAMPLE)
                  for w, c, sm, pan, loud in zones]
            kgs.append(Keygroup(lo=lo, hi=hi, zones=zs, env=env))
        p = Program(name, keygroups=kgs, midi_prog=pn, polyphony=31, loudness=80)   # program 1-9 (same number = layered)
        b = bytearray(program_bytes(p, T_PROG1))
        hl = 150
        for i in range(len(kgs)):
            o = hl + i * KG_SIZE
            b[o + KG_KEYFILT] = keyf
            b[o + KG_ENV2FILT] = e2f
        files.append((name, T_PROG1, bytes(b)))
    return files


if __name__ == "__main__":
    tot = 0
    for kind in ("SAW", "SQR", "PLS", "TRI", "SIN"):
        for r in range(len(RANGES)):
            s, nh = make_sample(kind, r)
            lo, hi, root = RANGES[r]
            print(f"  {s.name:12s} keys {lo:3d}-{hi:3d} root {root} {PRE}+{s.n - GUARD - PRE:4d}+{GUARD} samples, {nh:3d} harmonics, tune {s.cents:+.1f} c")
    for n, t, b in build():
        tot += len(b)
    print(f"  {len(build())} files, {tot / 1024:.1f} KB")
