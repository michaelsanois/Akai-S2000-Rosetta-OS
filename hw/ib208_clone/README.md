# IB-208P clone: 8 individual outs for the S2000 (open source, no digital I/O)

The stock Akai IB-208P (S2000 / S3000XL; the MPC2000XL's IB-M208P is near identical) adds 8 individual analog outs.
No open clone exists. Akai's schematic is only in a service manual scan (S2000/S3000XL, IB-208P around page 61,
Akai part numbers, not values).

## From the service manual (2026-10-15)
`akai_s2000_s3000xl_s3200xl_eb16_ib-208p_service_manual.pdf` (Akai's, not in this repo: find it on Elektrotanya).
**PDF page 61** = "S3000XL 8 PARA/DIO, S2000 IB-208P (OPTION) schematic, L603602M". (Zoomed crops kept locally.)
The stock board is 8 outs + digital I/O (YM3623B receiver, CS8402A transmitter): the clone is the 8-out half only.

### Header WS01, 34 pins, to the main PCB's P13 (the user has the ribbon)
| Pin | Signal | Clone |
|---|---|---|
| 1, 2 | +5 V | DAC digital supply |
| 3, 4, 8, 10, 15, 17, 21, 26 | GND | digital ground |
| 5 PD, 6 MUTE, 7 YMLR, 9 INTYM, 11 SDATA, 12 SCLK, 13 PSYNC, 14 ADLR | digital I/O | leave open |
| **16** | **OPDETN** (option detect, active low) | tie as the stock board does (to GND: check the main-board side has a pull-up) |
| **18** | **8BTCK** bit clock | -> XOR gate (HC86, the other input tied) -> BTCKB -> every DAC's BCK + CLK |
| **19 / 20** | **LOUT / ROUT** serial data | HC244 buffer -> LOUTB / ROUTB -> every DAC (DR / DL) |
| **22 / 23** | **I01WCK / I23WCK** word clocks | HC244 buffer -> one DAC each; an HC86 XOR (other input +5 V) = the inverted clock for the other DAC of the pair |
| 24 BLRWCK, 25 XTAL | digital I/O clocks | leave open |
| 27, 28, 31, 32 | AG analog ground | op-amp / DAC analog ground |
| 29, 30 / 33, 34 | +12 V / -12 V | op-amps; a 7805 off +12 V = +5A, the DACs' analog supply |

### DACs: 4 x PCM69A (DIP-16 pin names as drawn)
DL 14 <- ROUTB, DR 10 <- LOUTB, WDCK 13 <- its word clock (I01, /I01, I23, /I23), BCK 11 + CLK 12 <- BTCKB,
+VDD 16 (+5 V), TP1 15, DG 9, AG 8, +VCC 1 (+5A), VCOML 2, IOUTL 3, SER(VO) 4, REF 5, IOUTR 6, VCOMR 7.
SER / REF / VCOM: 220 uF / 10 V-class caps as drawn (values readable on the page). All 4 DACs share the data
lines: each latches its own words on its own word-clock edge (time-multiplexed stream).
**Check your chips:** the D-70 notes were for PCM69AU (SOIC-20, mode pins MC1-3); the IB-208P uses the 16-pin
version with no mode pins. Same die, different pinout.

### Each output (x 8)
IOUT -> op-amp I/V (feedback 4.99 k-ish + small cap) -> active low-pass (1.91 k / 5.76 k, 470 pF / 0.01 uF) ->
balanced output stage (two op-amps, 10 k / 3.16 k network, 220 pF) -> 100 R -> 1/4" TRS jack J501-J508.
Op-amps drawn as "M5220"/"M5218"-class duals (Mitsubishi) on +-12 V; any good audio dual fits (user's call).
Component values: read them off the page (crop + zoom) when building each stage.

## Steps
1. Board out of the rack: find P13 on the main board (pin 1), confirm OPDETN's pull-up with a meter.
2. Ribbon + IDC breakout on vero. Scope pins 18 / 19 / 22 / 23 while a note plays on an individual out (EDIT
   PROGRAM: zone "Indiv"): clock rates, word rate, which word clock edge = which DAC.
3. Vero: HC244 + HC86 (or skip the HC244 on short wires), ONE PCM69A (outs 1-2) + the I/V and output stages. Listen.
4. Copy to 4 chips. Then mill the final PCB (same footprint / mounting as the IB-208P) once the CNC mill is built.

## Open
- Which DAC / word-clock edge maps to outs 1-8 (scope, or read the remaining labels on page 61).
- OPDETN on the stock board: to GND or through a part (zoom on its net).
- Rosetta: the voice chip routes per voice (reg 7 dest nibble); FX or live reverse to their own outs later.
