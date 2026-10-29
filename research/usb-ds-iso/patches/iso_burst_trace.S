/* A15: HS-only, one URB containing 16 independent 1ms Isoch+ED TDs.
 * Mailbox ISO2: +16 completed bitmap, +20 actual sum, +24 first virtual TRB.
 * Each ED must report exactly 192 bytes; completion releases DMA only after
 * all 16 distinct EDs. Never chains one Isoch TRB into another Isoch TD.
 */
.section .text.iso,"ax",%progbits
.global iso_enter, iso_event, iso_report, iso_end
.equ ISO_ENTRY, 0x270
iso_enter:
    cbz x2, reject_original
    cmp w3, #3072
    b.ne reject_original
    ldr w9, [x1, #2]
    mov w10, #0x183 /* endpoint83, ISO, MPS256 (low byte0) */
    movk w10, #0x100, lsl #16
    cmp w9, w10
    b.ne reject_original
    ldrb w9, [x1, #6]
    cmp w9, #4
    b.ne reject_original
    add x6, x0, #0x22, lsl #12
    ldr w9, [x6, #0xa58]
    cmp w9, #3 /* HS only; SS remains unverified */
    b.ne reject_original
    ldp x8, x9, [x1, #0x18]
    cmp x8, x9
    b.ne reject_original
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
    movk w9, #0x324f, lsl #16 /* ISO2 */
    stp w9, wzr, [x5]
    stp xzr, xzr, [x5, #8]
    str x8, [x5, #24]
    ldr x9, [x6, #8]
    ldr w9, [x9, #0x48]
    lsr w9, w9, #3
    add w9, w9, #32
    and w9, w9, #0x7ff
    lsl w11, w9, #20
    mov w10, #0x1410
    orr w11, w11, w10
    ldrb w12, [x1, #0x40]
    mov w14, #16
    mov x4, x8 /* first TRB gate; DMA remains in x2 */
packet:
    orr w9, w11, w12
    cmp x8, x4
    b.ne ready_cycle
    eor w9, w9, #1
ready_cycle:
    str x2, [x8]
    mov w10, #192
    stp w10, w9, [x8, #8]
    mov w15, #0x10
    bl advance
    mov x9, #0x1c2000000000
    orr x9, x9, x12, lsl #32
    stp x8, x9, [x8] /* self-tag, length0, ED IOC/cycle */
    mov w15, #0
    bl advance
    add x2, x2, #192
    add w11, w11, #256, lsl #12
    bic w11, w11, #0x80000000 /* FrameID wraps at 2048; SIA remains0 */
    subs w14, w14, #1
    b.ne packet
    str x8, [x1, #0x18]
    strb w12, [x1, #0x40]
    dsb sy
    ldr w9, [x4, #12]
    eor w9, w9, #1
    str w9, [x4, #12]
    str w9, [x5, #60] /* A15 retains first control: FrameID/type/cycle */
    dsb sy
    ldp x29, x30, [sp], #16
    b doorbell_tail
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
    ldr w6, [x5, #12]
    cbnz w6, done
    ldr x6, [x1]
    tbnz w8, #2, virtual_tag
    ldr x7, [x10, #0x38]
    sub x6, x6, x7
    ldr x7, [x10, #0x10]
    add x6, x6, x7
virtual_tag:
    ldr x7, [x10, #0x10]
    sub x7, x6, x7
    cmp x7, #0xf70
    b.hs done /* ignore null underrun and foreign pointers */
    ldr x7, [x5, #24]
    sub x6, x6, x7
    tbz x6, #63, unwrapped_tag
    add x6, x6, #0xf70
unwrapped_tag:
    cmp x6, #512
    b.hs done
    and w7, w8, #4
    eor w4, w6, w7, lsl #2
    tst w4, #31
    b.ne done /* ED only on odd slots, Isoch only on even slots */
    ldr w4, [x1, #8]
    lsr w7, w4, #24
    cmp w7, #1
    b.ne error
    tbz w8, #2, done
    and w4, w4, #0xffffff
    cmp w4, #192
    b.ne error
    lsr w6, w6, #5
    mov w7, #1
    lsl w7, w7, w6
    ldr w6, [x5, #16]
    tst w6, w7
    b.ne done
    orr w6, w6, w7
    str w6, [x5, #16]
    ldr w4, [x5, #20]
    add w4, w4, #192
    str w4, [x5, #20]
    cmp w4, #3072 /* exactly16 distinct successful EDs, each192 bytes */
    b.ne done
    mov w7, #1
    str w7, [x5, #12]
    ldr x6, [x10, #0x18]
    str x6, [x10, #0x20]
    ldr x0, [x9, #0x9b8]
    mov w1, #0x83
    mov w2, #0
    mov w3, #1
    mov w5, #1
    b complete_original
error:
    str w6, [x5, #4] /* matched byte offset from first TRB; identifies TD */
    orr w7, w7, #0x80000000
    ldr x6, [x9, #8]
    ldr w6, [x6, #0x48]
    stp w6, w7, [x5, #8] /* word2=current MFI on error, not event count */
    ldr q0, [x1]
    str q0, [x5, #64] /* first matched error event, not ED snapshot */
done:
    ret
iso_report:
    ldrb w8, [x19, #0x70]
    cmp w8, #0x83
    b.ne report_done
    mov w9, #0x5349
    movk w9, #0x314f, lsl #16
    str w9, [x20, #16]
    str x19, [x20, #24]
    ldr w9, [x19, #0]
    str w9, [x20, #32]
    ldr w9, [x19, #4]
    str w9, [x20, #36]
    ldr w9, [x19, #8]
    str w9, [x20, #40]
report_done:
    add x0, x19, #0x10
    b report_epilogue
iso_end:
