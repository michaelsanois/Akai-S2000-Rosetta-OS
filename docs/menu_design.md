# Rosetta menu redesign

Goal (the user, 2026-10-13): submenus, essentials first, fewer combos, always know where you are.
MPC ideas wanted: home-screen hub, EXIT = back one level, quick jobs. First target: the home screen.

## What stock does (emulator page walk, build/pagewalk.txt)
- Keys: PAGE ◀▶ = r1c0/r0c0 (one page), GROUP ◀▶ = r5c0/r4c0 (next block), 2 soft keys under the LCD
  (r2c1/r5c1), EDIT (r0c1) flips the mode to its edit twin (SINGLE↔EDIT PROG, REC↔EDIT SAMPLE,
  MULTI↔EDIT MULTI, EFFECTS↔EDIT FX), DATA wheel, PLAY.
- EDIT PROGRAM = one flat list of 85+ pages: program (Pnum, MIDI ch, poly, xfade, legato, tune,
  transpose, OUT/PAN mods), then per keygroup: count/span/mute/xfade, ZONE1-4 × 8 pages, ENV1, AMP MOD,
  FILTER + 3 mods, ENV2 × 6, PITCH mods.
- MULTI 9 pages, REC 4, TUNE/GLOBAL 26 (tune, output level, MIDI, SCSI, format, a hidden SMF song player,
  MIDI via SCSI, sysex channel). LOAD/SAVE already shortened by Rosetta 0.06.

## Principle: a navigation layer on top of the stock pages
All editing stays stock (every page, value and range works as before). Rosetta adds:
1. **HOME** hub (replaces main page 0).
2. **Menus** per area: a list of groups, essentials first. Picking one jumps to that group's stock pages;
   PAGE ◀▶ stays inside the group (wraps), so no more scrolling 85 pages.
3. **EXIT = back one level**: page → group menu → area menu → HOME.
4. **Breadcrumb flash**: entering a group shows `PROG>FILTER` for ~0.4 s, then the stock page.

## HOME (16 × 2)
```
P36 ROSETTA KIT       line 1: program no. + name (DATA wheel = program, as stock)
LOAD  HALL    EDIT    line 2: soft L = quick LOAD, middle = status card, soft R = EDIT menu
```
- Status card (SELECT/PAGE ◀▶ on HOME cycles it): FX type+wet · current sample · MIDI ch · voices
  playing · free memory.
- PLAY auditions the current sample when no program is active (0.08), else plays the program.

## EDIT PROGRAM menu (essentials first)
```
EDIT PROG    1/8
>SAMPLES & ZONES      DATA / PAGE: move, soft R: enter, EXIT: back to HOME
```
1. SAMPLES & ZONES (zone assign, level/pan, tune per zone)
2. AMP ENVELOPE (ENV1 ADSR + hold, velocity)
3. FILTER (freq/reso, key track, mods, ENV2)
4. PITCH (tune, transpose, pitch mods, LFO1)
5. OUTPUT (loud/vel, pan, indiv out, FX send)
6. KEYGROUPS (count, span, mute group, xfade)
7. PROGRAM (number, MIDI ch, polyphony, priority, mono/legato)
8. MODULATION (OUT/PAN/AMP mods, LFOs)

Same pattern later for SAMPLE (record / trim+loop / name), MULTI (parts), GLOBAL (MIDI · disk/SCSI ·
song player · system) and FX (0.11 page).

