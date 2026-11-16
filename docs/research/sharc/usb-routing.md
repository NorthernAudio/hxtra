# USB routing and the app graph

Where the HX Stomp's inputs and outputs are chosen, and what reaches the computer over USB. Asked by issue #81 (monitoring through the DAW only). The Output block's own mixing into Main and Send is hxtra-a4's #93 research. Status tags as in [conventions.md](../conventions.md).

## What a user sees [community reports, not checked]

- USB 1/2 carries the main output to the computer, and USB 1/2 from the computer plays on the outputs and phones. USB 5/6 to the computer is the dry Main L/R input, and USB 7/8 is the dry Return L/R. Path B's Output reportedly reaches USB 3/4. Path A's Output offers no USB-only destination.
- So monitoring through a DAW without the HX Stomp's direct sound has no setting. Turning Path A's Output level down also silences USB 1/2.
- The Helix Floor, LT and Rack offer Output = USB 3/4 or USB 5/6 instead, which sends the processed sound to the computer only.

## The app graph (Entry 3 and Entry 4 blob 1) [verified offline]

- The routing is a fixed DSP graph, `HelixStomp_App`. Its model record is at e3 `0x19b00` (name string 4029, blob 1) and is not in the main model table. Its parameter records run from `0x80358` to `0x80b78`, 66 of them.
- Routing parameters:

| parameter | slot | type | values |
|---|---|---|---|
| `inputSelect.0`, `inputSelect.1` | 34, 35 | int | 0..7 |
| `outputSelect.1` (path B) | 36 | int | 0..9, default 0 |
| `outputSelect.0` (path A) | 37 | int | 0..9, default 1 |
| `returnType` | 54 | list | 0 Return, 1 Aux In |
| `masterVolSelect` | 55 | list | 1 Phones, 2 Main+HP |
| `usbInGain0_1` | 56 | float dB | -60..18, "USB Input Trim" |
| `applyEQ` | 58 | list | 0 Off, 1 1/4", 2 Send, 3 1/4"+Send |
| `phonesSelect` | 60 | list | 1 Main, 2 FX Send |
| `tunerOutputSelect` | 63 | int | 0..9 |

- The Output block models' `select` (`HelixStomp_AppDSPFlowOutputMain` slot 3, `...OutputSend` slot 100) is also int 0..9. The Input block's `select` (slot 4) is 0..7.
- Blob 1's parameter map wires these to the DSP:
  - `outputSelect.0` → an int input node (op `0xb`) → a writer to path [83], pid 3. The node tree overrides member 83 to composite `0x60000a`.
  - `outputSelect.1` → path [71], pid 100.
  - `usbInGain0_1` → paths [99] and [105], pid 1.
  - `phonesSelect` → two op `0x43` nodes → path [0] (the app itself), pids 42 and 45.
