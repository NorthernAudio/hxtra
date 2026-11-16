"""Path A Out's DSP side (issues #81, #93): src/sharc/usb_monitor.asm in ssim (the meter's control function keeping the mode, the
Send jacks' writer silenced in USB Only), the app parameter 'Output' and its writer (tools/patch_usbmon.py), its place in Block 3,
the registry and build.py's steps."""
import importlib.util
import os
import re
import struct
import sys
from pathlib import Path

import pytest

import block3
import patch_amp as pa
import patch_click
import patch_comp as pc
import patch_gate as pg
import patch_usbmon as pu
import sasm
import ssim

ROOT = Path(__file__).resolve().parent.parent
QUIET = dict(log=lambda *_: None)
WRITER, CTRL = 0x90100, 0x90300           # stand-ins for the Send writer's stock process code and the meter's control function
SRC, COPY = 0x7000, 0x7100                # the stand-in writer copies its 16-sample input (I1) to COPY


# ---- the DSP code, in ssim

def dsp():
    src = pu.dsp_asm(0xe7a00, 0xe5200)
    for k, v in (('ORIG_2AAA', WRITER), ('ORIG_CTRL_25E8', CTRL)):
        src, n = re.subn(r'(\.equ %s,\s*)0x[0-9a-fA-F]+' % k, r'\g<1>%#x' % v, src)
        assert n == 1, k
    ret = '    I12 = DM(M7, I6);\n    JUMP (M14, I12) (DB);\n    NOP;\n    RFRAME;'
    assert ret in src
    src = src.replace(ret, '    RTS;')     # the C return needs the caller's frame
    src += f"""
.section dm 0x6f00
FAKE_CTRL: .space 1
.section pm {WRITER:#x}
    I4 = {COPY:#x};
    LCNTR = 16, DO fw UNTIL LCE;
      R0 = DM(I1, 1);
fw:   DM(I4, 1) = R0;
    RTS;
.section pm {CTRL:#x}
    R0 = 0x777;
    DM(FAKE_CTRL) = R0;
    RTS;
"""
    secs, syms = sasm.assemble(src, 'usb_monitor_test')
    s = ssim.Sim()
    s.load(secs)
    return s, syms


def ctrl(s, syms, pid, value):
    """The control function as the framework calls it: pid R4, a pointer to the value R8, the meter's state R12."""
    s.wr(0x5000, value & 0xffffffff)
    s.u[4], s.u[8], s.u[12], s.u[3] = pid, 0x5000, 0x6000, 0x1234
    s.wr(syms['FAKE_CTRL'], 0)
    s.call(syms['CTRL_25E8'])
    assert s.u[3] == 0x1234
    return s.rd(syms['FAKE_CTRL']) == 0x777       # handed to the stock function


def write(s, syms):
    """One call of the wrapped Send writer on samples 1..16: what reached the stock writer, and I1 after."""
    for k in range(16):
        s.wr(SRC + k, k + 1)
    s.u[0x11] = SRC
    s.call(syms['ENTRY_2AAA'])
    return [s.rd(COPY + k) for k in range(16)], s.u[0x11]


@pytest.mark.parametrize('mode', [0, 1, 3])
def test_other_modes_write_the_send_jacks(mode):
    s, syms = dsp()
    assert not ctrl(s, syms, pu.MODE_PID, mode)
    samples, i1 = write(s, syms)
    assert samples == list(range(1, 17)) and i1 == SRC


def test_usb_only_writes_silence_to_the_send_jacks():
    s, syms = dsp()
    ctrl(s, syms, pu.MODE_PID, 2)
    samples, i1 = write(s, syms)
    assert samples == [0] * 16 and i1 == SRC, 'silence, and I1 back as it came'
    ctrl(s, syms, pu.MODE_PID, 1)
    assert write(s, syms)[0] == list(range(1, 17)), 'back to stock'


def test_the_mode_starts_stock():
    s, syms = dsp()
    assert s.rd(syms['USB_MODE']) == 0
    assert write(s, syms)[0] == list(range(1, 17))


@pytest.mark.parametrize('value, kept', [(0, 0), (2, 2), (3, 3), (4, 0), (-1, 0), (0x7fffffff, 0)])
def test_the_mode_word_holds_0_to_3(value, kept):
    s, syms = dsp()
    ctrl(s, syms, pu.MODE_PID, value)
    assert s.rd(syms['USB_MODE']) == kept


@pytest.mark.parametrize('pid', [0, 1, 2, 99, 101])
def test_other_pids_go_to_the_stock_control_function(pid):
    s, syms = dsp()
    assert ctrl(s, syms, pid, 2)
    assert s.rd(syms['USB_MODE']) == 0


