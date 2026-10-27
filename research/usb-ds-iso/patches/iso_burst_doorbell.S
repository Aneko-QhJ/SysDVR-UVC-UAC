/* A20 ISO5 original doorbell-tail bracket. Header/events match ISO4.
 * +72 selection MFI, +76 after publication/before ORIGINAL tail,
 * +80 after ORIGINAL tail returns, +84 returned doorbell operand.
 * Marker0x700 proves this software path reached the original EP7 store;
 * zero/other values are incomplete/rejected and must be ignored.
 * Original tail and MMIO write are untouched; caller LR stays on stack.
 * +88..111 reserved/stale. Reads bracket software, not hardware service.
 */
.section .text.iso,"ax",%progbits
.global iso_enter, iso_event, iso_report, iso_end
.equ ISO_ENTRY, 0x270
iso_enter:
    cbz x2, reject_original
    cmp w3, #3072
    ldr w9, [x1, #2]
    mov w10, #0x183
    movk w10, #0x100, lsl #16
    ccmp w9, w10, #0, eq
    ldrb w9, [x1, #6]
    ccmp w9, #4, #0, eq
    add x6, x0, #0x22, lsl #12
    ldr w9, [x6, #0xa58]
    ccmp w9, #3, #0, eq
    ldp x8, x9, [x1, #0x18]
    ccmp x8, x9, #0, eq
    b.ne reject_original
    ldr x10, [x1, #0x10]
    add x13, x10, #0xf70
    ldr x9, [x1, #0x28]
    ldr q0, [x9]
    str q0, [x13]
    str x13, [x1, #0x28]
    add x5, x10, #0xf80
    mov w9, #0x5349
    movk w9, #0x354f, lsl #16 /* ISO5 */
    stp x9, xzr, [x5] /* magic, error offset0, control0, terminal0 */
    stp xzr, x8, [x5, #16] /* bitmap0, actual0, first TRB */
    /* Only TD0/TD1 event controls and phase_valid are reset. Invalid
     * records and reserved bytes may be stale; never interpret them. */
    str wzr, [x5, #44]
    str wzr, [x5, #64]
    str wzr, [x5, #84] /* doorbell_marker=0; stale anchors must be ignored */
    ldr x14, [x6, #8]
frame_select_read:
    ldr w9, [x14, #0x48]
    str w9, [x5, #72]
    lsr w9, w9, #3
    add w9, w9, #32
    mov w11, #0x1410
    bfi w11, w9, #20, #11
    ldrb w12, [x1, #0x40]
    mov x4, x8
packet:
    orr w9, w11, w12
    cmp x8, x4
    b.ne ready_cycle
    eor w9, w9, #1
ready_cycle:
    str x2, [x8]
    mov w10, #192
    stp w10, w9, [x8, #8]
    mov w15, #0x1812
    bl advance
    mov x9, #0x1c2000000000
    orr x9, x9, x12, lsl #32
    stp x8, x9, [x8]
    mov w15, #0x1802
    bl advance
    add x2, x2, #192
    add w11, w11, #256, lsl #12
    bic w11, w11, #0x80000000
    subs w3, w3, #192
    b.ne packet
    str x8, [x1, #0x18]
    strb w12, [x1, #0x40]
    dsb sy
    ldr w9, [x4, #12]
    eor w9, w9, #1
    str w9, [x4, #12]
    str w9, [x5, #8]
    dsb sy
before_doorbell_read:
    ldr w9, [x14, #0x48]
    str w9, [x5, #76]
    bl doorbell_tail /* original return stays in w0; x5/x14 preserved */
 after_doorbell_read:
    ldr w9, [x14, #0x48]
    str w9, [x5, #80]
    str w8, [x5, #84] /*0x700 after EP7 store; <=0xff if rejected */
    ldp x29, x30, [sp], #16
    ret
advance:
    add x8, x8, #16
    cmp x8, x13
    b.ne advance_done
    orr w9, w15, w12
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
    ldr x4, [x10, #0x10]
    cbz x4, event_original
    add x5, x4, #0xf80
    ldr x3, [x9, #8]
    ldr w3, [x3, #0x48]
    ldr w6, [x5, #12]
    cbnz w6, done
    ldr x6, [x1]
    ldr x7, [x10, #0x38]
    tbz w8, #2, base_ready
    mov x7, x4
base_ready:
    sub x6, x6, x7
    cmp x6, #0xf70
    b.hs done
    ldr x7, [x5, #24]
    sub x7, x7, x4
    sub x6, x6, x7
    tbz x6, #63, unwrapped_tag
    add x6, x6, #0xf70
unwrapped_tag:
    cmp x6, #512
    b.hs done
    and w7, w8, #4
    eor w4, w6, w7, lsl #2
    tst w4, #31
    b.ne done
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
    ldp w2, w4, [x5, #16]
    tst w2, w7
    b.ne done
    orr w2, w2, w7
    add w4, w4, #192
    stp w2, w4, [x5, #16]
    cmp w6, #2
    b.hs no_td_snapshot
    mov w7, #20
    madd x7, x6, x7, x5
    ldr q0, [x1]
    str q0, [x7, #32]
    str w3, [x7, #48]
no_td_snapshot:
    cmp w4, #3072
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
    str w6, [x5, #4]
    orr w7, w7, #0x80000000
    str w7, [x5, #12]
    add x4, x5, #52
capture:
    ldr q0, [x1]
    str q0, [x4]
    str w3, [x4, #16]
done:
    ret
iso_report:
    ldrb w8, [x19, #0x70]
    cmp w8, #0x83
    b.ne report_done
    ldr w8, [x20, #128]
    cmp w8, #1
    b.hi report_done
    ldr x8, [x19, #0x60]
    add x8, x8, #0x22, lsl #12
    ldr x8, [x8, #(ISO_ENTRY + 0x10)]
    cbz x8, report_done
    add x1, x8, #0xf80
    add x0, x20, #16
    mov w2, #112
    bl copy_original /* validated original memmove; caller saved LR */
report_done:
    add x0, x19, #0x10
    b report_epilogue
iso_end:
