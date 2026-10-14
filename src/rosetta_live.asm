; LIVE input FX (0.23, EXPERIMENTAL: does not pass audio yet). Included by rosetta_hi.asm, runs from its tick.
; On hw (0.23 lab) this start gives a running DMA ring that only carries DC: the chip must be put in its input
; mode first (`out 88h, 150h`, 2345:3078: DMA ch3 ring -> chip, voices 0/10h/15h/17h), and that mode clashes
; with the sample-RAM DMA (2345:1B66) the copy here and the reverse engine use. Next: build on the OS mode.
;
; The S2000 only reads its input on the SAMPLE page: the OS points DMA channel 2 at an 8 KB ring in CPU RAM
; (0:90D0, autoinit, 2345:1FD9), unmasks it, pulses an ADC reset (board latch port C0 bit 5, shadow [7349])
; and sets latch bit 3 (bit 4 too for stereo): from then on every input sample lands in the ring (hw 0.22
; lab). Here the input keeps streaming in any mode; each 256 new samples are copied (OS sample-RAM DMA
; 2345:1AC8, straight from the ring) into a 16K-sample ring in sample RAM, and reserved voice 25 plays that
; ring 1024 samples (23 ms) behind the newest input, looping (16K ring), on the chip's own clock (the ADC's too).
; The voice sends into the delay line, so every FX preset (reverse included) works on the input.
;   CC 30 LIVE      input into the FX (send level), 0 = off
;   CC 31 LIVE DRY  the input itself on the S2000's outs (the S2000 has no analog monitoring)
; Mono, left input.

LV_VOICE  equ 25              ; odd: the sample-RAM DMA rewrites the even voices' high address bits
LV_HI     equ 0xFD            ; ring at sample RAM word FD0000 (below the reverse buffers)
LV_LEN    equ 16384           ; words (0.37 s); a loop length of 0x8000+ reads as negative on the chip (noise)
LV_SL     equ 256             ; words per copy
LV_LAT    equ 1024            ; the voice starts this far behind
RING      equ 0x90D0          ; the OS's input ring (segment 0), 0x2000 bytes
LATCH     equ 0x7349          ; shadow of board latch port C0

live_run:
        mov al, [cs:par + 10]
        or al, al
        jnz .on
        cmp byte [cs:lv_act], 0
        je .r
        jmp live_stop
.on:    cmp byte [cs:lv_act], 0
        jne .run
        call live_start
.run:   push es
        mov ax, 0x2D95
        mov es, ax
        or byte [es:VOICES + LV_VOICE * 0x1BC + 0x14D], 1
        pop es
        call live_stream
        call live_copy
        call live_copy        ; up to 2 slices a pass
        call live_mix
.r:     ret

live_start:
        mov byte [cs:lv_act], 1
        mov byte [cs:lv_on], 0    ; voice not started yet
        mov word [cs:lv_w], 0
        mov byte [cs:lv_mine], 0
        mov word [cs:lv_lr], 0xFFFF   ; force a level write
        call live_stream
        call live_dmapos
        mov [cs:lv_rd], ax
        ret

; the input streams while latch bit 3 is on; if it's off (any page but SAMPLE), switch it on like the OS
live_stream:
        test byte [LATCH], 0x08
        jnz .r
        call 0x2345:0x1FD9    ; DMA ch2 -> 0:90D0 ring, autoinit
        mov cl, 4
        call 0x2345:0x2644    ; unmask ch2
        mov al, [LATCH]       ; ADC reset pulse (0FE4:51DC)
        and al, 0xE7
        or al, 0x20
        out 0xC0, al
        mov [LATCH], al
        and al, 0xDF
        out 0xC0, al
        mov [LATCH], al
        mov ax, 0x5D          ; the OS lets it settle ~85 ms
.w:     mov cx, 0x7D0
.w1:    loop .w1
        dec ax
        jnz .w
        mov al, [LATCH]
        or al, 0x08           ; input on (mono)
        out 0xC0, al
        mov [LATCH], al
        mov byte [cs:lv_mine], 1
        call live_dmapos
        mov [cs:lv_rd], ax
