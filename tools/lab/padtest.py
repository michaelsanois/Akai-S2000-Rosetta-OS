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
for chord in ((36, 43), (48, 55, 60, 64), (72, 76, 79)):
    for name, fx in (("OFF", 0), ("JUNO", 8)):
        x = take(fx, chord)[int(1.4 * SR):int(2.3 * SR)]
        out = []
        for c in range(2):
            e = lpc_resid(x[:, c].astype(np.float64))
            s = np.std(e)
            k = np.mean((e / s) ** 4)
            sp = int(np.sum(np.abs(e) > 8 * s))
            out.append(f"kurt {k:5.1f} spikes>8sd {sp:3d}")
        print(f"chord {chord} {name:4s} peak {np.abs(x).max():.2f} | " + " | ".join(out), flush=True)
lab.select(8)
