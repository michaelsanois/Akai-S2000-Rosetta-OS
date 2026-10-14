; Rosetta hi code: CPU RAM 4000:0000-FFFF (64 KB the OS never touches), stored on the boot floppy right
; after the 256 KB OS file and read in after boot by src/rosetta_load.asm. Room for the big features.
;
; The OS is all RAM, so hi_init hooks it at run time (patch table below, every stock byte checked first):
; nothing points at the hi code unless it really loaded. The OS hooks call fixed slots in the header, so a
; new build can be sent into a running S2000 over SysEx (tools/hiload.py): the loader's tick is parked,
; the blob uploaded, the hooks re-pointed from the blob's patch table, and its tick runs `apply` itself.
;
; SYNTH basics (0.20), per voice, all 0 = exactly stock:
;   CC 20 DRIFT     analog-style slow random pitch wander, up to +-20 cents
;   CC 21 DRIFT SPD how fast it wanders
;   CC 22 DETUNE    fixed per-voice detune spread, up to +-25 cents (voices rotate, so every note differs)
;   CC 23 FLT LFO   filter LFO depth: the cutoff dips from where the program sets it and comes back (on hw,
;                   127 = down ~2000 log steps, highs -30 dB+; the top ~800 steps of an open filter are inaudible)
;   CC 24 LFO RATE  0.03-10 Hz
;   CC 25 LFO SPRD  per-voice LFO phase spread (0 = all voices together, 127 = all different)
; Hooks: 2345:5611 (every pitch write: note-on + the ~15 ms update, pitch = semitone * 256) and 2345:59CD
; (every cutoff target, log 0-FFF, the chip glides to it), 2B9D:01AE (MIDI CC in, any channel).
        cpu 186
        bits 16
        org 0
%ifndef HI_VERSION
HI_VERSION equ 0
%endif
HI_SEG    equ 0x4000
POPUP     equ 0x8FE0          ; OS popup text buffer in segment 0 (2 x 16 chars + FF)
NVOICE    equ 32
CC_FIRST  equ 20
NCC       equ 6
RETF_2345 equ 0x27CB          ; a retf in segment 2345 (near-call trick)

        db "RSHI"             ; +0 magic
        dw HI_VERSION         ; +4
        jmp near hi_init      ; +6 once, right after loading
        jmp near hi_tick      ; +9 every main-loop tick: keep all registers
        jmp near pitch_in     ; +C  from 2345:5611
        jmp near cut_tgt      ; +F  from 2345:59CD
        jmp near cc_in        ; +12 from 2B9D:01AE
        dw patches            ; +15 for tools/hiload.py

hi_init:
        pusha
        push es
        call apply
        mov byte [cs:inited], 1
        mov si, msg_ok
        cmp byte [cs:pfail], 0
        je .m
        mov si, msg_pf
.m:     call popup
        pop es
        popa
        retf

; patch table: dw seg, off / db n / n stock bytes / n new bytes; seg 0 ends it
apply:  mov si, patches
.p:     mov ax, [cs:si]
        or ax, ax
        jz .r
        mov es, ax
        mov di, [cs:si + 2]
        mov cl, [cs:si + 4]
        xor ch, ch
        add si, 5
        push si
        push di
        push cx
.cmp:   mov al, [cs:si]
        cmp al, [es:di]
        jne .bad
        inc si
        inc di
        loop .cmp
        pop cx
        pop di
        pop si
        add si, cx
.cp:    mov al, [cs:si]
        mov [es:di], al
        inc si
        inc di
        loop .cp
        jmp .p
.bad:   pop cx                ; not stock: fine if it already holds our bytes (hot reload)
        pop di
        pop si
        push si
        push di
        push cx
        add si, cx
.cmp2:  mov al, [cs:si]
        cmp al, [es:di]
        jne .bad2
        inc si
        inc di
        loop .cmp2
        pop cx
        pop di
        pop si
        add si, cx
        add si, cx
        jmp .p
.bad2:  pop cx
        pop di
        pop si
        add si, cx
        add si, cx
        mov byte [cs:pfail], 1
        jmp .p
.r:     ret

