#!/usr/bin/env python3
"""patch_usbmon.py - Path A Out's output modes in the DSP (issues #81 and #93): the mode word and the USB Only mode.

usage: patch_usbmon.py <in .hxf | L6IA> <out .hxf | L6IA> [--donor stock.hxf]

The M4 (tools/features/usb_monitor.py) sends the setting as the app's parameter 'Output' after each send of path A's destination.
  Entry 3: HelixStomp_App gets an int parameter named with the stock string 'Output' (a name no other app parameter has, so the
           M4's lookup by string index finds it in every build; no string is added).
  Entry 4: blob 1 gets its input node, a root default (0) and a writer handing it to path [83, 10], the output block's stereo meter
           0x25e8, as pid MODE_PID. That path has a sub-binding already, so no binding is added (docs/research/sharc/cores/gates.md).
  Entry 2: src/sharc/usb_monitor.asm in Block 3 where tools/block3.py places it; 0x25e8's control function keeps the mode in
           USB_MODE, and the Send jacks' writer 0x2aaa writes silence while it is USB Only.
Run it after patch_click.py and patch_gate.py and before patch_comp.py: the steps that add models rebuild Entry 3's and Entry 4's tails.
"""
import argparse
import os
import struct

import block3
import nam_multi
import patch_amp as pa
import patch_comp as pc

ASM = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src', 'sharc', 'usb_monitor.asm')
FLAG = 'HX_USB_MONITOR'
APP = 'HelixStomp_App'
NAME = 'Output'                         # stock string 1247: display text of block models, no app parameter's name
MODE_PID = 100                          # usb_monitor.asm's
MODE_MAX = 3                            # 0 Main L/R, 1 Send/USB, 2 USB Only, 3 Main+Snd (DECISIONS.md)
METER_PATH = (2, 83, 10)                # path A's output block (app member 83, composite 0x60000a), its member 10: the meter
INT_OP = 0x0b                           # an int input node, as outputSelect.0's
SEND, SEND_PROC = 0x2aaa, 0x8ce36       # the Send jacks' writer and its stock process code
METER, METER_PROC, METER_CTRL = 0x25e8, 0x8db42, 0x6105d1   # the stereo meter: process code (unchanged) and control function


def dsp_asm(dm, pm):
    """usb_monitor.asm with its data at dm and its code at pm."""
    return open(ASM).read().replace('UM_DM_BASE', f'{dm:#x}').replace('UM_PM_BASE', f'{pm:#x}')


def dsp_size():
    """(data words, instructions) of usb_monitor.asm."""
    secs, _ = pa.sasm.assemble(dsp_asm(nam_multi.B3, nam_multi.NW3), 'usb_monitor.asm')
    return tuple(sum(len(s.words) for s in secs if s.kind == k) for k in ('dm', 'pm'))


def dsp_place():
    """(DM base, PM base) of usb_monitor.asm (tools/block3.py)."""
    return block3.place(FLAG)


def mode_word(env=os.environ):
    """USB_MODE's DM address in the build env describes: the word the output writers' wrappers read."""
    dm, pm = block3.place(FLAG, env)
    _, syms = pa.sasm.assemble(dsp_asm(dm, pm), 'usb_monitor.asm')
    return syms['USB_MODE']


def patch_dsp(l6ia_bytes, log=print):
    """Entry 2: usb_monitor.asm at dsp_place(); the Send writer's process function and the meter's control function entering it."""
    dm, pm = dsp_place()
    secs, syms = pa.sasm.assemble(dsp_asm(dm, pm), 'usb_monitor.asm')
    entries = pa.l6ia.parse(l6ia_bytes)
    e2 = l6ia_bytes[entries[2]['payload_off']: entries[2]['payload_off'] + entries[2]['payload_len']]
    ldr = []
    for sec in secs:
        ldr += (pa.pack_init_l48 if sec.kind == 'pm' else pa.pack_init_l32)(sec.addr, sec.words)
        log(f"[+] Entry 2: USB monitor {len(sec.words)} {'instructions' if sec.kind == 'pm' else 'words'} @ {sec.kind.upper()} {sec.addr:#x}")
    ldr += pa.wrap_primitive(e2, f'{SEND:#x}:{SEND_PROC:#x}', syms['ENTRY_2AAA'])
    ldr += pa.wrap_primitive(e2, f'{METER:#x}:{METER_PROC:#x}', METER_PROC, (METER_CTRL, syms['CTRL_25E8']))
    log(f"[+] Entry 2: the mode word is DM {syms['USB_MODE']:#x}")
    new, _, _ = pa.l6ia.rebuild_archive(l6ia_bytes, {2: pa.l6ia.swap32(pa.inject_sharc_ldr_blocks(e2, ldr))})
    return new


