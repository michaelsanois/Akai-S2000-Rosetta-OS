; Rosetta EDIT PROGRAM menu (menu redesign M2, docs/menu_design.md). Included by rosetta_menu.asm.
;
; EDIT (mode 1) opens a menu instead of 99 pages in a row:
;     EDIT PROGRAM 1/8
;     >SAMPLES+ZONES
; DATA wheel / PAGE / GROUP keys pick a group, the right soft key goes in, the left one (or home) goes out.
; Inside a group the stock pages work as before, but PAGE wraps inside the group, GROUP jumps to the
; next/previous group, and the home key comes back to this menu.
;
; The menu lives on the FX page slot (mode 6 page 0x0C, no EB16): ctx = CTX_PROG there. Entering a group
; sets mode 1 + the group's first page and redraws (0FE4:0616), exactly what a stock page step ends with.
; S2000s with an EB16 fitted keep the stock EDIT (the slot is the real EFFECTS page there).

CTX_FX    equ 0
CTX_PROG  equ 1
MODE_PROG equ 1

; page0_hook (mode entry): EDIT PROGRAM -> the menu. Returns with MODE = 6 so the stock EB16-absent path
; runs fx_entry next (which renders the menu for ctx = CTX_PROG). Keeps ax.
prog_entry:
        mov byte [cs:grp], 0
        mov byte [cs:ctx], CTX_FX
        cmp byte [MODE], MODE_PROG
        jne .r
        cmp byte [EB16], 0
        jne .r
        mov byte [cs:ctx], CTX_PROG
        mov byte [MODE], MODE_FX
.r:     ret

; soft key al (0-7) on the menu page
pm_key: cmp al, 1
        je pm_enter
        cmp al, 0
        je .out
        cmp al, 4
        je .dn
        cmp al, 6
        je .dn
        cmp al, 5
        je .up
        cmp al, 7
        je .up
        ret
.dn:    mov al, -1
        jmp pm_move
.up:    mov al, 1
        jmp pm_move
.out:   ret                   ; (left soft key: handled as "home" by key_hook)

; al = signed step for the menu selection (wraps)
pm_move:
        add al, [cs:psel]
.w1:    or al, al
        jns .w2
        add al, NGROUPS
        jmp .w1
.w2:    cmp al, NGROUPS
        jb .w3
        sub al, NGROUPS
        jmp .w2
.w3:    mov [cs:psel], al
        mov al, 1
        jmp pm_render

; go into group [psel]
pm_enter:
        mov bl, [cs:psel]
        ; fall through
; bl = group index: mode 1, first page of the group, redraw
pm_goto:
        mov [cs:psel], bl
        inc bl
        mov [cs:grp], bl
        dec bl
        xor bh, bh
        mov al, [cs:g_start + bx]
        mov byte [cs:onfx], 0
        mov byte [MODE], MODE_PROG
        mov [PAGE], al
        jmp redraw

; back from a group to the menu
pm_back:
        mov byte [cs:grp], 0
        mov byte [cs:ctx], CTX_PROG
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

; inside a group (mode 1, grp != 0): soft key al (0-7). Returns CF = 1 if consumed.
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
.next:  call inB
        jc .nb
        cmp ah, [cs:g_end + bx]
        jb .step1
        call firstB
        jmp .set
.nb:    cmp ah, [cs:g_end2 + bx]
        jb .step1
        mov al, [cs:g_start + bx]
        jmp .set
.prev:  call inB
        jc .pb
        cmp ah, [cs:g_start + bx]
        ja .step0
        call lastB
        jmp .set
.pb:    cmp ah, [cs:g_start2 + bx]
        ja .step0
        mov al, [cs:g_back + bx]
        jmp .set
.step1: mov byte [cs:pstep], 1        ; stock steps (it skips hidden pages); pm_poll checks the result
        jmp .st
.step0: mov byte [cs:pstep], 0xFF
.st:    mov [cs:pfrom], ah
        clc
        ret
.gn:    inc bl
        cmp bl, NGROUPS
        jb .gg
        xor bl, bl
        jmp .gg
.gp:    dec bl
        jns .gg
        mov bl, NGROUPS - 1
.gg:    call pm_goto
        stc
        ret
.set:   mov [PAGE], al
        call redraw
        stc
        ret

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
        cmp byte [MODE], MODE_PROG
        jne .r
        mov bl, [cs:grp]
        or bl, bl
        jz .r
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
        mov si, txt_pm
        mov di, fxbuf
        mov cx, 13
.t:     mov al, [cs:si]
        mov [cs:di], al
        inc si
        inc di
        loop .t
        mov al, [cs:psel]
        add al, '1'
        mov [cs:fxbuf + 13], al
        mov byte [cs:fxbuf + 14], '/'
        mov byte [cs:fxbuf + 15], '0' + NGROUPS
        mov byte [cs:fxbuf + 16], '>'
        mov al, [cs:psel]
        mov ah, 15
        mul ah
        mov si, g_names
        add si, ax
        mov di, fxbuf + 17
        mov cx, 15
.n:     mov al, [cs:si]
        mov [cs:di], al
        inc si
        inc di
        loop .n
        pop ax
        jmp fx_out

txt_pm:   db "EDIT PROGRAM "
pstep:    db 0                ; 1 / -1 after a stock PAGE step inside a group (pm_poll checks it)
pfrom:    db 0                ; the page it stepped from
psel:     db 0
grp:      db 0                ; 0 = not in a group, else group index + 1
ctx:      db CTX_FX

; groups, essentials first (user-approved order). Stock EDIT PROGRAM pages (mode 1, docs/pagewalk_edit.txt).
NGROUPS   equ 8
g_names:  db "SAMPLES+ZONES  "
          db "AMP ENVELOPE   "
          db "FILTER+ENV2    "
          db "PITCH+BEND     "
          db "OUTPUT         "
          db "KEYGROUPS      "
          db "PROGRAM        "
          db "MODS+LFO       "
; stock EDIT PROGRAM pages (mode 1, docs/pagewalk_edit.txt; 10-11, 21, empty zones and 71-83 are hidden):
; range A = start..end, back = last always-visible page of A (PAGE < wraps there); range B likewise, FF = none
;                 SAMP AMP FILT PTCH OUT  KG  PROG MOD
g_start:  db       22,  54,  60,   6,   8,  17,   0,  84
g_end:    db       53,  59,  70,   7,  16,  21,   5,  95
g_back:   db       46,  59,  70,   7,  16,  20,   5,  95
g_start2: db     0xFF,0xFF,0xFF,  96,0xFF,0xFF,0xFF,0xFF
g_end2:   db     0xFF,0xFF,0xFF,  98,0xFF,0xFF,0xFF,0xFF
g_back2:  db     0xFF,0xFF,0xFF,  98,0xFF,0xFF,0xFF,0xFF
