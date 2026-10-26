# IB-208P clone: lean analog section (plan, 2026-10-26)

User: keep the 4 PCM69AP, cut the analog section down. Stock values: `ROUTING_PREP.md` (read off page 61).

## Verdict
- **Keep:** I/V + the Sallen-Key. Together they set the frequency response (I/V pole 14.5 kHz + SK 22 kHz Q 2 =
  a steep top end that also covers the NOS droop). Changing them changes the sound.
- **Cut:** the output diff amp + the sleeve network (3.16 k / 10 k matched pairs, 220 pF, 47 R, 10 nF, 1 nF).
  That's the fiddly half: ~10 parts per out, 1 % matching, and it only buys +10 dB of gain and ground-loop cancelling.
- **Result:** 1 dual op-amp per out (A = I/V, B = filter) = **8 duals**, about **9 parts per out instead of ~19**,
  the same response as stock. Unbalanced out (what most mixer setups use anyway).

## Per out (x 8)
```
DAC IOUT (pin 3 L / 6 R) --+-- Rf 4.99k --+--+
                           +-- Cf 2.2n  --+  |
                           |                 |
                         (-)A               |
DAC VCOM (pin 2 / 7) --+-(+)A   outA ------+-- R 1.91k --+-- R 5.76k --+-- (+)B
                       |                                  |             |
                     100u/10 to AG                    C 10n to outB   470p to AG
                                                         (-)B = outB (unity)
outB -- 47u/16 (+ toward outB) --+-- 100R -- jack TIP
                                 +-- 100k to AG (bleeds the cap, no pop on plug-in)
jack SLEEVE -- AG (one wire, straight to the AG bus)
```
- outA idles at VCOM (DC), so the 47 uF coupling cap stays (stock C571).
- Op-amp: socketed DIP-8 dual (NE5532 to start; LM4562 / OPA2134 / M5220 to compare). 100 nF + 47 nF at the
  supply pins, short feedback.

## Level (the cut drops the stock +10 dB)
1. Build out 1 stock-lean as drawn. Play a full-scale sine, scope outA: note the peak swing.
2. If you want more level: raise Rf and lower Cf by the same factor (keep Rf x Cf = 11 us, the pole stays put),
   e.g. **10 k + 1.1 nF = +6 dB**. Keep outA peaks under ~+-10 V on +-12 V rails.
3. Or leave it: the mixer's gain makes up 10 dB easily.

## Parts per DAC (2 outs) vs stock
| | Stock | Lean |
|---|---|---|
| Op-amp halves | 6 | 4 (2 duals) |
| Resistors | 2x(4.99k, 1.91k, 5.76k, 3.16k x2, 10k x2, 100R, 47R) = 18 | 2x(Rf, 1.91k, 5.76k, 100R, 100k) = 10 |
| Caps | 2x(2.2n, 100u, 10n, 470p, 47u, 220p x2, 1n, 10n) = 18 | 2x(2.2n, 100u, 10n, 470p, 47u) = 10 |

DAC support parts stay as stock (SER / REF 220 uF, VDD 47 nF, TP1 10 uF, VCC 10 uF, the 7805 for +5A).

## Order
1. Scope the stream (README step 2), one DAC + 2 outs on the vero as above.
2. Listen against the main stereo out; check the level, hum (unbalanced into your mixer), the top end.
3. If hum shows up on some setups: add the stock diff amp back on just those outs (the second dual), or use a
   DI / balanced input on the mixer side.
4. Copy x4. The milled boards (ROUTING_PREP.md) then need 8 DIP-8 duals instead of 6 TL074 quads.
