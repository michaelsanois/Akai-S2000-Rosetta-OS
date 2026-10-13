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
        retf

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
