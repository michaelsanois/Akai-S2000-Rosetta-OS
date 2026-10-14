; Rosetta hi-code loader. Lives at LOAD_SEG:0000 (linear 0x3E020) in the free load.asm junk before the
; boot dragon (0x3E01B-0x3E200, no refs, never written). The boot ROM only loads the first 256 KB of the
; OS file (0.18 test on hw), so the rest of it (the hi code, blocks HI_BLOCK.. right after the OS on the
; boot floppy) is read here, on the first main-loop tick, into CPU RAM 0x40000-0x4FFFF (never used by the
; OS, checked on hw). lfo_hook calls +0 on every tick; once the hi code is in, that call goes to its tick.
;
; Floppy reads go through the OS's own raw sector read, far call 1F50:00BB: CL = cylinder, DH = head,
; DL = first sector (1-based), CH = N (3 = 1 KB), BX = bytes, ES:BP = buffer -> AL = 0 ok. It readies the
; drive itself (first access: ~4 s motor wait), keeps its own error frame and stays on one track, so the
; read is split per track. Akai HD disk: block b = cylinder b / 20, head (b % 20) / 10, sector b % 10 + 1.
        cpu 186
        bits 16
        org 0

HI_SEG    equ 0x4000
HI_INIT   equ 0x0006          ; hi header: 'RSHI', dw version, jmp hi_init, jmp hi_tick (src/rosetta_hi.asm)
HI_TICK   equ 0x0009
%ifndef HI_BLOCK
HI_BLOCK  equ 273             ; first block after the 256 KB OS file at block 17 (set by mkbaby.py)
%endif
%ifndef HI_NBLK
HI_NBLK   equ 1               ; hi code size in KB (set by mkbaby.py)
%endif
SPT       equ 10              ; 1 KB sectors per track (HD)
POPUP     equ 0x8FE0          ; OS popup text buffer in segment 0 (2 x 16 chars + FF)

        jmp near tick         ; +0  every main-loop tick (lfo_hook), DS = 0
state:  db 0                  ; +3  0 = not tried, 1 = hi code running, 2 = failed, 3 = loading
status: db 0                  ; +4  floppy result: 0 ok, FE/FF = read error, FD = no hi code (bad magic)

tick:   cmp byte [cs:state], 1
        je .hi
        jb load
        retf
.hi:    jmp HI_SEG:HI_TICK    ; its retf goes back to lfo_hook

load:   mov byte [cs:state], 3
        pusha
        push es
        mov si, msg_load
        call popup
        mov ax, HI_BLOCK
        mov si, HI_NBLK       ; blocks left
        mov di, HI_SEG        ; where they go
.trk:   push ax
        mov bl, 2 * SPT
        div bl                ; al = cylinder, ah = block in the cylinder
        mov cl, al
        mov dl, ah
        xor dh, dh
        cmp dl, SPT
        jb .h0
        sub dl, SPT
        inc dh                ; head 1
.h0:    mov al, SPT
        sub al, dl            ; blocks left on this track
        cbw
        cmp ax, si
        jbe .n
        mov ax, si
.n:     mov [cs:nblk], ax
        inc dl                ; sectors count from 1
        mov bh, al
        shl bh, 2
        xor bl, bl            ; bx = bytes
        mov ch, 3             ; 1 KB sectors
        mov es, di
        xor bp, bp
        call 0x1F50:0x00BB
        pop dx                ; block
        mov [cs:status], al
        or al, al
        jnz .fail
        mov ax, [cs:nblk]
        add dx, ax
        sub si, ax
        shl ax, 6
        add di, ax            ; 1 KB = 0x40 paragraphs
        mov ax, dx
        or si, si
        jnz .trk
        mov ax, HI_SEG
        mov es, ax
        cmp word [es:0], 'RS'
        jne .bad
        cmp word [es:2], 'HI'
        jne .bad
        mov byte [cs:state], 1
        pop es
        popa
        call HI_SEG:HI_INIT
        retf
.bad:   mov byte [cs:status], 0xFD
.fail:  mov byte [cs:state], 2
        mov si, msg_fail
        call popup
        pop es
        popa
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

nblk:     dw 0
msg_load: db "ROSETTA+        LOADING DISK... "
msg_fail: db "ROSETTA+ FAILED EXTRAS ARE OFF  "
