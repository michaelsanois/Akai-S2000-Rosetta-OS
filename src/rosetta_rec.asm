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
        mov byte [cs:intake], 0
        retf

; ---------------------------------------------------------------------------------------------
; REC key = start / stop. Armed (`About to record  GO  EXIT`), the REC key starts the take at once.
; Held: the take stops when REC is let go. Tapped (let go within ~0.3 s): it runs until REC is pressed
; again. Either way the sample is cut to what was recorded (mono; stereo takes run their full length).
;
; Stock take (0.16 probe, docs/menu_design.md): the record loop runs 16 progress steps; each step
; (2345:2781) waits on the audio DMA ring (2345:27EB `call 27F8`) until [7A68..7A6C] more bytes have come
; in, then 2345:2819 bumps [7A7C]; at 16 the loop ends and 0FE4:3B77 stops the chip and builds the sample
; from [87BA] = length + 1. Stopping early = end this step now, [7A7C] = 15, and [87BA] = recorded + 1.
KEY_REC   equ 0xC2                    ; mode key 2 = REC
TAP_BYTES equ 0x6000                  ; ~0.28 s of mono 44.1 kHz DMA: shorter hold = tap (latch)

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
        mov byte [cs:armed], 0
        mov byte [cs:hold], 1
        xor ax, ax
        mov [cs:phase], al            ; (also dfirst, stopping)
        mov [cs:dfirst], al
        mov [cs:stopping], al
        mov [cs:dbytes], ax
        mov [cs:dbytes + 2], ax
        mov al, 0x40                  ; = left soft key (GO): start now
.r:     retf

; 2345:27EB (a record step's DMA wait, replaces `call 27F8` + `jb 27F7`). Returns to 27F0 (copy the new
; chunk, wait on) or, when the wait is over, to 27F7 (its ret).
rec_wait:
        cmp byte [cs:intake], 0
        jne .go
        call take_start
.go:    cmp byte [cs:hold], 0
        je .wait
        cmp byte [cs:stopping], 0
        jne .done
        pusha
        call rec_track
        popa
        cmp byte [cs:stopping], 0
        jne .done
.wait:  push cs                       ; near-call 2345:27F8: its ret lands on the retf at 2345:27CB
        push .back
        push 0x27CB
        jmp 0x2345:0x27F8
.back:  jc .done
        retf
.done:  push bp
        mov bp, sp
        mov word [bp + 2], 0x27F7
        pop bp
        retf

; first record step of a take (0.30): the next ARM starts fresh; a take not started with the REC key
; (ARM threshold, GO, MIDI start, Bridge) is tracked as latched, so REC or Bridge's STOP ends it
take_start:
        mov byte [cs:intake], 1
        mov byte [cs:armed], 0
        push ax
        mov ax, [RXWP]                ; Bridge's STOP: only MIDI bytes from now on count
        mov [cs:rxpos], ax
        mov byte [cs:rst], 0
        cmp byte [cs:hold], 0
        jne .h
        mov byte [cs:hold], 1
        mov byte [cs:phase], 2
        xor ax, ax
        mov [cs:dfirst], al
        mov [cs:stopping], al
        mov [cs:dbytes], ax
        mov [cs:dbytes + 2], ax
.h:     pop ax
        ret

