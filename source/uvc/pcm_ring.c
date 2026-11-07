#include <string.h>
#include "pcm_ring.h"

void PcmRingInit(PcmRing *ring, uint8_t *buf, uint32_t capacity)
{
    ring->buf = buf;
    ring->mask = capacity - 1;
    ring->head = 0;
    ring->tail = 0;
    ring->underrun_bytes = 0;
    ring->overrun_bytes = 0;
}

uint32_t PcmRingUsed(const PcmRing *ring)
{
    const uint64_t head = __atomic_load_n(&ring->head, __ATOMIC_ACQUIRE);
    const uint64_t tail = __atomic_load_n(&ring->tail, __ATOMIC_ACQUIRE);
    return (uint32_t)(head - tail);
}

void PcmRingReset(PcmRing *ring)
{
    const uint64_t head = __atomic_load_n(&ring->head, __ATOMIC_ACQUIRE);
    __atomic_store_n(&ring->tail, head, __ATOMIC_RELEASE);
}

uint32_t PcmRingWrite(PcmRing *ring, const void *src, uint32_t n)
{
    const uint64_t head = __atomic_load_n(&ring->head, __ATOMIC_RELAXED);
    uint64_t tail = __atomic_load_n(&ring->tail, __ATOMIC_ACQUIRE);
    const uint32_t capacity = ring->mask + 1;
    uint32_t used = (uint32_t)(head - tail);

    if (n > capacity) {
        /* a single write larger than the ring keeps only the newest part */
        const uint32_t skip = (n - capacity + 3u) & ~3u;
        ring->overrun_bytes += skip;
        src = (const uint8_t *)src + skip;
        n -= skip;
    }
    if (n > capacity - used) {
        uint32_t drop = n - (capacity - used);
        drop = (drop + 3u) & ~3u;
        if (drop > used) drop = used;
        tail += drop;
        __atomic_store_n(&ring->tail, tail, __ATOMIC_RELEASE);
        ring->overrun_bytes += drop;
        used -= drop;
    }

    const uint8_t *p = (const uint8_t *)src;
    for (uint32_t i = 0; i < n; ++i) {
        ring->buf[(uint32_t)((head + i) & ring->mask)] = p[i];
    }
    __atomic_store_n(&ring->head, head + n, __ATOMIC_RELEASE);
    return n;
}

uint32_t PcmRingReadFill(PcmRing *ring, void *dst, uint32_t n)
{
    const uint64_t tail = __atomic_load_n(&ring->tail, __ATOMIC_RELAXED);
    const uint64_t head = __atomic_load_n(&ring->head, __ATOMIC_ACQUIRE);
    uint32_t avail = (uint32_t)(head - tail);
    uint32_t take = n < avail ? n : avail;
    uint8_t *d = (uint8_t *)dst;

    for (uint32_t i = 0; i < take; ++i) {
        d[i] = ring->buf[(uint32_t)((tail + i) & ring->mask)];
    }
    if (take < n) {
        memset(d + take, 0, n - take);
        ring->underrun_bytes += n - take;
    }
    __atomic_store_n(&ring->tail, tail + take, __ATOMIC_RELEASE);
    return take;
}
