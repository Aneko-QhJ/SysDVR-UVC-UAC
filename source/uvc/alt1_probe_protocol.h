#pragma once
#include <stdint.h>

// Vendor alt1 installation probe. The sysmodule exposes one vendor interface
// with alt0 (no endpoint) and alt1 (bulk IN 0x84); the host sets alt1 and
// triggers one 64-byte transfer. No UAC, no ISO, no IPS patch.

#define ALT1_PROBE_TRIGGER 0x50
#define ALT1_PROBE_STATUS 0x51
#define ALT1_PROBE_CANCEL 0x52

#define ALT1_PROBE_STATUS_MAGIC 0x31544C41u  // "ALT1"
#define ALT1_PROBE_BUFFER_SIZE 64

enum {
    ALT1_PROBE_IDLE = 0,
    ALT1_PROBE_PENDING = 1,
    ALT1_PROBE_COMPLETE = 2,
    ALT1_PROBE_FAILED = 3,
};

typedef struct __attribute__((packed)) {
    uint32_t magic;
    uint32_t version;
    uint32_t alt;
    uint32_t state;
    uint32_t post_result;
    uint32_t urb_id;
    uint32_t completed;
    uint32_t transferred;
    uint32_t urb_status;
    uint32_t triggers;
    uint32_t reports;
} Alt1ProbeStatus;
