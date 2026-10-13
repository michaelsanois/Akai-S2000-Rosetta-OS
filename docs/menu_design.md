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

## Build order
- **M1 (0.12)**: HOME hub + status card + quick LOAD / EDIT soft keys + EXIT = back one level.
- **M2**: EDIT PROGRAM menu with group-limited paging + breadcrumb.
- **M3**: SAMPLE, MULTI, GLOBAL menus.
- **M4**: more quick jobs.

## Open
- EDIT SAMPLE (mode 5) and EDIT FX (7) page lists aren't walked yet.
- Real panel labels (only known from the matrix + reviews).
- Free code space: ~0.6 KB left in MENU_SEG; the menus need the demo songs/setups space (OK'd).
