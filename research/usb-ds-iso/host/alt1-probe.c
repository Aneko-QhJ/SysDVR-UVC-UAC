#define _POSIX_C_SOURCE 200809L
#include <libusb.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "../../../source/uvc/alt1_probe_protocol.h"

#define PROBE_VID 0x1209
#define PROBE_PID 0xCA57
#define PROBE_IFACE 2
#define PROBE_EP_IN 0x84

static const char *err_name(int rc)
{
    const char *name = libusb_error_name(rc);
    return name ? name : "unknown";
}

int main(void)
{
    libusb_context *ctx = NULL;
    libusb_device **list = NULL;
    libusb_device_handle *handle = NULL;
    int rc = libusb_init(&ctx);
    if (rc != 0) {
        fprintf(stderr, "libusb_init: %d (%s)\n", rc, err_name(rc));
        return 2;
    }

    ssize_t count = libusb_get_device_list(ctx, &list);
    if (count < 0) {
        fprintf(stderr, "get_device_list: %zd\n", count);
        libusb_exit(ctx);
        return 2;
    }
    for (ssize_t i = 0; i < count; ++i) {
        struct libusb_device_descriptor desc;
        if (libusb_get_device_descriptor(list[i], &desc) != 0) continue;
        if (desc.idVendor != PROBE_VID || desc.idProduct != PROBE_PID) continue;
        rc = libusb_open(list[i], &handle);
        if (rc != 0) {
            fprintf(stderr, "open %04x:%04x: %d (%s)\n",
                    PROBE_VID, PROBE_PID, rc, err_name(rc));
        }
        break;
    }
    if (!handle) {
        fprintf(stderr, "device %04x:%04x not found (or open failed)\n",
                PROBE_VID, PROBE_PID);
        libusb_free_device_list(list, 1);
        libusb_exit(ctx);
        return 2;
    }

    if (libusb_kernel_driver_active(handle, PROBE_IFACE) == 1)
        (void)libusb_detach_kernel_driver(handle, PROBE_IFACE);

    rc = libusb_claim_interface(handle, PROBE_IFACE);
    printf("claim_interface(%d): %d (%s)\n", PROBE_IFACE, rc, err_name(rc));
    if (rc != 0) {
        libusb_close(handle);
        libusb_free_device_list(list, 1);
        libusb_exit(ctx);
        return 2;
    }

    rc = libusb_set_interface_alt_setting(handle, PROBE_IFACE, 1);
    printf("set_alt(1): %d (%s)\n", rc, err_name(rc));
    const int set_alt_ok = (rc == 0);

    uint8_t buffer[ALT1_PROBE_BUFFER_SIZE];
    memset(buffer, 0, sizeof(buffer));

    rc = libusb_control_transfer(handle, 0x41, ALT1_PROBE_TRIGGER, 0,
                                 PROBE_IFACE, NULL, 0, 1000);
    printf("trigger: %d (%s)\n", rc, err_name(rc));

    int transferred = 0;
    int bulk_rc = libusb_bulk_transfer(handle, PROBE_EP_IN, buffer,
                                       sizeof(buffer), &transferred, 3000);
    printf("bulk(0x%02x): %d (%s) transferred=%d\n",
           PROBE_EP_IN, bulk_rc, err_name(bulk_rc), transferred);
    if (transferred >= 4) {
        printf("data: %02x %02x %02x %02x %02x %02x %02x %02x\n",
               buffer[0], buffer[1], buffer[2], buffer[3],
               buffer[4], buffer[5], buffer[6], buffer[7]);
    }

    Alt1ProbeStatus status;
    memset(&status, 0, sizeof(status));
    int status_rc = libusb_control_transfer(handle, 0xC1, ALT1_PROBE_STATUS, 0,
                                            PROBE_IFACE, (uint8_t *)&status,
                                            sizeof(status), 1000);
    printf("status: %d (%s)\n", status_rc, err_name(status_rc));
    if (status_rc == (int)sizeof(status)) {
        printf("magic=%08x version=%u alt=%u state=%u post=0x%08x urb=%u "
               "completed=%u transferred=%u urb_status=%u triggers=%u reports=%u\n",
               status.magic, status.version, status.alt, status.state,
               status.post_result, status.urb_id, status.completed,
               status.transferred, status.urb_status, status.triggers,
               status.reports);
    }

    (void)libusb_set_interface_alt_setting(handle, PROBE_IFACE, 0);
    libusb_release_interface(handle, PROBE_IFACE);
    libusb_close(handle);
    libusb_free_device_list(list, 1);
    libusb_exit(ctx);

    const int data_ok = transferred >= 4 && buffer[0] == 'A' &&
                        buffer[1] == 'L' && buffer[2] == 'T' && buffer[3] == '1';
    return (set_alt_ok && bulk_rc == 0 && data_ok) ? 0 : 1;
}
