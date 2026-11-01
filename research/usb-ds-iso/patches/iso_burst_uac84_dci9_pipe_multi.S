/* U2 v28 multi-segment cave: the v26B cursor cave for one larger transfer.
 *
 * v27 showed the usb:ds AS endpoint is single-transfer: a second post while
 * one request is in flight never reaches the cave and completes with status
 * 5.  v28 therefore keeps one post and makes the request itself larger: two
 * 3072 B segments (32 x 192 B, 32 ms) in one buffer.  The cave builds one
 * Isoch+ED TD pair per 192 B frame of the request:
 *
 *   packets = request_bytes / 192        (32 for the 6144 B candidate)
 *
 * so the TD count follows the request length; the remaining distance is
 * carried by the DMA cursor (x16 = buffer + request_bytes), not a counter.
 * The completion gate is the 32-bit ED bitmap: all 32 distinct slots must
 * have completed (one transfer, so no chunk bookkeeping is needed).
 *
 * The frame cursor is unchanged:
 *   frame = max(MFI/8 + 32, cursor)      (cursor only if it is ahead)
 *   after the request's frames: cursor = frame + packets
 *
 * An empty ring means the driver (or the installer) memset the ring, which
 * clears the cursor, so the MFI baseline is used again.
 *
 * The driver resets the ring only after a controller service error, and that
 * happens when the ring runs dry.  With two buffers in flight the ring still
 * holds the next TD set when the previous one completes, so the error reset
 * does not fire and no re-arm is needed.  This cave therefore:
 *
 *   prod == cons  -> replay 0x2feb0 (context commit + halt clear + ring
 *                    reset), fix the link, write the TD set at the base;
 *   prod != cons  -> write the next TD set at prod, keep the ring/context,
 *                    no memset, no link rewrite (the empty path already put
 *                    the link at ring+0xf70 and the cycle stays 1).
 *
 * v23 re-arm candidate: the DCI-9 no-report cave plus one driver call.
 *
 * Why: the installer (0x295d0) is only a descriptor walker -- the controller
 * is armed by the endpoint setup path 0x2fd30 -> 0x2fd80 + 0x2feb0, which
 * installs the 64-byte endpoint context and writes regs+0x58 (commit) and
 * clears the halt bits at regs+0x54/0x50.  The completion error path
 * (0x30ff4) rewrites the same ring/context after a burst but never commits
 * and never clears the halt, so the controller keeps its stale state and the
 * next TD set at the ring base is never fetched.  Re-running the driver's own
 * setup before each burst restores the state that made burst 1 work.
 *
 * Only the empty-ring path is re-armed (the existing prod == cons gate), and
 * the driver's ABI is preserved: x0/x1/x2 and LR are saved across the call,
 * x8 (write cursor) and x6 (controller area) are reloaded afterwards.
 *
 * U2: A15 producer ported to the UAC AS alt1 endpoint.
 * HS-only, one URB containing the request's 1ms Isoch+ED TD pairs (32 for
 * the 6144 B candidate).
 * Mailbox ISO2: +16 completed bitmap, +20 actual sum, +24 first virtual TRB.
 * Each ED must report exactly 192 bytes; completion releases DMA only after
 * all 32 distinct EDs. Never chains one Isoch TRB into another Isoch TD.
 *
 * Endpoint word 0x00C00584: address 0x84, bmAttributes 0x05 (ISOCHRONOUS |
 * async sync type, see UacBuildAsConfiguration), wMaxPacketSize 192.  The
 * A23 vendor endpoint used 0x01000183 (attributes 0x01), so this port is not
 * a pure address/MPS substitution.
 */
.section .text.iso,"ax",%progbits
.global iso_enter, iso_event, iso_end
.equ ISO_ENTRY, 0x270
iso_enter:
    cbz x2, fail_accept
    mov w9, #0x1800 /* the 2 x 3072 B candidate */
    cmp w3, w9
    b.ne fail_accept
    ldr w9, [x1, #2]
    mov w10, #0x584 /* endpoint 0x84, ISO+async, MPS192 */
    movk w10, #0x00c0, lsl #16
    cmp w9, w10
    b.ne fail_accept
    ldrb w9, [x1, #6]
    cmp w9, #4
    b.ne fail_accept
    add x6, x0, #0x22, lsl #12
    ldr w9, [x6, #0xa58]
    cmp w9, #3 /* HS only; SS remains unverified */
    b.ne fail_accept
    ldp x8, x9, [x1, #0x18]
    cmp x8, x9
    b.ne pipe_nonempty
    /* Empty ring: the driver has reset (or this is the first burst).  Replay
       the driver endpoint setup so the context commit and the halt clear
       happen before this TD set.  Enters with x0 = controller and
       x1 = endpoint object, exactly the arguments 0x2feb0 expects. */
    stp x0, x1, [sp, #-16]!
    stp x2, x30, [sp, #-16]!
    bl rearm_endpoint
    ldp x2, x30, [sp], #16
    ldp x0, x1, [sp], #16
    add x6, x0, #0x22, lsl #12
    ldp x8, x9, [x1, #0x18] /* the re-arm reset prod/cons to the ring base */
    ldr x10, [x1, #0x10]
    add x13, x10, #0xf70
    ldr x9, [x1, #0x28]
    cmp x9, x13
    b.eq installed
    ldr q0, [x9]
    str q0, [x13]
    str x13, [x1, #0x28]
    b installed
pipe_nonempty:
    /* Ring already holds an in-flight TD set: write the next set at prod.
       x6 = controller area, x10 = ring base, x13 = link slot; x8 is prod
       from the gate load. */
    add x6, x0, #0x22, lsl #12
    ldr x10, [x1, #0x10]
    add x13, x10, #0xf70
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
    /* v26B: prefer the cursor when it is ahead of the MFI baseline. */
    ldrh w10, [x5, #0x38]
    cbz w10, 1f
    sub w12, w10, w9
    and w12, w12, #0x7ff
    cmp w12, #0x400
    b.hs 1f
    mov w9, w10
1:
    lsl w11, w9, #20
    mov w10, #0x1410
    orr w11, w11, w10
    ldrb w12, [x1, #0x40]
    add x16, x2, w3, uxtw /* DMA end; TD count follows the request length */
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
    cmp x2, x16
    b.ne packet
    /* v26B: the cursor is the first frame after this TD set. */
    lsr w10, w11, #20
    strh w10, [x5, #0x38]
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
fail_accept:
    ldp x29, x30, [sp], #16
    mov w0, #0
    ret
iso_event:
    ldr w8, [x1, #12]
    ubfx w9, w8, #16, #5
    cmp w9, #9 /* UAC EP0x84 DCI; A23 EP0x83 used 7 */
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
    cmp x6, #1024
    b.hs done
    and w7, w8, #4
    eor w4, w6, w7, lsl #2
    tst w4, #31
    b.ne done /* ED only on odd slots, Isoch only on even slots */
    ldr w4, [x1, #8]
    lsr w7, w4, #24
    cmp w7, #1
    b.ne done
    tbz w8, #2, done
    and w4, w4, #0xffffff
    cmp w4, #192
    b.ne done
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
    cmn w6, #1 /* all 32 distinct ED slots completed (6144 B request) */
    b.ne done
    mov w7, #1
    str w7, [x5, #12]
    ldr x6, [x10, #0x18]
    str x6, [x10, #0x20]
    ldr x0, [x9, #0x9b8]
    mov w1, #0x84
    mov w2, #0
    mov w3, #1
    mov w5, #1
    b complete_original
done:
    ret
iso_end:
