#pragma once
#include <sys/stat.h>
#include <unistd.h>

/* Read only the native batch written before this callback. The evidence file
 * is mandatory: missing/partial/malformed/replaced data closes the serial gate.
 * Empty-slot native errors are preserved; all overall results must still be0. */
static long native_guard_offset;
static dev_t native_guard_device;
static ino_t native_guard_inode;
static bool native_guard_identity_set;
static bool native_file_guard(struct libusb_transfer *transfer, unsigned *records,
                              unsigned *payloads) {
    *records = *payloads = 0;
    const char *path = getenv("ISO_NATIVE_LOG_PATH");
    if (!path || !*path || fflush(stderr)) return false;
    FILE *file = fopen(path, "r");
    if (!file) return false;
    struct stat info;
    bool pass = fstat(fileno(file), &info) == 0 && S_ISREG(info.st_mode);
    if (pass && native_guard_identity_set)
        pass = info.st_dev == native_guard_device && info.st_ino == native_guard_inode;
    if (!pass || info.st_size < native_guard_offset || fseek(file, native_guard_offset, SEEK_SET)) {
        fclose(file); return false;
    }
    native_guard_device=info.st_dev; native_guard_inode=info.st_ino; native_guard_identity_set=true;
    char line[1024];
    while (fgets(line, sizeof(line), file)) {
        if (strncmp(line, "{\"kind\":\"darwin_iso_native\"", 27)) continue;
        unsigned index,overall,status,requested,actual;
        int end=0;
        int fields=sscanf(line,"{\"kind\":\"darwin_iso_native\",\"index\":%u,\"overall\":%u,\"status\":%u,\"requested\":%u,\"actual\":%u}%n",
                          &index,&overall,&status,&requested,&actual,&end);
        if (fields!=5 || !end || (line[end]!='\n' && line[end]!='\0')) { pass=false; continue; }
        if (index!=*records || index>=(unsigned)transfer->num_iso_packets) { pass=false; ++*records; continue; }
        ++*records;
        const struct libusb_iso_packet_descriptor *packet=&transfer->iso_packet_desc[index];
        if (overall || requested!=192 || requested!=packet->length || actual!=packet->actual_length) pass=false;
        if (actual) {
            ++*payloads;
            if (actual!=192 || status) pass=false;
        }
    }
    if (ferror(file)) pass=false;
    long end=ftell(file);
    if (end<0) pass=false; else native_guard_offset=end;
    if (fclose(file)) pass=false;
    return pass && *records==(unsigned)transfer->num_iso_packets && *payloads==16;
}
