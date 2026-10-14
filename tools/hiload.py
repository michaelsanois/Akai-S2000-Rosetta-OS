"""Send a new hi-code build into a running S2000 over the Rosetta SysEx lab (no reboot, no floppy).

  py -3.10 hiload.py [build/rosetta_hi.bin]

Needs the running hi code to be 0.20+ (header hook slots). Steps: park the loader's tick (state 2), upload
the blob, re-point every OS hook from the blob's patch table to its new bytes, then unpark (state 1): the
new blob's tick sees `inited` = 0 and runs its own `apply` (new hooks, if any). Play no notes meanwhile.
"""
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s2kfx  # noqa: E402

HI_SEG = 0x4000
LOAD_SEG, STATE = 0x3E02, 0x0003      # src/rosetta_load.asm: state 1 = running, 2 = parked

path = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                                                           "build", "rosetta_hi.bin")
blob = open(path, "rb").read()
assert blob[:4] == b"RSHI"
lab = s2kfx.Lab()
ver = lab.ping()
print(f"S2000 version {ver:#06x}, running hi {lab.peek(HI_SEG, 0, 6)!r}, loader state "
      f"{lab.peek(LOAD_SEG, STATE, 1)[0]}")
assert lab.peek(HI_SEG, 0, 4) == b"RSHI", "no hi code running"
# the hi code patches and reads the menu code by its build's addresses (build/lo_syms.inc): only send it into
# an S2000 booted from the same build (the menu code's VERSION_W = the hi header's version)
hv = struct.unpack_from("<H", blob, 4)[0]
if ver != hv and "--force" not in sys.argv:
    raise SystemExit(f"the S2000 runs menu code {ver:#06x}, this hi build is {hv:#06x}: boot the matching floppy "
                     f"(or --force if only the hi code changed since)")

# the new blob's patch table (header +15): dw seg, off / db n / stock / new; seg 0 ends it
p = struct.unpack_from("<H", blob, 0x15)[0]
hooks = []
while True:
    seg, off = struct.unpack_from("<HH", blob, p)
    if not seg:
        break
    n = blob[p + 4]
    hooks.append((seg, off, blob[p + 5:p + 5 + n], blob[p + 5 + n:p + 5 + 2 * n]))
    p += 5 + 2 * n

lab.poke(LOAD_SEG, STATE, b"\x02")
time.sleep(0.1)
lab.poke(HI_SEG, 0, blob)
time.sleep(0.1)
assert lab.peek(HI_SEG, 0, len(blob)) == blob, "upload read-back mismatch"
for seg, off, stock, new in hooks:
    cur = lab.peek(seg, off, len(new))
    if cur == new:
        continue
    assert cur == stock or cur[0] == 0x9A and cur[3:5] == b"\x00\x40", f"{seg:04x}:{off:04x} holds {cur.hex()}"
    lab.poke(seg, off, new)
    print(f"  hook {seg:04x}:{off:04x} {cur.hex()} -> {new.hex()}")
lab.poke(LOAD_SEG, STATE, b"\x01")
time.sleep(0.3)
print(f"loaded {len(blob)} B, version {struct.unpack_from('<H', blob, 4)[0]:#06x}; loader state "
      f"{lab.peek(LOAD_SEG, STATE, 1)[0]}")
