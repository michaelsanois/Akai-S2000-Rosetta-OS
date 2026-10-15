# Smart EB: our own board in the S2000's EB16 slot (idea, 2026-10-15)

The EB16 (service manual PDF page 74, the same Akai manual as `../ib208_clone`) = Akai FX LSI L7A1414
+ 3 x uPD431000 SRAM on a 44-pin header P1 (to the main PCB). Ours: a small MCU board in its place, digital FX
controlled by Rosetta over the CPU bus. **No analog filter here** (one shared bus filter = paraphonic, rejected by
the user); per-voice analog filters belong on the 8 outs (`../ib208_clone/`).

## Slot signals (P1, from the schematic; pin numbers to confirm on a zoomed crop)
- Audio in (the voices' FX sends): U0IN, U1IN + MCK, USYNC (serial).
- Audio out (FX return into the mix): F0OUT, F1OUT.
- CPU bus: D0-D15, A1-A4, IORB / IOWB strobes, NFCS / FXCS / NSCS chip selects, FXRDY (wait), RST.
- VCC, GND, FXP.

## Brain options
| Option | Bus | DSP / RAM |
|---|---|---|
| RP2350 + PSRAM (Pico 2 class) | PIO answers the bus | FPU, 520 KB + 8 MB PSRAM: best single chip |
| ESP32-S3 (N8R8) + 74HC574 latch / 74HC541 buffer | latches (it can't answer the bus in time) | 240 MHz x2, 8 MB PSRAM |
| RP2040 (bus + stream glue) + ESP32-S3 (DSP) over I2S | PIO | ESP |
The S2000 bus is **5 V**: MCU pins are 3.3 V, so the latch / buffer chips are 74HCT / 74LVC parts that also shift
levels. Board can be tiny (grape size) apart from the 44-pin header.

## Capabilities (RP2350 or S3)
Looper (~45 s stereo / 8 MB, overdub, reverse, half speed, freeze), live reverse without the 12 ms lag or the
S2000's CPU, one good FDN / plate reverb + delays / shimmer / pitch shift, light granular. Parameters from
Rosetta pages over the bus.

## WiFi (user, 2026-10-15): screen out, remote panel, sample transfer
- Screen: the slot can't see the LCD (ports 60h / 62h are elsewhere): Rosetta hooks the OS's HD44780 writes and
  copies the 32 chars to the board on change. ESP32-S3 serves a web page with the 2x16 screen.
- Remote panel: web buttons / wheel -> board register -> Rosetta injects key events ([73D4], wheel [73A5], rocker
  [73A4]).
- WAV upload in the browser -> board -> Rosetta writes it into sample RAM + a sample header.
- WiFi bursts vs real-time DSP on one chip = glitch risk. **Parts on hand: RP2040 + ESP32-S3 (no RP2350).** Split:
  RP2040 = bus (PIO) + stream format + the latency-critical, small-RAM FX (live reverse, short delays);
  ESP32-S3 = looper / reverb in PSRAM on core 1 (audio buffers in internal SRAM), WiFi / web on core 0.
  RP2040 <-> S3 by I2S (audio) + SPI/UART (control). Test WiFi + DSP together early.
- **Decision (user):** WiFi = an EDIT mode only, switched on from a Rosetta page; off while playing. Glitches and
  RF noise in the analog outs only matter while it's on, and editing / sample upload don't care.

## Order
1. The 8-out board first: its scope capture tells the S2000's serial audio format.
2. Pass-through (send -> return), 3. bus registers (Rosetta pokes, board answers), 4. looper / reverse.
5. Rosetta's own pages move off the "EB16 not present" slot when the board reports itself.
