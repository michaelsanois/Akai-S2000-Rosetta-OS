; Rosetta FX (no EB16): the EFFECTS page + a preset engine on the L7A1045's own delay engine.
; Included by rosetta_menu.asm (same segment, DS = 0 at every entry point).
;
; Page 0x0C of mode 6 (stock "EB16 not present") becomes
;     >HALL    >WET 50          TYPE / WET (send level 0-99)
;     >T100 >F100 >R100         TIME % (delays/size) / FEEDBACK % / LFO RATE %
; '>' marks the selected field. Soft keys 0x40/0x41 (r2c1/r5c1) move it, the inner DATA wheel ([73A5]) and
; the +-1 step ([73AC]) and soft keys 0x44-0x47 change it. EFFECTS again = next type.

TICK      equ 0x73DA          ; ++ every 0.511 ms by int 9 (0FE4:0B92), measured on hw (not 2.04 ms)
KEYEV     equ 0x73D4          ; key event: 0x40 | n = soft key n pressed, 0xC0 | n = mode key, 0x60 = release
WHEEL     equ 0x73A5          ; data wheel delta (int 9 adds it; stock consumer 0FE4:04A6)
INCDEC    equ 0x73AC          ; +1 / -1 step from port 0x40 bits 5/2 with slow repeat (int 9; stock: value step, 0FE4:0468)
FXPAGE    equ 0x0C
NFIELDS   equ 5
F_TYPE    equ 0
F_WET     equ 1
F_TIME    equ 2
F_FB      equ 3
F_RATE    equ 4

; ---------------------------------------------------------------------------------------------
; EFFECTS key (0FE4:03CB, EB16-absent path; the OS draws page 0x0C from RAM right after).
; First press shows the FX page, pressing it again while there steps to the next type.
fx_entry:
        mov byte [MODE], MODE_FX
        pusha
        push es
        cmp byte [cs:ctx], CTX_MENU   ; the area menus share this page slot
        jne .fx
        xor al, al
        call pm_render
        jmp .done
.fx:    cmp byte [cs:wasfx], 0
        je .show
        mov al, [cs:fxon]
        inc al
        cmp al, NPRESETS
        jb .s
        xor al, al
.s:     call fx_settype
.show:  mov byte [cs:onfx], 1
        xor al, al
        call fx_render
.done:  pop es
        popa
        retf

; soft key al (0-7) on the FX page (from key_hook in rosetta_home.asm)
fx_key: cmp al, 0
        je .left
        cmp al, 1
        je .right
        cmp al, 4
        je .dec
        cmp al, 6
        je .dec
        cmp al, 5
        je .inc
        cmp al, 7
        je .inc
        ret
.left:  mov al, [cs:fcur]
        dec al
        jns .l2
        mov al, NFIELDS - 1
.l2:    mov [cs:fcur], al
        jmp fx_show
.right: mov al, [cs:fcur]
        inc al
        cmp al, NFIELDS
        jb .r2
        xor al, al
.r2:    mov [cs:fcur], al
        jmp fx_show
.dec:   mov ax, -1
        jmp fx_change
.inc:   mov ax, 1
        jmp fx_change

; wheel / inc-dec on the FX page: called from lfo_hook (main-loop wait), grabs the deltas atomically
fx_poll:
        cmp byte [MODE], MODE_FX
        jne .r
        cmp byte [PAGE], FXPAGE
        jne .r
        xor al, al
        xchg al, [WHEEL]
        or al, al
        jnz .go
        xchg al, [INCDEC]     ; +1 / -1 (stock treats it as a value step on the field, like the wheel)
        or al, al
        jz .r
.go:    pusha                 ; DATA wheel / step: change the value
        push es
        cmp byte [cs:ctx], CTX_MENU
        jne .v
        call pm_move          ; menu: move the selection
        jmp .gd
.v:     cbw
        call fx_change
.gd:
        pop es
        popa
.r:     ret

; ax = signed delta for the selected field
fx_change:
        mov bl, [cs:fcur]
        cmp bl, F_TYPE
        jne .p
        mov cl, [cs:fxon]
        add al, cl            ; wrap into 0..NPRESETS-1
.w1:    or al, al
        jns .w2
        add al, NPRESETS
        jmp .w1
.w2:    cmp al, NPRESETS
        jb .w3
        sub al, NPRESETS
        jmp .w2
.w3:    cmp al, cl
        je fx_show
        call fx_settype
        jmp fx_show
.p:     xor bh, bh
        shl bx, 1
        mov di, [cs:fparam+bx]
        mov cx, [cs:fmin+bx]
        mov dx, [cs:fmax+bx]
        cmp bl, F_FB * 2
        jne .lim
        push ax
        push bx
        call fbmax
        mov dx, ax
        pop bx
        pop ax
