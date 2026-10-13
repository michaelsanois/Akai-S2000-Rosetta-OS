"""Record an A/B demo: for each preset, load it, then 3 hits of the current sample, into one wav.
  py -3.10 demo.py OUT.wav PRESET [PRESET ...]   (preset = name, .bin table, or .json exact taps)"""
import json, os, sys, time
import numpy as np, sounddevice as sd, soundfile as sf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s2kfx
SR = 44100
lab = s2kfx.Lab()
out, parts = sys.argv[1], []
for p in sys.argv[2:]:
    if p.startswith("sel"):
        lab.select(int(p[3:]))
    else:
        lab.poke(s2kfx.MENU_SEG, s2kfx.FXON_OFF, bytes([0 if p == "off" else 1]))
    if p.startswith("sel"):
        pass
    elif p.endswith(".json"):
        lab.load_taps(json.load(open(p)))
    else:
        lab.load_table(s2kfx.PRESETS[p]() if p in s2kfx.PRESETS else open(p, "rb").read())
    time.sleep(0.3)
    rec = sd.rec(int(5.0 * SR), samplerate=SR, channels=2, device=s2kfx.AUDIO_IN, dtype="float32")
    for k in range(3):
        time.sleep(0.25)
        lab.note(60, 250, 127)
        time.sleep(0.6 if k < 2 else 0)
    sd.wait()
    print(f"{p}: peak {np.abs(rec).max():.3f}")
    parts += [rec, np.zeros((int(0.3 * SR), 2), np.float32)]
sf.write(out, np.concatenate(parts), SR)
print("wrote", out)
