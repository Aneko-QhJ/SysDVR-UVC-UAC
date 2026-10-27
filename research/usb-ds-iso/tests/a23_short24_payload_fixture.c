/* Uses the generated device header, independently consumed by Python. */
#include <stdio.h>
#include <stdlib.h>
#include "iso_probe_protocol.h"
_Static_assert(ISO_PROBE_PACKET_SIZE == 24, "short packet size");
_Static_assert(ISO_PROBE_BURST_PACKETS == 16, "fixed TD count");
_Static_assert(ISO_PROBE_BURST_INTERVAL_MAGIC == 0x34325349u, "separate diagnostic identity");
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    unsigned first = (unsigned)strtoul(argv[1], NULL, 0);
    if (!first || first > 65520) return 2;
    for (unsigned p = 0; p < ISO_PROBE_BURST_PACKETS; ++p)
        for (unsigned i = 0; i < ISO_PROBE_PACKET_SIZE; ++i)
            if (putchar(isoProbeByte((uint16_t)(first+p), i)) == EOF) return 1;
    return fflush(stdout) == 0 ? 0 : 1;
}