.lim:   add ax, [cs:di]
        cmp ax, cx
        jge .c1
        mov ax, cx
.c1:    cmp ax, dx
        jle .c2
        mov ax, dx
.c2:    cmp ax, [cs:di]
        je fx_show
        mov [cs:di], ax
        cmp bl, F_WET * 2
        jne .ap
        call setsend
        jmp fx_show
.ap:    mov byte [cs:keepph], 1
        call fx_apply
        mov byte [cs:keepph], 0
        ; fall through
fx_show:
        mov al, 1
        jmp fx_render

; al = type: select it with default TIME / FB / RATE (WET stays)
fx_settype:
        mov [cs:fxon], al
        mov word [cs:ptime], 100
        mov word [cs:prate], 100
        call fbmax
        cmp ax, 100
        jbe .f
        mov ax, 100
.f:     mov [cs:pfb], ax
        mov byte [cs:keepph], 0
        call setsend
        jmp fx_apply

; send level byte = WET * 255 / 99 into reg7 word1 (dest 0xF = delay engine) via fxsendv
setsend:
        mov ax, [cs:pwet]
        mov dx, 255
        mul dx
        mov bx, 99
        div bx
        mov ah, al
        mov al, 0x0F
        mov [cs:fxsendv], ax
        ret

presetptr:                    ; si = record of preset [cs:fxon]
        mov bl, [cs:fxon]
        xor bh, bh
        shl bx, 1
        mov si, [cs:preset_ptrs+bx]
        ret

fbmax:  push si               ; ax = the preset's FEEDBACK limit (0 = no feedback taps)
        push bx
        call presetptr
        mov al, [cs:si+8]
        xor ah, ah
        pop bx
        pop si
        ret

; ---------------------------------------------------------------------------------------------
; 2 x 16 text into fxbuf -> page 0x0C RAM text (2D95:1402 / 1415); al != 0: also straight to the LCD
fx_render:
        push ax
        mov ah, F_TYPE
        call mark
        mov [cs:fxbuf], al
        call presetptr
        mov cx, 8
        mov di, fxbuf + 1
.n:     mov al, [cs:si]
        mov [cs:di], al
        inc si
        inc di
        loop .n
        mov ah, F_WET
        call mark
        mov [cs:fxbuf + 9], al
        mov word [cs:fxbuf + 10], 'WE'
        mov byte [cs:fxbuf + 12], 'T'
        mov ax, [cs:pwet]
        mov di, fxbuf + 13
        call itoa3
        mov ah, F_TIME
        call mark
        mov [cs:fxbuf + 16], al
        mov byte [cs:fxbuf + 17], 'T'
        mov ax, [cs:ptime]
        mov di, fxbuf + 18
        call itoa3
        mov ah, F_FB
        call mark
        mov [cs:fxbuf + 21], al
        mov byte [cs:fxbuf + 22], 'F'
        mov ax, [cs:pfb]
        mov di, fxbuf + 23
        call itoa3
        mov ah, F_RATE
        call mark
        mov [cs:fxbuf + 26], al
        mov byte [cs:fxbuf + 27], 'R'
        mov ax, [cs:prate]
        mov di, fxbuf + 28
        call itoa3
        mov byte [cs:fxbuf + 31], ' '
        pop ax
        ; fall through
; fxbuf -> page 0x0C RAM text (2D95:1402 / 1415); al != 0: also straight to the LCD
fx_out: push ax
        mov ax, DATA_SEG
        mov es, ax
        mov si, fxbuf
        mov di, FXPAGE_L1
        call cpy16
        mov di, FXPAGE_L2
        call cpy16
        pop ax
        or al, al
        jz .r
        mov al, 0x80          ; HD44780: line 1, 16 chars, line 2, 16 chars, cursor off
        call lcd_cmd
        mov si, fxbuf
        call lcd16
        mov al, 0xC0
        call lcd_cmd
        call lcd16
        mov al, 0x0C
        call lcd_cmd
.r:     ret

mark:   mov al, ' '           ; ah = field -> al = '>' if selected
        cmp ah, [cs:fcur]
        jne .m
        mov al, '>'
.m:     ret

itoa3:  push ax               ; ax = 0..999 -> 3 chars right-aligned at cs:di
        push bx
        push dx
        push ax
        mov bx, 10
        xor dx, dx
        div bx
        add dl, '0'
        mov [cs:di + 2], dl
        xor dx, dx
        div bx
        add dl, '0'
        mov [cs:di + 1], dl
        add al, '0'
        mov [cs:di], al
        pop ax
        cmp ax, 100
        jae .d
        mov byte [cs:di], ' '
        cmp ax, 10
        jae .d
        mov byte [cs:di + 1], ' '
