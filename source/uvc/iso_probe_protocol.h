#pragma once
#include <stddef.h>
#include <stdint.h>

/* Experimental interface protocol v1, little endian; shared with host tool. */
#define ISO_PROBE_TRIGGER 0x50
#define ISO_PROBE_STATUS  0x51
#define ISO_PROBE_CANCEL  0x52
#define ISO_PROBE_FRAMES  0x53
#define ISO_PROBE_BURST   0x54
#define ISO_PROBE_STREAM_START 0x55
#define ISO_PROBE_BURST_PACKETS 16
#define ISO_PROBE_BURST_DIAG_MAGIC 0x324f5349u
#define ISO_PROBE_BURST_AUDIT_MAGIC 0x334f5349u
#define ISO_PROBE_BURST_PUBLICATION_MAGIC 0x344f5349u
#define ISO_PROBE_BURST_DOORBELL_MAGIC 0x354f5349u
#define ISO_PROBE_BURST_CONTEXT_MAGIC 0x364f5349u
#define ISO_PROBE_BURST_INTERVAL_MAGIC 0x374f5349u
#define ISO_PROBE_FRAMES_MAGIC 0x314d5246u
#define ISO_PROBE_FRAME_SAMPLES 8
#define ISO_PROBE_PACKET_SIZE 192
#define ISO_PROBE_DIAG_MAGIC 0x314f5349u
#define ISO_PROBE_REPORT_MARKER 0xd1u
#define ISO_PROBE_ENTER_MARKER 0xd2u
#define ISO_PROBE_STATUS_MAGIC 0x31505349u
#define ISO_PROBE_SUCCESS_RETAINED 0x40000001u
enum { ISO_PROBE_IDLE, ISO_PROBE_PENDING, ISO_PROBE_COMPLETE,
       ISO_PROBE_FAILED, ISO_PROBE_RETAINED };

typedef struct __attribute__((packed)) {
    uint32_t magic, variant, event_count, terminal;
    uint32_t context[4];
    uint64_t iso_physical, ed_tag;
    uint32_t iso_trb[4], ed_trb[4], events[2][4];
} IsoProbeDiagnostics;

/* ISO3 keeps the report/STATUS sizes and terminal/bitmap/actual offsets.
 * A record is valid only when event[3] != 0. Invalid records can contain
 * stale bytes. td[1] is replaced by the first matched error on retention.
 * Filtered and post-terminal records never affect DMA ownership. */
typedef struct __attribute__((packed)) {
    uint32_t event[4], mfi;
} IsoProbeAuditEvent;
typedef struct __attribute__((packed)) {
    uint32_t magic, error_offset, first_control, terminal;
    uint32_t completed_bitmap, actual_sum;
    uint64_t first_virtual_trb;
    IsoProbeAuditEvent td[2], filtered, post_terminal;
} IsoProbeBurstAuditDiagnostics;

/* ISO4 shares header/TD records with ISO3. The three software MFI anchors
 * are usable only when phase_valid == 1 and frame_select matches control.
 * They do not timestamp the MMIO doorbell write. Copies remain non-atomic;
 * reserved bytes may be stale and must never be interpreted. */
typedef struct __attribute__((packed)) {
    uint32_t magic, error_offset, first_control, terminal;
    uint32_t completed_bitmap, actual_sum;
    uint64_t first_virtual_trb;
    IsoProbeAuditEvent td[2];
    uint32_t frame_select_mfi, before_publish_mfi, before_doorbell_mfi, phase_valid;
    uint32_t reserved[6];
} IsoProbeBurstPublicationDiagnostics;

/* ISO5 moves two anchors around the unmodified original doorbell tail.
 * Operand0x700 is stored only after the EP7 tail returns; early rejection
 * stores an unshifted endpoint index, which is invalid. No bus timestamp. */
typedef struct __attribute__((packed)) {
    uint32_t magic, error_offset, first_control, terminal;
    uint32_t completed_bitmap, actual_sum;
    uint64_t first_virtual_trb;
    IsoProbeAuditEvent td[2];
    uint32_t frame_select_mfi, before_tail_mfi, after_tail_mfi, doorbell_marker;
    uint32_t reserved[6];
} IsoProbeBurstDoorbellDiagnostics;

