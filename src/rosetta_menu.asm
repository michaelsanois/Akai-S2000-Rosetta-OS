; Rosetta permanent helpers. Lives at MENU_SEG:0000 (linear 0x3EA00, right after the boot dragon) in the leftover load.asm object
; junk (0x3E01B-0x3FFFF): no refs, no segment reaches it, the voice table (2D95:9F80, 32 x 0x1BC) and
; MIDI tx ring (3B05:0000) below end at 0x3B160, and the emulator never writes it.
;
; Entry points are far procedures behind a fixed jump table (keep it first, offsets are patched in).
        cpu 186
        bits 16
        org 0

PAGE      equ 0x762C          ; current page in mode (DS = 0)
MODE      equ 0x762B          ; current mode (0 main, 6 EFFECTS, 9 SAVE, 0x0A LOAD)
MODE_FX   equ 0x06
MODE_SAVE equ 0x09
MODE_LOAD equ 0x0A
FLASH_SEG equ 0x2316          ; 1F50 module data: dword at 2316:0024 = fitted flash (0 = none)

DATA_SEG  equ 0x2D95          ; OS data segment for pages + delay presets
FXPAGE_L1 equ 0x1402          ; page 0x0C text ("Effects board" / "EB16 not present"), 16 chars each
FXPAGE_L2 equ 0x1415
FX_SEND   equ 0x800F          ; reg7 word1: send level 0x80 (bits 15-8), e = 0, dest 0xF = delay engine

        jmp near page0_hook   ; +0  from 0FE4:03B1 (replaces `mov byte [762C],0`)
        jmp near fx_entry     ; +3  from 0FE4:03CB (replaces `mov byte [762B],6`; EB16-absent path only)
        jmp near send84       ; +6  from 2345:50EE (note-on) + 2345:5480 (periodic vol/pan update): `mov ax,[si+84h]` + `out 84h,ax`, + nop
        jmp near send22       ; +9  from 2345:41A8 (replaces `mov ax,[si+22h]` + `out 84h,ax`)
        jmp near sx_start     ; +C  from 2B9D:00FB (replaces `mov word [7DE6],63CBh` + nop): SysEx start
        jmp near sx_byte      ; +F  from the 0FE4:F6B2 pad stub (`lcall MENU_SEG:000F; ret`): SysEx data byte
                              ; (+15 lfo_hook sits after the data below: +12/+13 are poked by the lab)

