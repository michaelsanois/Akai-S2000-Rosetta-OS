# Crackle hunt: moving delay taps (QUEUED, multi-session, after the SP-808 push)

User, 2026-10-15: "worth chasing", as a multi-session hunt. State at park time: build 0.27 (local commits up to
f0e78d0) is on the stick; RS PAD + JUNO crackles "in and out", stronger at times.

## Solved on the way (keep)
- **Rompler seam clicks** (FX OFF): the chip's interpolator reads 6-9 samples past a loop end and a few before the
  loop start after the jump. ROSETTA ROM now stores PRE 32 | loop | GUARD 64 (tools/rompler.py). Sine at root:
  glitch 0.6 -> 0.003 x amp. See FINDINGS "Loops need the wave on both sides".
- **Tap pair write order** (src/rosetta_fx.asm lfo_run): lengths first, then both gains back to back under cli.
  Cut the spike count about in half, not to zero.

## Still open: every LFO type clicks on held chords (CHORUS, FLANGER, JUNO, TAPE); static ones (ECHO) don't
Metric: LPC-residual kurtosis + >8 sd spikes on a held RS PAD chord 36+43 (tools/lab/padtest*.py). OFF / ECHO
kurt ~6-20; LFO types 200-1700. A simulated ideal chorus (even with 3.9 ms update steps) scores LOWER than dry,
so the spikes are real chip behaviour, not the meter.

| Test (hw, LFO frozen unless noted) | Clicks? |
|---|---|
| LFO frozen (nmods 0), any crossfade position (inc 0) | no |
| Same values rewritten every main-loop pass (depth 0) | no |
| One tap: gain step 1 LSB / 16 LSB / 2 % (SysEx rate, ~8/s) | no |
| One tap: gain step 50 % / to 0 | yes (normal: a big level step) |
| One tap: delay +-1 / +-2 samples at full gain | no |
| One tap: delay +-8 samples | some |
| Engine running, depth only +-4 samples at 0.5 Hz | **yes** (~30/s) |
| Clicks fall on the ~3.9 ms update grid, 1-2 sample blips | |

The model says a slow crossfade (tiny gain steps, a 2-sample move only at ~0 gain) is smooth, and the chip
disagrees. Nothing tested alone reproduces it at SysEx rate.

## Plan
1. Hot-load (tools/hiload.py) a hi-code lab routine that replays lfo_run's exact pair writes per main-loop pass with
   switches: gains only (fixed lengths) / lengths only / both; pair vs single tap; with / without cli.
2. Capture one click at sample resolution with a sine (not saws), find which write precedes it (log TICK +
   the chip's delay position, fn 0, around each write).
3. Suspects: the chip latches a length write late (e.g. at its own block boundary) while gains apply at once;
   a gain write hitting mid-sample; the even/odd role swap at a parity change; the sum of the pair's Q15 gains
   not being linear in the chip (log / float gain format would make the crossfade dip).
4. Fallbacks if the chip can't move taps cleanly: move only while the tap's gain is 0 (two pairs, ping-pong
   handover) or modulate gains only (fixed delays, amplitude crossfade between 3-4 static taps).

## Notes
- **Never poke lo/hi addresses from an old build**: the lab scripts read them from build/lo_syms.inc and
  rosetta_hi.map at run time (tools/lab/labsym.py). A stale `nmods` poke hung the S2000 once (2026-10-15).
- Test notes go out over the OCTA MIDI at normal level; warn the user first.
