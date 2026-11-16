"""tools/features/usb_monitor.py and src/m4/usb_monitor.s: the handlers in unicorn (path A's Main sent as Send while the setting says
so, everything else untouched; a turn or a reset sending path A again only when it changes), and the firmware it builds (its
section, the virtual setting, the hooks)."""
import struct

import pytest

import features
import setting_ids
from features import usb_monitor as um
import patch_menu as pm
from firmware import assert_virtual, branch_target, built, built_e0
from test_hxtra import page_table

MODS = features.load()
IDS = setting_ids.by_name()
ID = IDS['usb_monitor.path_a']
MOD = 0x28e60000
GET_VALUE = 0x28e1f844
STOCK = 0x28e70000                          # stands in for the moved prologue of 0x28df5760
ENGINE, SET_OUTPUT = 0x28d92a98, 0x28e03c68
MAIN, SEND = 1, 6
_code = {}


class Monitor:
    """usb_monitor.s in tests/m4emu.py's M4: GET_VALUE answers self.value (None: unset); the stock send, ENGINE and SET_OUTPUT logged."""

    def __init__(self, m4emu):
        if 'um' not in _code:
            _code['um'] = m4emu.assemble('src/m4/usb_monitor.s', MODS, IDS)
        code, self.sym = _code['um']
        self.m = m4emu.M4(code, MOD)
        self.value = None
        self.m.stub(GET_VALUE, self.get_value)
        self.m.stub(STOCK)
        self.m.stub(ENGINE, lambda m: m.reg('r0', 0x2844adcc))
        self.m.stub(SET_OUTPUT)

    def get_value(self, m):
        assert m.reg('r0') == ID
        if self.value is None:
            m.reg('r0', -1)
        else:
            m.write(m.reg('r1'), struct.pack('<II', 2, self.value))
            m.reg('r0', 0)

    def send(self, ctx, app, path, value):
        """um_send as the owned 0x28df5760 -> (ctx, app, path, value) that reached the stock function."""
        before = len(self.m.calls(STOCK))
        self.m.reg('r12', STOCK | 1)
        self.m.call(MOD + self.sym['um_send'], ctx, app, path, value)
        got = self.m.calls(STOCK)[before:]
        assert len(got) == 1
        return tuple(got[0])

    def apply(self, sym, *args):
        """The SET_OUTPUT calls (engine, position, value) a handler made."""
        before = len(self.m.calls(SET_OUTPUT))
        self.m.call(MOD + self.sym[sym], *args)
        return [tuple(r[:3]) for r in self.m.calls(SET_OUTPUT)[before:]]


@pytest.fixture
def mon(m4emu):
    return Monitor(m4emu)


def test_feature_setting():
    s, = um.SETTINGS
    assert um.FLAG == 'HX_USB_MONITOR' and um.MENU == 'Ins/Outs'
    assert pm.STOCK_CATEGORIES['Ins/Outs'] == (0, 0x28e3b55c)
    assert s.values == (b'Main L/R', b'Send/USB') and s.default == 0
    assert all(len(v) <= 8 for v in s.values)
    assert (ID, 112, 0, 2) in [(v, c, b, n) for v, c, b, n, who, _ in setting_ids.VIRTUAL if who == 'usb_monitor.path_a']


@pytest.mark.parametrize('value, sent', [(None, MAIN), (0, MAIN), (1, SEND)])
def test_path_a_main_follows_the_setting(mon, value, sent):
    mon.value = value
    assert mon.send(0x1111, 0x2222, 0, MAIN) == (0x1111, 0x2222, 0, sent)


@pytest.mark.parametrize('path, dest', [(0, 0), (0, SEND), (1, 0), (1, MAIN), (1, SEND)])
def test_everything_else_goes_through(mon, path, dest):
    mon.value = 1
    assert mon.send(0x1111, 0x2222, path, dest) == (0x1111, 0x2222, path, dest)


def test_a_turn_sends_path_a_again(mon):
    mon.value = 0
    mon.send(0x1111, 0x2222, 0, MAIN)
    mon.value = 1
    assert mon.apply('um_changed', 0x3333, ID) == [(0x2844adcc, 9, MAIN)]
    assert mon.send(0, 0, 0, MAIN)[3] == SEND


def test_other_settings_are_ignored(mon):
    mon.send(0x1111, 0x2222, 0, MAIN)
    mon.value = 1
    assert mon.apply('um_changed', 0x3333, ID + 1) == []
    assert mon.apply('um_changed', 0x3333, 0x10) == []


def test_a_reset_comes_through_the_page_repaint(mon):
    mon.value = 1
    mon.send(0x1111, 0x2222, 0, MAIN)
    mon.value = 0
    assert mon.apply('um_page', 0x3333) == [(0x2844adcc, 9, MAIN)]
    mon.send(0x1111, 0x2222, 0, MAIN)                                # where the stock API's call ends on the unit
    assert mon.apply('um_page', 0x3333) == []


def test_nothing_is_sent_when_it_already_matches(mon):
    mon.value = 1
    mon.send(0x1111, 0x2222, 0, MAIN)
    assert mon.apply('um_page', 0x3333) == []
    assert mon.apply('um_changed', 0x3333, ID) == []


@pytest.mark.parametrize('first', [None, 0])
def test_nothing_is_sent_while_path_a_is_off_or_unsent(mon, first):
    if first is not None:
        mon.send(0x1111, 0x2222, 0, first)
    mon.value = 1
    assert mon.apply('um_changed', 0x3333, ID) == []
    assert mon.apply('um_page', 0x3333) == []


def test_off_unless_asked_for():
    assert um not in features.enabled(MODS, {})
    assert um in features.enabled(MODS, {'HX_USB_MONITOR': '1'})


@pytest.mark.firmware
def test_firmware():
    read, on = built({'HX_USB_MONITOR': '1'}, MODS)
    assert 'usb_monitor' in on
    assert read(um.SEND_FN, 4) != um.SEND_FN_STOCK, 'the send goes to the handler'
    for fn, stock in ((um.CHANGED, um.CHANGED_STOCK), (um.PAGE, um.PAGE_STOCK)):
        assert read(fn, 4) != stock, f'{fn:#x} is chained'
        assert branch_target(fn, read(fn, 4)) > fn, f'{fn:#x} branches to its chain'
    assert_virtual(built_e0({'HX_USB_MONITOR': '1'}, MODS), um, um.SETTINGS[0])


@pytest.mark.firmware
def test_ins_outs_last_empty_slot_holds_the_setting():
    read, _ = built({'HX_USB_MONITOR': '1'}, MODS)
    stock_ids = (0x1f, 0x5e, 2, 3, 0x9a, 0x99, 0x9e, 0x9c)
    for site in pm.SITES:
        table = page_table(read, 0, site)
        assert struct.unpack('<9H', read(table, 18)) == (*stock_ids, ID), site
    pages = struct.unpack('<I', read(pm.ARRAYS['pages'][1][0], 4))[0]
    assert read(pages, 4) == struct.pack('<I', 3), 'Ins/Outs keeps its three pages'
