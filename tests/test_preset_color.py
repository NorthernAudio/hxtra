"""tools/features/preset_color.py and src/m4/preset_color.s: the handlers in unicorn (the current preset's ring and switch icon, the
Home paint's recolouring after a change), the stock sites they take, and the firmware it builds (Displays' second page, the virtual
setting, the hooks)."""
import struct

import pytest

import features
import image_store
import patch_menu as pm
import setting_ids
from features import preset_color as pc, tap_color as tc
from firmware import assert_virtual, branch_target, built, built_e0, reader, stock_e0, stock_entry

MODS = features.load()
IDS = setting_ids.by_name()
SETTING = pc.SETTINGS[0]
MOD = 0x28e60000
GET_VALUE = 0x28e1f844
HOME = 0x2812a0c8
FS_FUNCTIONS, LED_MODES = 0x28128a74, 0x281f35f8
PRESET, STOMP, SNAPSHOT = 13, 2, 14
RED_ICON, DARK_ICON = 0x78, 0x112
COLOURS = ('Red', 'DarkOrange', 'LightOrange', 'Yellow', 'Green', 'Turquoise', 'Blue', 'Violet', 'Pink', 'White')
LEDS = (0x0300ff, 0x002dff, 0x00afd0, 0x00ff84, 0x00ff06, 0x80ff00, 0xff3200, 0xff0032, 0x2800ff, 0xceff6b)
ICONS = (0x78, 0x1ca, 0x90, 0x83, 0x1b6, 0x21e, 0x234, 0x110, 0x127, 0x115)
_code = {}


class Preset:
    """preset_color.s in tests/m4emu.py's M4: GET_VALUE answers self.value (None: unset), the LED colour and setImage logged."""

    def __init__(self, m4emu):
        if 'preset' not in _code:
            _code['preset'] = m4emu.assemble(pc.MODULE, MODS, IDS)
        code, self.sym = _code['preset']
        self.m = m4emu.M4(code, MOD)
        self.value = None
        self.m.stub(GET_VALUE, self.get_value)
        for fn in (pc.LED_COLOUR, pc.SET_IMAGE):
            self.m.stub(fn)
        self.mode((PRESET,) * 3, (0, 0, 0))

    def get_value(self, m):
        assert m.reg('r0') == IDS['preset_color.color']
        if self.value is None:
            m.reg('r0', -1)
        else:
            m.write(m.reg('r1'), struct.pack('<II', 0, self.value))
            m.reg('r0', 0)

    def mode(self, fns, rings):
        for k, f in enumerate(fns + (2, 2)):
            self.m.write(FS_FUNCTIONS + 2 * k, bytes([f, 0]))
        self.m.write(LED_MODES, bytes(rings))

    def call(self, sym, *args):
        self.m.log.clear()
        self.m.call(MOD + self.sym[sym], *args)
        return [(fn, tuple(regs[:2])) for fn, regs in self.m.log if fn != GET_VALUE]


@pytest.fixture
def preset(m4emu):
    return Preset(m4emu)


def test_feature_settings():
    assert pc.FLAG == 'HX_PRESET_COLOR' and pc.MENU == 'Displays'
    assert SETTING.label == b'LED\nPreset' and SETTING.default == 0
    assert SETTING.values == (b'Red', b'DkOrange', b'LtOrange', b'Yellow', b'Green', b'Teal', b'Blue', b'Violet', b'Pink', b'White')
    assert pc.LEDS == tc.LEDS == LEDS and pc.ICONS == ICONS, "Tap LED Color's palette"


@pytest.mark.parametrize('value', range(10))
def test_each_value_colours_the_ring_and_the_icon(preset, value):
    preset.value = value
    assert preset.call('preset_led', 1, 0x0300ff) == [(pc.LED_COLOUR, (1, LEDS[value]))]
    assert preset.call('preset_icon', 0x2812a4bc, RED_ICON) == [(pc.SET_IMAGE, (0x2812a4bc, ICONS[value]))]


@pytest.mark.parametrize('value', range(10))
def test_the_other_presets_icons_stay_dark(preset, value):
    preset.value = value
    assert preset.call('preset_icon', 0x2812a4e0, DARK_ICON) == [(pc.SET_IMAGE, (0x2812a4e0, DARK_ICON))]


@pytest.mark.parametrize('value', (None, 10, 15))
def test_unset_or_out_of_range_is_stock_red(preset, value):
    preset.value = value
    assert preset.call('preset_led', 0, 0) == [(pc.LED_COLOUR, (0, LEDS[0]))]
    assert preset.call('preset_icon', 1, RED_ICON) == [(pc.SET_IMAGE, (1, RED_ICON))]


def lit(k, value):
    return [(pc.LED_COLOUR, (k, LEDS[value])), (pc.SET_IMAGE, (HOME + pc_icon(k), ICONS[value]))]


def pc_icon(k):
    return 0x3f4 + 0x24 * k