; count the DMA bytes since the start, watch the REC key, stop when it says so (pusha'd, DS = 0)
rec_track:
        cmp byte [0x7500], 0          ; stereo: full length (cutting it isn't worked out yet)
        jne .r
        call rscan                    ; Bridge's STOP (0.30)
        jc rec_stop
        mov dx, 0xC001
        mov al, 2
        out dx, al
        mov dx, 0xC004
        in ax, dx
        mov cx, ax
        sub ax, [cs:dprev]
        and ax, 0x1FFF                ; ring of 0x2000 bytes
        cmp byte [cs:dfirst], 0
        jne .acc
        mov byte [cs:dfirst], 1       ; first look: just the reference
        xor ax, ax
.acc:   mov [cs:dprev], cx
        add [cs:dbytes], ax
        adc word [cs:dbytes + 2], 0
        mov al, 0x7F                  ; REC key: matrix row 7, col 1, low = down
        out 0x52, al
        in al, 0x50
        mov bl, [cs:phase]            ; 0 held, 1 tapped (waiting for it to settle up), 2 latched
        test al, 2
        jz .down
        or bl, bl
        jnz .up12
        cmp word [cs:dbytes + 2], 0   ; let go: after a hold = stop, after a tap = latch
        jne rec_stop
        cmp word [cs:dbytes], TAP_BYTES
        jae rec_stop
        mov byte [cs:phase], 1
        mov ax, [cs:dbytes]
        mov [cs:tapat], ax
.r:     ret
.up12:  cmp bl, 1                     ; tapped: latch once it has stayed up ~23 ms (no bounce)
        jne .r
        mov ax, [cs:dbytes]
        sub ax, [cs:tapat]
        cmp ax, 0x1000
        jb .r
        mov byte [cs:phase], 2
        ret
.down:  cmp bl, 2                     ; latched + pressed again = stop
        jne .r
        mov byte [cs:eatrec], 1       ; and that press mustn't open REC again afterwards
        ; fall through
; recorded samples = DMA bytes >> k (2^k DMA bytes per sample: 16 steps of [7A6A..] bytes = the length)
rec_stop:
        mov byte [cs:stopping], 1
        mov ax, [0x87BA]
        mov dx, [0x87BC]
        sub ax, 1
        sbb dx, 0                     ; dx:ax = L
        mov si, [0x7A6A]
        mov di, [0x7A6C]
        mov cx, 4
.t:     shl si, 1
        rcl di, 1
        loop .t                       ; di:si = 16 steps of bytes (integer part)
        mov bx, ax
        mov bp, dx
        shr bp, 1
        rcr bx, 1
        add bx, ax
        adc bp, dx                    ; bp:bx = 1.5 L
.k:     cmp di, bp                    ; bytes < 1.5 L * 2^k -> k
        jb .kd
        ja .kn
        cmp si, bx
        jb .kd
.kn:    shl bx, 1
        rcl bp, 1
        inc cl
        cmp cl, 3
        jb .k
.kd:    mov ax, [cs:dbytes]
        mov dx, [cs:dbytes + 2]
        jcxz .n
.sh:    shr dx, 1
        rcr ax, 1
        loop .sh
.n:     cmp dx, 0                     ; at least 0x1000 samples (the stock minimum)
        jne .min
        cmp ax, 0x1000
        jae .min
        mov ax, 0x1000
.min:   add ax, 1
        adc dx, 0                     ; + 1, as [87BA] holds it
        cmp dx, [0x87BC]              ; only ever shorter
        ja .end
        jb .set
        cmp ax, [0x87BA]
        jae .end
.set:   mov [0x87BA], ax
        mov [0x87BC], dx
.end:   xor ax, ax                    ; end this step now, and the take after it
        mov [0x7A6E], ax
        mov [0x7A70], ax
        mov [0x7A72], ax
        mov byte [0x7A7C], 15
        ret

; Bridge's STOP during a take (0.30): the OS doesn't parse MIDI while it records, but the rx ISR still fills
; its ring (page 0x0300, write pointer [73A0]). Look through the bytes since the last look for F0 7D 53 0C
; (MIDI real-time bytes can sit anywhere in it). CF = 1: seen. (pusha'd, DS = 0)
RXWP      equ 0x73A0
rscan:  mov si, [cs:rxpos]
        mov bl, [cs:rst]
        xor bh, bh
.l:     cmp si, [RXWP]
        je .no
        mov al, [si]
        inc si
        and si, 0x00FF
        or si, 0x0300
        cmp al, 0xF8
        jae .l
        cmp al, [cs:rpat + bx]
        jne .miss
        inc bx
        cmp bl, 4
        jb .l
        mov [cs:rxpos], si
        mov byte [cs:rst], 0
        stc
        ret
.miss:  xor bl, bl
        cmp al, 0xF0
        jne .l
        inc bl
        jmp short .l
.no:    mov [cs:rxpos], si
        mov [cs:rst], bl
        clc
        ret
rpat:   db 0xF0, 0x7D, 0x53, 0x0C

; main-loop wait: after a take, go to the sample select page (after the record routine has returned);
; time out the "eat the stopping REC press" window. The main loop doesn't run while armed or recording,
; so here no take is under way (0.30: an aborted ARM or take starts the next one fresh).
rec_poll:
        mov byte [cs:armed], 0
        mov byte [cs:intake], 0
        cmp byte [cs:eatrec], 0
        je .t
        call 0x2345:0x0A47            ; al = tick
        cmp byte [cs:eatrec], 1
        jne .e2
        mov [cs:eattick], al
        mov byte [cs:eatrec], 2
.e2:    sub al, [cs:eattick]
        cmp al, 120                   ; ~0.3 s
        jb .t
        mov byte [cs:eatrec], 0
.t:     cmp byte [cs:recdone], 0
        je .r
        mov byte [cs:recdone], 0
        pusha
        push es
        mov al, 0x4D                  ; take done (0.30, Bridge): F0 7D 53 4D <frames: 8 nibbles> <stereo: 2> F7
        call tx_head
        mov ax, [0x87BA]              ; = frames + 1
        mov dx, [0x87BC]
        sub ax, 1
        sbb dx, 0
        xchg ax, dx
        call tx_w
        mov ax, dx
        call tx_w
        mov al, [0x7500]
        call tx_b
        call tx_end
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

; key_hook: the REC press that stopped a latched take arrives after it (debounce): eat it once, if it
; comes within ~0.3 s (rec_poll times that out). CF = 1: eat it.
rec_eat:
        cmp byte [cs:eatrec], 0
        je .no
        mov byte [cs:eatrec], 0
        stc
        ret
.no:    clc
        ret

recdone:  db 0
intake:   db 0                ; a take is running (set by its first record step)
rst:      db 0                ; rscan: how much of F0 7D 53 0C has matched
rxpos:    dw 0                ; rscan: next rx ring byte to look at
armed:    db 0                ; set on the armed loop's first pass, cleared when REC starts the take
hold:     db 0                ; the take was started with the REC key
phase:    db 0
dfirst:   db 0
stopping: db 0
eatrec:   db 0                ; 1 = set by a latched stop, 2 = timing out (from eattick)
eattick:  db 0
dprev:    dw 0
tapat:    dw 0
dbytes:   dd 0
