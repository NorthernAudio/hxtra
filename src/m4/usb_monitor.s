@ usb_monitor.s - Path A Out: Send/USB sends path A to the Send bus instead of Main L/R. The Send bus is the Send jacks and
@ USB 3/4 to the computer, so a DAW can monitor the processed sound while Main and the phones play only what it sends back on
@ USB 1/2. The swap happens where the destination goes to the DSP, so every preset follows the setting.
.syntax unified
.thumb
.include "hxtra.inc"
.equ ENGINE, 0x28d92a99             @ () -> the engine the UI's block calls take
.equ SET_OUTPUT, 0x28e03c69         @ (engine, grid position, value): an Output block's destination, as when Path B's merge moves
.equ OUTPUT_A, 9                    @ path A's Output block's grid position
.equ MAIN, 1
.equ SEND, 6
.equ UNSENT, 0xff

.thumb_func
um_send:                            @ owns 0x28df5760(ctx, app, path, value), which sends a path's destination to the DSP; r12 its stock
    push {r0-r3, r12, lr}
    cbnz r2, um_send_stock
    cmp r3, #MAIN
    bne um_send_note
    bl um_wanted
    str r0, [sp, #12]
    mov r3, r0
um_send_note:
    adr r1, um_sent
    strb r3, [r1]
um_send_stock:
    pop {r0-r3, r12, lr}
    bx r12

.thumb_func
um_changed:                         @ after the Global Settings slot repaint CHANGED(view, ID): a turn of this setting
    cmp r1, #SETTING_USB_MONITOR_PATH_A
    it ne
    bxne lr
    b um_apply

.thumb_func
um_page:                            @ after the Global Settings page repaint: a click's reset to the default comes this way
    b um_apply

um_apply:                           @ sends path A's destination again when it is Main or Send and the setting wants the other
    push {r4, lr}
    adr r1, um_sent
    ldrb r4, [r1]
    cmp r4, #MAIN
    it ne
    cmpne r4, #SEND
    bne um_apply_done               @ unsent, or path A's Output is off
    bl um_wanted
    cmp r0, r4
    beq um_apply_done
    ldr r3, =ENGINE
    blx r3
    movs r1, #OUTPUT_A
    movs r2, #MAIN                  @ um_send swaps it when the setting says Send
    ldr r3, =SET_OUTPUT
    blx r3
um_apply_done:
    pop {r4, pc}

um_wanted:                          @ -> r0 path A's destination for a preset's Main: MAIN or SEND
    push {r3, lr}
    movs r0, #SETTING_USB_MONITOR_PATH_A
    movs r1, #SETTING_USB_MONITOR_PATH_A_MAX
    movs r2, #SETTING_USB_MONITOR_PATH_A_DEFAULT
    bl hxtra_setting_get
    cmp r0, #0
    ite eq
    moveq r0, #MAIN
    movne r0, #SEND
    pop {r3, pc}

HXTRA_SETTING_GET

.ltorg
um_sent:                            @ what um_send last sent for path A, in its low byte
    .word UNSENT
