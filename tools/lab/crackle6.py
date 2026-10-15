import sys, time, mido, numpy as np, sounddevice as sd
sys.path.insert(0, r"C:\Users\JUNKSMITHWIZARD\Desktop\s2000_os\tools")
import s2kfx
lab = s2kfx.Lab(); SR = 44100
lab.select(0)
lab.out.send(mido.Message("program_change", program=4, channel=0)); time.sleep(0.8)
RNG = {66: (358, 66), 78: (298, 78), 90: (268, 90), 77: (298, 78), 79: (298, 78)}
for note, (n, root) in RNG.items():
    r = sd.rec(int(2.6 * SR), samplerate=SR, channels=2, device=s2kfx.AUDIO_IN, dtype="float32")
    time.sleep(0.2); lab.out.send(mido.Message("note_on", note=note, velocity=110))
    time.sleep(2.0); lab.out.send(mido.Message("note_off", note=note)); sd.wait()
    x = r[int(0.8 * SR):int(2.1 * SR), 0]; t = np.arange(len(x)) / SR
    X = np.abs(np.fft.rfft(x * np.hanning(len(x)))); fr = np.fft.rfftfreq(len(x), 1 / SR); f0 = fr[np.argmax(X)]
    best = None
    for f in np.linspace(f0 - 2, f0 + 2, 801):
        A = np.vstack([np.sin(2 * np.pi * f * t), np.cos(2 * np.pi * f * t)]).T
        c, res, _, _ = np.linalg.lstsq(A, x, rcond=None)
        if best is None or res[0] < best[0]: best = (res[0], f, c)
    _, f, c = best; amp = np.hypot(*c)
    rr = x - (c[0] * np.sin(2 * np.pi * f * t) + c[1] * np.cos(2 * np.pi * f * t))
    P = n / 2 ** ((note - root) / 12); nb = int(round(P))
    ph = ((np.arange(len(rr)) / P) % 1 * nb).astype(int)
    avg = np.array([rr[ph == b].mean() for b in range(nb)])
    exp = 440 * 2 ** ((note - 69) / 12)
    print(f"pitch {1200*np.log2(f/exp):+.2f} c |", end=" ")
    print(f"note {note}: residual {20*np.log10(np.std(rr)/np.std(x)):.1f} dB, loop glitch peak {np.abs(avg).max()/amp:.3f} x amp", flush=True)
lab.out.send(mido.Message("program_change", program=7, channel=0)); time.sleep(0.4)
lab.select(8); time.sleep(0.3)
print("set: prog", lab.peek(0, 0x758A, 1)[0], "fx", lab.peek(s2kfx.MENU_SEG, 0x12, 1)[0])
