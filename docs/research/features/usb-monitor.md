# USB monitoring

Global Settings > Ins/Outs > Path A Out (`HX_USB_MONITOR`, `tools/features/usb_monitor.py`, `src/m4/usb_monitor.s`): Send/USB sends path A to the Send bus, which is USB 3/4 to the computer and the Send jacks, instead of Main L/R. A DAW can then monitor the processed sound (issue #81). How the routing works: [sharc/usb-routing.md](../sharc/usb-routing.md). Status tags as in [conventions.md](../conventions.md).

## How it works [verified offline, unicorn: tests/test_usb_monitor.py]

- **The setting**: virtual ID `0xe0`, container 112 bits 0..1, in Ins/Outs' last empty slot (page 3, slot 3). Ins/Outs is stock category 0, with page table `0x28e3b55c` and 3 pages (`patch_menu.STOCK_CATEGORIES`).
- **The swap**: the feature owns `0x28df5760(ctx, app, path, value)`, which sends a path's destination to the DSP. For path 0 with value 1 (Main) it reads the setting and sends 6 (Send) instead when the setting is Send/USB. Every other path and value goes through unchanged. It notes the value it sent for path A in `um_sent`.
- **A change takes effect at once**:
  - After CHANGED `0x28dceb30(view, ID)` with ID `0xe0` (a turn), and after the page repaint `0x28dce854(view)` (a click's reset), `um_apply` compares the setting with `um_sent`.
  - When they differ and path A is on Main or Send, it calls the stock output API `0x28e03c68(engine, 9, 1)`. The engine comes from `0x28d92a98()`, and 9 is path A's Output block's grid position. That call ends in the owned send, which applies the setting.
  - Nothing is sent while path A's Output is off (0) or before the first send.
- **Presets**: the edit buffer reads back the value sent, so a preset saved with Send/USB on holds 6 for path A. A stock unit's setter refuses 6 on path A and keeps Main.

## On the unit [verified on unit, 2026-11-16]

All on RAM runs from `next`. The Volt 4 had Main Out L on input 1 and the phones on input 2. Plucks played on USB 5/6 with input A on USB 5/6, or on USB 1/2 for "DAW".

- **usb-monitor-4** (own section, image `877cd8b0…`):
  - Main L/R: the guitar is on USB 1/2, Main L at -15.6 dBFS and the phones at -1.9.
  - Send/USB: the guitar is on USB 3/4 at -21.3, and Main and the phones sit at their floors (-63.8 and -66.6 against -60 and -64 with nothing playing). The DAW on USB 1/2 reaches Main (-33.6) and the phones (-12.1).
  - A knob turn to Send/USB moved the sound to USB 3/4 with no preset reload, and a knob-press reset brought it back to Main.
  - The section's title, label and value read right.
- **usb-monitor-5** (in Ins/Outs, image `997d079e…`): Send/USB gave the same results (USB 3/4 at -21.3, Main and phones at their floors, the DAW on both).
- With a Send or FX Loop block in path A, their send adds into USB 3/4. See [sharc/usb-routing.md](../sharc/usb-routing.md), "Send and FX Loop blocks share the Send bus".
