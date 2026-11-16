// usb_monitor.asm - Path A Out's output modes in the DSP (issues #81, #93), around two stock primitives:
//   the output meter 0x25e8's control function keeps the mode the app parameter 'Output' writes (pid MODE_PID,
//   tools/patch_usbmon.py) in USB_MODE, 0..3 (anything else is 0, stock); every other pid goes to the stock function;
//   the Send jacks' writer 0x2aaa writes silence while USB_MODE is USB_ONLY, so path A on the Send bus reaches only USB 3/4.
// USB_MODE is the one mode word every output-writer wrapper reads (DECISIONS.md, "Output modes share one mode word").
// tools/patch_usbmon.py places it in Block 3 (UM_DM_BASE, UM_PM_BASE).
.equ PEYEN,   0x200000
.equ BDCST9,  0x400000
.equ ORIG_2AAA, 0x8ce36                 // the Send jacks' writer's stock process code (port 6, SPORT4 B)
.equ ORIG_CTRL_25E8, 0x6105d1           // the output meter's stock control function (compiled C, VISA code in DDR2)
.equ MODE_PID, 100                      // past the meter's own pids
.equ MODE_MAX, 3                        // 0 Main L/R, 1 Send/USB, 2 USB Only, 3 Main+Snd
.equ USB_ONLY, 2
.equ BLOCK,   16                        // samples a call

.section dm UM_DM_BASE
USB_MODE: .space 1
U_I1:     .space 1
U_SAVE:   .space 3
U_ZERO:   .space BLOCK                  // a silent input

.section pm UM_PM_BASE
ENTRY_2AAA:                             // the Send jacks' writer: I0 its instance (DM(0, I0) the channel), I1 its 16-sample input
    DM(U_I1) = I1;
    DM(U_SAVE + 0) = MODE1;
    BIT CLR MODE1 PEYEN | BDCST9;
    NOP;
    DM(U_SAVE + 1) = R0;
    DM(U_SAVE + 2) = R1;
    R0 = DM(USB_MODE);
    R1 = USB_ONLY;
    COMP(R0, R1);
    IF NE JUMP s_call;
    I1 = U_ZERO;
s_call:
    R0 = DM(U_SAVE + 1);
    R1 = DM(U_SAVE + 2);
    MODE1 = DM(U_SAVE + 0);
    NOP;
    CALL ORIG_2AAA;
    I1 = DM(U_I1);
    RTS;

CTRL_25E8:                              // (pid R4, the value at R8, the meter's state R12): a C function
    R2 = MODE_PID;
    COMP(R4, R2);
    IF NE JUMP ORIG_CTRL_25E8;
    I4 = R8;
    R8 = DM(0, I4);                     // the mode, an int
    R2 = MODE_MAX;
    COMPU(R8, R2);
    IF GT R8 = R8 - R8;                 // out of range (negative too): stock
    DM(USB_MODE) = R8;
    R0 = 0;
    I12 = DM(M7, I6);
    JUMP (M14, I12) (DB);
    NOP;
    RFRAME;
