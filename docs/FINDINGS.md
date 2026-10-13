# S2000 Rosetta OS: lab notebook

> Working notes, kept as written. Paths like `gotek/`, `build/`, `img/` and `rec/` are the author's local
> folders (disk images, builds, recordings) and are not in the repo.

Rosetta OS for the Akai S2000 (same name as the GP-16 Rosetta OS). Patch-the-stock-OS approach on the Akai S2000 OS 2.0. Boot from the Gotek (HFE). Nothing here touches ROM or flash.

## Files
- `gotek/S2K_OS20_STOCK.hfe`: stock OS 2.0 boot disk. This is the control.
- `gotek/S2K_BABY_001.hfe`: baby v0.01, which changes 2 strings and nothing else.
- `build/os20_stock.bin`: raw 256 KB OS file, for disassembly.
- `build/s2kos2.img`: raw 1.6 MB Akai HD disk image.
- `img/`: sources. `s2kos2.td0` comes from wiw.org/~meta/s2k.php. `online/osimage` is that site's independent raw image. `DSKA0000.hfe` is the blank HFE template.

## Tools (run with `python -I`)
- `tools/td0.py in.td0 out.img`: Teledisk to raw image. Handles normal "TD" images only.
- `tools/hfe.py info|read|write`: HFE v1 to and from raw image. `write` overlays the data fields onto the template bitstream and checks CRCs on read-back.
- `tools/mkbaby.py disk.img template.hfe build/NAME`: applies `PATCHES` (each one asserts the stock bytes first) and outputs .bin, .img and .hfe.

## Verified
- Your TD0 is byte-identical to the online one (sha1 cbb2fea1...).
- The OS file in the TD0 is byte-identical to the one in the independent `osimage` raw image.
- OS file sha1 is 6d9c7e94...; disk image sha1 is b33ef14c...
- An HFE round-trip comes back byte-identical with 0 CRC errors.

## Disk format (Akai S3000-type HD floppy)
- 80 cylinders, 2 heads, 10 sectors of 1024 bytes, MFM at 500 kbps. Cylinders 1+ are skewed and start at sector 6. gap3 is 128.
- Block 0 holds 64 legacy directory entries (24 bytes each). The FAT is at 0x600 (2 bytes per block: 0x4000 = reserved, 0xC000 = end of file).
- The volume label is at 0x1280 in the Akai charset (`0-9 space A-Z # + - .`). The S3000 directory (512 entries) starts at 0x1400.
- Directory entry layout: name[12], 4 reserved bytes, type, size (3 bytes, little-endian), start block (2 bytes), OS version (2 bytes).
- The OS entry is "OS", type 0x63, size 0x40000, start block 17, contiguous through block 272.

## OS 2.0 layout (load at linear 0, NEC V53 real mode)
- 0x000 is the interrupt vector table. INT0 and the default handler are at 2345:170B/17AA. The word at 0x1C-0x1F is `00 11 11 00` (version 0x1100, matching the directory entry).
- 0x050 is the entry point: `jmp 53`, then cli, ds=es=ss=0, sp=0x300, copy [1E]→[1D], set INT0, then `ljmp 0FE4:0002` (linear 0xFE42).
- LCD strings are ASCII terminated by 0xFF. 16-character line chunks are visible in the messages.
- 0x2D5C: "Searching for   AKAI SCSI disk" (boot SCSI scan).
- 0x2F9CE: "VERSION 2.00", shown on the SAVE page when type = System.
- 0x6B08: SCSI INQUIRY data, "AKAI EMI" / "S2000 SAMPLER   " / "2.00". Leave alone.
- 0x7263+: flash-ROM messages ("No Flash ROM fitted", "Flash jumpers wrong"). The OS supports an optional flash ROM.
- 0x3E036: leftover Turbo Assembler 4.0 / `load.asm` object junk in slack space. This is free space candidate #1.
- 0x304F onward and the end of the file: about 159 `_NAME` symbols (`_SHEAD _PRMEM _MODEL_NO _SETDOS _ESMODE ...`). This looks like a parameter/remote table rather than a linker map. Not decoded yet.
- No plain 8- or 16-bit checksum (sum16 = 0xD64A). Whether the boot loader verifies the OS is unknown. Baby 001 tests that.

