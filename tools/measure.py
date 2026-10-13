"""Fire the current sample (CLICK) via MIDI and list echoes per channel. Uses the Rosetta lab (0.09+).
  py -3.10 measure.py NAME [preset|keep] [secs]"""
import os, sys, time, struct
import numpy as np, sounddevice as sd, soundfile as sf, mido
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s2kfx
SR = 44100
name = sys.argv[1]; preset = sys.argv[2] if len(sys.argv) > 2 else "keep"; secs = float(sys.argv[3]) if len(sys.argv) > 3 else 2.5
lab = s2kfx.Lab()
if preset != "keep":
    on = preset != "off"
    lab.poke(s2kfx.MENU_SEG, s2kfx.FXON_OFF, bytes([1 if on else 0]))
    t = s2kfx.PRESETS[preset]() if preset in s2kfx.PRESETS else open(preset, "rb").read()
    lab.load_table(t)
    time.sleep(0.2)
rec = sd.rec(int(secs * SR), samplerate=SR, channels=2, device=s2kfx.AUDIO_IN, dtype="float32")
time.sleep(0.3)
lab.note(60, 50, 127)
sd.wait()
os.makedirs("rec", exist_ok=True)
sf.write(f"rec/{name}.wav", rec, SR)
x = rec
ref = np.abs(x).max()
dry = int(np.argmax(np.abs(x).max(axis=1)))
print(f"{name}: preset={preset} peak {ref:.3f} at {dry / SR * 1000:.0f} ms")
for ch, nm in ((0, "L"), (1, "R")):
    a = np.abs(x[:, ch])
    # local maxima in 1 ms windows above -50 dB of the overall peak, after the dry click
    w = 44
    seg = a[dry - 100:]
    n = len(seg) // w
    mx = seg[:n * w].reshape(n, w).max(axis=1)
    db = 20 * np.log10(mx / ref + 1e-9)
    pk = [i for i in range(1, n - 1) if mx[i] >= mx[i - 1] and mx[i] > mx[i + 1] and db[i] > -50]
    rows = [(i * w - 100, db[i]) for i in pk]
    print(f"  {nm}: " + ", ".join(f"{d / SR * 1000:.1f}ms({d}smp) {v:.0f}dB" for d, v in rows[:24]))
