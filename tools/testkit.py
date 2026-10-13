"""Test samples on the Rosetta boot floppy (load them with LOAD -> FLOPPY from the same Gotek image).

Samples are built with the user's akai_tool (akaitool.image.sample_bytes, S3000 type 0xF3, 192 B header)
and added after the OS file exactly like the S2000 writes a floppy (checked against wiw.org's osimage):
FAT chain at 0x600 (2 B/block, last = 0xC000), directory entry at 0x1400 + 24*i:
name[12], 00 00 06 0A, type, size (3 B LE), start block (2 B LE), 00 11.

  python testkit.py IN.img OUT.img      (also used by mkbaby.py)
"""
import os
import struct
import sys

import numpy as np

# akaitool = github.com/yuyoi/AKAI-CD-ISO-MAKER (the akaitool package): $AKAITOOL, or cloned next to this repo
_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.environ.get("AKAITOOL"), os.path.join(_HERE, "..", "..", "akai_tool"),
           os.path.join(_HERE, "..", "..", "AKAI-CD-ISO-MAKER")):
    if _p and os.path.isdir(os.path.join(_p, "akaitool")):
        sys.path.insert(0, _p)
        break
from akaitool.akai import LM_TO_END, T_SAMP3, Sample, enc_name  # noqa: E402
from akaitool.image import sample_bytes  # noqa: E402

BLOCK, NBLOCKS = 1024, 1600
FAT_AT, DIR_AT, DIR_N = 0x600, 0x1400, 512
SR = 44100


def test_samples():
    n = int(0.3 * SR)
    click = np.zeros(n, np.int16)
    click[int(0.1 * SR)] = 32767           # 100 ms in: note-on fades in over ~30 ms (would eat sample 1)
    rng = np.random.default_rng(1)
    burst = np.zeros(n, np.int16)
    m = int(0.015 * SR)
    burst[:m] = (rng.uniform(-1, 1, m) * 16000).astype(np.int16)
    t = np.arange(int(0.2 * SR)) / SR
    beep = 0.5 * np.sin(2 * np.pi * 1000 * t)
    f = int(0.005 * SR)
    beep[:f] *= np.linspace(0, 1, f)
    beep[-f:] *= np.linspace(1, 0, f)
    beep = (beep * 32767).astype(np.int16)
    return [Sample("CLICK", click, loop_mode=LM_TO_END), Sample("NOISE BURST", burst, loop_mode=LM_TO_END),
            Sample("BEEP 1K", beep, loop_mode=LM_TO_END)]


def add_files(img, files):
    """files: list of (name, type, bytes). Returns the new image."""
    img = bytearray(img)
    fat = [struct.unpack_from("<H", img, FAT_AT + 2 * b)[0] for b in range(NBLOCKS)]
    free = [b for b in range(17, NBLOCKS) if fat[b] == 0]
    slots = [i for i in range(DIR_N) if img[DIR_AT + 24 * i + 16] == 0]
    for name, ftype, data in files:
        nb = -(-len(data) // BLOCK)
        assert len(free) >= nb, "floppy full"
        blocks, free = free[:nb], free[nb:]
        for k, b in enumerate(blocks):
            nxt = blocks[k + 1] if k + 1 < nb else 0xC000
            struct.pack_into("<H", img, FAT_AT + 2 * b, nxt)
            chunk = data[k * BLOCK:(k + 1) * BLOCK]
            img[b * BLOCK:b * BLOCK + len(chunk)] = chunk
        i = slots.pop(0)
        e = enc_name(name) + bytes.fromhex("0000060A") + bytes([ftype]) + len(data).to_bytes(3, "little") + \
            struct.pack("<H", blocks[0]) + bytes.fromhex("0011")
        img[DIR_AT + 24 * i:DIR_AT + 24 * i + 24] = e
    return bytes(img)


def kit_files():
    return [(s.name, T_SAMP3, sample_bytes(s, T_SAMP3, addr=0x10400)) for s in test_samples()]


def listing(img):
    cs = "0123456789 ABCDEFGHIJKLMNOPQRSTUVWXYZ#+-."
    out = []
    for i in range(DIR_N):
        e = img[DIR_AT + 24 * i:DIR_AT + 24 * i + 24]
        if e[16]:
            out.append(("".join(cs[c] if c < len(cs) else "?" for c in e[:12]).strip(), e[16],
                        int.from_bytes(e[17:20], "little"), struct.unpack_from("<H", e, 20)[0]))
    return out


if __name__ == "__main__":
    src, dst = sys.argv[1:3]
    img = add_files(open(src, "rb").read(), kit_files())
    open(dst, "wb").write(img)
    for row in listing(img):
        print(row)
