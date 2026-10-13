"""Measure the delay engine as an impulse response: fire NOISE BURST with FX off (reference) and with a
preset, then deconvolve per channel (H = WET / DRY_REF). Peaks of h = tap times + gains.
  py -3.10 irmeasure.py PRESET [PRESET ...]      (needs current sample = NOISE BURST: [7639] = 1)"""
import os, sys, time
import numpy as np, sounddevice as sd, soundfile as sf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s2kfx
SR = 44100
lab = s2kfx.Lab()


def take(preset, secs=2.0):
    on = preset != "off"
    if not preset.startswith("sel"):
        lab.poke(s2kfx.MENU_SEG, s2kfx.FXON_OFF, bytes([1 if on else 0]))
    if preset.startswith("sel"):                          # sel6 = firmware preset 6 (0.10+)
        lab.select(int(preset[3:]))
    elif preset.endswith(".json"):
        import json
        lab.load_taps(json.load(open(preset)))
    else:
        t = s2kfx.PRESETS[preset]() if preset in s2kfx.PRESETS else open(preset, "rb").read()
        lab.load_table(t)
    time.sleep(0.3)
    rec = sd.rec(int(secs * SR), samplerate=SR, channels=2, device=s2kfx.AUDIO_IN, dtype="float32")
    time.sleep(0.3)
    lab.note(60, 300, 127)
    sd.wait()
    sf.write(f"rec/ir_{os.path.basename(preset).split('.')[0]}.wav", rec, SR)
    return rec


def ir(wet, ref, n=1 << 16):
    W, R = np.fft.rfft(wet, n), np.fft.rfft(ref, n)
    h = np.fft.irfft(W * np.conj(R) / (np.abs(R) ** 2 + 1e-3 * np.abs(R).max() ** 2), n)
    return h


os.makedirs("rec", exist_ok=True)
dry = take("off")
mono = dry.mean(axis=1)
on = np.argmax(np.abs(mono) > 0.05 * np.abs(mono).max())
ref = mono[on - 200:on + int(0.06 * SR)]                    # burst incl. 30 ms fade-in
print(f"dry peak L {np.abs(dry[:,0]).max():.3f} R {np.abs(dry[:,1]).max():.3f}, onset {on/SR*1000:.0f} ms")
N = 1 << 18
for p in sys.argv[1:]:
    secs = 4.0
    wet = take(p, secs)
    print(f"== {p}: peak L {np.abs(wet[:,0]).max():.3f} R {np.abs(wet[:,1]).max():.3f}")
    for ch, nm in ((0, "in1"), (1, "in2")):
        h = ir(wet[:, ch], ref, N)
        h = np.roll(h, 4000)                                  # allow negative lags
        a = np.abs(h)
        mw = np.abs(wet.mean(axis=1))
        onw = int(np.argmax(mw > 0.05 * mw.max()))
        z0 = onw - 200 + 4000                                 # lag where the dry burst sits
        z = z0 - 300 + int(np.argmax(a[z0 - 300:z0 + 300]))
        d0 = a[z]
        a = a[z:z + int(3.0 * SR)]
        w = 22
        nb = len(a) // w
        mx = a[:nb * w].reshape(nb, w).max(axis=1)
        am = a[:nb * w].reshape(nb, w).argmax(axis=1) + np.arange(nb) * w
        db = 20 * np.log10(mx / d0 + 1e-12)
        pk = [i for i in range(1, nb - 1) if mx[i] >= mx[i - 1] and mx[i] > mx[i + 1] and db[i] > -30 and am[i] > 30]
        pk = sorted(pk, key=lambda i: -mx[i])[:int(os.environ.get("NPK", 16))]
        print(f"  {nm}: " + ", ".join(f"{am[i]}/{am[i]/SR*1000:.0f}ms {db[i]:+.0f}" for i in sorted(pk)))
        e = np.cumsum((a ** 2)[::-1])[::-1]
        edb = 10 * np.log10(e / e[0] + 1e-12)
        marks = [int(np.argmax(edb < -t)) for t in (10, 20, 30)]
        print(f"     energy decay -10/-20/-30 dB at " + "/".join(f"{m/SR*1000:.0f}" for m in marks) + " ms")
