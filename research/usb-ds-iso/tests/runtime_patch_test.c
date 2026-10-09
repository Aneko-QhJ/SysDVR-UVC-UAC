#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
#include "../../../source/uvc/iso_runtime_patch.h"
#include "iso_runtime_payload.h"

typedef struct {
    uint8_t memory[0x69000];
    unsigned reads, writes, fail_write_at;
    bool fail_read, corrupt_verify, fail_rollback;
} Fixture;
static int read_memory(void *ctx, uint32_t offset, void *bytes, size_t size)
{
    Fixture *f = ctx; ++f->reads;
    assert(offset + size <= sizeof(f->memory));
    if (f->fail_read) return 1;
    memcpy(bytes, f->memory + offset, size);
    if (f->corrupt_verify && f->writes == 1) {
        ((uint8_t *)bytes)[0] ^= 1;
        f->corrupt_verify = false;
    }
    return 0;
}
static int write_memory(void *ctx, uint32_t offset, void *bytes, size_t size)
{
    Fixture *f = ctx; ++f->writes;
    assert(offset + size <= sizeof(f->memory));
    if (f->fail_rollback && f->writes > f->fail_write_at) return 1;
    if (f->writes == f->fail_write_at) {
        memcpy(f->memory + offset, bytes, size / 2); /* partial failed syscall */
        return 1;
    }
    memcpy(f->memory + offset, bytes, size);
    return 0;
}
static void reset(Fixture *f)
{
    memset(f, 0, sizeof(*f));
    for (size_t i = 0; i < sizeof(isoRuntimeEdits)/sizeof(*isoRuntimeEdits); ++i) {
        const IsoRuntimeEdit *e = &isoRuntimeEdits[i];
        memcpy(f->memory + e->offset, e->before, e->size);
    }
}
static bool matches(Fixture *f, bool after)
{
    for (size_t i = 0; i < sizeof(isoRuntimeEdits)/sizeof(*isoRuntimeEdits); ++i) {
        const IsoRuntimeEdit *e = &isoRuntimeEdits[i];
        if (memcmp(f->memory + e->offset, after ? e->after : e->before, e->size)) return false;
    }
    return true;
}
int main(void)
{
    assert(sizeof(isoRuntimeBuildId) == 32 && isoRuntimeBuildId[0] == 0xad);
    Fixture *f = malloc(sizeof(*f)); assert(f);
    size_t failed = 0, n = sizeof(isoRuntimeEdits)/sizeof(*isoRuntimeEdits);
    #define APPLY() isoApplyRuntimePatch(isoRuntimeEdits, n, read_memory, write_memory, f, &failed)
    reset(f); assert(APPLY() == 0 && matches(f, true));
    unsigned writes = f->writes;
    assert(APPLY() == 1 && f->writes == writes);
    reset(f); f->memory[isoRuntimeEdits[0].offset] ^= 0x55;
    assert(APPLY() == -2 && f->writes == 0);
    reset(f); memcpy(f->memory + isoRuntimeEdits[0].offset, isoRuntimeEdits[0].after, isoRuntimeEdits[0].size);
    assert(APPLY() == -2 && f->writes == 0);
    reset(f); f->fail_read = true;
    assert(APPLY() == -1 && f->writes == 0);
    reset(f); f->fail_write_at = 2;
    assert(APPLY() == -3 && matches(f, false));
    reset(f); f->corrupt_verify = true;
    assert(APPLY() == -3 && matches(f, false));
    reset(f); f->fail_write_at = 2; f->fail_rollback = true;
    assert(APPLY() == -4);
    free(f);
    puts("runtime preflight, idempotence, mixed input, partial write and rollback: PASS");
    return 0;
}