.r:     ret

live_dmapos:                  ; ax = byte offset in the ring where DMA writes next
        mov dx, 0xC001
        mov al, 2
        out dx, al
        mov dx, 0xC004
        in ax, dx
        sub ax, RING
        and ax, 0x1FFE
        ret

; copy one slice if there is one; start the voice once LV_LAT samples are in
live_copy:
        call live_dmapos
        sub ax, [cs:lv_rd]
        and ax, 0x1FFF
        cmp ax, LV_SL * 2
        jb .r
        push word [0x78E4]
        push word [0x78E6]
        mov ax, [cs:lv_w]
        mov [0x78E4], ax
        mov word [0x78E6], LV_HI
        mov cx, LV_SL
        xor dx, dx            ; segment 0
        mov si, RING
        add si, [cs:lv_rd]
        call 0x2345:0x1AC8    ; ring -> sample RAM
        pop word [0x78E6]
        pop word [0x78E4]
        mov ax, [cs:lv_rd]
        add ax, LV_SL * 2
        and ax, 0x1FFF
        mov [cs:lv_rd], ax
        mov ax, [cs:lv_w]
        add ax, LV_SL
        and ax, LV_LEN - 1
        mov [cs:lv_w], ax
        cmp byte [cs:lv_on], 0
        jne .r
        cmp ax, LV_LAT
        jb .r
        mov byte [cs:lv_on], 1    ; the voice loops the whole ring from its start, LV_LAT behind
        mov bl, LV_VOICE
        mov byte [cs:vs_hi], LV_HI
        mov word [cs:vs_len], LV_LEN
        mov word [cs:vs_rate], 0x1000
        mov word [cs:vs_lvl], 0x3F80
        call live_levels
        call vstart
.r:     ret

; send + dry from CC 30/31 into vs_send / vs_lr; rewrite the running voice's reg 7 when they change
live_levels:
        mov al, [cs:par + 10]
        shl al, 1
        mov ah, al
        mov al, 0x0F          ; send << 8 | dest delay line
        mov [cs:vs_send], ax
        mov al, [cs:par + 11]
        shl al, 1
        mov ah, al            ; L = R = dry
        mov [cs:vs_lr], ax
        ret

live_mix:
        cmp byte [cs:lv_on], 0
        je .r
        mov al, [cs:par + 10]
        mov ah, [cs:par + 11]
        cmp ax, [cs:lv_lr]
        je .r
        mov [cs:lv_lr], ax
        call live_levels
        mov bl, LV_VOICE
        VSEL 7
        mov ax, [cs:vs_lr]
        out 0x82, ax
        mov ax, [cs:vs_send]
        out 0x84, ax
.r:     ret

live_stop:
        mov byte [cs:lv_act], 0
        cmp byte [cs:lv_on], 0
        je .v
        mov bl, LV_VOICE
        mov word [cs:vs_lvl], 0x3F80
        call vfade
.v:     push es
        mov ax, 0x2D95
        mov es, ax
        and byte [es:VOICES + LV_VOICE * 0x1BC + 0x14D], 0xFE
        pop es
        cmp byte [cs:lv_mine], 0  ; switch the input off again if we switched it on, unless the SAMPLE page
        je .r                     ; (mode 4) has it
        cmp byte [0x762B], 4
        je .r
        mov al, [LATCH]           ; as the OS stops it (0FE4:3D37)
        and al, 0xE7
        or al, 0x20
        out 0xC0, al
        mov [LATCH], al
        mov cl, 4
        call 0x2345:0x263C        ; mask ch2
.r:     mov byte [cs:lv_mine], 0
        ret

lv_act:   db 0
lv_on:    db 0
lv_mine:  db 0                ; we switched the input on
lv_rd:    dw 0                ; ring byte offset copied up to
lv_w:     dw 0                ; sample RAM ring write position (words)
lv_lr:    dw 0                ; last CC 30/31 written
