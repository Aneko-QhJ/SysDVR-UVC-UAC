/* Host-side test for the UAC PCM ring (no Switch, no libnx). */
#include <stdio.h>
#include <string.h>
#include "pcm_ring.h"

static uint8_t buf[1024];
static uint8_t big[4096];
static uint8_t out[4096];

static int failures;
#define CHECK(cond) do { \
    if (!(cond)) { \
        printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); \
        ++failures; \
    } \
} while (0)

int main(void)
{
    PcmRing ring;
    PcmRingInit(&ring, buf, sizeof(buf));

    /* empty ring reads as silence, counted as underrun */
    memset(out, 0xAA, 32);
    CHECK(PcmRingReadFill(&ring, out, 32) == 0);
    CHECK(out[0] == 0 && out[31] == 0);
    CHECK(ring.underrun_bytes == 32);
    CHECK(PcmRingUsed(&ring) == 0);

    /* plain write/read round trip */
    for (int i = 0; i < 512; ++i) big[i] = (uint8_t)i;
    CHECK(PcmRingWrite(&ring, big, 512) == 512);
    CHECK(PcmRingUsed(&ring) == 512);
    CHECK(PcmRingReadFill(&ring, out, 512) == 512);
    CHECK(memcmp(out, big, 512) == 0);
    CHECK(PcmRingUsed(&ring) == 0);

    /* a write larger than the ring keeps the newest capacity bytes */
    for (int i = 0; i < 4096; ++i) big[i] = (uint8_t)(i * 7);
    CHECK(PcmRingWrite(&ring, big, 4096) == 1024);
    CHECK(ring.overrun_bytes == 4096 - 1024);
    CHECK(PcmRingUsed(&ring) == 1024);
    CHECK(PcmRingReadFill(&ring, out, 1024) == 1024);
    CHECK(memcmp(out, big + 3072, 1024) == 0);

    /* partial fill: old data goes out, the tail is silence */
    CHECK(PcmRingWrite(&ring, big, 400) == 400);
    memset(out, 0x55, 600);
    CHECK(PcmRingReadFill(&ring, out, 600) == 400);
    CHECK(memcmp(out, big, 400) == 0);
    CHECK(out[400] == 0 && out[599] == 0);
    CHECK(ring.underrun_bytes == 32 + 200);

    /* wrap a realistic 8 KiB ring with 4096-in / 4096-out rounds */
    static uint8_t ringbuf[8192];
    uint8_t chunk[4096];
    PcmRingInit(&ring, ringbuf, sizeof(ringbuf));
    uint32_t byte = 0;
    for (int round = 0; round < 40; ++round) {
        for (int i = 0; i < 4096; ++i) chunk[i] = (uint8_t)(byte + (uint32_t)i);
        CHECK(PcmRingWrite(&ring, chunk, sizeof(chunk)) == sizeof(chunk));
        CHECK(PcmRingReadFill(&ring, out, 4096) == 4096);
        CHECK(memcmp(out, chunk, 4096) == 0);
        byte += 4096;
    }
    CHECK(ring.overrun_bytes == 0);
    CHECK(ring.underrun_bytes == 0);

    /* reset drops the backlog */
    CHECK(PcmRingWrite(&ring, chunk, 1024) == 1024);
    PcmRingReset(&ring);
    CHECK(PcmRingUsed(&ring) == 0);
    CHECK(PcmRingReadFill(&ring, out, 16) == 0);

    if (failures == 0) {
        printf("pcm_ring: ok\n");
        return 0;
    }
    return 1;
}
