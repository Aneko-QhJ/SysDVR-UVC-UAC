/* Raw UAC AS alt1 ISO probe: try to take interface 3 away from the macOS
   audio driver, then submit concurrent 16 x 192 B isochronous IN transfers
   around the SET_CUR trigger.  This is a diagnostic host tool; it never
   changes the device firmware. */
#include <libusb.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#define VID 0x1209
#define PID 0xca57
#define AS_INTERFACE 3
#define AS_ENDPOINT 0x84
#define PACKET 192
#define PACKETS 16
#define MAX_XFERS 32
#define MAX_URBS_TOTAL 1024

struct xfer_state {
    volatile int done;
};

static void LIBUSB_CALL on_iso_done(struct libusb_transfer *transfer)
{
    struct xfer_state *state = transfer->user_data;
    if (state) state->done = 1;
}

static int submit_iso(struct libusb_transfer *t, libusb_device_handle *h,
                      int endpoint, unsigned char *buf, unsigned packets,
                      int timeout_ms, struct xfer_state *state)
{
    state->done = 0;
    libusb_fill_iso_transfer(t, h, (unsigned char)endpoint, buf,
                             (int)(packets * PACKET), (int)packets,
                             on_iso_done, state, timeout_ms);
    libusb_set_iso_packet_lengths(t, PACKET);
    return libusb_submit_transfer(t);
}

static void packet_stats(const struct libusb_transfer *t, unsigned packets,
                         unsigned *valid, unsigned *bad, unsigned *bytes)
{
    unsigned v = 0, b = 0, n = 0;
    for (unsigned p = 0; p < packets; ++p) {
        const struct libusb_iso_packet_descriptor *d = &t->iso_packet_desc[p];
        if (d->status == LIBUSB_TRANSFER_COMPLETED) {
            ++v;
            n += d->actual_length;
        } else {
            ++b;
        }
    }
    *valid = v;
    *bad = b;
    *bytes = n;
}

static unsigned long long now_ms(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (unsigned long long)ts.tv_sec * 1000ULL +
           (unsigned long long)ts.tv_nsec / 1000000ULL;
}

static void usage(const char *argv0)
{
    fprintf(stderr,
        "usage: %s [--interface N] [--endpoint 0xNN] [--packets N] "
        "[--claim-only] [--no-trigger] [--no-detach] "
        "[--trigger-first] [--delay-ms N] [--transfers N] "
        "[--timeout-ms N] [--rearm] [--max-urbs N]\n", argv0);
}