## Quick jobs (v1)
- HOME soft L **LOAD**: straight into the disk browser (no DISK/FLOPPY questions when there's one choice).
- After a load: PLAY auditions the newest sample.
- Later: "audition → assign to key/pad" in two presses.

## Built (emulator-tested)
- **0.12 = M1**: HOME line 2 `LOAD  <fx>  EDIT`, soft keys = LOAD / EDIT, home key = back one level.
- **0.13 = M2**: EDIT opens `EDIT PROGRAM n/8` + `>GROUP` (on the FX page slot, mode 6 page 0x0C).
  Wheel / PAGE / GROUP pick, right soft key = in, left soft key / home / EDIT = out.
  Groups (stock pages): SAMPLES+ZONES 22-53, AMP ENVELOPE 54-59, FILTER+ENV2 60-70,
  PITCH+BEND 6-7 + 96-98, OUTPUT 8-16, KEYGROUPS 17-21, PROGRAM 0-5, MODS+LFO 84-95.
  Inside: PAGE wraps within the group (two-range groups jump A -> B -> A), GROUP = next/prev group,
  home = back to the menu. Hidden stock pages (10-11, 21, empty zones, 71-83) are skipped by the stock step.
- Code moved to MENU_SEG 0x3EA0 (0x3EA00-0x3FFFF, 5.5 KB) in 0.13.
- **0.14 = M3**: one menu engine, three areas (tables `a_*` / `g_*` in src/rosetta_prog.asm):
  - EDIT SAMPLE (REC then EDIT) `EDIT SAMPLE n/6`: SAMPLE+PITCH 0-4, TRIM 6-7, LOOP 8-13,
    NORM+REV+FADE 5 + 14-16, RESAMPLE 17-19, TIMESTRETCH 20-24. Out = back to REC.
  - GLOBAL (TUNE key) `GLOBAL n/4`: TUNE+LEVEL 0-1, MIDI 2-5 + 26, DISK+SCSI 6-7 + 24-25,
    SONG PLAYER 17-22. Out = HOME.
  - The selection is remembered per area. EDIT MULTI (9 pages) stays stock.
- **Sampling screen (M3b, user-picked "quick" version)**: REC opens on the stock record page (mode 4 page 5,
  normally hidden behind GROUP): input meter + `SETUP        ARM`. Left = SETUP (REC pages 0-4: name,
  length+B/W, start+mono/stereo, orig pitch, threshold), home = back to the meter, home again = HOME.
  Stock record flow (emulator trace): ARM -> `About to record / GO  EXIT` = ARMED (loop 0FE4:3A98: the
  threshold starts the take, GO = left key starts now (3ABD -> 3AFD), EXIT = right key) -> `RECORDING analog /
  ABORT` = the take is running (loop 0FE4:3B13, ends when [7A7C] reaches 16 = the 16-step progress bar).
  0.16: the REC key in the armed loop = GO (hook 3AA0) - hardware OK. A probe (hook 3B2C, removed in 0.17)
  logged a 5 s mono take: [7508] = 220500 samples, [753D] = start 0x18AE0, [87BA] = length + 1, [7A68..7A6C]
  = DMA bytes per 1/16 step (27562.5 = 2 bytes x 220500 / 16), [7A7C] = step 1..16 (~98 ticks each),
  [7A74..76] = DMA ring target (16.16), [7A64] stays the start. Each step (2345:2781) waits on the record DMA
  (channel 2, current address port C004, ring 0:90D0 of 0x2000 bytes) in 2345:27EB `call 27F8`; 2345:2819
  bumps [7A7C]; at 16 the loop ends, 0FE4:3B77 stops the chip and builds the sample from [87BA].
  0.17 = REC key start/stop (hook 2345:27EB, src/rosetta_rec.asm): held = stops on release, tapped
  (< ~0.28 s) = latched until the next press; stop = this step ends now, [7A7C] = 15, [87BA] = DMA bytes
  since the start / bytes-per-sample + 1 (min 0x1000). Mono only; stereo takes run full length (the R half
  starts at start + full length, cutting it isn't worked out). The emulator moves the DMA with `recdma`. A kept take (0FE4:3CE7) lands on
  the sample select page (EDIT SAMPLE page 0, inside its SAMPLE+PITCH group); ABORT stays on the meter.
  Later (user: "full later"?): one custom MPC page (`>ST >5.0s  ARM` + meter), skip the GO confirm.
  REC variables (read off the record code, not yet confirmed): [7500] stereo, [7501], [7502] start type (0 = THRES), [7503] threshold, [7508] length (dword),
  [750C] bandwidth, [7577] digital in, [7581] armed, [7A87] input level.

## Build order
- **M1 (0.12)**: HOME hub + status card + quick LOAD / EDIT soft keys + EXIT = back one level.
- **M2**: EDIT PROGRAM menu with group-limited paging + breadcrumb.
- **M3 (0.14)**: SAMPLE + GLOBAL menus (MULTI is short enough to stay stock).
- **M4**: more quick jobs.

## Open
- EDIT FX (7) page list isn't walked yet (only matters with an EB16).
- Real panel labels (only known from the matrix + reviews).
- Free code space: ~0.7 KB left in MENU_SEG (0.14 blob 4955 of 5632 B).
