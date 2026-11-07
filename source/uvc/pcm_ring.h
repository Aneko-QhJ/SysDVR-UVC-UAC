#pragma once
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Single-producer / single-consumer byte ring for the UAC PCM path.
 *
 * Producer: the grc:d audio thread (CaptureReadAudioFrame, 4096 B chunks).
 * Consumer: the UAC burst poster (3072 B = 16 ms sets).
 *
 * Byte counters are monotonic and never wrap in practice (64-bit), so the
 * used/free arithmetic needs no sentinel slot.  Capacity must be a power of
 * two.  Both sides move whole 4-byte stereo frames.
 *
 * Overflow policy: drop the oldest bytes to make room (the capture thread
 * must never block on USB) and count them.  Underrun policy: zero-fill the
 * short tail (silence) and count it; never replay old samples.
 */
typedef struct {
    uint8_t *buf;
    uint32_t mask;   /* capacity - 1, capacity is a power of two */
    uint64_t head;   /* bytes written, monotonic */
    uint64_t tail;   /* bytes read, monotonic */
    uint64_t underrun_bytes;
    uint64_t overrun_bytes;
} PcmRing;

void PcmRingInit(PcmRing *ring, uint8_t *buf, uint32_t capacity);

/* Returns bytes stored; oldest bytes are dropped if the ring is full. */
uint32_t PcmRingWrite(PcmRing *ring, const void *src, uint32_t n);

/* Returns bytes taken from the ring; the rest of dst is zero-filled. */
uint32_t PcmRingReadFill(PcmRing *ring, void *dst, uint32_t n);

/* Bytes currently buffered. */
uint32_t PcmRingUsed(const PcmRing *ring);

/* Drop everything buffered (alt0 -> fresh stream on the next alt1). */
void PcmRingReset(PcmRing *ring);

#ifdef __cplusplus
}
#endif
