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

MSL = labsym.lo("mslots")
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

def slots(depth=None, inc=None, gain=None):
    def f():
        for k in range(2):
            b = MSL + 16 * k
            if depth is not None: lab.poke(s2kfx.MENU_SEG, b + 7, struct.pack("<H", depth))
            if inc is not None: lab.poke(s2kfx.MENU_SEG, b + 9, struct.pack("<H", inc))
    return f
print("slot0", lab.peek(s2kfx.MENU_SEG, MSL, 16).hex(), "slot1", lab.peek(s2kfx.MENU_SEG, MSL + 16, 16).hex())
run("JUNO", 8)
run("JUNO depth 0 (same values)", 8, slots(depth=0))
run("JUNO depth 0, f mid", 8, slots(depth=0))
run("JUNO depth 4 samples", 8, slots(depth=4))
run("JUNO inc 0 (phase frozen)", 8, slots(inc=0))
run("JUNO", 8)
lab.select(8)