fxon:   db 0                  ; +12 current FX preset (0 = off; PC lab can poke it)
fxsendv: dw FX_SEND           ; +13 reg7 word1 OR value while on (send level/e/dest), PC-tunable
        jmp near lfo_hook     ; +15 from 0FE4:000D (replaces the main-loop wait's lcall 2345:0A47)
        jmp near key_hook     ; +18 from 0FE4:0264 (replaces `mov al,[73D4]` + `test al,0C0h`): HOME jobs,
                              ;     home key = back one level, FX page keys (src/rosetta_home.asm)
        jmp near rec_done     ; +1B from 0FE4:3CE7 (replaces `mov byte [8215],0` at the end of a kept take)
        jmp near rec_armkey   ; +1E from 0FE4:3AA0 (armed loop's `mov al,[73D4]` + `mov byte [73D4],0`, + 3 nop)
        jmp near rec_wait     ; +21 from 2345:27EB (a record step's `call 27F8` + `jb 27F7`): REC key stops

; Mode entry sets page 0. For LOAD/SAVE without a flash ROM, page 0 only asks
; "DISK or FLASHROM" and FLASHROM just says "No Flash ROM fitted!" -> start on page 1
; (DISK LOAD / DISK SAVE), exactly what pressing DISK does (0FE4:0648 sets the page;
; its [7385] bookkeeping only feeds dead code at 0FE4:06E9).
page0_hook:
        mov byte [PAGE], 0
        push ax
        call prog_entry       ; EDIT PROGRAM / EDIT SAMPLE / GLOBAL -> Rosetta menu (switches MODE to the 6 / 0x0C page slot)
        mov al, [cs:onfx]     ; FX page bookkeeping: EFFECTS pressed while on it = next type
        mov [cs:wasfx], al
        mov byte [cs:onfx], 0
        mov al, [MODE]
        or al, al
        jnz .ls
        call home_text        ; HOME: refresh line 2 (FX name) before the OS draws it
        jmp .done
.ls:    cmp al, MODE_REC
        jne .ls2
        mov byte [PAGE], REC_ARM  ; REC opens on the meter + ARM page (src/rosetta_rec.asm)
        jmp .done
.ls2:   cmp al, MODE_LOAD
        je .chk
        cmp al, MODE_SAVE
        jne .done
.chk:   call noflash
        jnz .done             ; flash fitted: keep the stock question
        mov byte [PAGE], 1
.done:  pop ax
        retf

; reg7 word1 writes (send level / effect / destination): add the delay-engine send while FX is on.
send84: mov ax, [si+0x84]
        call fxsend
        out 0x84, ax
        retf

send22: mov ax, [si+0x22]
        call fxsend
        out 0x84, ax
        retf

fxsend: cmp byte [cs:fxon], 0
        je .r
        and ax, 0x00F0        ; keep the unknown "e" bits, replace send level + destination
        or ax, [cs:fxsendv]
.r:     ret

; ---------------------------------------------------------------------------------------------
; SysEx lab backdoor: F0 7D 53 <cmd> <nibbles...> F7  (7D = non-commercial ID, 53 = 'S')
; The OS parser takes F0 + 2 data bytes ([7BD6] = 7D, [7DEA] = 53), then feeds every further data
; byte to the near handler [7DE6] in segment 0FE4, one byte late: AL = byte, [7DF1] = F7 on the last.
; Runs in the main loop (0FE4:6040), DS = 0, so chip/port access here is safe.
SX_STOCK  equ 0x63CB          ; Akai SysEx handler 0FE4:63CB
SX_STUB   equ 0xF6B2          ; 0FE4:F6B2 pad stub -> sx_byte
SX_MAX    equ 420
VERSION_W equ 0x0019          ; reply to PING

sx_start:
        mov word [0x7DE6], SX_STOCK
        cmp byte [0x7BD6], 0x7D
        jne .r
        cmp byte [0x7DEA], 0x53
        jne .r
        mov word [0x7DE6], SX_STUB
        mov word [cs:sxn], 0
.r:     retf

sx_byte:
        push bx
        mov bx, [cs:sxn]
        cmp bx, SX_MAX
        jae .full
        mov [cs:sxbuf+bx], al
        inc word [cs:sxn]
.full:  pop bx
        cmp byte [0x7DF1], 0xF7
        jne .r
        pusha
        push ds
        push es
        call sx_exec
        pop es
        pop ds
        popa
.r:     retf

; nibble readers over sxbuf: si = index of first nibble; return value in ax, si advanced
nib2:   mov cx, 2
        jmp short nibn
nib4:   mov cx, 4
nibn:   xor ax, ax
.l:     shl ax, 4
        or al, [cs:sxbuf+si]
        inc si
        loop .l
        ret

sx_exec:
        mov al, [cs:sxbuf]
        mov si, 1
        cmp al, 0x01
        je .outw
        cmp al, 0x02
        je .outb
        cmp al, 0x03
        je .poke
        cmp al, 0x04
        je .peek
        cmp al, 0x05
        je .ping
        cmp al, 0x06
        je .fxprog
        cmp al, 0x07
        je .inw
        cmp al, 0x08
        je .fxsel
        ret
.fxsel: call nib2             ; 08 nn: select FX preset nn (same as stepping to it with EFFECTS)
        cmp al, NPRESETS
        jae .fsr
        call fx_settype
        xor al, al
        call fx_render
.fsr:   ret
.outw:  call nib2
        mov dx, ax
        call nib4
        out dx, ax
        ret
.outb:  call nib2
        mov dx, ax
        call nib2
        out dx, al
        ret
.poke:  call nib4
        mov es, ax
        call nib4
        mov di, ax
        call nib2
        mov bp, ax            ; count
.pk:    or bp, bp
        jz .pkd
        call nib2
        stosb
        dec bp
        jmp .pk
.pkd:   ret
.peek:  call nib4
        mov es, ax
        call nib4
        mov di, ax
        call nib2
        mov bp, ax
        mov al, 0x44
        call tx_head
        mov ax, es
        call tx_w
        mov ax, di
        call tx_w
.pe:    or bp, bp
        jz .ped
        mov al, [es:di]
        call tx_b
        inc di
        dec bp
        jmp .pe
.ped:   jmp tx_end
.ping:  mov al, 0x45
        call tx_head
        mov ax, VERSION_W
        call tx_w
        jmp tx_end
.fxprog:
        mov byte [cs:nmods], 0  ; lab table load: stop the LFO so it doesn't fight the table
        xor ax, ax
        mov es, ax
        call 0x2345:0x818F    ; stock: program reg A functions 1-31 from the DS:6D00 shadow
        ret
.inw:   call nib2
        mov dx, ax
        mov al, 0x47
        call tx_head
        mov ax, dx
        call tx_b
        in ax, dx
        call tx_w
        jmp tx_end

; MIDI out via the OS tx ring (lcall 2345:0A6B, byte in AH; clobbers dx, al)
txa:    push dx
        push ax
        mov ah, al
        call 0x2345:0x0A6B
        pop ax
        pop dx
        ret
tx_head: push ax
        mov al, 0xF0
        call txa
        mov al, 0x7D
        call txa
        mov al, 0x53
        call txa
        pop ax
        jmp txa
tx_end: mov al, 0xF7
        jmp txa
tx_b:   push ax               ; byte in al -> 2 nibbles
        shr al, 4
        call txa
        pop ax
        push ax
        and al, 0x0F
        call txa
        pop ax
        ret
tx_w:   push ax               ; word in ax -> 4 nibbles
        mov al, ah
        call tx_b
        pop ax
        jmp tx_b

%include "rosetta_fx.asm"
%include "rosetta_home.asm"
%include "rosetta_prog.asm"
%include "rosetta_rec.asm"

sxn:    dw 0
sxbuf:  times SX_MAX db 0

