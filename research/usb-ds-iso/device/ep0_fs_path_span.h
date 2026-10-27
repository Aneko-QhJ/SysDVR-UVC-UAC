#ifndef EP0_FS_PATH_SPAN_H
#define EP0_FS_PATH_SPAN_H
/* Offline prototype only. No filesystem calls, deployment or concurrency policy.
 * The caller supplies true accessible capacities and owns destination exclusively
 * until its synchronous SDK call returns. This does not validate a filesystem path.
 */
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#define EP0_FS_PATH_SPAN 0x301u
#ifdef FS_MAX_PATH
_Static_assert(EP0_FS_PATH_SPAN == FS_MAX_PATH, "SDK path span changed");
#endif
static inline bool ep0_fs_path_prepare(char *destination, size_t capacity,
        const char *source, size_t source_capacity) {
    if (!destination || !source || capacity < EP0_FS_PATH_SPAN) return false;
    size_t limit = source_capacity < EP0_FS_PATH_SPAN ? source_capacity : EP0_FS_PATH_SPAN;
    size_t length = 0;
    while (length < limit && source[length]) ++length;
    if (length == limit) return false;
    /* memmove also permits a caller-owned overlapping source; inspect first. */
    memmove(destination, source, length + 1);
    memset(destination + length + 1, 0, EP0_FS_PATH_SPAN - length - 1);
    return true;
}
#endif
