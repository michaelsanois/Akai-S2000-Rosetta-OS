; Rosetta HOME hub + "back one level" (menu redesign M1, docs/menu_design.md).
; Included by rosetta_menu.asm (same segment, DS = 0 at every entry point).
;
; HOME = main mode 0 page 0. Line 1 stays stock (program name + number, DATA wheel = program).
; Line 2 (stock "    prog active", a 15-char RAM text record at 2D95:0483; the active-count field is
; dropped from the page def by mkbaby.py) becomes   LOAD  HALL  EDIT   : soft key L = LOAD,
; soft key R = EDIT (program), middle = current Rosetta FX.
; The home key (mode key 0, r1c1) = back one level: a deeper page -> the mode's top page, top -> HOME.

HOME_TXT  equ 0x0483          ; 2D95:0483, 15 chars of main page 0 line 2 (col 0)
EB16      equ 0x84E0          ; EB16 fitted
KEY_LOAD  equ 0xC7            ; mode key events (0xC0 | code, code -> mode via DS:05FD)
KEY_EDIT  equ 0xC4            ; EDIT: flips the mode to its edit twin (0 -> 1 = EDIT PROGRAM)
REDRAW    equ 0x0616          ; 0FE4:0616 = far: [738D]=1, redraw the current page, [738D]=0

; key dispatcher's event read (0FE4:0264, replaces `mov al,[73D4]` + `test al,0C0h`). The caller uses
; the AL we return as the event (0026x: mov ah,al / and al,3Fh / ...), so a job can rewrite it; a consumed
; key returns AL = 0 / ZF set (= no event).
key_hook:
        mov al, [KEYEV]
        mov ah, al
        and ah, 0xE0
        cmp ah, 0xC0
        je .mode
        cmp ah, 0x40
        jne .pass
        cmp byte [MODE], 0            ; soft key
        jne .fx
        cmp byte [PAGE], 0
        jne .pass
        cmp al, 0x40                  ; HOME: soft L = LOAD, soft R = EDIT
        jne .h1
        mov al, KEY_LOAD
        jmp .pass
.h1:    cmp al, 0x41
        jne .pass
        mov al, KEY_EDIT
        jmp .pass
.fx:    cmp byte [MODE], MODE_FX
        jne .pass
        cmp byte [PAGE], FXPAGE
        jne .pass
        pusha
        push es
        and al, 0x1F
        call fx_key
        pop es
        popa
        jmp .eat
.mode:  cmp al, 0xC0                  ; home key
        jne .pass
        push ax
        call top_page
        cmp [PAGE], bl
        pop ax
        je .pass                      ; at the top already: stock = HOME
        mov [PAGE], bl
        pusha
        push es
        call 0x0FE4:REDRAW
        pop es
        popa
.eat:   mov byte [KEYEV], 0
        xor al, al
.pass:  test al, 0xC0
        retf

; bl = the top page of [MODE]: FX page 0x0C without EB16, LOAD/SAVE page 1 without flash, else 0
top_page:
        mov bl, 0
        mov ah, [MODE]
        cmp ah, 6
        je .fx
        cmp ah, 7
        je .fx
        cmp ah, MODE_LOAD
        je .ls
        cmp ah, MODE_SAVE
        jne .r
.ls:    call noflash
        jnz .r
        mov bl, 1
.r:     ret
.fx:    cmp byte [EB16], 0
        jne .r
        mov bl, FXPAGE
        ret

; ZF = 1 when no flash ROM is fitted (dword 2316:0024 == 0)
noflash:
        push es
        push ax
        mov ax, FLASH_SEG
        mov es, ax
        mov ax, [es:0x24]
        or ax, [es:0x26]
        pop ax
        pop es
        ret

; HOME line 2 text in RAM: "LOAD " + FX short name (5) + " EDIT" (the OS draws it on page entry)
home_text:
        push es
        pusha
        mov ax, DATA_SEG
        mov es, ax
        mov di, HOME_TXT
        mov si, txt_load
        mov cx, 5
        call cpyn
        mov al, [cs:fxon]
        mov ah, 5
        mul ah
        mov si, fx_short
        add si, ax
        mov cx, 5
        call cpyn
        mov si, txt_edit
        mov cx, 5
        call cpyn
        popa
        pop es
        ret

cpyn:   mov al, [cs:si]               ; cx bytes cs:si -> es:di
        stosb
        inc si
        loop cpyn
        ret

txt_load: db "LOAD "
txt_edit: db " EDIT"
