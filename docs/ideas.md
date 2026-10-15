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

### 0.18 hardware result (2026-10-13)
- The boot ROM loads a fixed 256 KB and ignores the bigger size field. The 4000:0000 peek showed power-up junk,
  not "ROSETTA HI", and the 3EA0 jump table read back fine. 0x40000-0x4FFFF is never written on hw: 64 KB free.
- **Plan: a runtime loader.** OS raw floppy read = far call `1F50:00BB`: CL = cyl, DH = head, DL = sector (1-based),
  CH = N (3 = 1 KB), BX = bytes, ES:BP = destination, AL = 0 on success. It stays on one track (split the read
  per track), sets its own error frame ([8063]), skips the Akai directory read ([8060] bit 0x40), and has a
  ~4.4 s motor spin-up on first access (0FE4:A63B `cmp al,9`; Gotek could use less). Block b = cyl b/20,
  head (b%20)/10, sector b%10+1.
- Loader home: free junk 0x3E01B-0x3E200 (480 B, before the dragon), e.g. LOAD_SEG 0x3E02. It's called from
  lfo_hook (`call LOAD_SEG:0`, 5 B, first tick loads; state 0/1/2/3), checks a magic at 4000:0000, then calls hi
  init/tick. Popup text must sit in segment 0 (copy it to 0:8FE0, then `call 0FE4:0D4E` = timed popup, DS = 0).
- The dragon area (0x3E200 + 550 B .. stack) is also free after boot: ~1.7 KB more lo space overall.
- FDC: IR3 = int 0x0B = 0000:80F2 (`or [8060],20h`), unmasked by 2345:09BF. DMA ch1 = C001/C004/C006/C002.
- Emulator: tools/s2k_emu.py takes a disk image (env S2K_DISK, s2k_ui uses the .img next to the .bin): read data via DMA ch1
  + IR3, sense interrupt with nothing pending = ready change (the OS reads 2 bytes). With a disk the OS reads the
  catalogue at boot. 0.19 (emulator PASS): the loader reads the hi code, READY popup, hi tick runs, menus OK.

## Roadmap from the user (2026-10-15)
- **MULTI = SYNTH** (stock multi mode not used). A top menu with arrows into the synth modes:
  - **ANALOG** (0.26): one-screen editing of the current program's keygroups (wave on ROSETTA ROM programs,
    filter, resonance, key track, filter env, amp env, drift / detune / LFO), on any program.
  - **FAKE FM**: 2-op FM single cycles precomputed per modulation index (a frame table), the index knob picks
    the frame; later swept from the tick (loop start per voice) for real FM-like movement.
  - **WAVETABLE**: frame tables (morphs, formants, PWM) scanned by moving each voice's loop through the table (#6).
