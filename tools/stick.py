"""Put a build on the Gotek's USB stick as DSKA0000.hfe, keeping the knobs saved on it (REV menu SAV, 0.25).

  py -3.11 -I tools/stick.py build/S2K_ROSETTA_025 J:

The drive must hold FF.CFG (the stick, not some other drive). The knobs live in one 1 KB block at the end of the
hi code (src/rosetta_knobs.asm), and that block moves when the hi code grows, so a new image would lose them:
this reads the stick's DSKA0000.hfe, finds the saved block (magic "RKNB" + the same layout byte, at a block start
inside the OS file), puts it into the build's knob block, writes the stick and compares it back.
"""
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hfe  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
BLOCK, FIRST, LAST = 1024, 273, 400        # the hi code follows the 256 KB OS file at block 17


def stick_image(path):
    h = hfe.HFE(open(path, "rb").read())
    sectors, bad = hfe.read_image(h)
    img = bytearray()
    for c in range(h.ntracks):
        for hd in range(h.nsides):
            for r in range(1, 11):
                img += sectors.get((c, hd, r), bytes(BLOCK))
    return img, bad


def main():
    prefix, d = sys.argv[1], sys.argv[2]
    drive = d.rstrip(":\\/") + ":\\" if len(d.rstrip(":\\/")) == 1 else d   # a drive letter, or a folder (tests)
    assert os.path.isfile(os.path.join(drive, "FF.CFG")), f"{drive} has no FF.CFG: not the Gotek stick"
    img = bytearray(open(prefix + ".img", "rb").read())
    hmap = open(os.path.join(ROOT, "build", "rosetta_hi.map")).read()
    kn = int(re.search(r"^\s*([0-9A-F]+)\s+[0-9A-F]+\s+kn_blk\s*$", hmap, re.M).group(1), 16)
    new_blk = FIRST + kn // BLOCK
    assert img[new_blk * BLOCK:(new_blk + 1) * BLOCK] == bytes(BLOCK), "the build's knob block isn't empty"
    old = os.path.join(drive, "DSKA0000.hfe")
    if os.path.isfile(old):
        simg, bad = stick_image(old)
        found = [b for b in range(FIRST, LAST) if simg[b * BLOCK:b * BLOCK + 4] == b"RKNB"]
        if found:
            b = found[-1]
            saved = simg[b * BLOCK:(b + 1) * BLOCK]
            img[new_blk * BLOCK:(new_blk + 1) * BLOCK] = saved
            print(f"  saved knobs: stick block {b} -> block {new_blk} (layout {saved[4]}, FB {struct.unpack_from('<H', saved, 6)[0]},"
                  f" IN {struct.unpack_from('<H', saved, 8)[0]}, BPM {saved[10]}; bad crc on the stick {bad})")
        else:
            print("  no saved knobs on the stick")
    tmp = prefix + "_stick.img"
    open(tmp, "wb").write(img)
    out = prefix + "_stick.hfe"
    hfe.cmd_write(os.path.join(ROOT, "img", "DSKA0000.hfe"), tmp, out)
    data = open(out, "rb").read()
    with open(old, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    assert open(old, "rb").read() == data, "read-back differs"
    print(f"  {old}: {len(data)} B written and verified")


if __name__ == "__main__":
    main()
