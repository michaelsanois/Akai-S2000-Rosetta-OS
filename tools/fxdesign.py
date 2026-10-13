"""Offline model of the L7A1045 delay engine (measured 2026-10-13 with irmeasure.py):
one 65536-sample line @ 44.1 kHz; 30 taps (fn1-10, 12-31); tap delay = len + 1 samples;
gain Q15 (int8 level x 0x28F, 50 ~ unity); route 1 = L out (OCTA in1), 0 = R out (in2), 2 = feedback.
Designs reverb tap sets, scores them, writes IR wavs + rosetta preset tables.
  py -3.10 fxdesign.py"""
import os, struct
import numpy as np
from scipy.signal import lfilter

SR = 44100
L, R, FB = 1, 0, 2


def render(taps, n=int(4 * SR)):
    """taps: list of (gain float, route, delay samples). Returns (irL, irR, line)."""
    fb = [(g, d) for g, r, d in taps if r == FB]
    line = np.zeros(n)
    line[0] = 1.0
    if fb:
        m = min(d for _, d in fb)                   # block recursion: each block only reads older blocks
        for t0 in range(1, n, m):
            t1 = min(n, t0 + m)
            for g, d in fb:
                lo = t0 - d
                if t1 - d > 0:
                    a0 = max(lo, 0)
                    line[t0 + (a0 - lo):t1] += g * line[a0:t1 - d]
    out = {L: np.zeros(n), R: np.zeros(n)}
    for g, r, d in taps:
        if r in out:
            out[r][d:] += g * line[:n - d]
    return out[L], out[R], line


def metrics(irL, irR):
    e = irL ** 2 + irR ** 2
    edc = np.cumsum(e[::-1])[::-1]
    edb = 10 * np.log10(edc / edc[0] + 1e-30)
    t20 = (np.argmax(edb < -25) - np.argmax(edb < -5)) / SR * 3       # RT60 from -5..-25
    # echo density (Abel): fraction of samples outside 1 std in 20 ms windows, normalised (1 = gaussian)
    w = int(0.02 * SR)
    dens = []
    for t0 in (int(0.05 * SR), int(0.1 * SR), int(0.2 * SR)):
        s = irL[t0:t0 + w]
        sd = s.std() + 1e-30
        dens.append(np.mean(np.abs(s) > sd) / 0.3173)
    # tail colouration: spectrum peak-to-median of 100-300 ms segment, 1/12 oct smoothed-ish
    seg = irL[int(0.1 * SR):int(0.4 * SR)]
    sp = np.abs(np.fft.rfft(seg, 1 << 15))
    f = np.fft.rfftfreq(1 << 15, 1 / SR)
    band = (f > 200) & (f < 8000)
    k = 25
    sm = np.convolve(sp[band] ** 2, np.ones(k) / k, "same")
    col = 10 * np.log10(sm.max() / np.median(sm))
    lo_e = np.sum(np.abs(np.fft.rfft(irL[int(0.2 * SR):int(1.0 * SR)], 1 << 16))[:int(150 * 65536 / SR)] ** 2)
    all_e = np.sum(np.abs(np.fft.rfft(irL[int(0.2 * SR):int(1.0 * SR)], 1 << 16)) ** 2) + 1e-30
    c = np.corrcoef(irL[int(0.05 * SR):int(0.5 * SR)], irR[int(0.05 * SR):int(0.5 * SR)])[0, 1]
    return dict(rt60=t20, dens=[round(d, 2) for d in dens], colour=round(col, 1), lrcorr=round(c, 2),
                peak=round(max(np.abs(irL).max(), np.abs(irR).max()), 2), boom=round(10 * np.log10(lo_e / all_e + 1e-12), 1))


def design(seed, nfb, fb_lo, fb_hi, loop, nout, out_lo, out_hi, out_gain, damp=1):
    rng = np.random.default_rng(seed)
    taps = []
    ds = np.sort(rng.integers(int(fb_lo * SR / 1000), int(fb_hi * SR / 1000), nfb))
    signs = rng.choice([-1, 1], nfb)
    w = rng.uniform(0.6, 1.0, nfb)
    w = w / w.sum() * loop
    for d, s, g in zip(ds, signs, w):
        if damp:                                    # adjacent pair = (1 + z^-damp)/2 lowpass in the loop
            taps += [(s * g / 2, FB, int(d)), (s * g / 2, FB, int(d) + damp)]
        else:
            taps.append((s * g, FB, int(d)))
    for r in (L, R):
        od = np.sort(rng.integers(int(out_lo * SR / 1000), int(out_hi * SR / 1000), nout))
        og = out_gain * rng.uniform(0.5, 1.0, nout) * rng.choice([-1, 1], nout)
        taps += [(float(g), r, int(d)) for g, d in zip(og, od)]
    return taps


def search(name, n_try, **kw):
    best = None
    for seed in range(n_try):
        t = design(seed, **kw)
        m = metrics(*render(t, int(2.5 * SR))[:2])
        score = m["colour"] - 4 * min(m["dens"]) + 3 * abs(m["lrcorr"])
        if best is None or score < best[0]:
            best = (score, seed, t, m)
    print(f"{name}: seed {best[1]} {best[3]}  taps {len(best[2])}")
    return best[2]


def to_table(taps):
    """30 taps -> 192-byte preset table (fn1-10, 12-31; fn11 kept as stock (0,0,65535))."""
    assert len(taps) <= 30
    t = bytearray(192)
    struct.pack_into("<bBHH", t, 66, 0, 0, 65535, 0)
    fns = [f for f in range(1, 32) if f != 11]
    for fn, (g, r, d) in zip(fns, taps):
        lvl = int(round(g * 50))
        assert -127 <= lvl <= 127 and d >= 2
        struct.pack_into("<bBHH", t, 6 * fn, lvl, r, d - 1, 0)
    return bytes(t)


if __name__ == "__main__":
    import soundfile as sf
    os.makedirs("rec/design", exist_ok=True)
    designs = {
        "room":  dict(n_try=300, nfb=7, fb_lo=23, fb_hi=61, loop=0.80, nout=8, out_lo=4, out_hi=45, out_gain=0.35),
        "hall":  dict(n_try=300, nfb=7, fb_lo=41, fb_hi=113, loop=0.88, nout=8, out_lo=11, out_hi=97, out_gain=0.3),
        "plate": dict(n_try=300, nfb=7, fb_lo=9, fb_hi=37, loop=0.86, nout=8, out_lo=1, out_hi=29, out_gain=0.3),
    }
    for nm, kw in designs.items():
        t = search(nm, **kw)
        iL, iR, _ = render(t)
        sf.write(f"rec/design/{nm}_ir.wav", np.stack([iL, iR], 1) / max(np.abs(iL).max(), np.abs(iR).max()), SR)
        open(f"rec/design/{nm}.bin", "wb").write(to_table(t))
