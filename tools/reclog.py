"""Read the Rosetta 0.16 record probe over the SysEx lab and print it (hold-to-record research).

  py -3.11 -I tools/reclog.py [out.bin]

After a take on the S2000 (started with the REC key, let go mid-take), the probe at 3E50:0000 holds:
  0x00 'RL', snapshot count, flags (bit0 started by REC, bit1 REC let go, bit2 take kept)
  0x10 7500-750F (REC settings)   0x20 7A30-7A8F at take start   0x80 87A0-87CF   0xB0 7538-7547
  0x100 + 16 n: snapshots (tick, flags, [7A7C], [7A62..7A67], [7A5E], [7A60], [7A74])
  0x380 7A30-7A8F when REC was let go   0x3E0 7A30-7A8F + 0x440 87A0-87CF when the take was kept
"""
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from s2kfx import Lab  # noqa: E402

LOG_SEG = 0x3E50
SIZE = 0x470


def words(b, base):
    return " ".join(f"{base + i:04x}:{struct.unpack_from('<H', b, i)[0]:04x}" for i in range(0, len(b), 2))


def main():
    lab = Lab()
    print("Rosetta", hex(lab.ping()))
    d = lab.peek(LOG_SEG, 0, SIZE)
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join("rec", f"reclog_{time.strftime('%H%M%S')}.bin")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    open(out, "wb").write(d)
    print("saved", out)
    if d[:2] != b"RL":
        raise SystemExit("no log (magic missing): record a take first")
    n, fl = d[2], d[3]
    print(f"snapshots {n}, started by REC {fl & 1}, let go {fl >> 1 & 1}, kept {fl >> 2 & 1}")
    print("7500:", d[0x10:0x20].hex(" "))
    print("7538:", d[0xB0:0xC0].hex(" "))
    for name, off, base, ln in (("start 7A30", 0x20, 0x7A30, 0x60), ("start 87A0", 0x80, 0x87A0, 0x30),
                                ("let go 7A30", 0x380, 0x7A30, 0x60), ("kept 7A30", 0x3E0, 0x7A30, 0x60),
                                ("kept 87A0", 0x440, 0x87A0, 0x30)):
        print(f"-- {name}")
        blk = d[off:off + ln]
        for i in range(0, ln, 16):
            print("  ", words(blk[i:i + 16], base + i))
    print("-- snapshots: tick fl 7A7C | 7A62 7A64 7A66 | 7A5E 7A60 | 7A74")
    for k in range(min(n, 40)):
        s = d[0x100 + 16 * k:0x110 + 16 * k]
        t, f = s[0], s[1]
        w = struct.unpack_from("<7H", s, 2)
        print(f"  {t:3d} {f}  {w[0]:4x} | {w[1]:04x} {w[2]:04x} {w[3]:04x} | {w[4]:04x} {w[5]:04x} | {w[6]:04x}")


if __name__ == "__main__":
    main()
