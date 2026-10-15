"""HW lab: hunt hidden L7A1045 filter modes. Noise loop on voice 25 (lab cmd 8), poke filter regs, record, compare.
  py -3.10 filtlab.py"""
import struct, sys, time, json
import numpy as np
sys.path.insert(0, r"C:\Users\JUNKSMITHWIZARD\Desktop\s2000_os\tools")
import s2kfx
import sounddevice as sd

HI = 0x4000
MBOX, MB_ADDR, MB_COUNT, MB_RES = 0x629, 0x62B, 0x62F, 0x632
V = 25
SR = 44100
lab = s2kfx.Lab()
print("version", hex(lab.ping()))
hb = open(sys.argv[1], "rb").read() if len(sys.argv) > 1 else None
if hb:
    got = lab.peek(HI, 0, 64)
    assert got == hb[:64], "hi code on the S2000 != the 0.25 map build"
    print("hi header matches the 0.25 build")


def mb(cmd, addr, count, to=3.0):
    lab.poke(HI, MB_ADDR, struct.pack("<IH", addr, count))
    lab.poke(HI, MBOX, bytes([cmd]))
    end = time.time() + to
    while time.time() < end:
        if lab.peek(HI, MBOX, 1)[0] == 0:
            return struct.unpack("<H", lab.peek(HI, MB_RES, 2))[0]
        time.sleep(0.05)
    raise SystemExit(f"mailbox cmd {cmd} timed out")


def reg(r, port, val):          # main bank, atomic
    mb(6, (port << 16) | (r << 8) | V, val & 0xFFFF)


def ebank(fn, port, val):       # second bank E0-E4 (not atomic, OS only writes it on note-on)
    lab.outw(0xE0, (fn << 8) | V)
    lab.outw(port, val & 0xFFFF)


def cut(c, res=0):              # c = 0..0x7FF (11 bit) -> target word, current = target/2
    w = (c << 4) | res
    reg(5, 0x84, w >> 1)
    reg(6, 0x84, w)


def take(secs=1.0):
    time.sleep(0.25)
    r = sd.rec(int(secs * SR), samplerate=SR, channels=2, device=s2kfx.AUDIO_IN, dtype="float32")
    sd.wait()
    return r[:, 0] + r[:, 1]


BANDS = [63, 125, 250, 500, 1000, 2000, 4000, 8000, 12000, 16000]
def psd(x, n=4096):
    w = np.hanning(n)
    fr = [np.abs(np.fft.rfft(x[i:i + n] * w)) ** 2 for i in range(0, len(x) - n, n // 2)]
    return np.mean(fr, 0)
f = np.fft.rfftfreq(4096, 1 / SR)
def bands(p):
    return [10 * np.log10(np.mean(p[(f > b / 1.26) & (f < b * 1.26)]) + 1e-20) for b in BANDS]


# FX off, noise into sample RAM word FE0000 (Rosetta's reverse scratch), tone on
lab.select(0)
rng = np.random.default_rng(1)
noise = (rng.uniform(-1, 1, 2048) * 4000).astype("<i2").tobytes()
lab.poke(0x4800, 0, noise)
mb(2, 0x00FE0000, 2048)
mb(8, 0x00FE0000, 2048)
time.sleep(0.5)
base = psd(take())
peak = None
print("base (open) band levels dB:", " ".join(f"{b:6.1f}" for b in bands(base)))
print("bands Hz:                   ", " ".join(f"{b:6d}" for b in BANDS))
out = {}


def test(name, setup, undo):
    setup()
    p = psd(take())
    undo()
    rel = [a - b for a, b in zip(bands(p), bands(base))]
    out[name] = rel
    print(f"{name:28s}", " ".join(f"{r:6.1f}" for r in rel), flush=True)


DEF = lambda: (cut(0x7FF), ebank(1, 0xE4, 0x8000), ebank(1, 0xE2, 0), ebank(4, 0xE4, 0x20),
               ebank(2, 0xE2, 0), ebank(2, 0xE4, 0))
MID = 0x500
test("LP mid res0", lambda: cut(MID, 0), DEF)
test("LP mid res8", lambda: cut(MID, 8), DEF)
test("LP mid res15", lambda: cut(MID, 15), DEF)
test("LP low res8", lambda: cut(0x380, 8), DEF)
for fn, port, vals in [(1, 0xE4, [0x0000, 0x4000, 0xC000, 0xFFFF]), (1, 0xE2, [0x8000, 0x4000]),
                       (4, 0xE4, [0x00, 0x10, 0x40, 0x80, 0x200, 0x2000]), (2, 0xE2, [0x8000, 0x2000]),
                       (2, 0xE4, [0x8000, 0x2000]), (3, 0xE2, [0x8000]), (3, 0xE4, [0x8000, 0x2000]),
                       (0, 0xE4, [0x8000]), (5, 0xE4, [0x8000]), (6, 0xE4, [0x8000]), (7, 0xE4, [0x8000])]:
    for v in vals:
        test(f"mid8 E{fn}.{port:02X}={v:04X}", lambda fn=fn, port=port, v=v: (cut(MID, 8), ebank(fn, port, v)), DEF)
test("mid8 reg6 bit15", lambda: (reg(5, 0x84, 0x2804), reg(6, 0x84, 0x8000 | (MID << 4) | 8)), DEF)
for r, port, v in [(6, 0x86, 0x8000), (6, 0x86, 0x0001), (5, 0x82, 0x8000), (5, 0x86, 0x8000), (6, 0x8C, 0x8000)]:
    o = mb(7, (port << 16) | (r << 8) | V, 0)
    print(f"  reg{r}.{port:02X} reads {o:04X}")
    test(f"mid8 reg{r}.{port:02X}={v:04X}", lambda r=r, port=port, v=v: (cut(MID, 8), reg(r, port, v)),
         lambda r=r, port=port, o=o: (reg(r, port, o), DEF()))
mb(8, 0, 0)
json.dump(out, open("filtlab.json", "w"))
print("done, tone off")