def test_dsp_is_the_last_feature_in_block3():
    assert block3.FEATURES[-1] == ('HX_USB_MONITOR', 'patch_usbmon')
    env = {'HX_CLICK': '1', 'HX_FX_GATE': '1', 'HX_GR': '1', 'HX_USB_MONITOR': '1'}
    dm, pm = block3.place('HX_USB_MONITOR', env)
    n_dm, n_pm = pu.dsp_size()
    gr_dm, gr_pm = block3.place('HX_GR', env)
    assert dm + n_dm == block3.nw(pm) and block3.nw(pm + n_pm) <= gr_dm and pm % 2 == 0
    assert dm >= block3.room(block3.slots(env))[0]
    assert pu.mode_word(env) == dm, 'USB_MODE is the first data word'


# ---- the firmware tools/patch_usbmon.py builds

def stock_l6ia():
    stock = os.environ.get('HX_STOMP_HXF')
    if not stock:
        pytest.skip('HX_STOMP_HXF is not set')
    return pa.load_l6ia_from_any(stock)[0]


@pytest.fixture(scope='module')
def patched():
    data = stock_l6ia()
    return data, pu.patch_usbmon(pu.patch_dsp(data, **QUIET), **QUIET)


def ldr_blocks(data):
    e = pa.l6ia.parse(data)[2]
    raw = data[e['payload_off']: e['payload_off'] + e['payload_len']]
    w = struct.unpack('<%dI' % (len(raw) // 4), raw)
    size = {5: lambda c: ((c + 1) & ~1) * 3 // 2, 4: lambda c: c, 3: lambda c: (c + 1) // 2,
            6: lambda c: c * 2, 10: lambda c: c, 9: lambda c: c}
    i, out = 384, []
    while w[i] != 0:
        tag, cnt, addr = w[i:i + 3]
        n = size.get(tag, lambda c: 0)(cnt)
        out.append((tag, addr, tuple(w[i + 3:i + 3 + n])))
        i += 3 + n
    return out


@pytest.mark.firmware
def test_the_send_writer_and_the_meter_enter_the_dsp_code(patched):
    _, new = patched
    dm, pm = pu.dsp_place()
    _, syms = pa.sasm.assemble(pu.dsp_asm(dm, pm), 'usb_monitor.asm')
    rows = {b[0]: b for t, a, b in ldr_blocks(new) if t == 4 and len(b) == 8}
    assert rows[pu.SEND][4:6] == (0x60a5ed, syms['ENTRY_2AAA']), 'the writer\'s process code, its control function stock'
    assert rows[pu.METER][4:6] == (syms['CTRL_25E8'], pu.METER_PROC), 'the meter\'s control function, its process code stock'


@pytest.mark.firmware
def test_the_app_gets_the_mode_parameter(patched):
    data, new = patched
    before = pa.parse_entry3_full(pa.get_entry_swapped(data, 3))['models'][0]
    info = pa.parse_entry3_full(pa.get_entry_swapped(new, 3))
    app = info['models'][0]
    assert app['name'] == pu.APP
    assert [p['name'] for p in app['params'][:-1]] == [p['name'] for p in before['params']]
    p = app['params'][-1]
    assert (p['name'], p['type'], p['slot'], p['meta']) == (pu.NAME, 2, 67, {})
    assert struct.unpack('<2I', struct.pack('<2f', p['min'], p['max'])) == (0, pu.MODE_MAX)
    assert info['strings'].index(pu.NAME) == 1247, 'the stock string the M4 looks the parameter up by'


@pytest.mark.firmware
def test_no_other_app_parameter_is_named_output(patched):
    for data in patched:
        app = pa.parse_entry3_full(pa.get_entry_swapped(data, 3))['models'][0]
        assert [p['name'] for p in app['params']].count(pu.NAME) == (data is patched[1])


@pytest.mark.firmware
def test_the_parameter_writes_the_meter_as_the_mode_pid(patched):
    _, new = patched
    e4 = pa.get_entry_swapped(new, 4)
    w4 = struct.unpack('<%dI' % (len(e4) // 4), e4)
    b = pa.entry4_blob.blob(w4, 1)
    pm = b[b[6]: b[6] + b[7]]
    nodes = [pm[pm[0] + 10 * k: pm[0] + 10 * k + 10] for k in range(pm[18])]
    dt = [pm[pm[6] + 4 * k: pm[6] + 4 * k + 4] for k in range(pm[21])]
    ct = [pm[pm[4] + 4 * k: pm[4] + 4 * k + 4] for k in range(pm[20])]
    node, = [r[0] for r in dt if r[2] == 67]
    assert nodes[node][3] == pu.INT_OP
    to, = [r[1] for r in ct if r[0] == node]
    path, pid, n = pm[nodes[to][0]: nodes[to][0] + 3]
    assert nodes[to][3] == 1 and (pid, n) == (pu.MODE_PID, 1)
    assert b[path: path + 3] == list(pu.METER_PATH)
    pins = [b[b[10] + 4 * k: b[10] + 4 * k + 4] for k in range(b[11])]
    dflt, = [r for r in pins if r[1] == 67]
    assert b[dflt[0]: dflt[0] + 2] == [1, 0] and b[dflt[2]: dflt[2] + 2] == [1, 0], 'a root default of 0'
    assert not pa.pmap_slots_without_param(e4, 1, pa.parse_entry3_full(pa.get_entry_swapped(new, 3))['models'][0]['params'])


@pytest.mark.firmware
def test_other_models_and_blob0_are_unchanged(patched):
    data, new = patched
    old, now = (pa.parse_entry3_full(pa.get_entry_swapped(d, 3))['models'] for d in (data, new))
    assert pc.models_view({'models': old[1:]}) == pc.models_view({'models': now[1:]})
    e4s = [pa.get_entry_swapped(d, 4) for d in (data, new)]
    w4s = [struct.unpack('<%dI' % (len(e) // 4), e) for e in e4s]
    assert pa.entry4_blob.blob(w4s[0], 0) == pa.entry4_blob.blob(w4s[1], 0)


def test_runs_after_the_gate_and_before_the_gr_knobs():
    added, _ = patch_click.add_click(stock_l6ia(), **QUIET)
    out = pc.patch_comp(pu.patch_usbmon(pg.patch_gate(added, **QUIET), **QUIET), **QUIET)
    info = pa.parse_entry3_full(pa.get_entry_swapped(out, 3))
    assert info['models'][0]['params'][-1]['name'] == pu.NAME
    assert [p['name'] for p in pa.find_model(info, pc.COMP_MODELS[0][0])['params']][-3:] == [k[0] for k in pc.GR_KNOBS]


def test_entry3_goes_back_to_its_stock_place():
    """With NAM's add-model (its tables at the tail), the string section moves home first: Entry 3 stays under E3_MAX."""
    added, _ = patch_click.add_click(stock_l6ia(), **QUIET)        # a model step leaves the tables at the tail
    moved = pa.get_entry_swapped(added, 3)
    assert struct.unpack_from('<I', moved, 12)[0] >= pc.STOCK_E3_END
    back, _ = pc.e3_add_strings(moved, [pu.NAME], home=True)
    assert struct.unpack_from('<I', back, 12)[0] == pc.STR_HOME
    assert pc.models_view(pa.parse_entry3_full(moved)) == pc.models_view(pa.parse_entry3_full(back))


def build_steps(tmp_path, monkeypatch, unit, env):
    spec = importlib.util.spec_from_file_location('hxtra_build', ROOT / 'build.py')
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    stock = tmp_path / 'stock.hxf'
    stock.write_bytes(b'not firmware')
    import hashlib
    monkeypatch.setattr(build, 'STOCK_MD5', {hashlib.md5(stock.read_bytes()).hexdigest(): unit})
    for k in ('HX_GR', 'HX_CLICK', 'HX_FX_GATE', 'HX_USB_MONITOR'):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(build.os, 'replace', lambda *a: None)
    monkeypatch.setattr(build.os, 'remove', lambda *a: None)
    monkeypatch.setattr(sys, 'argv', ['build.py', str(stock), '-o', str(tmp_path / 'out.hxf'), '--no-check'])
    ran = []
    monkeypatch.setattr(build, 'run', lambda *a: ran.append(a[1:]) or 'ALL OK')
    build.main()
    return [a[0] for a in ran]


def test_build_order(tmp_path, monkeypatch):
    ran = build_steps(tmp_path, monkeypatch, 'HX_Stomp', {k: '1' for k in ('HX_CLICK', 'HX_FX_GATE', 'HX_GR', 'HX_USB_MONITOR')})
    assert ran.index('tools/patch_click.py') < ran.index('tools/patch_gate.py') < ran.index('tools/patch_usbmon.py') \
        < ran.index('tools/patch_comp.py')


def test_build_without_the_flag(tmp_path, monkeypatch):
    assert 'tools/patch_usbmon.py' not in build_steps(tmp_path, monkeypatch, 'HX_Stomp', {})


@pytest.mark.parametrize('unit', ['HX_Stomp_XL', 'HX_Effects'])
def test_hx_stomp_only(tmp_path, monkeypatch, unit):
    assert 'tools/patch_usbmon.py' not in build_steps(tmp_path, monkeypatch, unit, {'HX_USB_MONITOR': '1'})
