/* Dump the SysDVR USB device/configuration descriptors without claiming it.
 *
 * This is read-only: libusb_get_config_descriptor() does not select a
 * configuration or send any data to an endpoint.  It is used to tell whether
 * the AC/AS interfaces and alt1 endpoint are actually present in the published
 * configuration when a host refuses to bind a UAC driver.
 */
#include <libusb.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define VID 0x1209
#define PID 0xca57

static void hex(const unsigned char *data, int length)
{
    for (int i = 0; i < length; ++i) printf("%02x", data[i]);
}

static void dump_extra(const char *where, const unsigned char *extra, int length)
{
    if (!extra || length <= 0) return;
    printf("  %s extra[%d]=", where, length);
    hex(extra, length);
    printf("\n");
}

int main(void)
{
    libusb_context *ctx = NULL;
    libusb_device_handle *device = NULL;
    struct libusb_device_descriptor dd;
    struct libusb_config_descriptor *config = NULL;
    int result = 1;

    if (libusb_init(&ctx)) {
        fprintf(stderr, "libusb_init failed\n");
        return 1;
    }
    device = libusb_open_device_with_vid_pid(ctx, VID, PID);
    if (!device) {
        fprintf(stderr, "SysDVR %04x:%04x not found\n", VID, PID);
        goto cleanup;
    }
    if (libusb_get_device_descriptor(libusb_get_device(device), &dd)) {
        fprintf(stderr, "device descriptor failed\n");
        goto cleanup;
    }
    printf("device idVendor=%04x idProduct=%04x bcdUSB=%04x bDeviceClass=%02x "
           "bNumConfigurations=%u\n",
           dd.idVendor, dd.idProduct, dd.bcdUSB, dd.bDeviceClass,
           dd.bNumConfigurations);

    if (libusb_get_config_descriptor(libusb_get_device(device), 0, &config)) {
        fprintf(stderr, "configuration descriptor 0 failed\n");
        goto cleanup;
    }
    printf("config[0] wTotalLength=%u bNumInterfaces=%u bConfigurationValue=%u "
           "bmAttributes=%02x bMaxPower=%u\n",
           config->wTotalLength, config->bNumInterfaces,
           config->bConfigurationValue, config->bmAttributes, config->MaxPower);
    dump_extra("config", config->extra, config->extra_length);

    for (unsigned i = 0; i < config->bNumInterfaces; ++i) {
        const struct libusb_interface *iface = &config->interface[i];
        for (int j = 0; j < iface->num_altsetting; ++j) {
            const struct libusb_interface_descriptor *id = &iface->altsetting[j];
            printf("interface %u alt %u class=%02x subclass=%02x protocol=%02x "
                   "endpoints=%u\n",
                   id->bInterfaceNumber, id->bAlternateSetting,
                   id->bInterfaceClass, id->bInterfaceSubClass,
                   id->bInterfaceProtocol, id->bNumEndpoints);
            dump_extra("interface", id->extra, id->extra_length);
            for (unsigned k = 0; k < id->bNumEndpoints; ++k) {
                const struct libusb_endpoint_descriptor *ep = &id->endpoint[k];
                printf("  ep %02x attr=%02x mps=%u interval=%u\n",
                       ep->bEndpointAddress, ep->bmAttributes,
                       ep->wMaxPacketSize, ep->bInterval);
                dump_extra("endpoint", ep->extra, ep->extra_length);
            }
        }
    }

    result = 0;
cleanup:
    if (config) libusb_free_config_descriptor(config);
    if (device) libusb_close(device);
    libusb_exit(ctx);
    return result;
}