int main(int argc, char **argv)
{
    int iface = AS_INTERFACE;
    int endpoint = AS_ENDPOINT;
    unsigned packets = PACKETS;
    unsigned transfers = 1;
    int claim_only = 0, no_trigger = 0, no_detach = 0;
    int trigger_first = 0, delay_ms = 0, timeout_ms = 500;
    int rearm = 0;
    unsigned max_urbs = 64;
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
        } else if (!strcmp(argv[i], "--trigger-first")) {
            trigger_first = 1;
        } else if (!strcmp(argv[i], "--delay-ms") && i + 1 < argc) {
            delay_ms = atoi(argv[++i]);
        } else if (!strcmp(argv[i], "--transfers") && i + 1 < argc) {
            transfers = (unsigned)strtoul(argv[++i], NULL, 0);
        } else if (!strcmp(argv[i], "--timeout-ms") && i + 1 < argc) {
            timeout_ms = atoi(argv[++i]);
        } else if (!strcmp(argv[i], "--rearm")) {
            rearm = 1;
        } else if (!strcmp(argv[i], "--max-urbs") && i + 1 < argc) {
            max_urbs = (unsigned)strtoul(argv[++i], NULL, 0);
        } else {
            usage(argv[0]);
            return 2;
        }
    }
    if (packets < 1 || packets > 128) {
        fprintf(stderr, "packets must be 1..128\n");
        return 2;
    }
    if (transfers < 1 || transfers > MAX_XFERS) {
        fprintf(stderr, "transfers must be 1..%d\n", MAX_XFERS);
        return 2;
    }
    if (timeout_ms < 50 || timeout_ms > 10000) {
        fprintf(stderr, "timeout-ms must be 50..10000\n");
        return 2;
    }
    if (max_urbs < 1 || max_urbs > MAX_URBS_TOTAL) {
        fprintf(stderr, "max-urbs must be 1..%d\n", MAX_URBS_TOTAL);
        return 2;
    }
    if (rearm && max_urbs < transfers) {
        fprintf(stderr, "max-urbs must be >= transfers (window)\n");
        return 2;
    }
    setvbuf(stdout, NULL, _IONBF, 0);

    libusb_context *ctx = NULL;
    libusb_device_handle *h = NULL;
    struct libusb_transfer *xfers[MAX_XFERS] = {0};
    unsigned char *bufs[MAX_XFERS] = {0};
    struct xfer_state states[MAX_XFERS] = {{0}};
    unsigned submitted = 0;
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
    if (rc) goto restore_alt;
    usleep(20000);

    unsigned char rate[3] = {0x80, 0xBB, 0x00};
    int crc = 0;
    if (trigger_first && !no_trigger) {
        crc = libusb_control_transfer(h, 0x22, 0x01, 0x0100,
            (uint16_t)endpoint, rate, sizeof(rate), 1000);
        printf("set_cur=%d (%s)\n", crc,
               crc < 0 ? libusb_error_name(crc) : "ok");
        if (crc < 0) goto restore_alt;
    }
    if (delay_ms > 0) usleep((useconds_t)delay_ms * 1000);

    const unsigned budget = rearm ? max_urbs : transfers;
    if (rearm)
        printf("rearm window=%u max_urbs=%u packets=%u timeout_ms=%d\n",
               transfers, max_urbs, packets, timeout_ms);
    else
        printf("concurrent transfers=%u packets=%u timeout_ms=%d\n",
               transfers, packets, timeout_ms);
    for (unsigned i = 0; i < transfers; ++i) {
        xfers[i] = libusb_alloc_transfer((int)packets);
        bufs[i] = calloc(packets, PACKET);
        if (!xfers[i] || !bufs[i]) {
            fprintf(stderr, "alloc failed at %u\n", i);
            break;
        }
    }
    const unsigned limit = (rearm && budget < transfers) ? budget : transfers;
    for (unsigned i = 0; i < limit; ++i) {
        rc = submit_iso(xfers[i], h, endpoint, bufs[i], packets, timeout_ms,
                        &states[i]);
        printf("submit[%u]=%d (%s)\n", i, rc,
               rc ? libusb_error_name(rc) : "ok");
        if (rc) break;
        ++submitted;
    }

    if (!no_trigger && !trigger_first) {
        crc = libusb_control_transfer(h, 0x22, 0x01, 0x0100,
            (uint16_t)endpoint, rate, sizeof(rate), 1000);
        printf("set_cur=%d (%s)\n", crc,
               crc < 0 ? libusb_error_name(crc) : "ok");
    }
    if (submitted == 0) goto restore_alt;

    unsigned long long started = now_ms();
    unsigned long long deadline = started + (unsigned long long)timeout_ms;
    unsigned total_valid = 0, total_bad = 0, total_bytes = 0;
    unsigned done_urbs = 0;

    if (rearm) {
        /* Keep `transfers` URBs in flight at all times: every completion is
           replaced immediately, so each new cave TD window (+32 frames) finds
           URBs already queued.  A one-shot batch of 8 only covers the first
           burst; after it drains the second device post has no host window. */
        unsigned in_flight = submitted;
        while ((submitted < budget || in_flight > 0) && now_ms() < deadline) {
            struct timeval tv = {0, 5000};
            rc = libusb_handle_events_timeout(ctx, &tv);
            if (rc < 0) {
                printf("events=%d (%s)\n", rc, libusb_error_name(rc));
                break;
            }
            for (unsigned i = 0; i < transfers; ++i) {
                if (!states[i].done) continue;
                struct libusb_transfer *t = xfers[i];
                unsigned valid = 0, bad = 0, bytes = 0;
                packet_stats(t, packets, &valid, &bad, &bytes);
                total_valid += valid;
                total_bad += bad;
                total_bytes += bytes;
                printf("urb[%u] t=%llums status=%d valid=%u bad=%u bytes=%u\n",
                       ++done_urbs, now_ms() - started, t->status, valid, bad,
                       bytes);
                --in_flight;
                if (submitted < budget && now_ms() < deadline) {
                    rc = submit_iso(t, h, endpoint, bufs[i], packets,
                                    timeout_ms, &states[i]);
                    if (rc == 0) {
                        ++submitted;
                        ++in_flight;
                    } else {
                        printf("resubmit[%u]=%d (%s)\n", i, rc,
                               libusb_error_name(rc));
                    }
                }
            }
        }
        if (in_flight > 0) {
            printf("cancel remaining=%u/%u\n", in_flight, submitted);
            for (unsigned i = 0; i < transfers; ++i)
                if (!states[i].done) libusb_cancel_transfer(xfers[i]);
            for (unsigned n = 0; n < 20; ++n) {
                struct timeval tv = {0, 5000};
                libusb_handle_events_timeout(ctx, &tv);
            }
        }
        printf("done transfers=%u packets=%u valid=%u bad=%u bytes=%u\n",
               done_urbs, packets, total_valid, total_bad, total_bytes);
        result = (total_bytes > 0) ? 0 : 1;
    } else {
        unsigned completed = 0;
        while (completed < submitted && now_ms() < deadline) {
            struct timeval tv = {0, 10000};
            rc = libusb_handle_events_timeout(ctx, &tv);
            if (rc < 0) {
                printf("events=%d (%s)\n", rc, libusb_error_name(rc));
                break;
            }
            completed = 0;
            for (unsigned i = 0; i < submitted; ++i)
                if (states[i].done) ++completed;
        }
        if (completed < submitted) {
            printf("cancel remaining=%u/%u\n", submitted - completed, submitted);
            for (unsigned i = 0; i < submitted; ++i)
                if (!states[i].done) libusb_cancel_transfer(xfers[i]);
            for (unsigned n = 0; n < 20; ++n) {
                struct timeval tv = {0, 5000};
                libusb_handle_events_timeout(ctx, &tv);
            }
        }

        for (unsigned i = 0; i < submitted; ++i) {
            struct libusb_transfer *t = xfers[i];
            unsigned valid = 0, bad = 0, bytes = 0;
            packet_stats(t, packets, &valid, &bad, &bytes);
            total_valid += valid;
            total_bad += bad;
            total_bytes += bytes;
            printf("transfer[%u] status=%d valid=%u bad=%u bytes=%u\n",
                   i, t->status, valid, bad, bytes);
            if (i == 0) {
                for (unsigned p = 0; p < packets && p < 4; ++p) {
                    const struct libusb_iso_packet_descriptor *d =
                        &t->iso_packet_desc[p];
                    printf("packet[%u] status=%d actual=%u\n",
                           p, d->status, d->actual_length);
                }
            }
        }
        printf("done transfers=%u packets=%u valid=%u bad=%u bytes=%u\n",
               submitted, packets, total_valid, total_bad, total_bytes);
        result = (total_bytes > 0) ? 0 : 1;
    }

restore_alt:
    libusb_set_interface_alt_setting(h, iface, 0);
    libusb_release_interface(h, iface);
    claimed = 0;

cleanup:
    for (unsigned i = 0; i < MAX_XFERS; ++i) {
        if (xfers[i]) {
            if (states[i].done == 0 && xfers[i]->status != LIBUSB_TRANSFER_COMPLETED)
                libusb_cancel_transfer(xfers[i]);
            libusb_free_transfer(xfers[i]);
        }
        free(bufs[i]);
    }
    if (claimed) libusb_release_interface(h, iface);
    if (h) libusb_close(h);
    if (ctx) libusb_exit(ctx);
    return result;
}
