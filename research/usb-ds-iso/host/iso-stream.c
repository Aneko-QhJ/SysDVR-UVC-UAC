/* Continuous HS ISO reader for the 3-URB stream probe. */
#include <libusb.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define VID 0x1209
#define PID 0xca57
#define IFACE 2
#define EP 0x83
#define PACKET 192
#define PACKETS 16
#define TRANSFERS 100

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
            if (d->bInterfaceClass != 0xff || d->bInterfaceSubClass != 0x49 ||
                d->bInterfaceProtocol != 1 || d->bInterfaceNumber != IFACE ||
                d->bAlternateSetting != 1 || d->bNumEndpoints != 1) continue;
            const struct libusb_endpoint_descriptor *ep = &d->endpoint[0];
            if (ep->bEndpointAddress != EP ||
                (ep->bmAttributes & 3) != LIBUSB_TRANSFER_TYPE_ISOCHRONOUS ||
                ep->wMaxPacketSize != 256 || ep->bInterval != 4) continue;
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

    unsigned expected = 0;
    bool have_expected = false;
    unsigned packets = 0, bad = 0, gaps = 0, transfers = 0;
    unsigned wanted = TRANSFERS;
    unsigned per_transfer = PACKETS;
    for (int arg = 1; arg < argc; ++arg) {
        if (!strcmp(argv[arg], "--transfers") && arg + 1 < argc)
            wanted = (unsigned)strtoul(argv[++arg], NULL, 10);
        else if (!strcmp(argv[arg], "--packets") && arg + 1 < argc)
            per_transfer = (unsigned)strtoul(argv[++arg], NULL, 10);
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
        if (n == 0) {
            /* START before submitting the first ISO read: the device applies
               the per-URB delta while no ISO URB is active. */
            int crc = libusb_control_transfer(device, 0x41, 0x55, 0, (uint16_t)iface,
                NULL, 0, 1000);
            if (crc < 0) {
                fprintf(stderr, "stream START failed: %d\n", crc);
                libusb_free_transfer(transfer);
                free(buffer);
                break;
            }
        }
        if (libusb_submit_transfer(transfer)) {
            fprintf(stderr, "submit failed at %u\n", n);
            libusb_free_transfer(transfer);
            free(buffer);
            break;
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
                const unsigned char *data = libusb_get_iso_packet_buffer_simple(
                    transfer, p);
                if (pd->status != 0) {
                    ++bad;
                    continue;
                }
                if (pd->actual_length == 0) {
                    ++gaps; /* expected before/after the three 16 ms URBs */
                    continue;
                }
                if (pd->actual_length != PACKET || memcmp(data, "ISO1", 4) != 0) {
                    ++bad;
                    continue;
                }
                unsigned seq = (unsigned)data[4] | ((unsigned)data[5] << 8);
                if (!have_expected) {
                    expected = seq;
                    have_expected = true;
                }
                if (seq != (expected & 0xffff)) {
                    ++bad;
                    expected = seq;
                }
                ++expected;
                ++packets;
            }
        }
        libusb_free_transfer(transfer);
        free(buffer);
        if ((n + 1) % 10 == 0)
            printf("transfers=%u packets=%u bad=%u gaps=%u last-seq=%u\n",
                   transfers, packets, bad, gaps, expected ? expected - 1 : 0);
    }
    printf("done transfers=%u packets=%u bad=%u zero=%u\n",
           transfers, packets, bad, gaps);
    result = (bad == 0 && packets >= 48) ? 0 : 1;
    libusb_set_interface_alt_setting(device, iface, 0);
    libusb_release_interface(device, iface);
cleanup:
    if (device) libusb_close(device);
    libusb_exit(ctx);
    return result;
}