def e3_add_mode(e3):
    """Entry 3 with the int parameter NAME (0..MODE_MAX, default 0) after the app's own. Returns (Entry 3, its slot, name index)."""
    e3 = bytearray(e3)
    info = pa.parse_entry3_full(bytes(e3))
    m = info['models'][0]
    assert m['name'] == APP, f'model 0 is {m["name"]}, not {APP}'
    names = [p['name'] for p in m['params']]
    assert NAME not in names, f'{APP} has a parameter named {NAME!r} already'
    name_idx = info['strings'].index(NAME)
    d = list(m['words'])
    n_par = d[7]
    slot = max(p['slot'] for p in m['params']) + 1
    base = pa._align(len(e3), 4)
    e3 += bytes(base - len(e3))
    d[11] = base
    e3 += bytes(e3[m['words'][11]: m['words'][11] + 32 * n_par])
    e3 += struct.pack('<8I', 0, 0, name_idx, 2, slot, 0, MODE_MAX, 0)     # an int list: no meta, min 0, max MODE_MAX, default 0
    d[7] = n_par + 1
    struct.pack_into('<14I', e3, m['off'], *d)
    struct.pack_into('<I', e3, 8, len(e3))
    if len(e3) > pa.E3_MAX:
        raise SystemExit(f'Entry 3 would be {len(e3):#x} bytes; its partition holds {pa.E3_MAX:#x}')
    return bytes(e3), slot, name_idx


def path_offset(b, path):
    """The offset of the path words `path` among the blob's paths (before its node tree)."""
    found = [k for k in range(12, b[2]) if tuple(b[k: k + len(path)]) == tuple(path)]
    assert len(found) == 1, f'{len(found)} copies of path {list(path)} in the blob'
    return found[0]


