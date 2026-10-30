/* Send UAC1 class/standard control requests to the SysDVR device.
 *
 * Read-only by default (GET_INTERFACE and sampling-frequency GETs).  SET_CUR
 * and SET_INTERFACE require explicit flags.  The tool never claims an
 * interface and never starts streaming.
 */
#include <libusb.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define VID 0x1209
#define PID 0xca57
#define AS_INTERFACE 3
#define AS_ENDPOINT 0x84
#define RATE 48000u

static int failures;

static int ctrl(libusb_device_handle *h, uint8_t type, uint8_t request,
                uint16_t value, uint16_t index, uint8_t *data, uint16_t length,
                const char *label)
{
    int rc = libusb_control_transfer(h, type, request, value, index, data, length, 1000);
    printf("%-28s bm=%02x req=%02x val=%04x idx=%04x len=%u -> %d", label, type,
           request, value, index, length, rc);
    if (rc >= 0) {
        printf(" data=");
        for (int i = 0; i < rc; ++i) printf("%02x", data[i]);
    } else {
        printf(" err=%s", libusb_error_name(rc));
    }
    printf("\n");
    return rc;
}

static int rate_ok(const uint8_t *data, int length)
{
    return length == 3 && (data[0] | (data[1] << 8) | (data[2] << 16)) == RATE;
}