def test_home_paint_recolours_the_lit_preset_ring_once_per_change(preset):
    preset.mode((PRESET,) * 3, (0, 1, 0))
    preset.value = 4
    assert preset.call('preset_paint', 0x28d1ce98, HOME) == lit(1, 4)
    assert preset.call('preset_paint', 0x28d1ce98, HOME) == [], 'the same setting: nothing to do'
    preset.value = 7
    assert preset.call('preset_paint', 0x28d1ce98, HOME) == lit(1, 7)


@pytest.mark.parametrize('fns, rings', [
    ((PRESET,) * 3, (0, 0, 0)),                 # a bank opened that holds no current preset: every ring off
    ((STOMP,) * 3, (1, 1, 0)),                  # Stomp mode: block colours, not ours
    ((SNAPSHOT,) * 3, (1, 0, 0)),               # Snapshot mode
    ((PRESET,) * 3, (2, 2, 2)),                 # blinking
])
def test_home_paint_leaves_rings_that_are_not_a_lit_preset(preset, fns, rings):
    preset.mode(fns, rings)
    preset.value = 5
    assert preset.call('preset_paint', 0, HOME) == []


def test_module_tables_are_the_palette(preset):
    words = lambda name: struct.unpack('<10I', preset.m.read(MOD + preset.sym[name], 40))
    assert (words('preset_leds'), words('preset_icons')) == (LEDS, ICONS)


@pytest.mark.firmware
def test_the_preset_case_lights_the_stock_red_from_one_literal():
    read = reader(stock_e0())
    assert struct.unpack('<I', read(pc.PRESET_RED_LIT, 4))[0] == pc.PRESET_RED
    assert struct.unpack('<I', read(pc.PRESET_RED, 4))[0] == LEDS[0], 'the Preset ring is the palette red'
    assert read(0x28dd0b52, 4) == bytes.fromhex('dff8eca3'), 'ldr.w r10, [pc, #0x3ec]: the literal at 0x28dd0f40'
    assert read(pc.LED_LOAD[0], 4) == pc.LED_LOAD[1] and read(pc.LED_CALL, 4) == pm.bl(pc.LED_CALL, pc.LED_COLOUR)
    assert stock_e0().count(struct.pack('<I', pc.PRESET_RED)) == 1, 'no other code loads the red word'


@pytest.mark.firmware
def test_the_preset_icons_are_red_and_dark_and_each_colour_has_one():
    read = reader(stock_e0())
    assert read(pc.ICON_PICK[0], 4) == pc.ICON_PICK[1]
    assert read(pc.ICON_PICK[0] + 8, 4) == bytes([0x08, 0xbf, RED_ICON, 0x21]), 'it eq; moveq r1, #0x78'
    assert read(pc.ICON_CALL, 4) == pm.bl(pc.ICON_CALL, pc.SET_IMAGE)
    names = image_store.names(stock_entry(7))
    assert (names[RED_ICON], names[DARK_ICON]) == (b'Icon_SwitchRed', b'Icon_SwitchDark')
    assert [names[i] for i in ICONS] == [f'Icon_Switch{c}'.encode() for c in COLOURS]


@pytest.mark.firmware
def test_build_sends_the_preset_calls_and_the_home_paint_to_the_module(m4emu):
    code, sym = m4emu.assemble(pc.MODULE, MODS, IDS)
    read, on = built({'HX_PRESET_COLOR': '1'})
    assert 'preset_color' in on
    module = branch_target(pc.LED_CALL, read(pc.LED_CALL, 4)) - sym['preset_led']
    assert read(module, len(code)) == code
    assert branch_target(pc.ICON_CALL, read(pc.ICON_CALL, 4)) == module + sym['preset_icon']
    stub = struct.unpack('<I', read(pc.HOME_PAINT_LIT, 4))[0] & ~1
    assert branch_target(stub + 6, read(stub + 6, 4)) == module + sym['preset_paint'], 'push, ldm, then the before handler'


@pytest.mark.firmware
def test_build_puts_preset_led_color_on_the_displays_page():
    new = built_e0({'HX_PRESET_COLOR': '1'})
    assert reader(new)(0x28e3b540, 6) == reader(stock_e0())(0x28e3b540, 6), 'the stock table stays'
    assert_virtual(new, pc, SETTING)


@pytest.mark.firmware
def test_without_the_flag_the_sites_stay_stock():
    read, on = built({})
    assert 'preset_color' not in on
    assert read(pc.LED_CALL, 4) == pm.bl(pc.LED_CALL, pc.LED_COLOUR)
    assert read(pc.ICON_CALL, 4) == pm.bl(pc.ICON_CALL, pc.SET_IMAGE)


@pytest.mark.firmware
def test_builds_alongside_every_other_feature():
    env = {f: '1' for m in MODS for f in features.flags(m)}
    _, on = built(env)
    assert {'tap_color', 'preset_color', 'bpm', 'breathing_line', 'more_snapshots'} <= set(on)
