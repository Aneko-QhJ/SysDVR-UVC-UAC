#include "ep0_fs_path_span.h"
#include <assert.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>

static void inaccessible(int signal_number) { (void)signal_number; _exit(77); }
/* Model the fixed-width input copy, not Switch IPC or its returned error code. */
static int read_span(const char *p) {
    pid_t child = fork(); assert(child >= 0);
    if (!child) {
        signal(SIGBUS, inaccessible); signal(SIGSEGV, inaccessible);
        volatile unsigned checksum = 0;
        for (size_t i = 0; i < EP0_FS_PATH_SPAN; ++i) checksum += (unsigned char)p[i];
        (void)checksum; _exit(0);
    }
    int status = 0; assert(waitpid(child, &status, 0) == child);
    assert(WIFEXITED(status)); return WEXITSTATUS(status);
}
int main(void) {
    long page = sysconf(_SC_PAGESIZE); assert(page > (long)EP0_FS_PATH_SPAN);
    char *memory = mmap(NULL, (size_t)page * 2, PROT_READ | PROT_WRITE,
                        MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(memory != MAP_FAILED); assert(!mprotect(memory + page, (size_t)page, PROT_NONE));
    char *small = memory + page - 96; memset(small, 0, 96); strcpy(small, "/ep0-short.bin");
    assert(read_span(small) == 77); /* A short NUL-terminated string is insufficient. */
    char *full = memory + page - EP0_FS_PATH_SPAN;
    assert(ep0_fs_path_prepare(full, EP0_FS_PATH_SPAN, small, 96));
    assert(!strcmp(full, "/ep0-short.bin")); assert(read_span(full) == 0);
    for (size_t i = strlen(full) + 1; i < EP0_FS_PATH_SPAN; ++i) assert(!full[i]);
    char source[EP0_FS_PATH_SPAN], destination[EP0_FS_PATH_SPAN + 8];
    for (size_t length = 0; length < EP0_FS_PATH_SPAN; ++length) {
        memset(source, 'p', sizeof(source)); source[length] = 0;
        memset(destination, 0x55, sizeof(destination));
        assert(ep0_fs_path_prepare(destination, EP0_FS_PATH_SPAN, source, length + 1));
        assert(!memcmp(destination, source, length + 1));
        for (size_t i = length + 1; i < EP0_FS_PATH_SPAN; ++i) assert(!destination[i]);
        for (size_t i = EP0_FS_PATH_SPAN; i < sizeof(destination); ++i) assert(destination[i] == 0x55);
    }
    memset(source, 'p', sizeof(source)); memset(destination, 0x55, sizeof(destination));
    assert(!ep0_fs_path_prepare(destination, sizeof(destination), source, sizeof(source)));
    for (size_t i = 0; i < sizeof(destination); ++i) assert(destination[i] == 0x55);
    assert(!ep0_fs_path_prepare(destination, EP0_FS_PATH_SPAN - 1, "x", 2));
    assert(!ep0_fs_path_prepare(destination, sizeof(destination), "x", 1));
    assert(!ep0_fs_path_prepare(destination, sizeof(destination), "", 0));
    assert(!ep0_fs_path_prepare(NULL, sizeof(destination), "", 1));
    assert(!ep0_fs_path_prepare(destination, sizeof(destination), NULL, 1));
    strcpy(destination + 12, "/overlap");
    assert(ep0_fs_path_prepare(destination, sizeof(destination), destination + 12, 9));
    assert(!strcmp(destination, "/overlap"));
    assert(!munmap(memory, (size_t)page * 2));
    puts("{\"guarded_short_span_rejected\":true,\"guarded_full_span_readable\":true,\"length_cases\":769,\"kernel_emulated\":false}");
    return 0;
}