- **SAMPLE** gets the same kind of menu: **LOOPER** (#2 freeze + overdub), **MPC** (pads + auto-chop, #8 / #11),
  **KEYBOARD** (the stock sampling + map the take across the keys).

## Ideas, coolest-per-effort first
| # | Idea | How | Effort |
|---|---|---|---|
| 1 | **Shimmer / pitch-shift / harmonizer FX** | two sawtooth-swept, crossfaded delay taps (the chorus LFO code already does crossfaded taps); route the shifted tap back into the line = shimmer | small |
| 2 | **Freeze / live looper** | feedback 1.0 + voice sends off = the 1.49 s line loops forever; a button punches in/out | small |
| 3 | **Resonator** (Rings-lite) | short feedback taps tuned to the last MIDI note(s): plucked/bowed strings from any sample | small |
| 4 | **Unison / detune / supersaw, round-robin, velocity layers** | note-on hook (2B9D:016C): stack detuned voices, rotate zones per hit | small-med |
| 5 | **Arp / chord memory / tempo-synced echo** | note-on hook + the 0.51 ms tick, MIDI clock in | med |
| 6 | **Wavetable / transwave synth** | rewrite each voice's loop start from the tick (LFO, envelope, mod wheel): Ensoniq-style wave scanning through a sample; CPU-generated single cycles (saw/PWM/formant, U-110 waves) | med |
| 7 | **Filter LFO / filter FM / reso sweeps** | per-voice cutoff from the tick on top of the hardware envelope | small |
| 8 | **Auto-chop** (MPC) | after a take, find transients, make N keygroups across the keys | med |
| 9 | **Rompler browser** | wheel through a big SCSI2SD library by category, background load, instant audition; volumes built by akai_tool from WAV/SFZ/SF2 (incl. the user's own Roland wave ROMs) | med |
| 10 | **Flash rompler** | 2 x FMX016 (DIY or bought) = 32 MB of samples that need no loading (chip ROM space) + 32 MB RAM for sampling | hw + med |
| 11 | **Pad / pattern mode** | 16 pads from a MIDI controller, note repeat, swing, the SMF player grown into a pattern sequencer | big |
| 12 | **Stereo hold-to-record** | finish 0.17's stop-on-release for stereo takes | small |

## Synth layer (user, 2026-10-13: "we don't need many true voices, fake LA, fake analog, wavetable with a
## software backend so it's easy to sequence")
Principle: the PC does the heavy DSP offline (render waves, tables, multisamples), the S2000 plays them with
its 8-point sinc voices, and Rosetta moves the voice registers live from the 0.51 ms tick. 1 note = 1 voice
wherever possible.

| Idea | How (1 voice unless said) |
|---|---|
| **Fake LA** (D-50/D-110 style) | one sample = PCM attack spliced onto a single-cycle loop; chip filter env = TVF sweep. Attacks from the user's own D-110/U-110 dumps (personal use) |
| **Fake analog** | single-cycle saw/square/tri; random pitch drift + per-note detune from the tick; chip resonant LP + env; PWM = a scanned PWM table |
| **Wavetable** | table = N single cycles in a row; position = the voice's loop-start address, moved by LFO / env / velocity / mod wheel / CC (PPG-style steps) |
| **Wave sequencing** (Wavestation) | per note, step the start/loop through a list of waves over time |
| **Vector** (Prophet VS) | 4 voices per note, levels from a CC x/y |
| **Granular** | short loops with jittered start addresses, voices as grains |
| **Unison / supersaw** | 2-4 detuned voices, pan spread (costs voices: use for pads) |
| **Auto-sampler** (PC) | MIDI notes out to any synth (D-110, U-110, GP-16, softsynths), record via the OCTA, trim/loop, build Akai programs (akai_tool) -> SCSI2SD |
| **Wave lab** (PC) | draw/import/additive/FM-render single cycles and tables, send over SysEx or a disk image |
| **Easy to sequence** | every synth/FX param on a MIDI CC (NRPN for fine), program change = instant patch, MIDI clock sync for LFOs/arp/echo; PC editor over SysEx; Cubase bridge integration |
| **SYNTH tab** | a new area menu per program: OSC (wave/table/pos), FILTER (cutoff/reso/env/LFO), AMP, MOD (LFO/env -> pos/pitch/cutoff), UNISON, FX send |

### 0.20/0.21 on hw (2026-10-14)
- 0.19 loader CONFIRMED ("it loaded"). 0.20 SYNTH basics measured over MIDI + OCTA (BEEP 1K / NOISE BURST notes):
  DETUNE 127 = +19.3 c, 64 = +9.3 c on the audition voice (31); DRIFT 127/127 wanders -15..+13 c; all CCs 0 =
  exactly 1000.00 Hz, so untouched. 0.21 filter LFO (dips from the set cutoff, depth x16) sweeps NOISE highs from
  +13 dB down to -15 dB (64) / -24 dB (127). An open filter's top ~800 log steps are inaudible.
- **The OS tick [73DA] is 0.511 ms on hw (1957 Hz), not 2.04 ms.** Rescaled the hi timing. To check: rosetta_rec's
  eat window (120 ticks = 61 ms, meant as ~0.3 s), and the FX LFO and data-key repeat values were tuned by ear.
- tools/hiload.py hot-loads build/rosetta_hi.bin into a running S2000 over SysEx (no reboot): parks the loader tick,
  uploads, re-points the OS hooks (header slots +C/+F/+12), and the new blob's tick re-runs `apply`.

## SP-404 MKII FX on our engine (2026-10-15, list from memory)
Three paths: **TAPS** = the voice chip's delay line (1.49 s, 30 taps, gain/route/feedback, delays + gains moved
every 0.51 ms tick; zero latency). **CHUNK** = the live-reverse ring (CPU copies chunks to sample RAM, plays them
on voices with pitch / LP filter / envelope; ~12 ms latency; the CPU can touch every sample while copying:
clip, bit mask, sample-and-hold). **EB** = needs real per-sample DSP (smart EB board).

| SP-404 FX | Path | How |
|---|---|---|
| Sync Delay, Tape Echo, TimeCtrlDly, DJFX Delay, SX Delay, Ko-Da-Ma | TAPS | BPM taps + FB; tape = LFO wow on the tap |
| Reverb, SX Reverb | TAPS (have) | metallic until the EB |
| Chorus, JUNO Chorus, Flanger | TAPS (have chorus/flanger) | Juno = 2 taps, triangle LFO, opposite phase L/R |
| Tremolo / Pan, Slicer | TAPS | tap gain LFO / BPM gate pattern |
| Resonator, Hyper-Reso | TAPS | short tap + high FB = comb at a pitch; Hyper = pitch quantized to a scale |
| Ha-Dou, Zan-Zou, Cloud Delay | TAPS | modulated diffused taps (approximations) |
| DJFX Looper, Scatter, Stopper | CHUNK (half there: STR/END) | loop / shuffle / reverse slices of the ring |
| Downer, Back Spin | CHUNK | pitch envelope down on the chunk voice / reverse + pitch ramp |
| Chromatic PS, Harmony, Auto Pitch (crude) | CHUNK | crossfaded chunks at a new pitch: grainy, Auto Pitch needs pitch detect = weak |
| Lo-fi, Crusher | CHUNK | bit mask + sample-and-hold while copying |
| Overdrive, Distortion, WrmSaturator | CHUNK | gain + clip while copying (crude) |
| Wah, Filter+Drive, Super Filter (LP only) | CHUNK | the voice's resonant LP + LFO/env; no HP/BP |
| Compressor | CHUNK (have CMP) | per-chunk leveling, not a real comp |
| Cassette / 303 / 404 VinylSim | TAPS + CHUNK | wow on taps + a crackle/hiss sample voice + LP |
| Isolator, Equalizer, Phaser, Ring Mod, Vocoder, Gt Amp Sim | EB | need per-sample filters / multiplies |

### OG SP-404 (2005, 29 FX) extras the MKII table misses (user meant the OG; full OG list not found online,
### partly from memory)
| OG FX | Path | How |
|---|---|---|
| **Subsonic** | CHUNK peak + rompler | input peak over a threshold triggers an RS SINE voice (pitch + decay knobs): an 808-ish sub under the kick |
| **BPM Looper** | CHUNK | the DJFX Looper locked to BPM + DIV (live reverse already has both) |
| Center Cancel | CHUNK (maybe) | L-R while copying; only if both input channels reach the ring |
| Radio Tuning | TAPS + CHUNK, crude | hiss voice + LP + wobbling detune |
| Voice Transformer | EB | pitch + formant shift |
