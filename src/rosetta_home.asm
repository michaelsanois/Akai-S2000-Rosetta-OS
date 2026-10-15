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
KEY_FX    equ 0xC3            ; EFFECTS (sampling screen: the MFX page)
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
        call in_grp                   ; soft key inside a menu group
        jnc .s0
        pusha
        push es
        and al, 0x1F
        call pg_key
        pop es
        popa
        jc .eat
        jmp .pass
.s0:    cmp byte [MODE], MODE_REC     ; REC meter page: left = SETUP
        jne .s1
        cmp byte [cs:mfx], 0          ; MFX page up: its keys
        jne .fxk
        call rec_key
        jc .eat
        jmp .pass
.s1:    cmp byte [MODE], 0
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
        cmp byte [cs:ctx], CTX_MENU
        jne .fxk
        cmp al, 0x40                  ; menu: left soft key = out (same as home)
        jne .pmk
        mov al, 0xC0
        jmp .mode
.pmk:   pusha
        push es
        and al, 0x1F
        call pm_key
        pop es
        popa
        jmp .eat
.fxk:   pusha
        push es
        and al, 0x1F
        call fx_key
        pop es
        popa
        jmp .eat
.mode:  cmp byte [MODE], MODE_REC     ; sampling screen: EFFECTS = MFX page (show / next type),
        jne .mr                       ; home with it up = back to the meter
        cmp al, KEY_FX
        jne .mh
        pusha
        push es
        call mfx_key
        pop es
        popa
        jmp .eat
.mh:    cmp al, 0xC0
        jne .mr
        cmp byte [cs:mfx], 0
        je .mr
        mov byte [cs:mfx], 0
        pusha
        push es
        call 0x0FE4:REDRAW
        pop es
        popa
        jmp .eat
.mr:    cmp al, KEY_REC               ; the REC press that stopped a latched take: not a new REC
        jne .m0
        call rec_eat
        jc .eat
.m0:    cmp al, KEY_EDIT              ; EDIT on the menu = out (stock would flip 6 -> 7)
        jne .m1
        cmp byte [cs:ctx], CTX_SYN
        je .me
        cmp byte [cs:ctx], CTX_MENU
        jne .pass
.me:
        cmp byte [MODE], MODE_FX
        jne .pass
        mov al, 0xC0
.m1:    cmp al, 0xC0                  ; home key
        jne .pass
        cmp byte [cs:ctx], CTX_SYN    ; SYNTH: back one level inside it first (pages -> its mode menu)
        jne .m1b
        cmp byte [MODE], MODE_FX
        jne .m1b
        mov byte [cs:synret], 0
        pusha
        push es
        mov ah, 3
        call hi_rv
        jc .m1a                       ; (hi code not there)
        mov [cs:synret], al
.m1a:   pop es
        popa
        cmp byte [cs:synret], 0
        jne .eat
.m1b:   call in_grp                   ; in a group: back to the menu
        jnc .m2
        pusha
        push es
        call pm_back
        pop es
        popa
        jmp .eat
.m2:    cmp byte [cs:ctx], CTX_MENU   ; on a menu: out to where the area came from (HOME / REC)
        jne .m3
        cmp byte [MODE], MODE_FX
        jne .m3
        push bx
        call abx
        mov al, [cs:a_out + bx]
        pop bx
        jmp .pass
.m3:    push ax
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

synret:   db 0                ; the SYNTH page's answer to the home key (1 = it went back a level)

; bl = the top page of [MODE]: FX page 0x0C without EB16, LOAD/SAVE page 1 without flash,
; REC = the meter + ARM page, else 0
top_page:
        mov bl, REC_ARM
        mov ah, [MODE]
        cmp ah, MODE_REC
        je .r
        mov bl, 0
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
        mov si, [cs:fxhdr]
        mov si, [cs:si + 2]   ; fx_short
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