/* ISO6 captures the first32 bytes of the original EP7 context allocation
 * before the first TRB cycle is published. valid1 plus selection/control
 * consistency is required; the hardware may update these DMA words while
 * read. This is neither an atomic context snapshot nor a bus timestamp. */
typedef struct __attribute__((packed)) {
    uint32_t magic, error_offset, first_control, terminal;
    uint32_t completed_bitmap, actual_sum;
    uint64_t first_virtual_trb;
    IsoProbeAuditEvent td[2];
    uint32_t frame_select_mfi, context_valid;
    uint32_t context[8];
} IsoProbeBurstContextDiagnostics;

/* ISO7 uses the same ISO6 snapshot layout but expects bInterval1/125us.
 * TD0 remains explicit lead32; subsequent TDs use SIA. ABI sizes unchanged. */

static inline int isoProbeIsBurstDiagnostics(uint32_t magic)
{
    return magic == ISO_PROBE_BURST_DIAG_MAGIC || magic == ISO_PROBE_BURST_AUDIT_MAGIC ||
           magic == ISO_PROBE_BURST_PUBLICATION_MAGIC ||
           magic == ISO_PROBE_BURST_DOORBELL_MAGIC ||
           magic == ISO_PROBE_BURST_CONTEXT_MAGIC ||
           magic == ISO_PROBE_BURST_INTERVAL_MAGIC;
}

typedef struct __attribute__((packed)) {
    uint32_t magic, version, sequence, state;
    uint32_t post_result, urb_id, report_id, requested, transferred, urb_status;
    uint32_t speed, endpoint, report_count, report_result;
    IsoProbeDiagnostics diagnostics;
} IsoProbeStatus;

typedef struct __attribute__((packed)) {
    uint64_t ticks_before, ticks_after;
    uint32_t raw_mfi, control, portsc, result;
    uint64_t mmio;
} IsoProbeFrameSample;
typedef struct __attribute__((packed)) {
    uint32_t magic, version, count, tick_frequency, verified;
    IsoProbeFrameSample samples[ISO_PROBE_FRAME_SAMPLES];
} IsoProbeFrameReport;
_Static_assert(sizeof(IsoProbeFrameReport) == 340, "frame report ABI");

_Static_assert(sizeof(IsoProbeDiagnostics) == 112, "diagnostic ABI");
_Static_assert(sizeof(IsoProbeBurstAuditDiagnostics) == 112, "bounded audit ABI");
_Static_assert(sizeof(IsoProbeBurstPublicationDiagnostics) == 112, "publication audit ABI");
_Static_assert(sizeof(IsoProbeBurstDoorbellDiagnostics) == 112, "doorbell audit ABI");
_Static_assert(offsetof(IsoProbeBurstDoorbellDiagnostics, doorbell_marker) == 84, "doorbell sentinel ABI");
_Static_assert(offsetof(IsoProbeBurstPublicationDiagnostics, td) == offsetof(IsoProbeBurstAuditDiagnostics, td), "event record ABI");
_Static_assert(offsetof(IsoProbeBurstPublicationDiagnostics, phase_valid) == 84, "phase sentinel ABI");
_Static_assert(offsetof(IsoProbeBurstAuditDiagnostics, terminal) == offsetof(IsoProbeDiagnostics, terminal), "terminal ABI");
_Static_assert(offsetof(IsoProbeBurstAuditDiagnostics, completed_bitmap) == offsetof(IsoProbeDiagnostics, context), "burst count ABI");
_Static_assert(sizeof(IsoProbeBurstContextDiagnostics) == 112, "context audit ABI");
_Static_assert(offsetof(IsoProbeBurstContextDiagnostics, context_valid) == 76, "context sentinel ABI");
_Static_assert(offsetof(IsoProbeBurstContextDiagnostics, context) == 80, "context words ABI");
_Static_assert(sizeof(IsoProbeStatus) == 168, "status ABI");

static inline uint8_t isoProbeByte(uint16_t sequence, unsigned offset)
{
    if (offset < 4) return (uint8_t)"ISO1"[offset];
    if (offset == 4) return (uint8_t)sequence;
    if (offset == 5) return (uint8_t)(sequence >> 8);
    return (uint8_t)(offset ^ sequence ^ (sequence >> 8));
}