- Composite `0x60000a` (the output block) has two gains `0x225`, a pan/mix `0x2391`, two `0x25e6` sinks with init param 1 = 0 and 1, two `0x2390`, and a `0x25e8` with 2 inputs and init param 1 = 2.
- **[hypothesis]** `0x25e6` writes one output channel, and `select` picks its bus. Main and Send are separate models, and `OutputSend` has its own Mono/Stereo `Type`. So each of the 0..9 values is probably a single destination (6 = Send L/R), not a Helix-style "Multi" (post-send, #93).
- Blob 1's root node has type `0xffffffff`, and no composite in blob 0 has the 171 members its node tree uses (the largest, `0x6001ab`, has 154). So the app's top composite is not in blob 0. **[hypothesis]** The SHARC code builds it.

## The M4 rewrites Output select on preset load [verified on unit, 2026-11-14]

How it was tested: a plain build from `next` (image `9b4d2b60…`, boot hxtra-4c-1, RAM run). Every path block was emptied, the input block set to USB 5/6, and each Output select value written into the edit buffer with `hx_ctl.py load-preset` (preset block 9 key `6` for path A, block 19 key `16`.`6` for path B). Plucks from `play_mac` went in on USB 5/6, and `record_mac` recorded all 8 USB channels for 3 s.

- **Path A keeps 0 or 1 only.** Values 2..9 read back as 1 and sound exactly like 1. With 1, the signal is on USB 1/2 at -21.3 dBFS and USB 3..6 are digital zero. With 0, every channel is silent.
- **Path B keeps 0 or 6 only** (6 = Send). 1..5 read back as 0 and 7..9 as 6. With a block on path B, 0 also reads back as 6.
- `hx_ctl.py` still reports such a load as `verified`, so check the value read back, not that word.
- So the 0..9 range in Entry 3 is not reachable from a preset. The rewrite is M4 code: Entry 3 has no value list for these parameters.

## How the M4 sets an output's destination [verified offline, disassembly]

- The M4 names app-graph parameters by their Entry 3 string index. At app setup (`0x28df5d06`..), a loop resolves the table at `0x28e3db60` (mute, muteOutput, muteRampTimeMS, inputSelect.0/1, outputSelect.0/1, splitToLower, joinToLower) into handles at app + `0xacc`.. (outputSelect.0 at `+0xae0`, outputSelect.1 at `+0xae4`). The app object is `[engine] + 0x6484 * dsp`, and its instance handle is at `+0xac8`.
- `0x28df35e8(ctx + 4, instance, handle, &{u8 type, u32 value})` sets one app parameter (type 2 = int). The I/O Global Settings use it too: their keys at `0x28e3ec68` are string indices, e.g. 4217 phonesSelect, 4206 masterVolSelect, 4209 usbInGain0_1.
- **`0x28df5760(ctx, app, path, value)`** sends a destination. It refuses a value above 12 or outside mask `0x1cff` (0..7, 10..12). It stores the value at app + `0x150 * path + 0x2cd`, and 5 at `+0x2a9`. Then it sends it through the outputSelect.0/1 handle. Its getter is `0x28df57d8`.
- `0x28e002a8(engine, path, dsp, value)` checks the same mask, then calls `0x28df5760`. It has three callers, and the output block's setter is one of them.
- **`0x28e0a2fc(engine, block, value)`, the output block's setter, is the rewrite.** It acts only on block types 1 (output A) and 3 (merge, output B). A value of 0 is always set. Otherwise, on path A only 1 is set: other values reach `0x28e0a428` (`mov r11, r8; b` out). On path B only 6 is set, with extra setup at `0x28e0a42c` when `[block + 1] & ~2 == 1`: other values reach `0x28e0a382` (`mov r11, lr; b` out). A refused value changes nothing, which is why the preset reads back the old 1 or 6.
- A probe image (`output_any`, kept out of the repository since USB monitoring replaced it) turned both refusals into branches to the set at `0x28e0a390` (`05e0 00bf` at `0x28e0a382`, `b2e7 00bf` at `0x28e0a428`), so a preset could try every value the mask allows.
- To the computer, USB 5/6 was digital zero throughout, with nothing plugged into the Main inputs. USB 7/8 read about -95 dBFS, an analog noise floor. In none of these takes did the Send→Return L cable show signal on any USB channel.
- **Unconfirmed:** one last take played on USB 3/4, 1/2 or 7/8 from the computer with nothing routed. Every time, USB 7/8 to the computer read -21.7 dBFS, whichever channel played. It may have overlapped another session's boot, so repeat it before trusting it.

## What each destination does [verified on unit, 2026-11-14]

How it was tested: the sweep above on that probe build from `next` (image `5c82add0…`, boot usb-monitor-2, RAM run). Path A's Output select was set to each value the mask allows, with path B empty. Send L ran into Return L through a mono cable. The setting reads back as written now.

| path A Output select | USB to the computer |
|---|---|
| 1, 5 | 1/2 at -21.3 dBFS (Main); 3..8 as with no signal |
| 6 | **3/4 at -21.3 dBFS, 1/2 silent**; 7/8 at -21.8 dBFS through the cable |
| 0, 2, 3, 4, 7, 10, 11, 12 | silent everywhere (destinations the HX Stomp lacks) |
| 8, 9 | refused by `0x28df5760`'s mask |

- **USB 3/4 to the computer is the Send bus**: Send L/R and USB 3/4 carry the same signal. **USB 7/8 is Return L/R, dry**: the cable's Send L arrives on both 7 and 8, so a mono Return feeds both. USB 5/6 is the dry Main input, digital zero with nothing plugged in.
- So **path A Output = 6 is USB-only monitoring (issue #81)**. The processed sound goes to the computer on USB 3/4 and to the Send jacks, while Main, the phones (phonesSelect = Main) and USB 1/2 carry only the computer's playback. Stock firmware refuses it on path A. On path B the forum workaround reaches the same Send bus.
- **No value sends to Main and Send together** (no Helix-style Multi), so issue #93 gets nothing from this setting.
- Path B (a block kept on B, Output A = 1) gave no signal on any channel for any value, so path B was probably getting no audio in the test preset. Not conclusive. Value 5 on path B failed to load.

## Hardware against software monitoring, measured at the jacks [verified on unit, 2026-11-14]

How it was tested: same image and run as above. Main Out L went into input 1 of a Volt 4, the phones into input 2, both line level at a similar gain. The HX Stomp's USB and the Volt were recorded at the same time, 3 s per take. "Guitar" means plucks on USB 5/6 with input A set to USB 5/6. "DAW" means plucks on USB 1/2 from the computer. Levels are in dBFS.

| case | USB 1/2 | USB 3/4 | USB 7/8 (Return) | Main L | phones |
|---|---|---|---|---|---|
| nothing playing (noise floor) | silent | silent | -98 | -62 | -86 |
| Output A = Main, guitar | -21.3 | silent | -98 | **-7.4** | **-58.9** |
| Output A = Send, guitar | silent | **-21.3** | -21.8 | -62.1 (floor) | -86.0 (floor) |
| Output A = Send, DAW | silent | silent | -98 | -24.2 | -77.0 |
| Output A = Main, DAW | silent | silent | -98 | -24.2 | -77.0 |
| stock: A level -120, block on B, A/B split even, Output B = Send, guitar | silent | -27.5 | -27.9 | -63.1 (floor) | -85.9 (floor) |

- **Output A = Send is software monitoring.** The processed sound reaches only the computer (USB 3/4) and the Send jacks. Main and the phones stay at their noise floor, and the computer's playback on USB 1/2 still reaches both, exactly as with Main. This answers issue #81.
- **The stock route does the same**: path A's Output level at -120 dB, a block on path B, and Output B = Send. Only the even split's 6 dB is lost. It costs a block and a split, but needs no HXtra.
- The phones read lower than Main L only because of their own volume and the Volt's gain. Each column is compared with its own noise floor.

## Send and FX Loop blocks share the Send bus [verified on unit, 2026-11-16]

How it was tested: the USB Monitor build (image `997d079e…`, boot usb-monitor-5) with Path A Out on Send/USB, nothing plugged into Return, plucks on USB 5/6, one block in path A's first slot. Send L/R is preset ID 254, kind 29; FX Loop L/R is 145, kind 13 (Table 1 and the Send/Return browser items).

| path A | USB 3/4 |
|---|---|
| no block | -21.3 dBFS |
| Send L/R, Send -6 dB, DryThru 0 dB | -17.8 dBFS: the send (-27.3) and the output (-21.3) added |
| FX Loop L/R, Send 0 dB, Mix 0.5 | -15.3 dBFS: two copies added |

- A Send or FX Loop block's send and an output set to Send are summed into one bus, the Send jacks and USB 3/4 together. Neither replaces the other.
- So with an FX Loop block, an output on Send feeds back through whatever is in the loop.
- The HX Stomp adds a fourth value (a bool) to an FX Loop block's parameters when it loads one.

## Open

- The physical Main output for values 2..4, 7 and 10..12: only USB was recorded for them.
- What HX Edit shows for path A's Output with Send/USB on.
- A USB-only destination: Send/USB reaches the computer only through the Send bus. Separating USB 3/4 from the Send jacks needs the SHARC's side of the routing.
