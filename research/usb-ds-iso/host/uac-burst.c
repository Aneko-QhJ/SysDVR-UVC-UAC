/* One bounded UAC AS alt1 ISO burst reader (EP 0x84, 16 x 192 B).
 *
 * Order matters: claim interface 3, set alt1, submit the ISO transfer first,
 * then send one SET_CUR(48000) trigger.  The U2 producer builds its 16
 * Isoch+ED TDs when the device posts the URB from that request, so a trigger
 * sent before submit would land outside the host polling window (uac-burst
 * originally did that; iso-probe has always submitted first).
 *
 * Defaults: one 16-packet transfer, --trigger-delay-ms 10 (1..500).
 */
#include <libusb.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define VID 0x1209
#define PID 0xca57
#define IFACE 3
#define EP 0x84
#define PACKET 192
#define PACKETS 16
#define TRANSFERS 1

static volatile bool done;

static void LIBUSB_CALL on_transfer(struct libusb_transfer *transfer)
{
    (void)transfer;
    done = true;
}

static int find_interface(libusb_device_handle *device)
{
    struct libusb_config_descriptor *config = NULL;
    if (libusb_get_active_config_descriptor(libusb_get_device(device), &config)) return -1;
    int iface = -1;
    for (unsigned i = 0; i < config->bNumInterfaces; ++i) {
        for (int j = 0; j < config->interface[i].num_altsetting; ++j) {
            const struct libusb_interface_descriptor *d =
                &config->interface[i].altsetting[j];
            if (d->bInterfaceClass != 0x01 || d->bInterfaceSubClass != 0x02 ||
                d->bInterfaceProtocol != 0 || d->bInterfaceNumber != IFACE ||
                d->bAlternateSetting != 1 || d->bNumEndpoints != 1) continue;
            const struct libusb_endpoint_descriptor *ep = &d->endpoint[0];
            if (ep->bEndpointAddress != EP ||
                (ep->bmAttributes & 3) != LIBUSB_TRANSFER_TYPE_ISOCHRONOUS ||
                ep->wMaxPacketSize != 192 || ep->bInterval != 4) continue;
            iface = d->bInterfaceNumber;
        }
    }
    libusb_free_config_descriptor(config);
    return iface;
}

int main(int argc, char **argv)
{
    libusb_context *ctx = NULL;
    libusb_device_handle *device = NULL;
    int result = 1;
    if (libusb_init(&ctx)) {
        fprintf(stderr, "libusb_init failed\n");
        return 1;
    }
    device = libusb_open_device_with_vid_pid(ctx, VID, PID);
    if (!device) {
        fprintf(stderr, "SysDVR %04x:%04x not accessible\n", VID, PID);
        goto cleanup;
    }
    int speed = libusb_get_device_speed(libusb_get_device(device));
    if (speed != LIBUSB_SPEED_HIGH) {
        fprintf(stderr, "requires HS (speed=%d)\n", speed);
        goto cleanup;
    }
    int iface = find_interface(device);
    if (iface != IFACE) {
        fprintf(stderr, "stream interface/endpoint missing\n");
        goto cleanup;
    }
    if (libusb_claim_interface(device, iface)) {
        fprintf(stderr, "claim failed\n");
        goto cleanup;
    }
    if (libusb_set_interface_alt_setting(device, iface, 1)) {
        fprintf(stderr, "set alt1 failed\n");
        goto cleanup;
    }
    usleep(100000);

    unsigned packets = 0, bad = 0, gaps = 0, transfers = 0;
    unsigned wanted = TRANSFERS;
    unsigned per_transfer = PACKETS;
    unsigned trigger_delay_ms = 10;
    for (int arg = 1; arg < argc; ++arg) {
        if (!strcmp(argv[arg], "--transfers") && arg + 1 < argc)
            wanted = (unsigned)strtoul(argv[++arg], NULL, 10);
        else if (!strcmp(argv[arg], "--packets") && arg + 1 < argc)
            per_transfer = (unsigned)strtoul(argv[++arg], NULL, 10);
        else if (!strcmp(argv[arg], "--trigger-delay-ms") && arg + 1 < argc) {
            char *end = NULL;
            unsigned long n = strtoul(argv[++arg], &end, 10);
            if (*end || n < 1 || n > 500) {
                fprintf(stderr, "trigger delay must be 1..500 ms\n");
                goto cleanup;
            }
            trigger_delay_ms = (unsigned)n;
        }
    }
    for (unsigned n = 0; n < wanted; ++n) {
        struct libusb_transfer *transfer = libusb_alloc_transfer((int)per_transfer);
        unsigned char *buffer = calloc(per_transfer, PACKET);
        if (!transfer || !buffer) {
            libusb_free_transfer(transfer);
            free(buffer);
            break;
        }
        libusb_fill_iso_transfer(transfer, device, EP, buffer, per_transfer * PACKET,
            (int)per_transfer, on_transfer, NULL, (int)per_transfer + 2000);
        libusb_set_iso_packet_lengths(transfer, PACKET);
        done = false;
        if (libusb_submit_transfer(transfer)) {
            fprintf(stderr, "submit failed at %u\n", n);
            libusb_free_transfer(transfer);
            free(buffer);
            break;
        }
        if (n == 0) {
            /* UAC trigger: set the sampling rate once the host pipe is live.
               A U2 build posts one 3072-byte URB from this request, and the
               producer schedules its TDs at post time, so the transfer must
               already be submitted (the A23 host does the same). */
            usleep(trigger_delay_ms * 1000);
            uint8_t rate[3] = {0x80, 0xBB, 0x00};
            int crc = libusb_control_transfer(device, 0x22, 0x01, 0x0100, EP,
                rate, sizeof(rate), 1000);
            if (crc < 0) {
                fprintf(stderr, "UAC SET_CUR trigger failed: %d\n", crc);
                libusb_cancel_transfer(transfer);
                while (!done && libusb_handle_events(ctx) == 0) {}
                libusb_free_transfer(transfer);
                free(buffer);
                break;
            }
        }
        while (!done) {
            if (libusb_handle_events(ctx) < 0) break;
        }
        if (transfer->status != LIBUSB_TRANSFER_COMPLETED) {
            ++bad;
            fprintf(stderr, "transfer %u status %d\n", n, transfer->status);
        } else {
            ++transfers;
            for (unsigned p = 0; p < per_transfer; ++p) {
                const struct libusb_iso_packet_descriptor *pd =
                    &transfer->iso_packet_desc[p];
                if (pd->status != 0) {
                    ++bad;
                    continue;
                }
                if (pd->actual_length == 0) {
                    ++gaps; /* expected before/after the three 16 ms URBs */
                    continue;
                }
                if (pd->actual_length != PACKET) {
                    ++bad;
                    continue;
                }
                ++packets;
            }
        }
        libusb_free_transfer(transfer);
        free(buffer);
        if ((n + 1) % 10 == 0)
            printf("transfers=%u packets=%u bad=%u gaps=%u\n",
                   transfers, packets, bad, gaps);
    }
    printf("done transfers=%u packets=%u bad=%u zero=%u\n",
           transfers, packets, bad, gaps);
    result = (bad == 0 && packets >= 16) ? 0 : 1;
    libusb_set_interface_alt_setting(device, iface, 0);
    libusb_release_interface(device, iface);
cleanup:
    if (device) libusb_close(device);
    libusb_exit(ctx);
    return result;
}
