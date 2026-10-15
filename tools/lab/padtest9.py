import sys, os; sys.path.insert(0, os.environ["TEMP"]); import labsym
import sys, time, mido, numpy as np, sounddevice as sd
sys.path.insert(0, r"C:\Users\JUNKSMITHWIZARD\Desktop\s2000_os\tools")
import s2kfx
lab = s2kfx.Lab(); SR = 44100
lab.out.send(mido.Message("program_change", program=7, channel=0)); time.sleep(0.6)
def lpc_resid(x, p=24):
    r = np.correlate(x, x, "full")[len(x) - 1:len(x) + p]
    R = np.array([[r[abs(i - j)] for j in range(p)] for i in range(p)]) + np.eye(p) * r[0] * 1e-9
    a = np.linalg.solve(R, r[1:p + 1])
    e = x[p:] - np.array([x[p - 1 - np.arange(p) + i] @ a for i in range(len(x) - p)])
    return e
def take(fx, notes, secs=3.0):
    lab.select(fx); time.sleep(0.5)
    r = sd.rec(int(secs * SR), samplerate=SR, channels=2, device=s2kfx.AUDIO_IN, dtype="float32")
    time.sleep(0.2)
    for n in notes: lab.out.send(mido.Message("note_on", note=n, velocity=100))
    time.sleep(2.3)
    for n in notes: lab.out.send(mido.Message("note_off", note=n))
    sd.wait(); return r

sys.path.insert(0, r"C:\Users\JUNKSM~1\AppData\Local\Temp"); import labsym
NMODS, PRATE = labsym.lo("nmods"), labsym.lo("prate")
import struct
def run(label, fx, poke=None):
    lab.select(fx); time.sleep(0.5)
    if poke: poke(); time.sleep(0.3)
    r = sd.rec(int(3.0 * SR), samplerate=SR, channels=2, device=s2kfx.AUDIO_IN, dtype="float32")
    time.sleep(0.2)
    for n in (36, 43): lab.out.send(mido.Message("note_on", note=n, velocity=100))
    time.sleep(2.3)
    for n in (36, 43): lab.out.send(mido.Message("note_off", note=n))
    sd.wait()
    x = r[int(1.4 * SR):int(2.3 * SR)]
    out = []
    for c in range(2):
        e = lpc_resid(x[:, c].astype(np.float64)); s = np.std(e)
        out.append(f"kurt {np.mean((e / s) ** 4):6.1f} spikes {int(np.sum(np.abs(e) > 8 * s)):3d}")
    print(f"{label:22s} | " + " | ".join(out), flush=True)
import re, threading
m = open(r"C:\Users\JUNKSMITHWIZARD\Desktop\s2000_os\build\rosetta_hi.map").read()
sym = lambda n: int(re.search(r"^\s*([0-9A-F]+)\s+[0-9A-F]+\s+" + n + r"\s*$", m, re.M).group(1), 16)
MBOX, MB_ADDR, MB_RES = sym("mbox"), sym("mb_addr"), sym("mb_res")
def mb(cmd, addr, count):
    lab.poke(0x4000, MB_ADDR, struct.pack("<IH", addr, count)); lab.poke(0x4000, MBOX, bytes([cmd]))
    for _ in range(60):
        if lab.peek(0x4000, MBOX, 1)[0] == 0: return struct.unpack("<H", lab.peek(0x4000, MB_RES, 2))[0]
        time.sleep(0.02)
lab.select(8); time.sleep(0.5); lab.poke(s2kfx.MENU_SEG, NMODS, bytes([0])); time.sleep(0.3)
g = mb(7, (0x82 << 16) | 0x0A01, 0); d = mb(7, (0x84 << 16) | 0x0A01, 0)
print(f"tap 1 reads gain {g:04x} len {d:04x}")
def hammer(port, val, stop, cnt):
    while not stop.is_set():
        v = val[cnt[0] % 2]
        mb(6, (port << 16) | 0x0A01, v); cnt[0] += 1
def run2(label, port=None, val=None):
    stop = threading.Event(); cnt = [0]
    th = threading.Thread(target=hammer, args=(port, val, stop, cnt)) if port else None
    r = sd.rec(int(3.0 * SR), samplerate=SR, channels=2, device=s2kfx.AUDIO_IN, dtype="float32")
    time.sleep(0.2)
    for n in (36, 43): lab.out.send(mido.Message("note_on", note=n, velocity=100))
    if th: th.start()
    time.sleep(2.3)
    stop.set()
    if th: th.join()
    for n in (36, 43): lab.out.send(mido.Message("note_off", note=n))
    sd.wait()
    x = r[int(1.4 * SR):int(2.3 * SR)]
    out = []
    for c in range(2):
        e = lpc_resid(x[:, c].astype(np.float64)); s = np.std(e)
        out.append(f"kurt {np.mean((e / s) ** 4):6.1f} spikes {int(np.sum(np.abs(e) > 8 * s)):3d}")
    print(f"{label:26s} writes {cnt[0]:3d} | " + " | ".join(out), flush=True)
gd = (g & 0xFFFC) - (0x10000 if g & 0x8000 else 0)
gs = lambda x: (int(x) & 0xFFFC) | (g & 3)
run2("frozen, no writes")
run2("gain toggle 1 LSB", 0x82, (g, (g - 4) & 0xFFFF))
run2("gain toggle 16 LSB", 0x82, (g, (g - 64) & 0xFFFF))
run2("gain toggle 2%", 0x82, (g, gs(gd * 0.98)))
run2("gain toggle 50%", 0x82, (g, gs(gd * 0.5)))
run2("gain toggle to 0", 0x82, (g, g & 3))
mb(6, (0x84 << 16) | 0x0A01, d); mb(6, (0x82 << 16) | 0x0A01, g)
lab.select(8)
