/* Raw UAC AS alt1 ISO probe: try to take interface 3 away from the macOS
   audio driver, then submit one 16 x 192 B isochronous IN transfer before
   sending the SET_CUR trigger.  This is a diagnostic host tool; it never
   changes the device firmware. */
#include <libusb.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define VID 0x1209
#define PID 0xca57
#define AS_INTERFACE 3
#define AS_ENDPOINT 0x84
#define PACKET 192
#define PACKETS 16

static void usage(const char *argv0)
{
    fprintf(stderr,
        "usage: %s [--interface N] [--endpoint 0xNN] [--packets N] "
        "[--claim-only] [--no-trigger] [--no-detach]\n", argv0);
}

int main(int argc, char **argv)
{
    int iface = AS_INTERFACE;
    int endpoint = AS_ENDPOINT;
    unsigned packets = PACKETS;
    int claim_only = 0, no_trigger = 0, no_detach = 0;
    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--interface") && i + 1 < argc) {
            iface = atoi(argv[++i]);
        } else if (!strcmp(argv[i], "--endpoint") && i + 1 < argc) {
            endpoint = (int)strtol(argv[++i], NULL, 0);
        } else if (!strcmp(argv[i], "--packets") && i + 1 < argc) {
            packets = (unsigned)strtoul(argv[++i], NULL, 0);
        } else if (!strcmp(argv[i], "--claim-only")) {
            claim_only = 1;
        } else if (!strcmp(argv[i], "--no-trigger")) {
            no_trigger = 1;
        } else if (!strcmp(argv[i], "--no-detach")) {
            no_detach = 1;
        } else {
            usage(argv[0]);
            return 2;
        }
    }
    if (packets < 1 || packets > 128) {
        fprintf(stderr, "packets must be 1..128\n");
        return 2;
    }

    libusb_context *ctx = NULL;
    libusb_device_handle *h = NULL;
    struct libusb_transfer *transfer = NULL;
    unsigned char *buffer = NULL;
    int result = 1;
    int claimed = 0;

    if (libusb_init(&ctx)) {
        fprintf(stderr, "libusb_init failed\n");
        return 1;
    }
    h = libusb_open_device_with_vid_pid(ctx, VID, PID);
    if (!h) {
        fprintf(stderr, "SysDVR %04x:%04x not accessible\n", VID, PID);
        goto cleanup;
    }

    int auto_detach = libusb_set_auto_detach_kernel_driver(h, 1);
    printf("auto_detach=%d (%s)\n", auto_detach,
           auto_detach ? libusb_error_name(auto_detach) : "ok");
    if (!no_detach) {
        int detach = libusb_detach_kernel_driver(h, iface);
        printf("detach[%d]=%d (%s)\n", iface, detach,
               detach ? libusb_error_name(detach) : "ok");
    }

    int rc = libusb_claim_interface(h, iface);
    printf("claim[%d]=%d (%s)\n", iface, rc,
           rc ? libusb_error_name(rc) : "ok");
    if (rc) {
        fprintf(stderr, "claim failed; raw host path not available\n");
        goto cleanup;
    }
    claimed = 1;
    if (claim_only) {
        result = 0;
        goto cleanup;
    }

    rc = libusb_set_interface_alt_setting(h, iface, 1);
    printf("alt1=%d (%s)\n", rc, rc ? libusb_error_name(rc) : "ok");
    if (rc) goto cleanup;
    usleep(20000);

    transfer = libusb_alloc_transfer((int)packets);
    buffer = calloc(packets, PACKET);
    if (!transfer || !buffer) {
        fprintf(stderr, "alloc failed\n");
        goto cleanup;
    }
    libusb_fill_iso_transfer(transfer, h, (unsigned char)endpoint, buffer,
        (int)(packets * PACKET), (int)packets, NULL, NULL,
        (int)packets + 2000);
    libusb_set_iso_packet_lengths(transfer, PACKET);
    rc = libusb_submit_transfer(transfer);
    printf("submit=%d (%s)\n", rc, rc ? libusb_error_name(rc) : "ok");
    if (rc) goto restore_alt;

    if (!no_trigger) {
        unsigned char rate[3] = {0x80, 0xBB, 0x00};
        int crc = libusb_control_transfer(h, 0x22, 0x01, 0x0100,
            (uint16_t)endpoint, rate, sizeof(rate), 1000);
        printf("set_cur=%d (%s)\n", crc,
               crc < 0 ? libusb_error_name(crc) : "ok");
    }

    int attempts = 0;
    while (attempts++ < 2000) {
        rc = libusb_handle_events_timeout_completed(ctx, &(struct timeval){0, 10000}, NULL);
        if (rc) {
            printf("events=%d (%s)\n", rc, libusb_error_name(rc));
            break;
        }
        if (transfer->status != LIBUSB_TRANSFER_COMPLETED &&
            transfer->status != LIBUSB_TRANSFER_TIMED_OUT)
            break;
    }
    printf("transfer status=%d (%s)\n", transfer->status,
           libusb_error_name(transfer->status));
    unsigned valid = 0, bad = 0, bytes = 0;
    for (unsigned i = 0; i < packets; ++i) {
        const struct libusb_iso_packet_descriptor *p = &transfer->iso_packet_desc[i];
        if (p->status == LIBUSB_TRANSFER_COMPLETED) {
            ++valid;
            bytes += p->actual_length;
        } else {
            ++bad;
        }
    }
    printf("done packets=%u valid=%u bad=%u bytes=%u\n", packets, valid, bad, bytes);
    result = (valid == packets && bad == 0) ? 0 : 1;

restore_alt:
    libusb_set_interface_alt_setting(h, iface, 0);
    libusb_release_interface(h, iface);
    claimed = 0;

cleanup:
    if (transfer) {
        if (transfer->status != LIBUSB_TRANSFER_COMPLETED &&
            transfer->status != LIBUSB_TRANSFER_ERROR)
            libusb_cancel_transfer(transfer);
        libusb_free_transfer(transfer);
    }
    free(buffer);
    if (claimed) libusb_release_interface(h, iface);
    if (h) libusb_close(h);
    if (ctx) libusb_exit(ctx);
    return result;
}