patches:
        dw 0x2345, 0x5611     ; push cs / call 52A3 / add ax,[si+0B6h]  ->  pitch_in
        db 8
        db 0x0E, 0xE8, 0x8E, 0xFC, 0x03, 0x84, 0xB6, 0x00
        db 0x9A
        dw 0x000C, HI_SEG
        db 0x90, 0x90, 0x90
        dw 0x2345, 0x59CD     ; call 59A5 / mov dx,ax  ->  cut_tgt
        db 5
        db 0xE8, 0xD5, 0xFF, 0x8B, 0xD0
        db 0x9A
        dw 0x000F, HI_SEG
        dw 0x2B9D, 0x01AE     ; cmp dl,7Ah / jb 01E0  ->  cc_in
        db 5
        db 0x80, 0xFA, 0x7A, 0x72, 0x2D
        db 0x9A
        dw 0x0012, HI_SEG
        dw 0

; ---------------------------------------------------------------------------------------------
; 2345:5611: ax = pitch (semitone * 256), bl = voice. Stock: push cs / call 52A3 (pitch -> chip rate) /
; add ax,[si+0B6h] (fine offset on the rate).
pitch_in:
        push bx
        and bx, NVOICE - 1
        shl bx, 1
        add ax, [cs:poff + bx]
        pop bx
        call 0x2345:0x52A3
        add ax, [si + 0xB6]
        retf

; 2345:59CD: the cutoff target (log 0-FFF) for voice bl, then dx = it. Stock: call 59A5 / mov dx,ax.
cut_tgt:
        push cs
        push .back
        push RETF_2345
        jmp 0x2345:0x59A5     ; near routine: its ret lands on the retf at 2345:27CB
.back:  push bx
        and bx, NVOICE - 1
        shl bx, 1
        mov bx, [cs:coff + bx]
        or bx, bx
        jz .s                 ; no LFO on this voice: exactly stock
        add ax, bx
        jns .l
        xor ax, ax
.l:     cmp ax, 0x0FFF
        jbe .s
        mov ax, 0x0FFF
.s:     pop bx
        mov dx, ax
        retf

; 2B9D:01AE: control change, dl = controller, dh = value. Ours are kept (the stock code still sees them).
; Stock: cmp dl,7Ah / jb 01E0 (else 01B3).
cc_in:  push bp
        mov bp, sp
        cmp dl, CC_FIRST
        jb .stock
        cmp dl, CC_FIRST + NCC
        jae .stock
        push bx
        mov bl, dl
        sub bl, CC_FIRST
        xor bh, bh
        mov [cs:par + bx], dh
        pop bx
.stock: mov word [bp + 2], 0x01E0
        cmp dl, 0x7A
        jb .r
        mov word [bp + 2], 0x01B3
.r:     pop bp
        retf

; ---------------------------------------------------------------------------------------------
; every main-loop tick: advance the LFO + drift by the OS ticks since the last call (0.511 ms each), recompute the
; per-voice offsets
hi_tick:
        pusha
        push es
        cmp byte [cs:inited], 0
        jne .go
        mov byte [cs:inited], 1   ; sent in over SysEx: hook the OS ourselves
        call apply
.go:        call 0x2345:0x0A47    ; al = tick
        mov ah, al
        sub ah, [cs:lasttick]
        jz .out
        mov [cs:lasttick], al
        mov cl, ah            ; ticks since the last run
        xor ch, ch
        mov [cs:nt], cl
        ; filter LFO phase: inc = 1 + rate^2 / 48 per tick (OS tick [73DA] = 0.511 ms on hw, 1957 Hz:
        ; 0.03-10 Hz)
        mov al, [cs:par + 4]
        mul al
        mov bx, 48
        xor dx, dx
        div bx
        inc ax
        mul cx
        add [cs:lphase], ax
        ; drift: now and then one voice gets a new random target (every 160 ticks slow .. 33 fast, so each
        ; voice every ~2.6 .. 0.55 s); every 32 ticks (16 ms) all voices slew toward theirs
        add [cs:racc], cl
        mov al, [cs:par + 1]
        neg al
        add al, 160
        cmp [cs:racc], al
        jb .d1
        mov byte [cs:racc], 0
        call rnd
        sar ax, 1             ; Q14: tgt - pos can't overflow
        mov bx, [cs:dnext]
        inc word [cs:dnext]
        and bx, NVOICE - 1
        shl bx, 1
        mov [cs:dtgt + bx], ax
.d1:    add [cs:dacc], cl
        cmp byte [cs:dacc], 32
        jb .calc
        mov byte [cs:dacc], 0
        mov si, 0             ; pos += (tgt - pos) >> shift: 7 (~2 s) slow .. 4 (~0.25 s) fast
        mov cl, [cs:par + 1]
        shr cl, 5             ; 0..3
        neg cl
        add cl, 7             ; 7..4
