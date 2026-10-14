; Rosetta hi code: CPU RAM 4000:0000-FFFF (64 KB the OS never touches), stored on the boot floppy right
; after the 256 KB OS file and read in after boot by src/rosetta_load.asm. Room for the big features.
;
; Header (the loader checks the magic and calls the two entries far, DS = 0):
        cpu 186
        bits 16
        org 0
%ifndef HI_VERSION
HI_VERSION equ 0
%endif
POPUP     equ 0x8FE0          ; OS popup text buffer in segment 0 (2 x 16 chars + FF)

        db "RSHI"             ; +0 magic
        dw HI_VERSION         ; +4
        jmp near hi_init      ; +6 once, right after loading
        jmp near hi_tick      ; +9 every main-loop tick: keep all registers

hi_init:
        pusha
        push es
        mov si, msg_ok
        call popup
        pop es
        popa
        retf

hi_tick:
        inc word [cs:ticks]   ; proof of life over SysEx: peek 4000:<ticks>
        retf

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

ticks:  dw 0
msg_ok: db "ROSETTA+ READY  EXTRA CODE OK   "
