#pragma once
#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>

typedef struct {
    uint32_t offset, size;
    const uint8_t *before, *after;
} IsoRuntimeEdit;
typedef int (*IsoPatchIo)(void *, uint32_t, void *, size_t);
/* 0 applied, 1 already installed; -1 read error, -2 mismatch/mixed image,
   -3 write/verify failed and rolled back, -4 rollback could not be verified. */
static inline int isoApplyRuntimePatch(const IsoRuntimeEdit *edits, size_t count,
    IsoPatchIo read, IsoPatchIo write, void *ctx, size_t *failed)
{
    uint8_t scratch[1024];
    bool original = true, installed = true;
    for (size_t i = 0; i < count; ++i) {
        *failed = i;
        if (!edits[i].size || edits[i].size > sizeof(scratch)) return -2;
        if (read(ctx, edits[i].offset, scratch, edits[i].size)) return -1;
        original &= !memcmp(scratch, edits[i].before, edits[i].size);
        installed &= !memcmp(scratch, edits[i].after, edits[i].size);
    }
    if (installed) return 1;
    if (!original) return -2;
    size_t attempted = 0;
    for (size_t i = 0; i < count; ++i) {
        *failed = i;
        attempted = i + 1; /* include possible partially written failed range */
        if (write(ctx, edits[i].offset, (void *)edits[i].after, edits[i].size)) goto rollback;
        if (read(ctx, edits[i].offset, scratch, edits[i].size) ||
            memcmp(scratch, edits[i].after, edits[i].size)) goto rollback;
    }
    return 0;
rollback:
    {
        bool restored = true;
        while (attempted) {
            const IsoRuntimeEdit *e = &edits[--attempted];
            if (write(ctx, e->offset, (void *)e->before, e->size)) restored = false;
            if (read(ctx, e->offset, scratch, e->size) ||
                memcmp(scratch, e->before, e->size)) restored = false;
        }
        return restored ? -3 : -4;
    }
}
