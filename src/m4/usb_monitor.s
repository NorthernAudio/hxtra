@ usb_monitor.s - Path A Out: where path A's Output block goes. Send/USB and USB Only send it to the Send bus instead of Main L/R:
@ the Send jacks and USB 3/4 to the computer, so a DAW can monitor the processed sound while Main and the phones play only what it
@ sends back on USB 1/2. USB Only also silences the Send jacks: the setting goes to the DSP as the app's parameter 'Output' (the
@ mode word of src/sharc/usb_monitor.asm, tools/patch_usbmon.py), sent after each send of path A's destination. The swap happens
@ where the destination goes to the DSP, so every preset follows the setting.
.syntax unified
.thumb
.include "hxtra.inc"
.equ ENGINE, 0x28d92a99             @ () -> the engine the UI's block calls take
.equ SET_OUTPUT, 0x28e03c69         @ (engine, grid position, value): an Output block's destination, as when Path B's merge moves
.equ PARAM_FIND, 0x28df35a1         @ (ctx, instance, name's Entry 3 string, &handle): an app parameter's handle, < 0 when it has none
.equ PARAM_SEND, 0x28df35e9         @ (ctx, instance, handle, &{u8 type, u32 value}): an app parameter to the DSP
.equ MODE_NAME, 1247                @ the stock string 'Output', the mode parameter's name (tools/patch_usbmon.py NAME)
.equ OUTPUT_A, 9                    @ path A's Output block's grid position
.equ MAIN, 1
.equ SEND, 6
.equ INT, 2

.thumb_func
um_send:                            @ owns 0x28df5760(ctx, app, path, value), which sends a path's destination to the DSP; r12 its stock
    push {r4-r8, lr}
    mov r4, r0
    mov r5, r1
    mov r6, r2
    mov r7, r3
    mov r8, r12
    cbnz r6, um_send_call           @ path B: as it came
    cmp r7, #MAIN
    bne um_send_note
    bl um_wanted
    mov r7, r0
um_send_note:
    adr r1, um_sent
    strb r7, [r1]
um_send_call:
    mov r0, r4
    mov r1, r5
    mov r2, r6
    mov r3, r7
    blx r8
    cbnz r6, um_send_done
    mov r7, r0                      @ the stock send's result
    mov r0, r4
    mov r1, r5
    bl um_mode
    mov r0, r7
um_send_done:
    pop {r4-r8, pc}

um_mode:                            @ (ctx, app): the setting to the DSP as the app parameter MODE_NAME, when the app has it
    push {r4-r7, lr}
    sub sp, #12                     @ the value {type, value} at sp, the handle at sp + 8
    ldr r4, [r0, #0xc]
    adds r4, #4                     @ the parameter context, as 0x28df5760 takes it
    ldr.w r5, [r1, #0xac8]          @ the app's instance
    mov r0, r4
    mov r1, r5
    movw r2, #MODE_NAME
    add r3, sp, #8
    ldr r6, =PARAM_FIND
    blx r6                          @ looked up each time: a rebuilt app gets new handles
    cmp r0, #0
    blt um_mode_done                @ a build without the DSP side: nothing to send
    bl um_setting
    adr r1, um_sent
    strb r0, [r1, #1]
    str r0, [sp, #4]
    movs r1, #INT
    strb r1, [sp]
    mov r0, r4
    mov r1, r5
    ldr r2, [sp, #8]
    mov r3, sp
    ldr r6, =PARAM_SEND
    blx r6
um_mode_done:
    add sp, #12
    pop {r4-r7, pc}

.thumb_func
um_changed:                         @ after the Global Settings slot repaint CHANGED(view, ID): a turn of this setting
    cmp r1, #SETTING_USB_MONITOR_PATH_A
    it ne
    bxne lr
    b um_apply

.thumb_func
um_page:                            @ after the Global Settings page repaint: a click's reset to the default comes this way
    b um_apply

um_apply:                           @ sends path A's destination again when it is Main or Send and the setting wants another, or another mode
    push {r4, r5, r6, lr}
    adr r1, um_sent
    ldrb r4, [r1]
    ldrb r5, [r1, #1]
    cmp r4, #MAIN
    it ne
    cmpne r4, #SEND
    bne um_apply_done               @ unsent, or path A's Output is off
    bl um_wanted
    mov r6, r0
    bl um_setting
    cmp r6, r4
    it eq
    cmpeq r0, r5
    beq um_apply_done
    ldr r3, =ENGINE
    blx r3
    movs r1, #OUTPUT_A
    movs r2, #MAIN                  @ um_send swaps it for what the setting wants, then sends the mode
    ldr r3, =SET_OUTPUT
    blx r3
um_apply_done:
    pop {r4, r5, r6, pc}

um_wanted:                          @ -> r0 path A's destination for a preset's Main: SEND for Send/USB and USB Only, else MAIN
    push {r3, lr}
    bl um_setting
    subs r0, #1
    cmp r0, #1
    ite ls
    movls r0, #SEND
    movhi r0, #MAIN
    pop {r3, pc}

um_setting:                         @ -> r0 the setting, 0..its max
    push {r3, lr}
    movs r0, #SETTING_USB_MONITOR_PATH_A
    movs r1, #SETTING_USB_MONITOR_PATH_A_MAX
    movs r2, #SETTING_USB_MONITOR_PATH_A_DEFAULT
    bl hxtra_setting_get
    pop {r3, pc}

HXTRA_SETTING_GET

.ltorg
um_sent:                            @ what um_send last sent for path A: its destination in byte 0, the mode in byte 1
    .word 0xffff
