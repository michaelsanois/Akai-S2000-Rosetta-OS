# IB-208P clone: op-amp options for the PCM69 analog section (2026-10-26)

Source: Burr-Brown PCM67/69A datasheet (PDS-1168A). Stock values: `ROUTING_PREP.md`. Lean plan: `ANALOG_LEAN.md`.

## What the PCM69A hands the analog side (datasheet)
- **Current output, 0 to 1.2 mA** per channel, silence (bipolar zero) = 0.6 mA. Output impedance **1.8 k (+-30 %)**.
- **VCOM 3.5 V** (3.35-3.65): the I/V op-amp's (+) input sits there, so the I/V output rides on +3.5 V DC
  -> a coupling cap after the analog chain (stock 47 uF), or the datasheet's offset-current trick (Fig. 7) to
  centre it on 0 V.
- Full scale with Rf 4.99 k = **6 V p-p = 2.1 V RMS** at the I/V output.
- **It's a hybrid: 10-bit conventional DAC + an "advanced 1-bit" noise-shaped part** clocked by the system clock
  (pin 12, = the bit clock here). The 1-bit part's shaped noise sits above the audio band, which is one more
  reason to keep a real low-pass (not just the I/V pole). Clean, short bit-clock wiring matters (jitter).
- Specs: idle-channel SNR 110 dB, dynamic range 106 dB, THD 0.0025 % (-92 dB) F/S. Real-world floor: the
  S2000's 16-bit samples (~96 dB) sit above all of this anyway.
- Burr-Brown's own HiFi application circuit: **OPA2604 or NE5532** for I/V + filter; their THD test rig uses OPA627.

## Noise at the I/V output (the stage that matters)
The DAC's 1.8 k output impedance makes the I/V noise gain 1 + 4.99 k / 1.8 k = **3.8**, so the op-amp's voltage
noise counts x3.8. Rf (9.1 nV) and the DAC's 1.8 k (15 nV at the output, if resistive) are fixed.

| I/V op-amp | en (nV/rtHz) | Total at output | SNR vs 2.1 V RMS, 20 kHz BW |
|---|---|---|---|
| LM4562 / LME49720 | 2.7 (in 1.6 pA) | 22 nV/rtHz | **117 dB** |
| NE5532 | 5 (in 0.7 pA) | 26 | **115 dB** |
| OPA2134 | 8 (FET) | 35 | **113 dB** |
| OPA2604 | 10 (FET) | 42 | **111 dB** |
| TL072 / TL074 | 18 (FET) | 70 | **107 dB** (eats into the DAC's 106-110 dB) |
| M5218 / M5220 | (datasheet not checked) | | stock reference |

**Takeaway:** anything from the NE5532 class up is well below the DAC; only TL07x in the I/V spot costs real noise.
The filter and output stages run at gain ~1 with small resistors: their noise is negligible with any of these.

## By stage
| Stage | Job | Pick | Why |
|---|---|---|---|
| I/V | catch the DAC's current steps, Rf 4.99 k // Cf 2.2 nF | **LM4562** (55 MHz, 20 V/us) or **NE5532** (10 MHz, 9 V/us); OPA2604 / OPA2134 for the FET sound | low en (x3.8 gain), fast enough for the steps (Cf soaks most of them) |
| Sallen-Key (unity, Q 2, 22 kHz) | low-pass, flattens the I/V pole's droop | **NE5532** / LM4562 | unity-gain stable, low common-mode distortion as a follower |
| Output (stock diff amp, optional) | drive the cable, cancel ground loops | **NE5532** / LM4562 | strong into low loads / long cables |

Slew needed is tiny (full-scale 20 kHz at 3 V peak = 0.4 V/us): every part above has 20x margin.

## Topologies, ranked
1. **Lean = I/V + Sallen-Key, unbalanced** (`ANALOG_LEAN.md`): 1 dual per out (8 duals), stock frequency
   response, ~9 parts per out. **Recommended.**
2. **Stock** (+ diff output): 12 duals, +10 dB and ground-loop cancelling, ~19 parts per out with 1 % matching.
   Only if long cables / hum in your setup demand it (can be added per out later).
3. **I/V + passive RC only** (1 half per out): weak. Without the Sallen-Key's Q 2 lift the I/V pole droops the top
   end (-4.6 dB at 20 kHz from the pole alone), and the 1-bit part's ultrasonic noise gets through. Not worth the
   saved op-amp half.
4. **DC-coupled (datasheet Fig. 7 offset current, Rf ~5 k, centred on 0 V):** removes the 47 uF coupling caps from
   the signal path. Costs an offset trim / drift and a thump at power-on into whatever's plugged in. An option on top
   of #1 if you want no electrolytics in the path (or use a 4.7-10 uF film cap + 100 k bleed instead).

## Starting build (first DAC, outs 1-2)
- Sockets everywhere. I/V: NE5532 first, then roll LM4562 / OPA2604 / M5220 and listen.
- Filter: NE5532. Coupling: 47 uF stock (or a film cap). No diff amp.
- Decoupling: 100 nF + 47 nF at each op-amp, DAC pins as stock (SER / REF 220 uF, VCC / TP1 10 uF, VDD 47 nF).
