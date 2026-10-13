; Rosetta sampling screen (menu redesign M3b, docs/menu_design.md). Included by rosetta_menu.asm.
;
; REC opens straight on the stock record page (mode 4 page 5: input meter + ARM, normally hidden behind GROUP):
;     ||||||||||||||
;     SETUP        ARM        (line 2 text patched by mkbaby.py)
; Right soft key = ARM (stock: arms, then the left key starts now / threshold starts, right = ABORT).
; Left soft key = SETUP -> REC Length/B/W (stock pages 0-4: name, length+B/W, start+type, orig pitch,
; threshold). The home key on a setup page comes back to the meter (top_page), from the meter -> HOME.
; A finished take (not an abort) lands on the sample select page (EDIT SAMPLE page 0, the new sample is current),
; inside the SAMPLE+PITCH group of the EDIT SAMPLE menu.

MODE_REC  equ 4
REC_ARM   equ 5               ; mode 4 page 5 = meter + ARM
REC_SETUP equ 1               ; mode 4 page 1 = REC Length B/W

; key_hook: soft key al (0x40 | n) in REC mode. CF = 1 if consumed.
rec_key:
        cmp byte [PAGE], REC_ARM
        jne .no
        cmp al, 0x40                  ; left = SETUP
        jne .no
        mov byte [PAGE], REC_SETUP
        call redraw
        stc
        ret
.no:    clc
        ret

; 0FE4:3CE7 (the end of a kept take, replaces `mov byte [8215],0`): flag it for rec_poll
rec_done:
        mov byte [0x8215], 0
        mov byte [cs:recdone], 1
        pusha
        push es
        mov ax, LOG_SEG
        mov es, ax
        or byte [es:3], 4             ; log: kept
        mov si, 0x7A30
        mov di, 0x3E0
        mov cx, 0x60
        call logcpy
        mov si, 0x87A0
        mov cx, 0x30
        call logcpy
        pop es
        popa
        retf

; ---------------------------------------------------------------------------------------------
; Hold-to-record (step 1): the REC key starts an armed take at once (like the left soft key), and a
; probe logs the record engine's bookkeeping during the take (and the moment REC is let go) to
; LOG_SEG:0000, read back over the SysEx lab (tools/reclog.py), to build "stop on release" from.
KEY_REC   equ 0xC2                    ; mode key 2 = REC
LOG_SEG   equ 0x3E50                  ; 0x3E500: past the boot dragon (only runs at boot), below MENU_SEG

; 0FE4:3AA0 (armed loop's key read, replaces `mov al,[73D4]` + `mov byte [73D4],0`)
rec_armkey:
        cmp byte [cs:armed], 0
        jne .k
        mov byte [cs:armed], 1        ; first pass of this arm: no hold yet
        mov byte [cs:hold], 0
.k:     mov al, [KEYEV]
        mov byte [KEYEV], 0
        cmp al, KEY_REC
        jne .r
        mov byte [cs:hold], 1
        mov al, 0x40                  ; = left soft key: start now
.r:     retf

; 0FE4:3B2C (recording loop's key read, same bytes): log, watch the REC key
rec_loopkey:
        mov al, [KEYEV]
        mov byte [KEYEV], 0
        pusha
        push es
        mov ax, LOG_SEG
        mov es, ax
        cmp byte [cs:armed], 0
        je .go
        mov byte [cs:armed], 0        ; first pass of a take: fresh log + the start state
        mov word [es:0], 'RL'
        mov byte [es:2], 0
        mov al, [cs:hold]
        mov [es:3], al                ; bit0 hold, bit1 released, bit2 kept
        mov byte [cs:lastprog], 0xFF
        mov si, 0x7500
        mov di, 0x10
        mov cx, 0x10
        call logcpy                   ; 0x10: 7500-750F
        mov si, 0x7A30
        mov cx, 0x60
        call logcpy                   ; 0x20: 7A30-7A8F
        mov si, 0x87A0
        mov cx, 0x30
        call logcpy                   ; 0x80: 87A0-87CF
        mov si, 0x7538
        mov cx, 0x10
        call logcpy                   ; 0xB0: 7538-7547
.go:    xor dl, dl                    ; dl = snapshot flags
        test byte [es:3], 1
        jz .p
        test byte [es:3], 2
        jnz .p
        mov al, 0x7F                  ; REC key = matrix row 7, col 1 (active low)
        out 0x52, al
        in al, 0x50
        test al, 2
        jz .p
        or byte [es:3], 2             ; let go: flag it, snapshot + the big block
        mov dl, 1
        mov si, 0x7A30
        mov di, 0x380
        mov cx, 0x60
        call logcpy
.p:     mov al, [0x7A7C]
        cmp al, [cs:lastprog]
        jne .snap
        or dl, dl
        jz .x
.snap:  mov [cs:lastprog], al
        mov bl, [es:2]
        cmp bl, 40
        jae .x
        inc byte [es:2]
        xor bh, bh
        shl bx, 4
        lea di, [bx + 0x100]
        call 0x2345:0x0A47            ; tick
        stosb
        mov al, dl
        stosb
        mov si, 0x7A7C
        mov cx, 2
        call logcpy
        mov si, 0x7A62
        mov cx, 6
        call logcpy
        mov si, 0x7A5E
        mov cx, 4
        call logcpy
        mov si, 0x7A74
        mov cx, 2
        call logcpy
.x:     pop es
        popa
        retf

logcpy: mov al, [si]                  ; cx bytes DS:si -> es:di
        stosb
        inc si
        loop logcpy
        ret

; main-loop wait: after a take, go to the sample select page (after the record routine has returned)
rec_poll:
        cmp byte [cs:recdone], 0
        je .r
        mov byte [cs:recdone], 0
        pusha
        push es
        cmp byte [EB16], 0
        jne .stock
        mov byte [cs:area], 1         ; EDIT SAMPLE menu, group 1 (SAMPLE+PITCH, starts on page 0)
        mov byte [cs:a_sel + 1], 0
        mov byte [cs:ctx], CTX_MENU
        call pm_enter
        jmp .done
.stock: mov byte [MODE], 5
        mov byte [PAGE], 0
        call redraw
.done:  pop es
        popa
.r:     ret

recdone:  db 0
armed:    db 0                ; 1 while armed (set on the armed loop's first pass, cleared when the take starts)
hold:     db 0                ; the take was started with the REC key
lastprog: db 0