def blob_add_mode(b, slot):
    """Blob 1 with an int input node for the parameter at `slot`, a root default (0) and a writer handing it to the meter as
    MODE_PID. Laid out as patch_gate.blob_add_gate does: the parameter map, init records and relocation list are rebuilt after the
    node tree, nothing before the parameter map moves."""
    assert b[0] == 3 and b[6] < b[10] < b[4] < b[8] and b[8] + 2 * b[9] == len(b), 'unexpected blob layout'
    po, pl, pin, npin, ini, nini, sub, nsub = b[6], b[7], b[10], b[11], b[4], b[5], b[8], b[9]
    pm = list(b[po: po + pl])
    assert pc.pmap_sizes(pm) == pm[12:18], 'the parameter map\'s sizes do not follow its tables'
    a, c, d, e = pm[0], pm[4], pm[6], pm[8]
    nA, nC, nD, nE = pm[18], pm[20], pm[21], pm[22]
    nodes = [pm[a + 10 * k: a + 10 * k + 10] for k in range(nA)]
    ct = [pm[c + 4 * k: c + 4 * k + 4] for k in range(nC)]
    dt = [pm[d + 4 * k: d + 4 * k + 4] for k in range(nD)]
    et = [pm[e + 4 * k: e + 4 * k + 4] for k in range(nE)]
    assert sorted(r[2] for r in dt) == list(range(1, slot)), 'slot map is not slots 1..n'
    pins = [b[pin + 4 * k: pin + 4 * k + 4] for k in range(npin)]
    root = {r[0] for r in pins if r[3] == 1 and b[r[0]: r[0] + 2] == [1, 0]}
    assert len(root) == 1, 'no single root path among the init records'
    root = root.pop()
    meter = path_offset(b, METER_PATH)
    assert meter in {w for k in range(nsub) for w in b[sub + 2 * k: sub + 2 * k + 1]}, 'the meter\'s path has no sub-binding'
    like = [nd for nd in nodes if nd[3] == INT_OP]
    assert like, 'no int input node to take the data words of'
    nodes.append([like[0][0], 0, nA, INT_OP, 1, 2, 0, 0, 1, 0])
    dt.append([nA, nE, slot, 0])
    et.append([nA, nE, nE, 0])
    writer = len(pm)                    # its data {path, pid, 1}, for the relocation list
    nodes.append([writer, 0, nA + 1, 1, 0, 3, 3, 3, 0, 0])
    pm += [meter, MODE_PID, 1]
    ct.append([nA, nA + 1, 0, 0])
    pm[0] = len(pm)
    pm += [w for nd in nodes for w in nd]
    pm[4] = len(pm)
    pm += [w for r in ct for w in r]
    pm[6] = len(pm)
    pm += [w for r in dt for w in r]
    pm[8] = len(pm)
    pm += [w for r in et for w in r]
    pm[18], pm[20], pm[21], pm[22] = len(nodes), len(ct), len(dt), len(et)
    pm[12:18] = pc.pmap_sizes(pm)

    out = list(b[:po])
    new_po = len(out)
    out += pm
    new_pin = len(out)
    vals = new_pin + 4 * (npin + 1) + 2 * (nini + 2) + 2 * nsub
    for r in pins:
        out += r
    out += [root, slot, vals, 1]
    new_ini = len(out)
    for k in range(nini):
        t, off = b[ini + 2 * k: ini + 2 * k + 2]
        if po <= off < po + pl:
            off += new_po - po
        elif pin <= off < pin + 4 * npin:
            off += new_pin - pin
        else:
            assert off < po, f'relocation at {off:#x} is in no table this moves'
        out += [t, off]
    out += [1, new_po + writer]
    out += [1, new_pin + 4 * npin]
    new_sub = len(out)
    out += b[sub: sub + 2 * nsub]
    assert all(w < po for w in b[sub: sub + 2 * nsub]), 'a sub-binding points past the node tree'
    assert len(out) == vals
    out += [1, 0]                       # the default: 0, stock
    out[4], out[5], out[6], out[7] = new_ini, nini + 2, new_po, len(pm)
    out[8], out[10], out[11] = new_sub, new_pin, npin + 1
    return out


def patch_usbmon(l6ia_bytes, log=print):
    e3 = pa.get_entry_swapped(l6ia_bytes, 3)
    e4 = pa.get_entry_swapped(l6ia_bytes, 4)
    before, before_e3 = pa.parse_entry3_full(e3), e3
    e3, _ = pc.e3_add_strings(e3, [NAME], home=True)   # adds nothing; the section back in its stock place keeps Entry 3 small
    assert pc.models_view(before) == pc.models_view(pa.parse_entry3_full(e3)), 'the string section move changed a model'
    assert pc.slot_lists(before_e3) == pc.slot_lists(e3), 'the string section move changed a slot list'
    m = pa.parse_entry3_full(e3)['models'][0]
    e3, slot, name_idx = e3_add_mode(e3)
    w4 = struct.unpack('<%dI' % (len(e4) // 4), e4)
    e4 = pc.e4_replace_blob(e4, m['blob_index'], blob_add_mode(pa.entry4_blob.blob(w4, m['blob_index']), slot))
    chk = pa.parse_entry3_full(e3)['models'][0]
    assert not pa.pmap_slots_without_param(e4, m['blob_index'], chk['params'])
    log(f"[+] {APP}: parameter {NAME!r} (string {name_idx}) on slot {slot} to path {list(METER_PATH[1:])} pid {MODE_PID}")
    new, _, _ = pa.l6ia.rebuild_archive(l6ia_bytes, {3: e3, 4: e4})
    return new


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('input', help='.hxf or L6IA')
    ap.add_argument('output')
    ap.add_argument('--donor', help='Stock .hxf of the unit, when input is a raw L6IA and output a .hxf')
    a = ap.parse_args()
    data, is_hxf = pa.load_l6ia_from_any(a.input)
    pa.save_l6ia_to_any(patch_usbmon(patch_dsp(data)), a.output, donor_hxf=a.input if is_hxf else a.donor)
    print(f'[+] Wrote {a.output}')


if __name__ == '__main__':
    main()
