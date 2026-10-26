; Rosetta area menus (menu redesign M2 + M3, docs/menu_design.md). Included by rosetta_menu.asm.
;
; EDIT PROGRAM, EDIT SAMPLE and GLOBAL (the TUNE key) open a menu instead of a long row of pages:
;     EDIT PROGRAM 1/8
;     >SAMPLES+ZONES
; DATA wheel / PAGE / GROUP keys pick a group, the right soft key goes in, the left one (or home) goes out.
; Inside a group the stock pages work as before, but PAGE wraps inside the group, GROUP jumps to the
; next/previous group, and the home key comes back to the menu.
;
; The menus live on the FX page slot (mode 6 page 0x0C, no EB16): ctx = CTX_MENU there. Entering a group
; sets the area's mode + the group's first page and redraws (0FE4:0616), exactly what a stock page step ends with.
; S2000s with an EB16 fitted keep the stock pages (the slot is the real EFFECTS page there).

CTX_FX    equ 0
CTX_MENU  equ 1
CTX_SYN   equ 2               ; the SYNTH page (MULTI, 0.26): hi code (src/rosetta_synui.asm) draws and edits
MODE_MULTI equ 2

; page0_hook (mode entry): an area's mode -> its menu. Returns with MODE = 6 so the stock EB16-absent path
; runs fx_entry next (which renders the menu for ctx = CTX_MENU). Keeps bx.
prog_entry:
        mov byte [cs:grp], 0
        mov byte [cs:ctx], CTX_FX
        cmp byte [EB16], 0
        jne .r
        cmp byte [MODE], MODE_MULTI   ; MULTI = the SYNTH page (the user: "MULTI = SYNTH only")
        jne .a
        mov byte [cs:ctx], CTX_SYN
        mov byte [MODE], MODE_FX
        ret
.a:     push bx
        mov al, [MODE]
        mov bx, NAREAS - 1
.l:     cmp al, [cs:a_mode + bx]
        je .hit
        dec bx
        jns .l
        pop bx
.r:     ret
.hit:   mov [cs:area], bl
        mov byte [cs:ctx], CTX_MENU
        mov byte [MODE], MODE_FX
        pop bx
        ret

; bx = current area
abx:    mov bl, [cs:area]
        xor bh, bh
        ret

; soft key al (0-7) on the menu page
pm_key: cmp al, 1
        je pm_enter
        cmp al, 4
        je .dn
        cmp al, 6
        je .dn
        cmp al, 5
        je .up
        cmp al, 7
        je .up
        ret                   ; (left soft key: handled as "home" by key_hook)
.dn:    mov al, -1
        jmp pm_move
.up:    mov al, 1
        ; fall through
; al = signed step for the menu selection (wraps), then show it
pm_move:
        call selstep
        mov al, 1
        jmp pm_render

; al = signed step for the area's selection (wraps inside the area). Leaves bx = area.
selstep:
        call abx
        add al, [cs:a_sel + bx]
        mov ah, [cs:a_n + bx]
.w1:    or al, al
        jns .w2
        add al, ah
        jmp .w1
.w2:    cmp al, ah
        jb .w3
        sub al, ah
        jmp .w2
.w3:    mov [cs:a_sel + bx], al
        ret

; go into the selected group of the area
pm_enter:
        call abx
        mov al, [cs:a_sel + bx]
        add al, [cs:a_first + bx]
        mov [cs:grp], al
        inc byte [cs:grp]
        mov dl, [cs:a_mode + bx]
        mov bl, al
        mov al, [cs:g_start + bx]
        mov byte [cs:onfx], 0
        mov [MODE], dl
        mov [PAGE], al
        jmp redraw

; back from a group to the menu
pm_back:
        mov byte [cs:grp], 0
        mov byte [cs:ctx], CTX_MENU
        mov byte [MODE], MODE_FX
        mov byte [PAGE], FXPAGE
        xor al, al
        call pm_render
        jmp redraw

redraw: pusha
        push es
        call 0x0FE4:REDRAW
        pop es
        popa
        ret

; CF = 1 when a group is open and the OS is still in its area's mode
in_grp: cmp byte [cs:grp], 0
        je .no
        push bx
        call abx
        mov bl, [cs:a_mode + bx]
        cmp [MODE], bl
        pop bx
        jne .no
        stc
        ret
