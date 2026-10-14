# Akai S2000 Rosetta OS  (WIP)

<!-- mascot: docs/mascot/ (coming soon)
<p align="center"><img src="docs/mascot/MASCOT.png" width="260" alt="mascot art by JSW"></p>
-->

**New tricks for the Akai S2000 sampler.** Rosetta OS is a patch kit for the stock **OS 2.0**: you build a boot
floppy image from **your own** S2000 OS disk and boot it from a Gotek (FlashFloppy). It unlocks the voice chip's
hidden **delay engine** as 8 effects with their own EFFECTS page (no EB16 effects board needed), adds an
MPC-style home screen, and smooths out the menus. Nothing touches ROM or flash: boot your stock disk and it's
an S2000 again.

> **Made by JunkSmithWizard (JSW) together with Claude (Anthropic's AI).** Claude wrote the code and did the
> reverse engineering: NEC V53 disassembly, a whole-OS emulator, and the hidden delay engine measured over MIDI.
> JSW ran every build on a real S2000, built the measurement rig, and made the calls by ear.
> Same family as the [GP-16 Rosetta OS](https://github.com/yuyoi/super-Gp-16-Rosetta-OS), which the boot dragon comes from.

## Demo

**[Listen: rosetta_fx_demo.mp3](docs/demo/rosetta_fx_demo.mp3)** (0:58, recorded from a real S2000 running Rosetta 0.10)

> **⚠ AUDIO WARNING: turn your volume down first.** The test sounds are harsh: noise bursts and a 1 kHz beep.

- **0:00: noise burst, 3 hits per effect (~5 s each):** OFF, ROOM, HALL, PLATE, ECHO, PINGPONG, CHORUS, FLANGER.
- **0:42: 1 kHz beep:** OFF, CHORUS, FLANGER.

## What it adds

| Feature | Status |
|---|---|
| **Rosetta FX**: ROOM, HALL, PLATE, ECHO, PINGPONG, CHORUS, FLANGER on the voice chip's own delay engine | ✅ on hardware (0.10) |
| **EFFECTS page**: `>HALL >WET 50` / `>T100 >F100 >R100` (type, wet, time/size, feedback, LFO rate) | emulator ✅, hardware test next |
| **HOME hub**: main screen line 2 = `LOAD  HALL  EDIT`, the soft keys under the screen jump to LOAD and EDIT | emulator ✅, hardware test next |
| **Back one level**: the home key steps back (page → top of the mode → HOME) instead of always jumping home | emulator ✅, hardware test next |
| **Area menus**: EDIT PROGRAM (8 groups), EDIT SAMPLE (6) and GLOBAL (4) open a menu, essentials first. PAGE stays inside the group, GROUP jumps to the next one | EDIT PROGRAM ✅ on hardware (0.13), the rest emulator ✅ |
| **Sampling screen**: REC opens on the input meter with `SETUP        ARM` (stock hides it behind GROUP); a finished take lands on the sample select page | ✅ on hardware (0.16) |
| **REC = start/stop**: armed, hold REC to record while held, or tap to start and tap again to stop | emulator ✅, hardware test next |
| **PLAY always plays**: with no program active, PLAY and MIDI notes audition the current sample | ✅ on hardware |
| **LOAD / SAVE in one press**: skips "DISK or FLASHROM" when no flash ROM is fitted | ✅ on hardware |
| **Faster data-key repeat** | ✅ on hardware |
| **Boot dragon**: the GP-16 Rosetta animation on the LCD | ✅ on hardware |
| **FX lab**: poke/peek memory and the sound chip live from a PC over MIDI SysEx | ✅ on hardware |

## The hidden delay engine

The S2000's voice chip (L7A1045) has a delay engine built in: **one 65,536-sample line (~1.49 s at 44.1 kHz) and
30 taps**. Each tap has its own gain and a route: left out, right out, or back into the line (feedback). The stock
OS barely uses it: one preset for recording, plus a reverb-like preset that is never called.

We mapped it from a PC: Rosetta's SysEx backdoor writes taps, the PC fires a noise burst over MIDI and records
the outputs, and deconvolution shows every tap (`tools/irmeasure.py`). Delays land within 1 sample of the table.
Then:

- **Reverbs** are multi-tap feedback loops designed offline in a Python model of the engine (`tools/fxdesign.py`),
  with exact Q15 gains (the OS's own 8-bit levels halve the decay).
- **Chorus / flanger** sweep tap delays from an LFO every tick (0.51 ms). Two neighbouring taps crossfade for
  fractional delays, so the sweep is smooth with no clicks.
- **ECHO / PINGPONG** are plain taps plus feedback (375 ms echo, 300/600 ms ping-pong).

One delay line means no series allpasses, so the reverbs have a metallic, digital character. Cool, but there's
room to grow (modulated feedback taps are next).

## Using it

- **EFFECTS**: the first press opens the FX page; pressing it again picks the next effect.
  The two buttons under the screen move the `>`; the DATA wheel and the PAGE/GROUP keys change the value.
- **HOME** (main screen): line 2 shows `LOAD  <effect>  EDIT`. Left button under the screen = LOAD,
  right button = EDIT program.
- **Menus**: EDIT (program), REC → EDIT (sample) and TUNE (global) open a menu like `EDIT PROGRAM 1/8` /
  `>SAMPLES+ZONES`. DATA wheel or PAGE picks a group, the right button goes in, the left button goes out.
  Inside a group, PAGE loops through that group's pages and GROUP jumps to the next group.
- **REC**: opens on the input meter. Right button = ARM: the take starts when the sound passes the threshold,
  or press GO (left button) or REC to start now. **REC = start/stop**: hold it and the take stops when you let
  go; tap it and the take runs until you tap again (mono; the sample is cut to what was recorded, up to the
  SETUP length). Left button = SETUP (name, length, mono/stereo, pitch, threshold); home = back to
  the meter. After the take you land on the sample select page.
- **Home key**: back one level (page → menu → HOME).
- **PLAY**: auditions the current sample when no program is loaded.

## Quick start (build your own disk)

You need: your own S2000 **OS 2.0** floppy as a Teledisk `.td0` or raw 1.6 MB image, **Python 3.10+** with numpy,
**[NASM](https://www.nasm.us/)** on PATH (or `$NASM`), a Gotek with **FlashFloppy**, and one **HFE template**
of an Akai HD floppy (e.g. your stock OS disk converted with the HxC Floppy Emulator software; every sector
is overwritten, only its track layout is used).

```bash
python tools/td0.py s2kos2.td0 build/s2kos2.img
python -I tools/mkbaby.py build/s2kos2.img template.hfe build/S2K_ROSETTA
```

1. Copy `build/S2K_ROSETTA.hfe` to the Gotek's USB stick as `DSKA0000.hfe`, with `FF.CFG` set to `nav-mode = indexed`.
   Keep **one** image on the stick.
2. Boot the S2000 from the Gotek. The dragon flies, then the HOME screen.
3. The disk also carries a small **test kit** (CLICK, NOISE BURST, BEEP 1K) to LOAD from the same floppy.
   It's built with the akaitool package from [AKAI-CD-ISO-MAKER](https://github.com/yuyoi/AKAI-CD-ISO-MAKER)
   (clone it next to this repo or set `$AKAITOOL`), or set `TESTKIT=0` to leave it out.

Every patch checks the stock bytes first, so a wrong OS image fails loudly instead of building junk.

## Also in the box

- `tools/s2kfx.py`: the PC side of the **FX lab** (SysEx `F0 7D 53 ...`): `ping`, `peek`, `poke`, `outw`, `sel`
  (pick an effect), `load` (tap tables), `note`, `rec`. `tools/irmeasure.py` and `tools/demo.py` measure and record.
- `tools/s2k_emu.py` + `tools/s2k_ui.py`: a unicorn emulator that boots the real OS to the main screen and presses
  keys (`seq`, `fxcheck`, `pagewalk`, `isrcheck`, ...). Needs `unicorn` and `capstone`.
- `tools/x86dis.py`, `tools/sweep.py`: V53 disassembly helpers (code map, port map, xrefs).
- `tools/td0.py`, `tools/hfe.py`: Teledisk and HFE converters (HFE overlay with CRC check on read-back).
- `docs/FINDINGS.md`: the lab notebook (hardware map, code map, sound engine, build history).
- `docs/menu_design.md`: the menu redesign plan. `docs/pagewalk.txt`, `docs/ui_tree.txt`: stock UI maps.

## Status: work in progress 🚧

It boots and the FX work on a real S2000. Expect rough edges.

**Planned:**
- Quick jobs (load → audition → assign in a couple of presses).
- Per-program FX send, tempo-synced echo, denser and modulated reverbs.

Ideas, bug reports and test results are very welcome. Open an issue.

## Legal

Not affiliated with or endorsed by Akai Professional or inMusic. "Akai" and "S2000" are trademarks of their
owners. This repo contains **no Akai code or data**: you build from your own OS 2.0 disk, and the test-kit sounds
are synthesized. Build at your own risk; always keep your stock OS disk.

License: MIT (see `LICENSE`).

---

**Thanks for enjoying, and God bless you!** — JSW