## Hardware results (2026-10-13)
- DSKA0000 (stock), DSKA0001 (baby 0.01) and DSKA0002 (baby 0.02) all boot from the FlashFloppy Gotek, indexed mode.
- 0.02 shows **BABY OS 0.02** as the default program name on the main screen. **There is no OS checksum**, so code patches load as-is.
- The default program header (Akai charset name) has 3 copies, at 0x1629, 0xA0D3 and 0x1EE88.

## Original test plan (baby 001)
1. Boot `S2K_OS20_STOCK.hfe` first to prove the HFE path works.
2. Boot `S2K_BABY_001.hfe`. You should see "BABY OS v0.01" during the SCSI scan, and "BABY OS 0.01" on SAVE → type System (don't press GO).
3. If 2 fails and 1 works, the loader checks the OS. In that case, find the check and fix up the sum.

## Code map (RE so far)
- Boot sequence: `0FE4:0002` jumps to `1F50:0000` (init: clears RAM at 3B05:0, among other things), then `ljmp 0FE4:0007` at 0x1F547.
- `0FE4:0007` is `call 0073` (one-shot init). The **main loop** is `0FE4:000A`–`0071`: it waits for the tick from `2345:0A47` to advance by 10, then calls about 15 tasks.
- Far-call target segments: 2345 is the kernel (747 calls). The others are 1F50, 2BD5, 0FE4, 2D00 and 2CA7. Data uses DS=0.
- **LCD** (HD44780-style): port 0x62 = command/busy (bit 7 busy), port 0x60 = data. `0FE4:0D90` reads 16 characters back from the display.
- **Popup message**: `mov bx,STR; push cs; call 0FE4:0D6B`. It then calls `2345:10F1`, which saves the screen to 2D95:57B0 (linear 0x33100), copies 33 bytes to 0x8FE0, and draws via `2345:1078`. Strings are 2×16 characters terminated by 0xFF.
- The SCSI-search message (0x2D5C) only shows when `[0x75B7]==1`.
- The image doubles as RAM: 0x33100 (screen save) and 0x3B050 (cleared at init) are used at runtime. **Don't** treat high slack as free space without proof.
- 0x1EEC0–0x1F0xx are Akai default program/keygroup/sample templates, not free space.
- **Safe free space:** 0FE4:F6B2–F6BF, 14 bytes of alignment pad (the 0.03 hook uses 13).

## Builds
- 0.01: text only (SAVE System page, SCSI message).
- 0.02: plus the default program name, which shows on the main screen. **Confirmed on hw.**
- 0.03: first code hook (**confirmed on hw**).
- 0.04: **boot dragon** (port of the GP-16 Rosetta OS dragon). The hook `0FE4:0002 ljmp 1F50:0000` becomes `ljmp 3E20:0000`. The routine is `src/s2k_dragon.asm` (550 B, NASM from gp16/tools) and runs **before init**. It lives in the leftover load.asm object junk (0x3E01B–0x3FFFF, no refs) with a private stack. It draws the banner, eats line 1 then line 2 with a dot trail, restores CGRAM chars 1–3, and continues to 1F50:0000 with the exact entry state. `tools/emu_dragon.py` (unicorn plus a fake HD44780) PASSES. Tune the speed with DLY_OUTER/HOLD_STEPS in the asm. **Confirmed on hw: about 1.5 s total, one delay step is about 29 ms.**
- The OS's own "load OS" path (2BD5:0000) copies a fresh image from 0x50000 and then jumps to 0:0050, so the pre-init hook always sees intact code.
- Permanent free space for later features: the user OK'd taking the factory demo songs and setups (as was done on the GP-16). None found as such. **Permanent free space = 0x3E01B–0x3FFFF** (leftover object junk): no refs, no segment reaches it, the structures below are fixed size (voice table 2D95:9F80 = 32 × 0x1BC ends 0x3B050, MIDI tx ring 3B05:0000–0x10F), and the emulator never writes it. The dragon uses 0x3E200–0x3EA00 at boot; the menu code is at 0x3F000.
- 0.05: Rosetta naming plus the dragon at 4× (DLY_OUTER 4 / HOLD 9, about 4.6 s; the user picked it).
- 0.06: **menu-flow pack**. LOAD and SAVE skip "DISK or FLASHROM" when no flash ROM is fitted (dword 2316:0024 == 0). The mode-entry page-0 write at 0FE4:03B1 becomes `lcall 3F00:0000` (src/rosetta_menu.asm). Data-key auto-repeat: first repeat 1000 → 300 ticks, interval 200 → 80, floor 40 → 10 (ticks are about 2.04 ms: TCU ch0 4087 at 2 MHz). The boot popup is off (it waited for a key; BOOT_POPUP=1 restores it). Emulator: LOAD → DISK LOAD in one press; SAVE → DISK SAVE; with flash simulated, the stock question returns; other modes unchanged.
- 0.07: **hidden reverb experiment**. EFFECTS (mode 6) with no EB16 ([0x84E0] = 0): the stock code forces page 0x0C "EB16 not present"; its `mov [762B],6` at 0FE4:03CB becomes `lcall 3F00:0003`. That toggles the L7A1045 delay engine with the unreferenced preset 1 (2D95:3460) or preset 0 (off) via the OS loader 2345:8180 (ES = 0), and relabels page 0x0C in RAM: " ROSETTA REVERB" / "ON (EFX toggles)" / "OFF(...)". All three reg7 word1 writers (2345:50EE note-on and 2345:5480 periodic vol/pan via +6; 2345:41A8 live update via +9) OR in send 0x80 / dest 0xF while it's on. The emulator confirms the 31 reg A functions are programmed on/off and every reg7 word1 = 0x800F when on, 0 when off. The menu pack still passes. The delay buffer is sample-RAM words 0x0000–0xFFFF, reserved by the OS (allocation starts at 0x10100; init 2345:1907 sets [0x753D]=0x0001:0100 and [0x7679]=0x10000), so samples should be safe. **CONFIRMED ON HW 2026-10-13 (on 0.08): the reverb works; the user says it "sounds like a couple of delays" (preset 1 is mostly a multi-tap echo, with little feedback).**
- 0.08: **PLAY always plays**. With no program active, notes (PLAY and MIDI) audition the current sample: the note-on dispatcher's "0 active programs → exit" (0FE4:CA0C `jmp CAA4`) jumps to the sample-page audition branch (C9D4) instead. The emulator shows the main-page PLAY start the same voice (0x10416, SINE) and give the same voice/release behaviour as the stock sample-page audition. The sample is whatever the sample page last selected ([7637] = 0xFF means the temp keygroup at 8FE8).
- 0.09: **SysEx lab backdoor** (F0 7D 53 cmd nibbles F7): OUTW/OUTB/POKE/PEEK/PING/FXPROG/INW, replies over MIDI out. PC side: tools/s2kfx.py (OCTA-CAPTURE ports only: the Focusrite belongs to the GP-16 session). HW: PING works.
- 0.10: **8 FX presets on the delay engine** (OFF, ROOM, HALL, PLATE, ECHO, PINGPONG, CHORUS, FLANGER), EFFECTS steps through them. Bank = tools/fxbank.py + src/fx/*.json (reverbs designed offline with tools/fxdesign.py). Chorus/flanger: LFO slots updated once per 2 ms tick from the main-loop wait (0FE4:000D `lcall 2345:0A47` -> MENU_SEG:0015); each slot drives an even/odd tap pair with crossfaded gains = fractional delay without clicks. HW: "we got fx" (reverbs "metallic digital but cool", HALL "echoy").
- 0.11: **EFFECTS page with controls** (src/rosetta_fx.asm). Page 0x0C shows `>HALL    >WET 50` / `>T100 >F100 >R100` (type, wet 0-99 = voice send level, TIME 25-200 % of all delays, FEEDBACK % of the feedback gains capped per preset so the loop sum stays < 0.97, LFO RATE 10-400 %). Soft keys 0x40/0x41 (r2c1/r5c1) move the cursor, 0x44/0x46 (r1c0/r5c0) = -1, 0x45/0x47 (r0c0/r4c0) = +1, the data wheel ([73A5], grabbed with xchg in the main-loop wait) and the inc/dec pair ([73AC]) change the value. The key hook sits on the dispatcher's event read (0FE4:0264 `mov al,[73D4]; test al,0C0h` -> MENU_SEG:0018) and consumes soft keys only on page 0x0C. The text goes to the page's RAM copy (2D95:1402/1415) and straight to the HD44780. First EFFECTS press shows the page, the next ones step the type (page0_hook remembers whether the FX page was up). Emulator: cursor/values/limits/types all pass; chorus/flanger LFO unchanged from 0.10.
- Stock key quirk (not ours): 2345:07CD skips the matrix scan for 50 ticks (~100 ms) after a key change, compared on the byte tick counter that wraps every 0.52 s, so a short press ~0.5 s after the previous one can be eaten.
- PLAY = key r6c0. Stock PLAY only auditions on the sample/sampling pages (mode 4/5) and otherwise plays the selected program.
- Stick rule (the user's request): a single image only, DSKA0000 = the build under test.
- Mode codes: main 0, EFFECTS 6, SAVE 9, LOAD 0x0A. [0x84E0] = EB16 present. [0x762B] = mode, [0x762C] = page. Key → mode table at DS:05FD (0FE4:0396). Page lookup is 2345:0512 (BL = mode, BH = page). The page renderer is 2345:1040.
- Emulator gap: the FDC model raises no interrupt, so FLOPPY freezes the UI in emulation (stock does the same). The init call is redirected to the pad stub, which shows a "BABY OS v0.03 / code hook works" popup and then enters the main loop.

## Hardware map (from RE + emulation, 2026-10-13)
| I/O | Device |
|---|---|
| 0x00–0x1C | Fujitsu MB89352 SCSI controller (registers on even addresses) |
| 0x20 / 0x22 | NEC uPD72065 floppy controller: MSR/aux commands (0x36 = reset) and data. [0x8068] = 5 or 10 sectors (DD/HD) |
| 0x40 | misc inputs (bits 0x3C), read in the tick ISR. Probably the data wheel and switches |
| 0x50 / 0x52 | front-panel key matrix: 0x52 = row select (8 rows), 0x50 = 2 column bits |
| 0x54 | indicator latch (0xFF on note-on, 0x7F on note-off: MIDI LED?) |
| 0x60 / 0x62 | LCD HD44780 16×2: data / command+busy |
| 0x80–0x8C | **L7A1045 voice chip, exactly MAME's layout**: 0x80 = select (`reg<<8` + voice), 0x82/0x84/0x86 = data words 0/1/2 (bits 15–0/31–16/47–32), **0x88 = key on (bit 8)**, 0x8C = atomic zero. Also the DMA target (ch3) for sample transfers |
| 0xA0 / 0xA2 | companion DSP (coefficients/output stage?): A2 = select, A0 = data. Status select 0x180, bit 0 = busy |
| 0xC0 / 0xC2 | output latches (0xC0 shadowed in [0x7349]) |
| 0xE0–0xE4 | ? (written in pairs with a `ror 4` nibble; maybe the EB16/DFL interface) |
| 0xC000+ | V53 internal (OPHA = 0xC0): DMAU C000, ICU C010, SCU (MIDI) C020, TCU C030 |

- ICU: ICW2 = 8, auto-EOI, final mask 0xFC. **IR0 = int 8 = 0FE4:0C66** (SCU: MIDI rx, plus a tx ring at 3B05:0000). **IR1 = int 9 = 0FE4:0B92** (tick: `inc [0x73DA]`).
- MIDI: the ISR fills a 256 B ring at 0x0300 (write pointer [0x73A0], read pointer [0x73A2]). The main loop at 0FE4:6040 reads it and passes bytes to the parser 0FE4:6076. Complete messages go to `lcall 2B9D:00AF`, then the channel handler 2B9D:011D (AH = status, AL = channel, DL = note, DH = velocity). **The note-on is `2B9D:016C call 0354`, a single 3-byte hook point for faux FX.**
- Keys: 2345:079A scans 8 rows into 0x73BC. The keymap is 4 × 16 at 2D95:0030 (layer = [0x7381]&3). Auto-repeat is set by `[0x73B0]=1000` (initial delay) and `[0x73B4]=200` (repeat), at 2345:07F5/0802.
- Front-panel matrix (emulator): r1c1 = EXIT/PLAY (home), r2c1 = left soft key, r5c1 = right soft key, r0c0/r4c0 = page+, r0c1 = page−, r2c0 = LOAD, r6c1 = SAVE, r3c0 = EFFECTS, r3c1 = TUNE/global (OUTPUT LEVEL), r4c1 = MULTI, r7c1 = RECORD. r1c0, r5c0, r6c0 and r7c0 have no visible effect on the main page (cursor/data?). The full two-level tree is in build/ui_tree.txt.
- Page text: `8A col row` + text, terminated by `FF`.

## Emulator (tools/s2k_emu.py + tools/s2k_ui.py)
Unicorn boots the real OS to the main screen in about 50 s. The fake devices are: LCD, key matrix, uPD765/72065 (empty drive), 8259 ICU with the tick injected from the block hook, instant DMA, and an idle sound chip. MIDI goes in through `midi_in()` (rx ring). `s2k_ui.py keymap|tree|notes|seq` snapshots after boot and presses keys.
**Unicorn gotcha:** in 16-bit mode `emu_start(begin)` takes a LINEAR address (it sets IP = begin − CS·16). Resume with `(CS<<4)+IP`.
Not yet working: voices don't start on note-on in emulation (TEST PROGRAM's sample doesn't exist, or the voice start goes via DMA or IRQ). That's the next dig for faux FX.

## L7A1045 notes (MAME l7a1045_l6028_dsp_a.cpp, 2025+ register docs)
Per-voice registers: 0 start, 1 end + rate (4.12 fixed point vs 44.1k), 2 loop, 3/4 volume envelope (start/target/rate), 5/6 lowpass cutoff + resonance + cutoff envelope, 7 L/R volume + routing (**dest 0xF = send to delay effect**) + send level, A = delay buffer (64K samples, 3 stages, feedback). **The chip has a built-in delay engine**, which could give Rosetta FX without an EB16. The S2000 board's select encoding differs from MAME's MPC3000 one (selects seen: 0x00C8, 0x00F6, 0x0180–0x0182, 0x02xx) and is still to be decoded.

## Sound engine (emulator trace of a real note-on, 2026-10-13)
- Programs: [0x74F4] = count, segment table at DS:B0D0, header byte +0x0F = program number. [0x758A] = selected program (boots as 35, i.e. "36"). [0x74FA]/[0x74FB] = active-program list. MIDI PC 0 selects TEST PROGRAM, and then notes play.
- Note-on path: 2B9D:0354 → 0FE4:C93F (mode switch) → CA00 (active programs) → voice alloc 0FE4:CC33 (32 voices) → 2345:43C6..4BC2 voice start.
- Voice 31 at note-on: reg0 start 0x10416 (flags 01, RAM); reg1 rate 0x1000 (= 44.1 kHz); reg2 relative loop; reg3 env start 0 (atomic); reg4 env target 0x2DD0 / rate 0x082C; reg5 cutoff 0x3FFF; reg6 target 0x7FF; reg7 L 0x7D, R 0x7E, word1 (send/e/dest) = [voice+0x84] = 0; reg8/9 zeroed; then key on (0x88 ← 0x100).
- 0xE0–0xE4 is a second per-voice bank with the same select format (DFL second filter?).

## The chip's delay engine (register A) in the stock OS
- 2345:6302 zeroes register A, functions 0–31. 2345:3294 reads function 0's buffer position (20 bits). 2345:8180 loads a 192 B preset (32 × {int8 level, u8 routing, u16 length, u16 x}) from 2D95:SI into the DS:6D00 shadow and programs it: word0 = level × 0x28F | routing, word1 = −(length−1).
- Preset 0 @2D95:33A0 = off (restored at 0FE4:D4B5). **Preset 2 @2D95:3520 = recording** (4 taps of 64000 samples, loaded by 0FE4:53EB, which then syncs on the buffer position).
- **Preset 1 @2D95:3460 is never referenced: it looks like a REVERB** (7 negative-level diffusion taps plus taps at 200…5789+ samples, rising then falling). A candidate hidden effect.
- To hear it, voices must send to the engine: reg7 word1 = send level (bits 15–8) | e (7–4) | dest 0xF. The stock OS writes [voice+0x84] (0 here). Unknowns: the delay buffer's base address in sample RAM (could overwrite the first sample) and the "e" bits.

## Delay engine model (from the OS preset loader + the hardware result)
- Each register A function is one **tap**: it reads the 64K-sample buffer at (write position − length) × gain and sends it to dd.
- word0 = signed 16-bit gain with dd in bits 1–0. The preset byte `lvl` × 0x28F gives ±50 ≈ full scale; 0x80 is special-cased to 0x4000.
- dd: 0 = left out, 1 = right out, 3 = **feedback into the buffer input** (the preset stores 2 and the loader turns it into 3).
- word1 = −(length−1). The buffer input is the voices' sends (reg7 word1 v, d = 0xF) plus the feedback taps. Keep the sum of |feedback gains| < 1 for stability.
- Preset 1 (stock, unused): feedback taps at lengths 0–3 (no real tail), then output taps at 200…5789+ samples. That's why it sounds like "a couple of delays".

## Delay engine, MEASURED (2026-10-13, SysEx lab + OCTA capture, tools/irmeasure.py)
- NOISE BURST fired over MIDI with FX off (reference) and with a preset; per-channel deconvolution gives the tap pattern.
- **One 65536-sample line at 44.1 kHz (~1.49 s), 30 taps** = reg A functions 1-10 and 12-31 (fn11 is an ordinary function too; the stock presets just park it at length 65535).
- Tap delay = length word -> `2 - delay` (i.e. stored length + 1 samples). All 20 output taps of stock preset 1 land within 1 sample of the table.
- Routes: 1 -> OCTA in1 (L), 0 -> in2 (R), 3 -> feedback into the line. Feedback level 20 (0.4) repeats drop ~8 dB each: gain is linear Q15, level 50 ~ unity.
- Exact Q15 gains matter: the int8 table rounding halved the hall decay; Rosetta writes gain words directly (out 0x80 = 0x0A00|fn, 0x82 = gain|route, 0x80 again, 0x84 = 2-delay).
- Current audition sample = [0x7639] (index into the sample list); the lab can poke it.
- No ISR writes the voice chip (s2k_ui.py isrcheck: 0 writes in 1200 ticks with notes), so main-loop tap writes are safe.
- One line = no series allpasses: reverbs are multi-tap feedback loops (dense = short + ringy, long = echoey). Ideas: modulate a few feedback taps (Lexicon-style), trade output taps for more feedback taps.

## Opportunities (for Rosetta)
- Menu flow: skip LOAD/SAVE "DISK or FLASHROM" when there's no flash (it already detects "No Flash ROM fitted"), and skip "FLOPPY or HDSK" when there's no SCSI disk. That makes LOAD one press instead of three. Faster key auto-repeat. EFFECTS is a dead key without an EB16, so make it the Rosetta FX page.
- Faux FX: hook the note-on at 2B9D:016C (doubling, detune, harmony, echo repeats scheduled from the tick). Per-voice pitch, level, pan and filter LFOs. Unlock the chip's delay engine.

## Next
- Ghidra (x86 real mode 16-bit, base 0000:0000) or the capstone helpers. Follow 0FE4:0002 to the main loop, then the key/encoder dispatch, then the page/menu tables.
- Decide the first real feature (MIDI/perf, or live-FX mode). Free space is the 0x3E036 slack.
