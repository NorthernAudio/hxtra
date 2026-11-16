"""Preset LED Color: Global Settings > Displays picks the colour of the current preset's footswitch in Preset footswitch mode, for its
ring and for its switch icon on the Home screen, from the stock footswitch palette Tap LED Color uses (src/m4/preset_color.s). The
other presets' rings stay off and their icons dark, as stock."""
from features import Setting, tap_color

FLAG = 'HX_PRESET_COLOR'
MENU = 'Displays'
MODULE = 'src/m4/preset_color.s'
SETTINGS = (     # a label's last line shows on top: Preset over LED
    Setting('color', b'LED\nPreset', tap_color.SETTINGS[0].values[:10]),
)
LEDS, ICONS = tap_color.LEDS, (0x78, 0x1ca, 0x90, 0x83, 0x1b6, 0x21e, 0x234, 0x110, 0x127, 0x115)  # Icon_SwitchRed .. White

LED_COLOUR, SET_IMAGE = tap_color.LED_COLOUR, tap_color.SET_IMAGE
# The LED refresh 0x28dd0b3c's Preset case (function 13): mode on, then the red word below through r10, its only literal
PRESET_RED, PRESET_RED_LIT = 0x28e3c4a0, 0x28dd0f40
LED_CALL, LED_LOAD = 0x28dd0c44, (0x28dd0c3e, bytes.fromhex('daf80010'))     # ldr.w r1,[r10]
# The Preset-mode Home builder 0x28dc712c: Icon_SwitchRed for the current preset, Icon_SwitchDark (0x112) for the others
ICON_CALL, ICON_PICK = 0x28dc71a0, (0x28dc7194, bytes.fromhex('4ff48971'))   # mov.w r1,#0x112, then moveq r1,#0x78
HOME_PAINT_LIT, HOME_PAINT = tap_color.HOME_PAINT_LIT, tap_color.HOME_PAINT


def apply(p):
    m = p.module(MODULE)
    if p.u32(PRESET_RED_LIT) != PRESET_RED or p.u32(PRESET_RED) != LEDS[0]:
        raise SystemExit('patch-menu: the Preset case of the LED refresh does not load the stock red')
    p.expect(*LED_LOAD, 'the Preset ring colour load')
    p.own_call(LED_CALL, LED_COLOUR, 'the Preset ring colour', m['preset_led'])
    p.expect(*ICON_PICK, 'the Preset switch icon')
    p.own_call(ICON_CALL, SET_IMAGE, 'the Preset switch icon', m['preset_icon'])
    p.chain_ptr(HOME_PAINT_LIT, HOME_PAINT, before=m['preset_paint'])
