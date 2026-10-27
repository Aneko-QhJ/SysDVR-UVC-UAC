/* HOS usb AD8D36F2 only. AAPCS64, entered from 302E0 with its 16-byte frame.
 * Single 192-byte packet: ceil(length/MPS)=1 => TBC=0, TLBPC=0.
 * The tail of this ISO ring is a private bounded diagnostic mailbox.
 * No host-side code or objects are called or overwritten.
 */
.section .text.iso,"ax",%progbits
.global iso_enter, iso_event, iso_report, iso_end
.equ ISO_ENTRY, 0x270  /* 22078 + 7*48 = 22270; EP 83 => index 7 */

iso_enter:
    cbz x2, reject
    cmp w3, #192
    b.ne reject
    ldrb w9, [x1, #2]
    cmp w9, #0x83
    b.ne reject
    ldr w9, [x1, #4]  /* configured MPS, interval=4; +7 is companion bLength */
    and w9, w9, #0xffffff
    mov w10, #ISO_MPS
    movk w10, #4, lsl #16
    cmp w9, w10
    b.ne reject
    add x6, x0, #0x22, lsl #12
    ldr w9, [x6, #0xa58]
    sub w9, w9, #3
    cmp w9, #1
    b.hi reject
    cbz w9, check_burst
    ldrh w9, [x1, #0xb]
    cmp w9, #192
    b.ne reject
check_burst:
    ldrh w9, [x1, #9] /* burst/mult must both be zero */
    cbnz w9, reject
    ldp x8, x9, [x1, #0x18]
    cmp x8, x9        /* one TD in flight, including uncertain completions */
    b.ne reject
    ldr x10, [x1, #0x10]
    add x13, x10, #0xf70
    ldr x9, [x1, #0x28]
    cmp x9, x13
    b.eq installed
    ldr q0, [x9]
    str q0, [x13]
    str x13, [x1, #0x28]
installed:
    add x5, x10, #0xf80
    mov w9, #0x5349
    movk w9, #0x314f, lsl #16 /* ISO1 */
    mov w10, #VARIANT
    stp w9, w10, [x5]
    str xzr, [x5, #8] /* events, terminal */
    ldr x9, [x6, #0x50]
    ldr q0, [x9, #0x1c0]
    str q0, [x5, #0x10]
    ldr x9, [x1, #0x10]
    sub x9, x8, x9
    ldr x10, [x1, #0x38]
    add x9, x9, x10
    str x9, [x5, #0x20] /* Isoch physical pointer for ED=0 events */
    ldrb w12, [x1, #0x40]
#if VARIANT == 1
    mov w11, #0x1400
#else
    mov w11, #0x1420 /* IOC B/C, encoded directly */
#endif
#if FRAME_LEAD > 0 && (VARIANT == 2 || EXPLICIT_ALL)
    ldr x9, [x6, #8] /* verified device MMIO base */
    ldr w9, [x9, #0x48] /* 8 kHz microframe counter, sampled at publication */
    lsr w9, w9, #3
    add w9, w9, #FRAME_LEAD
    and w9, w9, #0x7ff
    orr w11, w11, w9, lsl #20 /* explicit Frame ID; SIA=0 */
#else
    movk w11, #0x8000, lsl #16 /* SIA bit31 */
#endif
#if VARIANT != 2
    orr w11, w11, #0x10 /* Chain A/C */
#endif
    orr w11, w11, w12
    eor w9, w11, #1 /* publish first TRB last */
    stp x2, xzr, [x8]
    stp w3, w9, [x8, #8]
    mov x2, x8       /* first TRB virtual address */
    mov w15, #0x10
#if VARIANT == 2
    mov w15, #0
#endif
    bl advance
#if VARIANT != 2
    str x8, [x5, #0x28] /* ED self/tag is virtual in original DS producer */
    stp x8, xzr, [x8]
    mov w9, #0x1c20
    orr w9, w9, w12
    str w9, [x8, #12]
    ldr q0, [x8]
    str q0, [x5, #0x40]
    mov w15, #0
    bl advance
#else
    str xzr, [x5, #0x28]
    stp xzr, xzr, [x5, #0x40]
#endif
    str x8, [x1, #0x18]
    strb w12, [x1, #0x40]
    dsb sy
    str w11, [x2, #12]
    ldr q0, [x2]
    str q0, [x5, #0x30]
    dsb sy
    ldp x29, x30, [sp], #16
    b doorbell_tail /* original device MMIO and doorbell checks */
reject:
    b reject_original

/* x8 next cursor, x13 Link, w12 cycle, w15 TD Chain. */
advance:
    add x8, x8, #16
    cmp x8, x13
    b.ne advance_done
    mov w9, #0x1802
    orr w9, w9, w12
    orr w9, w9, w15
    str w9, [x13, #12]
    eor w12, w12, #1
    ldr x8, [x1, #0x10]
advance_done:
    ret

/* Called in place of 30700's transfer-event dispatch; x0 controller, x1 event. */
iso_event:
    ldr w8, [x1, #12]
    ubfx w9, w8, #16, #5
    cmp w9, #7
    b.ne event_original
    add x9, x0, #0x22, lsl #12
    add x10, x9, #ISO_ENTRY
    ldr x5, [x10, #0x10]
    cbz x5, event_original
    add x5, x5, #0xf80
    ldr w6, [x5]
    mov w7, #0x5349
    movk w7, #0x314f, lsl #16
    cmp w6, w7
    b.ne event_original
    ldr w6, [x5, #8]
    cmp w6, #2
    b.hs log_latest
    add x7, x5, x6, lsl #4
    ldr q0, [x1]
    str q0, [x7, #0x50]
    b log_full
log_latest:
    ldr q0, [x1]
    str q0, [x5, #0x40] /* replace ED snapshot with latest event after event 2 */
log_full:
    add w6, w6, #1
    str w6, [x5, #8]
    ldr w6, [x5, #12]
    cbnz w6, event_done
    ldr x6, [x1]
#if VARIANT == 2
    tbnz w8, #2, event_done /* B has no ED tag, including tag zero */
#else
    tbz w8, #2, plain_event
    ldr x7, [x5, #0x28]
    b match_tag
#endif
plain_event:
    ldr x7, [x5, #0x20]
match_tag:
    cmp x6, x7
    b.ne event_done
    ldr w4, [x1, #8]
    lsr w6, w4, #24
    cmp w6, #1
    b.ne event_error /* latch error; a later successful ED cannot release */
#if VARIANT != 2
    tbz w8, #2, event_done /* plain success in A/C waits for ED */
#endif
    and w4, w4, #0xffffff
    cmp w4, #192
    b.hi event_error
    mov w6, #1
#if RETAIN_SUCCESS && (VARIANT == 2 || EXPLICIT_ALL)
    orr w6, w6, #0x40000000 /* observed hardware success, URB/DMA still owned */
    str w6, [x5, #12]
    ret
#else
    str w6, [x5, #12]
    ldr x6, [x10, #0x18]
    str x6, [x10, #0x20]
    ldr x0, [x9, #0x9b8]
    mov w1, #0x83
    mov w2, #0
    mov w3, #1      /* terminal; raw count kept without assuming residual semantics */
    mov w5, #1      /* take DsUrbRing lock */
    b complete_original
#endif
event_error:
    orr w6, w6, #0x80000000
    str w6, [x5, #12]
event_done:
    ret

/* 2C930 epilogue, x19 DsUrbRing, x20 UsbDsReportData. Private diagnostics
 * occupy the seven unused report slots; retain the sole real URB report. */
iso_report:
    ldrb w8, [x19, #0x70]
    cmp w8, #0x83
    b.ne report_done
    ldr w8, [x20, #128]
    cmp w8, #1
    b.hi report_done
    ldr x8, [x19, #0x60]
#if VARIANT == 2 && FRAME_LEAD == 0
    add x11, x8, #0x22, lsl #12
    ldr x8, [x11, #(ISO_ENTRY + 0x10)]
#else
    add x8, x8, #0x22, lsl #12
    ldr x8, [x8, #(ISO_ENTRY + 0x10)]
#endif
    cbz x8, report_done
    ldr w10, [x8, #0xf80]
#if VARIANT == 2 && FRAME_LEAD == 0
    cmp w10, #0xd1
    b.eq sample_frame
#endif
    cbnz w10, report_ready
    mov w10, #0xd1 /* report patch reached, no producer breadcrumb yet */
    str w10, [x8, #0xf80]
#if VARIANT == 2 && FRAME_LEAD == 0
sample_frame:
    ldr x11, [x11, #8] /* device register MMIO, same base as doorbell */
    ldr w10, [x11, #0x48] /* Tegra device MFINDEX candidate; reads only */
    str w10, [x8, #0xf90]
    ldr w10, [x11]
    str w10, [x8, #0xf94]
    ldr w10, [x11, #0x3c]
    str w10, [x8, #0xf98]
    str x11, [x8, #0xfa0]
#endif
report_ready:
    add x8, x8, #0xf80
    add x9, x20, #16
    mov w10, #7
report_copy:
    ldr q0, [x8], #16
    str q0, [x9], #16
    subs w10, w10, #1
    b.ne report_copy
report_done:
    add x0, x19, #0x10
    b report_epilogue
iso_end:
