# Rosetta S2000: what's possible (2026-10-13 dig)

The S2000 is a 32-voice sample-playback synth chip (L7A1045) with a 16M-word address space, a hardware
delay engine, per-voice resonant filter + envelopes, 8 individual outs, and a V53 we fully control.
Stock uses a fraction of it.

## Hardware facts that matter
- **Chip** (MAME l7a1045_l6028_dsp_a.cpp): per voice: 24-bit start/end, **RAM or ROM address space** (bit `s`),
  pitch 4.12 fixed (up to 16x), loop as length or **absolute loop-start address** (can be rewritten live),
  volume envelope (start/target/rate), resonant lowpass (16-bit cutoff, 4-bit reso, cutoff envelope
  target/rate; MAME models it as a Chamberlin SVF), L/R level, routing to 8 individual outs or the stereo
  pair, send to the delay engine. 8-point windowed-sinc interpolation. Second filter chip DFL (L7A0906)
  at ports 0xE0-0xE4 (still unknown).
- **RAM**: 72-pin SIMMs, 2 / 6 / 18 / 32 MB.
- **Flash**: two rear FMX008 slots (8 MB each, Akai). A hobbyist (tOri, reversing.pl) cloned it and made a
  16 MB FMX016: "their S2000 had 32 MB of flash". Clones are sold. The OS already has LOAD/FORMAT FLASHROM.
- **8 outs**: chip routing exists (keygroup "OUT Indiv"); the user's own DAC board replaces the IB-208P.
- **SCSI2SD** fitted: effectively unlimited disk.
- **Hidden in the OS**: an SMF song player (GLOBAL pages 17-22), MIDI via SCSI, the delay engine (now Rosetta FX).

## Step 0: code space
The menu blob is full (5.6 KB at 0x3EA00). Anything big needs a loader: at boot, read extra sectors from the
Rosetta disk into free CPU RAM (map free RAM with `s2k_ui.py memuse`), or reclaim the factory demo
songs/setups (user OK'd).

## Ideas, coolest-per-effort first
| # | Idea | How | Effort |
|---|---|---|---|
| 1 | **Shimmer / pitch-shift / harmonizer FX** | two sawtooth-swept, crossfaded delay taps (the chorus LFO code already does crossfaded taps); route the shifted tap back into the line = shimmer | small |
| 2 | **Freeze / live looper** | feedback 1.0 + voice sends off = the 1.49 s line loops forever; a button punches in/out | small |
| 3 | **Resonator** (Rings-lite) | short feedback taps tuned to the last MIDI note(s): plucked/bowed strings from any sample | small |
| 4 | **Unison / detune / supersaw, round-robin, velocity layers** | note-on hook (2B9D:016C): stack detuned voices, rotate zones per hit | small-med |
| 5 | **Arp / chord memory / tempo-synced echo** | note-on hook + the 2 ms tick, MIDI clock in | med |
| 6 | **Wavetable / transwave synth** | rewrite each voice's loop start from the tick (LFO, envelope, mod wheel): Ensoniq-style wave scanning through a sample; CPU-generated single cycles (saw/PWM/formant, U-110 waves) | med |
| 7 | **Filter LFO / filter FM / reso sweeps** | per-voice cutoff from the tick on top of the hardware envelope | small |
| 8 | **Auto-chop** (MPC) | after a take, find transients, make N keygroups across the keys | med |
| 9 | **Rompler browser** | wheel through a big SCSI2SD library by category, background load, instant audition; volumes built by akai_tool from WAV/SFZ/SF2 (incl. the user's own Roland wave ROMs) | med |
| 10 | **Flash rompler** | 2 x FMX016 (DIY or bought) = 32 MB of samples that need no loading (chip ROM space) + 32 MB RAM for sampling | hw + med |
| 11 | **Pad / pattern mode** | 16 pads from a MIDI controller, note repeat, swing, the SMF player grown into a pattern sequencer | big |
| 12 | **Stereo hold-to-record** | finish 0.17's stop-on-release for stereo takes | small |
