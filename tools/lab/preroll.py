import sys, struct, time, re
import numpy as np
sys.path.insert(0, r"C:\Users\JUNKSMITHWIZARD\Desktop\s2000_os\tools")
import s2kfx, testkit, rompler
lab = s2kfx.Lab()
m = open(r"C:\Users\JUNKSMITHWIZARD\Desktop\s2000_os\build\rosetta_hi.map").read()
sym = lambda n: int(re.search(r"^\s*([0-9A-F]+)\s+[0-9A-F]+\s+" + n + r"\s*$", m, re.M).group(1), 16)
MBOX, MB_ADDR = sym("mbox"), sym("mb_addr")
def mb(cmd, addr, count):
    lab.poke(0x4000, MB_ADDR, struct.pack("<IH", addr, count)); lab.poke(0x4000, MBOX, bytes([cmd]))
    for _ in range(60):
        if lab.peek(0x4000, MBOX, 1)[0] == 0: return
        time.sleep(0.05)
    raise SystemExit("timeout")
ADDR = {3: 0x1B1E0, 4: 0x1B390, 5: 0x1B500}
for r in (3, 4, 5):
    s = rompler.make_sample("SIN", r - 1)[0]
    n = len(s.pcm) - rompler.GUARD
    pre = s.pcm[n - 32:n].astype("<i2").tobytes()
    lab.poke(0x4800, 0, pre)
    mb(2, ADDR[r] - 32, 32)
    mb(1, ADDR[r] - 32, 32)
    print(f"SIN {r}: 32 pre-roll words before {ADDR[r]:05x}: verify {lab.peek(0x4800, 0, 64) == pre}")