.sl:    mov ax, [cs:dtgt + si]
        sub ax, [cs:dpos + si]
        sar ax, cl
        add [cs:dpos + si], ax
        add si, 2
        cmp si, 2 * NVOICE
        jb .sl
.calc:  mov al, [cs:nt]        ; per-voice offsets every 8 ticks (4 ms; the OS updates a voice every ~15 ms),
        add [cs:cacc], al     ; and not at all while every control is 0 (after one pass that zeroes them)
        cmp byte [cs:cacc], 8
        jb .out
        mov byte [cs:cacc], 0
        mov al, [cs:par + 0]
        or al, [cs:par + 2]
        or al, [cs:par + 3]
        mov ah, al
        or al, [cs:cbusy]
        jz .out
        mov [cs:cbusy], ah
        xor si, si            ; voice * 2
.v:     ; pitch offset = drift pos (Q14) * drift amt, scaled to +-50 units, + detune tab * detune amt / 256
        mov ax, [cs:dpos + si]
        mov bl, [cs:par + 0]
        xor bh, bh
        imul bx               ; dx:ax = pos * amt (Q14 * 0..127)
        mov ax, dx            ; >> 16: +-31
        mov bx, 51
        imul bx
        sar ax, 5             ; +-50 units = +-20 cents
        mov di, ax
        mov bx, si
        shr bx, 1
        mov al, [cs:dtab + bx]
        cbw
        mov bl, [cs:par + 2]
        xor bh, bh
        imul bx               ; -128..127 * 0..127
        sar ax, 8             ; +-63 units = +-25 cents
        add ax, di
        mov [cs:poff + si], ax
        ; cutoff offset = sin(phase + voice spread) * depth * 8 (log units)
        xor ax, ax
        mov bl, [cs:par + 3]
        or bl, bl
        jz .c0
        mov ax, si
        shr ax, 1
        mov bh, [cs:par + 5]
        mul bh                ; voice * spread (0..31 * 127)
        shl ax, 3             ; spread 127: voices spaced ~1/8 turn
        add ax, [cs:lphase]
        mov bl, ah            ; 256-step table
        xor bh, bh
        shl bx, 1
        mov ax, [cs:hsin + bx]    ; Q14
        sub ax, 16384         ; -32768..0: the cutoff dips from the set value and comes back
        mov bl, [cs:par + 3]
        xor bh, bh
        shl bx, 4             ; depth * 16: down to -2032
        imul bx
        shl ax, 1
        rcl dx, 1
        mov ax, dx            ; >> 15
.c0:    mov [cs:coff + si], ax
        add si, 2
        cmp si, 2 * NVOICE
        jb .v
.out:   inc word [cs:ticks]
        pop es
        popa
        retf

; ax = 16-bit random (xorshift)
rnd:    mov ax, [cs:seed]
        mov dx, ax
        shl dx, 7
        xor ax, dx
        mov dx, ax
        shr dx, 9
        xor ax, dx
        mov dx, ax
        shl dx, 8
        xor ax, dx
        mov [cs:seed], ax
        ret

; cs:si = 2 x 16 chars -> the OS popup buffer, shown for a few seconds (0FE4:0D4E, DS = 0).
; Clobbers ax, bx, si.
popup:  push es
        push di
        push cx
        xor ax, ax
        mov es, ax
        mov di, POPUP
        mov cx, 32
.c:     cs lodsb
        stosb
        loop .c
        mov al, 0xFF
        stosb
        mov bx, POPUP
        call 0x0FE4:0x0D4E
        pop cx
        pop di
        pop es
        ret

ticks:    dw 0
pfail:    db 0
inited:   db 0
lasttick: db 0
dacc:     db 0
racc:     db 0
cacc:     db 0
cbusy:    db 0                ; the last pass had a control on
nt:       db 0
par:     times NCC db 0      ; CC 20-25: drift, drift speed, detune, filter LFO depth, rate, spread
          db 0
seed:     dw 0xACE1
dnext:    dw 0
lphase:   dw 0
poff:     times NVOICE dw 0   ; per-voice pitch offset (1/256 semitone)
coff:     times NVOICE dw 0   ; per-voice cutoff offset (log units, 0 = off)
dpos:     times NVOICE dw 0   ; drift position (Q15)
dtgt:     times NVOICE dw 0   ; drift target (Q15)
msg_ok:   db "ROSETTA+ READY  SYNTH CC 20-25  "
msg_pf:   db "ROSETTA+ READY  PATCH MISMATCH! "

%include "hi_tables.inc"      ; hsin (256 x Q14), dtab (32 x signed detune spread), from mkbaby.py