.no:    clc
        ret

; inside a group: soft key al (0-7). Returns CF = 1 if consumed.
; A group is range A (+ optional range B). PAGE at a range edge jumps to the other range / wraps,
; GROUP = neighbour group, everything else (and PAGE inside a range) stays stock.
pg_key: mov bl, [cs:grp]
        dec bl
        xor bh, bh
        mov ah, [PAGE]
        cmp al, 5                     ; PAGE >
        je .next
        cmp al, 4                     ; PAGE <
        je .prev
        cmp al, 7                     ; GROUP >
        je .gn
        cmp al, 6                     ; GROUP <
        je .gp
        clc
        ret
.next:  call grp_page
        jnc .os
        call inB
        jc .nb
        cmp ah, [cs:g_end + bx]
        jb .step1
        call firstB
        jmp .set
.nb:    cmp ah, [cs:g_end2 + bx]
        jb .step1
        mov al, [cs:g_start + bx]
        jmp .set
.prev:  call grp_page
        jnc .os
        call inB
        jc .pb
        cmp ah, [cs:g_start + bx]
        ja .step0
        call lastB
        jmp .set
.pb:    cmp ah, [cs:g_start2 + bx]
        ja .step0
        mov al, [cs:g_back + bx]
        jmp .set
.os:    clc                           ; on an OS sub-page outside the group (FORMAT HARD DISK, backup, GO
        ret                           ; confirms): PAGE is stock, no pull-back (0.27 hid the HD format)
.step1: mov byte [cs:pstep], 1        ; stock steps (it skips hidden pages); pm_poll checks the result
        jmp .st
.step0: mov byte [cs:pstep], 0xFF
.st:    mov [cs:pfrom], ah
        clc
        ret
.gp:    mov al, -1
        jmp .gg
.gn:    mov al, 1
.gg:    call selstep                  ; a_sel = this group, step it inside the area
        call pm_enter
        stc
        ret
.set:   mov [PAGE], al
        call redraw
        stc
        ret

; bx = group: CF = 1 if page ah is one of the group's own pages (range A or B)
grp_page:
        call inA
        jc .r
        call inB
.r:     ret

; bx = group: CF = 1 if page ah is in range A / range B
inA:    cmp ah, [cs:g_start + bx]
        jb .no
        cmp ah, [cs:g_end + bx]
        ja .no
        stc
        ret
.no:    clc
        ret
inB:    cmp byte [cs:g_start2 + bx], 0xFF
        je .no
        cmp ah, [cs:g_start2 + bx]
        jb .no
        cmp ah, [cs:g_end2 + bx]
        ja .no
        stc
        ret
.no:    clc
        ret
firstB: mov al, [cs:g_start2 + bx]    ; al = B's first page, or A's if there's no B
        cmp al, 0xFF
        jne .r
        mov al, [cs:g_start + bx]
.r:     ret
lastB:  mov al, [cs:g_back2 + bx]     ; al = B's last visible page, or A's
        cmp al, 0xFF
        jne .r
        mov al, [cs:g_back + bx]
.r:     ret

; main-loop wait: after a stock PAGE step inside a group, pull the page back if it left the group
pm_poll:
        mov cl, [cs:pstep]
        or cl, cl
        jz .r
        mov byte [cs:pstep], 0
        call in_grp
        jnc .r
        mov bl, [cs:grp]
        dec bl
        xor bh, bh
        mov ah, [PAGE]
        call inA
        jc .r
        call inB
        jc .r
        mov ah, [cs:pfrom]            ; left the group: continue the way pg_key wraps
        or cl, cl
        js .back
        call inB
        jc .toA
        call firstB
        jmp .set
.toA:   mov al, [cs:g_start + bx]
        jmp .set
.back:  call inB
        jc .toAb
        call lastB
        jmp .set
.toAb:  mov al, [cs:g_back + bx]
.set:   mov [PAGE], al
        call redraw
.r:     ret