.d:     pop dx
        pop bx
        pop ax
        ret

cpy16:  mov cx, 16
.c:     mov al, [cs:si]
        stosb
        inc si
        loop .c
        ret

lcd_wait:                     ; busy flag at 0x62 bit 7 (as 0FE4:07FA), with a timeout
        push ax
        push cx
        mov cx, 4000
.w:     in al, 0x62
        test al, 0x80
        loopnz .w
        pop cx
        pop ax
        ret
lcd_cmd: call lcd_wait
        out 0x62, al
        ret
lcd16:  mov cx, 16            ; cs:si -> LCD data, si advanced
.l:     call lcd_wait
        mov al, [cs:si]
        out 0x60, al
        inc si
        loop .l
        ret

; ---------------------------------------------------------------------------------------------
; FX engine. Reg A function fn = one tap of the 65536-sample delay line (measured, see README):
;   select 0x80 = 0x0A00 | fn; 0x82 = Q15 gain, low 2 bits route (1 L, 0 R, 3 feedback); 0x84 = 2 - delay
; (2345:81B4/81E4 do the same from the int8 table at DS:6D00). Main-loop context only: nothing in the
; ISRs touches 0x80-0x8C (s2k_ui.py isrcheck), so a select + data pair can't be split.
M_FNE     equ 0               ; LFO slot record (scaled copy of the preset's, phase runs in place)
M_FNO     equ 1
M_ROUTE   equ 2
M_GAIN    equ 3
M_CENTER  equ 5
M_DEPTH   equ 7
M_INC     equ 9
M_PHASE   equ 11
MDEF      equ 13
MSLOT     equ 16
P_NAME    equ 0               ; preset record: name[8], fbmax, nstatic, nmod, taps (5 B), slots (MDEF B)
P_FBMAX   equ 8
P_NST     equ 9
P_NMOD    equ 10
P_TAPS    equ 11

; al = fn, bx = gain word, cx = delay (samples, >= 2); keeps all registers
wtap:   push ax
        push dx
        mov ah, 0x0A
        mov dx, ax
        out 0x80, ax
        mov ax, bx
        out 0x82, ax
        mov ax, dx
        out 0x80, ax
        mov ax, 2
        sub ax, cx
        out 0x84, ax
        pop dx
        pop ax
        ret

; ax (unsigned) * bx % -> ax, saturating at 0xFFFF
scaleu: mul bx
        cmp dx, 100
        jae .max
        div word [cs:c100]
        ret
.max:   mov ax, 0xFFFF
        ret

; ax (signed) * bx % -> ax, saturating at +-32767 (keeps idiv from faulting)
scales: imul bx
        cmp dx, 0x31
        jg .pmax
        cmp dx, -0x32
        jl .nmax
        idiv word [cs:c100]
        ret
.pmax:  mov ax, 32767
        ret
.nmax:  mov ax, -32767
        ret

; program preset [cs:fxon] with TIME / FB / RATE: all 30 taps silent, static taps, then LFO slots
; (keepph = 1 keeps the running LFO phases, for parameter edits)
fx_apply:
        pusha
        mov byte [cs:nmods], 0
        mov al, 1
        xor bx, bx
        mov cx, 2
.z:     cmp al, 11
        je .zn
        call wtap
.zn:    inc al
        cmp al, 32
        jb .z
        call presetptr
        mov dl, [cs:si + P_NST]
        mov dh, [cs:si + P_NMOD]
        add si, P_TAPS
.st:    or dl, dl
        jz .md
        push dx
        mov ax, [cs:si + 3]   ; delay * TIME
        mov bx, [cs:ptime]
        call scaleu
        cmp ax, 2
        jae .d2
        mov ax, 2
.d2:    mov cx, ax
        mov ax, [cs:si + 1]   ; gain word; feedback taps * FB
        mov bx, ax
        and bl, 3
        cmp bl, 3
        jne .g
        and al, 0xFC
        mov bx, [cs:pfb]
        call scales
        and al, 0xFC
        or al, 3
.g:     mov bx, ax
        mov al, [cs:si]
        call wtap
        pop dx
        add si, 5
        dec dl
        jmp .st
.md:    push dx               ; (scaleu / scales clobber dx: keep the slot count)
        mov di, mslots
        mov cl, dh
.cp:    or cl, cl
        jz .cpd
        push cx
        mov ax, [cs:si]       ; fnE, fnO
        mov [cs:di + M_FNE], ax
        mov al, [cs:si + 2]
        mov [cs:di + M_ROUTE], al
        mov ax, [cs:si + 3]   ; gain (* FB on feedback slots)
        cmp byte [cs:si + 2], 3
        jne .mg
        mov bx, [cs:pfb]
        call scales
.mg:    mov [cs:di + M_GAIN], ax
        mov ax, [cs:si + 5]   ; center, depth * TIME
        mov bx, [cs:ptime]
        call scaleu
        mov [cs:di + M_CENTER], ax
        mov ax, [cs:si + 7]
        mov bx, [cs:ptime]
        call scaleu
        mov [cs:di + M_DEPTH], ax
        mov ax, [cs:si + 9]   ; phase increment * RATE
        mov bx, [cs:prate]
        call scaleu
        mov [cs:di + M_INC], ax
        cmp byte [cs:keepph], 0
        jne .kp
        mov ax, [cs:si + 11]
        mov [cs:di + M_PHASE], ax
.kp:    pop cx
        add si, MDEF
        add di, MSLOT
        dec cl
        jmp .cp
.cpd:   pop dx
        mov al, [TICK]
        mov [cs:lasttick], al
        mov [cs:nmods], dh
        xor cl, cl
        call lfo_run
        popa
        ret

; main-loop wait (0FE4:000A..001B spins on the tick until 10 have passed): FX page wheel, then the LFO
; slots once per tick. Returns AL = tick like the 2345:0A47 it replaces.
lfo_hook:
        call 0x2345:0x0A47
        push ax
        call fx_poll
        call pm_poll
        call rec_poll
        call LOAD_SEG:0x0000  ; hi code: loads it on the first tick, then runs its tick (src/rosetta_load.asm)
        pop ax
        push ax
        cmp byte [cs:nmods], 0
        je .out
        mov ah, al
        sub ah, [cs:lasttick]
        jz .out
        mov [cs:lasttick], al
        pusha
        mov cl, ah
        call lfo_run
        popa
.out:   pop ax
        retf

; cl = elapsed ticks. Per slot: phase += inc * cl; delay = center + depth * sin(phase) (8.8 fixed);
; integer n and fraction f -> the even-delay tap and the odd-delay tap get g*(1-f) / g*f, so a tap
; only moves (by 2) while its gain is ~0: fractional delay without clicks.
lfo_run:
        mov si, mslots
        mov ch, [cs:nmods]
.sl:    or ch, ch
        jz .done
        push cx
        mov al, cl
        xor ah, ah
        mul word [cs:si + M_INC]
        add [cs:si + M_PHASE], ax
        mov bl, [cs:si + M_PHASE + 1]
        xor bh, bh
        shl bx, 1
        mov ax, [cs:sintab + bx]
        imul word [cs:si + M_DEPTH] ; dx:ax = sin (Q14) * depth (samples)
        mov bx, ax
        shr bx, 6
        and bx, 0xFF                ; f = 1/256 sample
        shl dx, 2
        shr ax, 14
        or dx, ax
        add dx, [cs:si + M_CENTER]  ; n
        push dx
        mov ax, 256
        sub ax, bx
        imul word [cs:si + M_GAIN]
        mov al, ah
        mov ah, dl
        and al, 0xFC
        or al, [cs:si + M_ROUTE]
        mov di, ax                  ; gain word at delay n
        mov ax, bx
        imul word [cs:si + M_GAIN]
        mov al, ah
        mov ah, dl
        and al, 0xFC
        or al, [cs:si + M_ROUTE]
        mov bp, ax                  ; gain word at delay n + 1
        pop cx                      ; n
        mov al, [cs:si + M_FNE]
        mov ah, [cs:si + M_FNO]
        test cl, 1
        jz .even
        xchg al, ah                 ; n odd: the odd tap takes delay n
.even:  mov bx, di
        call wtap
        mov al, ah
        mov bx, bp
        inc cx
        call wtap
        pop cx
        add si, MSLOT
        dec ch
        jmp .sl
.done:  ret

; ---------------------------------------------------------------------------------------------
fcur:     db 0                ; selected field
onfx:     db 0                ; FX page is showing (cleared by page0_hook on any mode entry)
wasfx:    db 0                ; ... and was showing when this mode entry started
keepph:   db 0
nmods:    db 0
lasttick: db 0
pwet:     dw 50
ptime:    dw 100
pfb:      dw 0                 ; boot preset OFF has no feedback (fbmax 0)
prate:    dw 100
c100:     dw 100
fparam:   dw 0, pwet, ptime, pfb, prate
fmin:     dw 0, 0, 25, 0, 10
fmax:     dw 0, 99, 200, 0, 400           ; FB max is per preset (fbmax)
fxbuf:    times 32 db ' '
mslots:   times 4 * MSLOT db 0

%include "fx_presets.inc"