int main(int argc, char **argv)
{
    int set_rate = 0, alt = -1, alt_only = 0, require_alt1 = 0, force_alt1 = 0;
    int repeat = 1, interval_ms = 20;
    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--set-rate")) set_rate = 1;
        else if (!strcmp(argv[i], "--alt-only")) alt_only = 1;
        else if (!strcmp(argv[i], "--require-alt1")) require_alt1 = 1;
        else if (!strcmp(argv[i], "--force-alt1")) force_alt1 = 1;
        else if (!strncmp(argv[i], "--alt=", 6)) alt = atoi(argv[i] + 6);
        else if (!strncmp(argv[i], "--repeat=", 9)) repeat = atoi(argv[i] + 9);
        else if (!strncmp(argv[i], "--interval-ms=", 14)) interval_ms = atoi(argv[i] + 14);
        else {
            fprintf(stderr, "usage: %s [--set-rate] [--alt-only] [--alt=0|1] "
                    "[--require-alt1] [--force-alt1] [--repeat=1..1000] "
                    "[--interval-ms=5..1000]\n", argv[0]);
            return 2;
        }
    }
    if (repeat < 1 || repeat > 1000 || interval_ms < 5 || interval_ms > 1000) {
        fprintf(stderr, "repeat must be 1..1000 and interval-ms 5..1000\n");
        return 2;
    }
    if (alt_only && require_alt1) {
        fprintf(stderr, "--require-alt1 cannot be combined with --alt-only\n");
        return 2;
    }
    if (alt_only && force_alt1) {
        fprintf(stderr, "--force-alt1 cannot be combined with --alt-only\n");
        return 2;
    }
    if (alt_only && alt < 0) alt = 1;

    libusb_context *ctx = NULL;
    libusb_device_handle *h = NULL;
    if (libusb_init(&ctx)) return 1;
    h = libusb_open_device_with_vid_pid(ctx, VID, PID);
    if (!h) {
        fprintf(stderr, "SysDVR %04x:%04x not found\n", VID, PID);
        libusb_exit(ctx);
        return 1;
    }

    uint8_t data[8] = {0};
    int rc;

    if (alt_only) {
        rc = ctrl(h, 0x81, 0x0A, 0, AS_INTERFACE, data, 1, "GET_INTERFACE before");
        if (rc != 1 || data[0] != 0) ++failures;
        rc = ctrl(h, 0x01, 0x0B, (uint16_t)alt, AS_INTERFACE, NULL, 0,
                  alt == 1 ? "SET_INTERFACE(1)" : "SET_INTERFACE(alt)");
        if (rc != 0) ++failures;
        usleep(10000);
        rc = ctrl(h, 0x81, 0x0A, 0, AS_INTERFACE, data, 1, "GET_INTERFACE alt");
        if (rc != 1 || data[0] != alt) ++failures;
        rc = ctrl(h, 0x01, 0x0B, 0, AS_INTERFACE, NULL, 0, "SET_INTERFACE(0)");
        if (rc != 0) ++failures;
        usleep(10000);
        rc = ctrl(h, 0x81, 0x0A, 0, AS_INTERFACE, data, 1, "GET_INTERFACE after");
        if (rc != 1 || data[0] != 0) ++failures;
        libusb_close(h);
        libusb_exit(ctx);
        printf("failures=%d\n", failures);
        return failures ? 1 : 0;
    }

    rc = ctrl(h, 0x81, 0x0A, 0, AS_INTERFACE, data, 1, "GET_INTERFACE(AS)");
    if (force_alt1) {
        /* Always issue SET_INTERFACE(1), even if GET_INTERFACE already
           reads 1: the device installer runs on this control request, and
           an alt1 state selected by the macOS audio driver alone leaves
           installed/table at 0 (2026-10-31 v4 run). */
        rc = ctrl(h, 0x01, 0x0B, 1, AS_INTERFACE, NULL, 0,
                  "SET_INTERFACE(1) force");
        if (rc != 0) ++failures;
        usleep(20000);
        rc = ctrl(h, 0x81, 0x0A, 0, AS_INTERFACE, data, 1,
                  "GET_INTERFACE forced");
    }
    if (rc != 1) {
        ++failures;
        if (require_alt1 || force_alt1) {
            fprintf(stderr, "GET_INTERFACE failed; aborting before SET_CUR\n");
            libusb_close(h);
            libusb_exit(ctx);
            return 1;
        }
    } else {
        printf("  alt=%u\n", data[0]);
        if ((require_alt1 || force_alt1) && data[0] != 1) {
            fprintf(stderr,
                    "alt1 required but GET_INTERFACE=%u; not sending SET_CUR\n",
                    data[0]);
            libusb_close(h);
            libusb_exit(ctx);
            return 1;
        }
    }

    const uint16_t indexes[] = {AS_ENDPOINT, AS_INTERFACE};
    const char *names[] = {"ep", "if"};
    for (int t = 0; t < 2; ++t) {
        uint16_t index = indexes[t];
        char label[48];
        const uint8_t get_type = t == 0 ? 0xA2 : 0xA1;  // endpoint vs interface
        snprintf(label, sizeof(label), "GET_CUR rate (%s)", names[t]);
        rc = ctrl(h, get_type, 0x81, 0x0100, index, data, 3, label);
        if (rc != 3 || !rate_ok(data, rc)) ++failures;
        snprintf(label, sizeof(label), "GET_MIN rate (%s)", names[t]);
        rc = ctrl(h, get_type, 0x82, 0x0100, index, data, 3, label);
        if (rc != 3 || !rate_ok(data, rc)) ++failures;
        snprintf(label, sizeof(label), "GET_MAX rate (%s)", names[t]);
        rc = ctrl(h, get_type, 0x83, 0x0100, index, data, 3, label);
        if (rc != 3 || !rate_ok(data, rc)) ++failures;
        snprintf(label, sizeof(label), "GET_RES rate (%s)", names[t]);
        rc = ctrl(h, get_type, 0x84, 0x0100, index, data, 3, label);
        if (rc != 3 || !rate_ok(data, rc)) ++failures;
        snprintf(label, sizeof(label), "GET_LEN rate (%s)", names[t]);
        rc = ctrl(h, get_type, 0x85, 0x0100, index, data, 2, label);
        if (rc != 2 || data[0] != 3 || data[1] != 0) ++failures;
    }

    if (set_rate) {
        /* The macOS audio driver only keeps alt1 briefly around config-change
           restarts, so the U2 trigger is repeated: the device posts at most
           once per boot (burstPosted), and logs every SET_CUR that arrives at
           alt0 as "UAC U2 skip". */
        uint8_t payload[3] = {0x80, 0xBB, 0x00};
        for (int n = 0; n < repeat; ++n) {
            rc = ctrl(h, 0x22, 0x01, 0x0100, AS_ENDPOINT, payload, 3,
                      n == 0 ? "SET_CUR rate 48k (ep)" : "SET_CUR retrigger (ep)");
            if (rc != 3) ++failures;
            if (n + 1 < repeat) usleep((useconds_t)interval_ms * 1000);
        }
        rc = ctrl(h, 0xA2, 0x81, 0x0100, AS_ENDPOINT, data, 3, "GET_CUR after SET (ep)");
        if (rc != 3 || !rate_ok(data, rc)) ++failures;
    }
    if (force_alt1) {
        rc = ctrl(h, 0x01, 0x0B, 0, AS_INTERFACE, NULL, 0,
                  "SET_INTERFACE(0) restore force");
        if (rc != 0) ++failures;
    }

    if (alt >= 0) {
        rc = ctrl(h, 0x01, 0x0B, (uint16_t)alt, AS_INTERFACE, NULL, 0, "SET_INTERFACE(AS)");
        if (rc != 0) ++failures;
        rc = ctrl(h, 0x81, 0x0A, 0, AS_INTERFACE, data, 1, "GET_INTERFACE after set");
        if (rc != 1 || data[0] != alt) ++failures;
        if (alt != 0) {
            rc = ctrl(h, 0x01, 0x0B, 0, AS_INTERFACE, NULL, 0, "SET_INTERFACE(0) restore");
            if (rc != 0) ++failures;
        }
    }

    libusb_close(h);
    libusb_exit(ctx);
    printf("failures=%d\n", failures);
    return failures ? 1 : 0;
}
