#!/usr/bin/env python3
"""m4cache.py - the M4 code of the web page's features, made at a release for the page, which has no clang.

usage: m4cache.py <HX_Stomp_v3.80.0_0x103966115.hxf> [-o build/m4cache.json] [--release v1.0.0]

Runs the features of tools/patch_menu.py, all those the page builds, on the images build.py gives them (the stock file with
NAM A2 Lite added, and without it for HX_NAM_SLOTS=0: the features' code reads addresses in it), keeping what every module
assembled to (keyed by m4asm.key), then builds every combination the page offers with build.py to pin its MD5: each NAM slot
count with each set of DSP features that fits beside it (tools/block3.py), with each set of the other opt-ins. The page reads
the room and the costs from "dsp". tools/release.py attaches the file to
the GitHub release, and the Pages workflow publishes it next to the page; m4asm reads it when HX_M4_CACHE names it.
"""
import argparse
import hashlib
import importlib.util
import itertools
import json
import os
import subprocess
import sys
import tempfile

import block3
import features
import m4asm
import patch_amp as pa
import patch_menu as pm

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
UNIT = 'HX_Stomp'                   # the features are the HX Stomp's only


def web_flags():
    """The switch of every feature the page always builds (WEB True, the default), in feature order."""
    return _web(True)


def web_options():
    """The switch of every feature the page offers as a checkbox, off until ticked (WEB 'opt-in'), in feature order."""
    return _web('opt-in')


def web_dsp():
    """The switch of every feature the page offers among its DSP features, off until ticked (WEB 'dsp'), in feature order."""
    return _web('dsp')


def _web(kind):
    return [features.flags(m)[0] for m in features.load() if features.flags(m) and getattr(m, 'WEB', True) == kind]


def combo_key(flags):
    return '+'.join(sorted(flags))


def subsets(flags):
    return [list(c) for n in range(len(flags) + 1) for c in itertools.combinations(flags, n)]


def slots_flag(slots):
    """The NAM slot count as the pseudo-flag a combination's key and built_md5's environment take."""
    return f'{block3.VAR}={slots}'


def nam_base(stock, d):
    """The image build.py hands tools/patch_menu.py: build.py's STEPS on the stock file, written in the directory d."""
    spec = importlib.util.spec_from_file_location('build', os.path.join(ROOT, 'build.py'))
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    src = stock
    for k, step in enumerate(build.STEPS[UNIT]):
        dst = os.path.join(d, f'nam_lite_{k}.l6ia')
        r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'patch_amp.py'), step[0], src, dst, *step[1:]],
                           cwd=ROOT, capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(f'm4cache: patch_amp.py {step[0]} failed:\n{r.stdout}{r.stderr}')
        src = dst
    return src


def modules(stock, flags, nam=True):
    """{m4asm.key: {code, symbols}} of every module the features of flags assemble, on the image with NAM A2 Lite (nam) or without."""
    out, assemble = {}, m4asm.assemble_module

    def keep(src, include=()):
        code, symbols = assemble(src, include)
        out[m4asm.key(src, include)] = {'code': code.hex(), 'symbols': symbols}
        return code, symbols

    with tempfile.TemporaryDirectory() as d:
        data, _ = pa.load_l6ia_from_any(nam_base(stock, d) if nam else stock)
    m4asm.assemble_module = keep
    try:
        pm.menu_entries(lambda e: pa.get_entry_swapped(data, e), env={f: '1' for f in flags})
    finally:
        m4asm.assemble_module = assemble
    return out


def built_md5(stock, flags):
    """The MD5 of build.py's .hxf with flags on (a 'VAR=value' one set to its value) and no other HX_ variable."""
    env = {k: v for k, v in os.environ.items() if not k.startswith('HX_')}
    env.update(f.split('=', 1) if '=' in f else (f, '1') for f in flags)
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, 'out.hxf')
        r = subprocess.run([sys.executable, os.path.join(ROOT, 'build.py'), os.path.abspath(stock), '-o', out, '--no-check'],
                           env=env, cwd=ROOT, capture_output=True, text=True)
        if r.returncode or 'ALL OK' not in r.stdout:
            raise SystemExit(f'm4cache: the build with {combo_key(flags) or "no features"} failed:\n{r.stdout}{r.stderr}')
        return hashlib.md5(open(out, 'rb').read()).hexdigest()


def make(stock, release=None):
    if os.environ.get(m4asm.CACHE):
        raise SystemExit(f'm4cache: unset {m4asm.CACHE}: this assembles with clang')
    flags, options, dsp = web_flags(), web_options(), web_dsp()
    combos = [flags + d + o + [slots_flag(s)] for s in block3.SLOTS for d in subsets(dsp) if block3.fits(s, d)
              for o in subsets(options)]
    every = flags + options + dsp
    return {'release': release, 'unit': UNIT, 'features': flags, 'options': options,
            'dsp': {'features': dsp, 'slots': list(block3.SLOTS), 'room': {str(s): block3.words(s) for s in block3.SLOTS},
                    'cost': {f: block3.cost(f) for f in dsp}},
            'md5': {UNIT: {combo_key(c): built_md5(stock, c) for c in combos}},
            'modules': {**modules(stock, every), **modules(stock, every, nam=False)}}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('stock', help='the stock HX Stomp 3.80.0 .hxf')
    ap.add_argument('-o', '--out', default=os.path.join(ROOT, 'build', 'm4cache.json'))
    ap.add_argument('--release', help='the release tag it is made for, shown on the page')
    a = ap.parse_args()
    cache = make(a.stock, a.release)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, 'w') as f:
        json.dump(cache, f, separators=(',', ':'), sort_keys=True)
    print(f'[+] Wrote {a.out}: {len(cache["modules"])} modules for {", ".join(cache["features"])}')


if __name__ == '__main__':
    main()