; 2 x 16 menu text -> page 0x0C RAM text (+ LCD when al != 0)
pm_render:
        push ax
        call abx
        mov al, 13
        mul bl
        add ax, a_title
        mov si, ax
        mov di, fxbuf
        mov cx, 13
        call pm_cpy
        mov al, [cs:a_sel + bx]
        add al, '1'
        mov [cs:fxbuf + 13], al
        mov byte [cs:fxbuf + 14], '/'
        mov al, [cs:a_n + bx]
        add al, '0'
        mov [cs:fxbuf + 15], al
        mov byte [cs:fxbuf + 16], '>'
        mov al, [cs:a_sel + bx]
        add al, [cs:a_first + bx]
        mov ah, 15
        mul ah
        add ax, g_names
        mov si, ax
        mov di, fxbuf + 17
        mov cx, 15
        call pm_cpy
        pop ax
        jmp fx_out

pm_cpy: mov al, [cs:si]               ; cx bytes cs:si -> cs:di
        mov [cs:di], al
        inc si
        inc di
        loop pm_cpy
        ret

pstep:    db 0                ; 1 / -1 after a stock PAGE step inside a group (pm_poll checks it)
pfrom:    db 0                ; the page it stepped from
grp:      db 0                ; 0 = not in a group, else group index + 1
ctx:      db CTX_FX
area:     db 0

; areas: the mode that opens the menu, where "out" goes (a mode key event), its groups in the g_ tables
NAREAS    equ 3
;                 PROG  SAMP  GLOB
a_mode:   db         1,    5,    8      ; EDIT PROGRAM, EDIT SAMPLE, TUNE/GLOBAL
a_out:    db      0xC0, 0xC2, 0xC0      ; HOME, REC (the page EDIT SAMPLE came from), HOME
a_first:  db         0,    8,   14
a_n:      db         8,    6,    4
a_sel:    db         0,    0,    0      ; selected group per area (kept while the OS runs)
a_title:  db "EDIT PROGRAM "
          db "EDIT SAMPLE  "
          db "GLOBAL       "

; groups, essentials first (EDIT PROGRAM order user-approved). 15 chars each.
g_names:  db "SAMPLES+ZONES  "        ; 0  EDIT PROGRAM (mode 1)
          db "AMP ENVELOPE   "
          db "FILTER+ENV2    "
          db "PITCH+BEND     "
          db "OUTPUT         "
          db "KEYGROUPS      "
          db "PROGRAM        "
          db "MODS+LFO       "
          db "SAMPLE+PITCH   "        ; 8  EDIT SAMPLE (mode 5)
          db "TRIM           "
          db "LOOP           "
          db "NORM+REV+FADE  "
          db "RESAMPLE       "
          db "TIMESTRETCH    "
          db "TUNE+LEVEL     "        ; 14 GLOBAL (mode 8)
          db "MIDI           "
          db "DISK+SCSI      "
          db "SONG PLAYER    "
; stock pages per group (docs/pagewalk_edit.txt, docs/pagewalk.txt). Hidden pages (EDIT PROGRAM 10-11, 21,
; empty zones, 71-83; EDIT SAMPLE 23; GLOBAL 8-16, 18, 23) are skipped by the stock step.
; range A = start..end, back = last always-visible page of A (PAGE < wraps there); range B likewise, FF = none
;                 SAMP AMP FILT PTCH OUT  KG  PROG MOD | SMP TRIM LOOP NRF  RES  TS  | TUNE MIDI DISK SONG
g_start:  db       22,  54,  60,   6,   8,  17,   0,  84,   0,   6,   8,   5,  17,  20,    0,   2,   6,  17
g_end:    db       53,  59,  70,   7,  16,  21,   5,  95,   4,   7,  13,   5,  19,  24,    1,   5,   7,  22
g_back:   db       46,  59,  70,   7,  16,  20,   5,  95,   4,   7,   8,   5,  19,  24,    1,   5,   7,  22
g_start2: db     0xFF,0xFF,0xFF,  96,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,  14,0xFF,0xFF, 0xFF,  26,  24,0xFF
g_end2:   db     0xFF,0xFF,0xFF,  98,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,  16,0xFF,0xFF, 0xFF,  26,  25,0xFF
g_back2:  db     0xFF,0xFF,0xFF,  98,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,  16,0xFF,0xFF, 0xFF,  26,  25,0xFF
