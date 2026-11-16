@ preset_color.s - in Preset footswitch mode, the current preset's footswitch in the colour Preset LED Color picks: its ring and its
@ switch icon on the Home screen. The other presets' rings stay off and their icons dark. tools/features/preset_color.py places the hooks.
.syntax unified
.thumb
.include "hxtra.inc"
.equ LED_COLOUR, 0x28db81fd         @ (led, 0xBBGGRR): the colour an LED shows while it is on; sends it at once to a lit one
.equ SET_IMAGE, 0x28e24c19          @ (image widget, image index)
.equ LED_MODES, 0x281f35f8          @ each ring's mode byte: 0 off, 1 on, 2 blink
.equ FS_FUNCTIONS, 0x28128a74       @ each footswitch's function, two bytes apart
.equ PRESET, 13                     @ the function Preset mode gives FS1..FS3
.equ ICON, 0x3f4                    @ in the Home view: footswitch k's switch icon, image widgets 0x24 bytes apart
.equ RED_ICON, 0x78                 @ Icon_SwitchRed, the current preset's
.equ RINGS, 3

.thumb_func
.global preset_led
preset_led:                         @ the LED refresh's Preset case, (led, red): the current preset's ring in our colour
    push {r0, lr}
    adr.w r0, preset_leds
    bl preset_pick
    mov r1, r0
    pop {r0, lr}
    ldr r3, =LED_COLOUR
    bx r3

.thumb_func
.global preset_icon
preset_icon:                        @ the Preset-mode Home builder, setImage (widget, Icon_SwitchRed or Icon_SwitchDark)
    cmp r1, #RED_ICON
    bne 1f
    push {r0, lr}
    adr.w r0, preset_icons
    bl preset_pick
    mov r1, r0
    pop {r0, lr}
1:  ldr r3, =SET_IMAGE
    bx r3

.thumb_func
.global preset_paint
preset_paint:                       @ before the Home paint (framebuffer, Home view): a changed setting recolours the lit Preset ring
    push {r4-r8, lr}
    mov r4, r1
    bl preset_setting
    adr.w r1, preset_shown
    ldrb r2, [r1]
    cmp r2, r0
    beq preset_paint_done
    strb r0, [r1]                   @ leaving Global Settings rebuilds no label and relights no ring
    adr.w r1, preset_leds
    ldr.w r6, [r1, r0, lsl #2]
    adr.w r1, preset_icons
    ldr.w r7, [r1, r0, lsl #2]
    movs r5, #0
preset_paint_each:
    ldr r0, =FS_FUNCTIONS
    ldrb.w r0, [r0, r5, lsl #1]
    cmp r0, #PRESET
    bne preset_paint_next
    ldr r0, =LED_MODES
    ldrb r0, [r0, r5]
    cmp r0, #1                      @ the stock lights only the current preset's ring
    bne preset_paint_next
    mov r0, r5
    mov r1, r6
    ldr r3, =LED_COLOUR
    blx r3
    movs r0, #0x24
    mul r0, r5, r0
    add r0, r4
    add.w r0, r0, #ICON
    mov r1, r7
    ldr r3, =SET_IMAGE
    blx r3
preset_paint_next:
    adds r5, #1
    cmp r5, #RINGS
    bne preset_paint_each
preset_paint_done:
    pop {r4-r8, pc}

preset_pick:                        @ (r0 a table) -> r0 its word for the setting's colour
    push {r4, lr}
    mov r4, r0
    bl preset_setting
    ldr.w r0, [r4, r0, lsl #2]
    pop {r4, pc}

preset_setting:                     @ -> r0 Preset LED Color
    movs r0, #SETTING_PRESET_COLOR_COLOR
    movs r1, #SETTING_PRESET_COLOR_COLOR_MAX
    movs r2, #SETTING_PRESET_COLOR_COLOR_DEFAULT
    b hxtra_setting_get

HXTRA_SETTING_GET
.ltorg
.balign 4
@ The stock palette, by Color: Red, Dk Orange, Lt Orange, Yellow, Green, Turquoise, Blue, Violet, Pink, White
preset_leds:                        @ the LED driver's lit colours (0x28dd8030)
    .word 0x0300ff, 0x002dff, 0x00afd0, 0x00ff84, 0x00ff06, 0x80ff00, 0xff3200, 0xff0032, 0x2800ff, 0xceff6b
preset_icons:                       @ Icon_SwitchRed .. Icon_SwitchWhite
    .word 0x78, 0x1ca, 0x90, 0x83, 0x1b6, 0x21e, 0x234, 0x110, 0x127, 0x115
preset_shown:                       @ the setting the ring was last recoloured for; none yet
    .word 0xff
