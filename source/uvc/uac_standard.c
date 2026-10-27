#include "uac_standard.h"
#include "uac_descriptors.h"

#include <stdio.h>
#include <string.h>

#ifndef USB_DT_INTERFACE
#define USB_DT_INTERFACE 0x04
#endif
#ifndef USB_DT_ENDPOINT
#define USB_DT_ENDPOINT 0x05
#endif
#ifndef USB_DT_INTERFACE_ASSOCIATION
#define USB_DT_INTERFACE_ASSOCIATION 0x0B
#endif
#ifndef USB_DT_SS_ENDPOINT_COMPANION
#define USB_DT_SS_ENDPOINT_COMPANION 0x30
#endif
#ifndef USB_DT_INTERFACE_SIZE
#define USB_DT_INTERFACE_SIZE 9
#endif
#ifndef USB_DT_ENDPOINT_SIZE
#define USB_DT_ENDPOINT_SIZE 7
#endif
#ifndef USB_ENDPOINT_IN
#define USB_ENDPOINT_IN 0x80
#endif
#ifndef USB_TRANSFER_TYPE_ISOCHRONOUS
#define USB_TRANSFER_TYPE_ISOCHRONOUS 0x01
#endif

#define UAC_REQ_SET_CUR 0x01
#define UAC_REQ_GET_CUR 0x81
#define UAC_REQ_GET_MIN 0x82
#define UAC_REQ_GET_MAX 0x83
#define UAC_REQ_GET_RES 0x84
#define UAC_REQ_GET_LEN 0x85
#define UAC_REQ_SET_INTERFACE 0x0B
#define UAC_REQ_GET_INTERFACE 0x0A

#define UAC_TYPE_MASK 0x60
#define UAC_TYPE_STANDARD 0x00
#define UAC_TYPE_CLASS 0x20
#define UAC_RECIPIENT_MASK 0x1F
#define UAC_RECIPIENT_INTERFACE 0x01
#define UAC_RECIPIENT_ENDPOINT 0x02
#define UAC_DIR_IN 0x80

#define UAC_AC_CLASS_SPECIFIC_SIZE 30
#define UAC_AS_FORMAT_SIZE 11

typedef struct {
    uint8_t *out;
    size_t cap;
    size_t len;
    bool ok;
} UacBuf;

static void put8(UacBuf *b, uint8_t value)
{
    if (b->len < b->cap) {
        b->out[b->len++] = value;
    } else {
        b->ok = false;
    }
}

static void put16(UacBuf *b, uint16_t value)
{
    put8(b, (uint8_t)(value & 0xFF));
    put8(b, (uint8_t)(value >> 8));
}

static size_t finish(UacBuf *b)
{
    return b->ok ? b->len : 0;
}

static uint16_t get16(const uint8_t *p, size_t offset)
{
    return (uint16_t)(p[offset] | ((uint16_t)p[offset + 1] << 8));
}

static uint32_t get24(const uint8_t *p, size_t offset)
{
    return (uint32_t)p[offset] | ((uint32_t)p[offset + 1] << 8) |
           ((uint32_t)p[offset + 2] << 16);
}

static bool fail(char *err, size_t err_cap, const char *message)
{
    if (err && err_cap) {
        snprintf(err, err_cap, "%s", message);
    }
    return false;
}

void UacStandardInit(UacStandardState *state, uint8_t ac_interface,
                     uint8_t as_interface, uint8_t ep_address)
{
    if (!state) return;
    memset(state, 0, sizeof(*state));
    state->ac_interface = ac_interface;
    state->as_interface = as_interface;
    state->ep_address = ep_address;
    state->alt_setting = 0;
    state->streaming = false;
    state->sample_rate = UAC_SAMPLE_RATE;
}

static UacActionResult action(UacAction kind)
{
    UacActionResult result;
    memset(&result, 0, sizeof(result));
    result.action = kind;
    return result;
}

static UacActionResult write_rate(uint32_t rate)
{
    UacActionResult result = action(UAC_ACT_WRITE);
    result.data[0] = (uint8_t)(rate & 0xFF);
    result.data[1] = (uint8_t)((rate >> 8) & 0xFF);
    result.data[2] = (uint8_t)((rate >> 16) & 0xFF);
    result.data_len = 3;
    return result;
}

UacActionResult UacStandardHandle(UacStandardState *state,
                                  const UacSetupPacket *setup,
                                  const uint8_t *payload, size_t payload_len)
{
    if (!state || !setup) return action(UAC_ACT_STALL);

    const uint8_t type = setup->bmRequestType & UAC_TYPE_MASK;
    const uint8_t recipient = setup->bmRequestType & UAC_RECIPIENT_MASK;
    const bool direction_in = (setup->bmRequestType & UAC_DIR_IN) != 0;
    const uint8_t control = (uint8_t)(setup->wValue >> 8);
    const uint8_t channel = (uint8_t)(setup->wValue & 0xFF);

    if (type == UAC_TYPE_STANDARD) {
        if (recipient != UAC_RECIPIENT_INTERFACE) return action(UAC_ACT_STALL);

        if (setup->bRequest == UAC_REQ_SET_INTERFACE) {
            if (setup->wLength != 0) return action(UAC_ACT_STALL);
            if (setup->wIndex == state->ac_interface) {
                return setup->wValue == 0 ? action(UAC_ACT_ACK) : action(UAC_ACT_STALL);
            }
            if (setup->wIndex != state->as_interface) return action(UAC_ACT_STALL);
            if (setup->wValue == 0) {
                state->alt_setting = 0;
                state->streaming = false;
                return action(UAC_ACT_STOP);
            }
            if (setup->wValue == 1) {
                state->alt_setting = 1;
                state->streaming = true;
                return action(UAC_ACT_START);
            }
            return action(UAC_ACT_STALL);
        }

        if (setup->bRequest == UAC_REQ_GET_INTERFACE) {
            if (!direction_in || setup->wLength != 1) return action(UAC_ACT_STALL);
            if (setup->wIndex == state->ac_interface) {
                UacActionResult result = action(UAC_ACT_WRITE);
                result.data[0] = 0;
                result.data_len = 1;
                return result;
            }
            if (setup->wIndex != state->as_interface) return action(UAC_ACT_STALL);
            UacActionResult result = action(UAC_ACT_WRITE);
            result.data[0] = state->alt_setting;
            result.data_len = 1;
            return result;
        }

        return action(UAC_ACT_STALL);
    }

    if (type == UAC_TYPE_CLASS) {
        if (control != UAC_EP_CS_SAMPLING_FREQ_CONTROL || channel != 0x01) {
            return action(UAC_ACT_STALL);
        }
        if (recipient == UAC_RECIPIENT_ENDPOINT) {
            if ((setup->wIndex & 0xFF) != state->ep_address) return action(UAC_ACT_STALL);
        } else if (recipient == UAC_RECIPIENT_INTERFACE) {
            if (setup->wIndex != state->as_interface) return action(UAC_ACT_STALL);
        } else {
            return action(UAC_ACT_STALL);
        }

        if (setup->bRequest == UAC_REQ_SET_CUR) {
            if (direction_in || setup->wLength != 3) return action(UAC_ACT_STALL);
            if (!payload || payload_len != 3) return action(UAC_ACT_STALL);
            uint32_t rate = get24(payload, 0);
            if (rate != UAC_SAMPLE_RATE) return action(UAC_ACT_STALL);
            state->sample_rate = rate;
            return action(UAC_ACT_ACK);
        }

        if (setup->bRequest == UAC_REQ_GET_CUR || setup->bRequest == UAC_REQ_GET_MIN ||
            setup->bRequest == UAC_REQ_GET_MAX || setup->bRequest == UAC_REQ_GET_RES) {
            if (!direction_in || setup->wLength != 3) return action(UAC_ACT_STALL);
            return write_rate(UAC_SAMPLE_RATE);
        }

        if (setup->bRequest == UAC_REQ_GET_LEN) {
            if (!direction_in || setup->wLength != 2) return action(UAC_ACT_STALL);
            UacActionResult result = action(UAC_ACT_WRITE);
            result.data[0] = 3;
            result.data[1] = 0;
            result.data_len = 2;
            return result;
        }

        return action(UAC_ACT_STALL);
    }

    return action(UAC_ACT_STALL);
}

size_t UacBuildAcConfiguration(uint8_t ac_interface, uint8_t as_interface,
                               uint8_t *out, size_t cap)
{
    if (!out) return 0;
    UacBuf b = { out, cap, 0, true };

    // Interface Association: AC + AS form one audio function.
    put8(&b, 8);
    put8(&b, USB_DT_INTERFACE_ASSOCIATION);
    put8(&b, ac_interface);
    put8(&b, 2);
    put8(&b, USB_CLASS_AUDIO);
    put8(&b, UAC_SC_AUDIOCONTROL);
    put8(&b, UAC_PC_PROTOCOL_UNDEFINED);
    put8(&b, 0);

    // AudioControl interface.
    put8(&b, USB_DT_INTERFACE_SIZE);
    put8(&b, USB_DT_INTERFACE);
    put8(&b, ac_interface);
    put8(&b, 0);
    put8(&b, 0);
    put8(&b, USB_CLASS_AUDIO);
    put8(&b, UAC_SC_AUDIOCONTROL);
    put8(&b, UAC_PC_PROTOCOL_UNDEFINED);
    put8(&b, 0);

    // Class-specific AC header.  wTotalLength covers only the three
    // class-specific descriptors that follow it.
    put8(&b, 9);
    put8(&b, UAC_CS_INTERFACE);
    put8(&b, UAC_AC_HEADER);
    put16(&b, 0x0100);
    put16(&b, UAC_AC_CLASS_SPECIFIC_SIZE);
    put8(&b, 1);
    put8(&b, as_interface);

    // Input Terminal (microphone) -> Output Terminal (USB streaming).
    put8(&b, 12);
    put8(&b, UAC_CS_INTERFACE);
    put8(&b, UAC_AC_INPUT_TERMINAL);
    put8(&b, UAC_ENTITY_INPUT_TERMINAL);
    put16(&b, UAC_ITT_MICROPHONE);
    put8(&b, 0);
    put8(&b, UAC_CHANNELS);
    put16(&b, UAC_CHANNEL_CONFIG_STEREO);
    put8(&b, 0);
    put8(&b, 0);

    put8(&b, 9);
    put8(&b, UAC_CS_INTERFACE);
    put8(&b, UAC_AC_OUTPUT_TERMINAL);
    put8(&b, UAC_ENTITY_OUTPUT_TERMINAL);
    put16(&b, UAC_TT_USB_STREAMING);
    put8(&b, 0);
    put8(&b, UAC_ENTITY_INPUT_TERMINAL);
    put8(&b, 0);

    return finish(&b);
}

size_t UacBuildAsConfiguration(uint8_t as_interface, uint8_t ep_address,
                               bool superspeed, uint8_t *out, size_t cap)
{
    if (!out || !(ep_address & USB_ENDPOINT_IN)) return 0;
    UacBuf b = { out, cap, 0, true };

    // Alt 0: zero bandwidth, no endpoint.
    put8(&b, USB_DT_INTERFACE_SIZE);
    put8(&b, USB_DT_INTERFACE);
    put8(&b, as_interface);
    put8(&b, 0);
    put8(&b, 0);
    put8(&b, USB_CLASS_AUDIO);
    put8(&b, UAC_SC_AUDIOSTREAMING);
    put8(&b, UAC_PC_PROTOCOL_UNDEFINED);
    put8(&b, 0);

    // Alt 1: one isochronous IN endpoint.
    put8(&b, USB_DT_INTERFACE_SIZE);
    put8(&b, USB_DT_INTERFACE);
    put8(&b, as_interface);
    put8(&b, 1);
    put8(&b, 1);
    put8(&b, USB_CLASS_AUDIO);
    put8(&b, UAC_SC_AUDIOSTREAMING);
    put8(&b, UAC_PC_PROTOCOL_UNDEFINED);
    put8(&b, 0);

    put8(&b, 7);
    put8(&b, UAC_CS_INTERFACE);
    put8(&b, UAC_AS_GENERAL);
    put8(&b, UAC_ENTITY_OUTPUT_TERMINAL);
    put8(&b, 1);
    put16(&b, UAC_FORMAT_TYPE_I_PCM);

    // Type I, 2ch, 16-bit, one discrete 48 kHz rate.
    put8(&b, UAC_AS_FORMAT_SIZE);
    put8(&b, UAC_CS_INTERFACE);
    put8(&b, UAC_AS_FORMAT_TYPE);
    put8(&b, 1);
    put8(&b, UAC_CHANNELS);
    put8(&b, UAC_SUBFRAME_SIZE);
    put8(&b, UAC_BIT_DEPTH);
    put8(&b, 1);
    put8(&b, (uint8_t)(UAC_SAMPLE_RATE & 0xFF));
    put8(&b, (uint8_t)((UAC_SAMPLE_RATE >> 8) & 0xFF));
    put8(&b, (uint8_t)((UAC_SAMPLE_RATE >> 16) & 0xFF));

    // 192 bytes per 1 ms frame, asynchronous, data endpoint.
    put8(&b, USB_DT_ENDPOINT_SIZE);
    put8(&b, USB_DT_ENDPOINT);
    put8(&b, ep_address);
    put8(&b, (uint8_t)(USB_TRANSFER_TYPE_ISOCHRONOUS | UAC_ISO_SYNC_TYPE_ASYNC | UAC_ISO_USAGE_DATA));
    put16(&b, UAC_ISO_PACKET_SIZE);
    put8(&b, 4);

    put8(&b, 7);
    put8(&b, UAC_CS_ENDPOINT);
    put8(&b, UAC_EP_GENERAL);
    put8(&b, 0);
    put8(&b, 0);
    put16(&b, 0);

    if (superspeed) {
        put8(&b, 6);
        put8(&b, USB_DT_SS_ENDPOINT_COMPANION);
        put8(&b, 0);
        put8(&b, 0);
        put16(&b, UAC_ISO_PACKET_SIZE);
    }

    return finish(&b);
}

bool UacLintConfiguration(const uint8_t *ac, size_t ac_len,
                          const uint8_t *as, size_t as_len,
                          char *err, size_t err_cap)
{
    if (!ac || !as) return fail(err, err_cap, "null descriptor");
    if (ac_len != UAC_AC_CONFIGURATION_SIZE) return fail(err, err_cap, "AC length");
    if (as_len != UAC_AS_HS_CONFIGURATION_SIZE && as_len != UAC_AS_SS_CONFIGURATION_SIZE) {
        return fail(err, err_cap, "AS length");
    }

    // Interface association descriptor.
    if (ac[0] != 8 || ac[1] != USB_DT_INTERFACE_ASSOCIATION) return fail(err, err_cap, "IAD header");
    if (ac[2] != ac[10]) return fail(err, err_cap, "IAD first interface");
    if (ac[3] != 2) return fail(err, err_cap, "IAD count");
    if (ac[4] != USB_CLASS_AUDIO || ac[5] != UAC_SC_AUDIOCONTROL || ac[6] != 0) {
        return fail(err, err_cap, "IAD class");
    }

    // AudioControl interface.
    if (ac[8] != USB_DT_INTERFACE_SIZE || ac[9] != USB_DT_INTERFACE) return fail(err, err_cap, "AC interface header");
    if (ac[11] != 0 || ac[12] != 0) return fail(err, err_cap, "AC alt/endpoints");
    if (ac[13] != USB_CLASS_AUDIO || ac[14] != UAC_SC_AUDIOCONTROL || ac[15] != 0) {
        return fail(err, err_cap, "AC interface class");
    }

    // AC header and its relationship with the AS interface number.
    if (ac[17] != 9 || ac[18] != UAC_CS_INTERFACE || ac[19] != UAC_AC_HEADER) return fail(err, err_cap, "AC header");
    if (get16(ac, 20) != 0x0100) return fail(err, err_cap, "bcdADC");
    if (get16(ac, 22) != UAC_AC_CLASS_SPECIFIC_SIZE) return fail(err, err_cap, "AC wTotalLength");
    if (ac[24] != 1) return fail(err, err_cap, "AC collection");
    if (ac[25] != as[2] || ac[25] != as[11]) return fail(err, err_cap, "AC baInterfaceNr1");
    if ((int)ac[10] + 1 != (int)as[2]) return fail(err, err_cap, "AC/AS not contiguous");

    // Input terminal.
    if (ac[26] != 12 || ac[27] != UAC_CS_INTERFACE || ac[28] != UAC_AC_INPUT_TERMINAL) return fail(err, err_cap, "IT header");
    if (ac[29] != UAC_ENTITY_INPUT_TERMINAL) return fail(err, err_cap, "IT id");
    if (get16(ac, 30) != UAC_ITT_MICROPHONE) return fail(err, err_cap, "IT type");
    if (ac[33] != UAC_CHANNELS || get16(ac, 34) != UAC_CHANNEL_CONFIG_STEREO) return fail(err, err_cap, "IT channels");

    // Output terminal.
    if (ac[38] != 9 || ac[39] != UAC_CS_INTERFACE || ac[40] != UAC_AC_OUTPUT_TERMINAL) return fail(err, err_cap, "OT header");
    if (ac[41] != UAC_ENTITY_OUTPUT_TERMINAL) return fail(err, err_cap, "OT id");
    if (get16(ac, 42) != UAC_TT_USB_STREAMING) return fail(err, err_cap, "OT type");
    if (ac[45] != UAC_ENTITY_INPUT_TERMINAL) return fail(err, err_cap, "OT source");

    // AS alt 0 and alt 1.
    if (as[0] != USB_DT_INTERFACE_SIZE || as[1] != USB_DT_INTERFACE || as[3] != 0) return fail(err, err_cap, "AS alt0 header");
    if (as[4] != 0) return fail(err, err_cap, "AS alt0 endpoints");
    if (as[5] != USB_CLASS_AUDIO || as[6] != UAC_SC_AUDIOSTREAMING) return fail(err, err_cap, "AS alt0 class");
    if (as[9] != USB_DT_INTERFACE_SIZE || as[10] != USB_DT_INTERFACE || as[12] != 1) return fail(err, err_cap, "AS alt1 header");
    if (as[13] != 1) return fail(err, err_cap, "AS alt1 endpoints");
    if (as[14] != USB_CLASS_AUDIO || as[15] != UAC_SC_AUDIOSTREAMING) return fail(err, err_cap, "AS alt1 class");
    if (as[2] != as[11]) return fail(err, err_cap, "AS interface number");

    // AS general and format.
    if (as[18] != 7 || as[19] != UAC_CS_INTERFACE || as[20] != UAC_AS_GENERAL) return fail(err, err_cap, "AS general");
    if (as[21] != UAC_ENTITY_OUTPUT_TERMINAL) return fail(err, err_cap, "AS terminal link");
    if (get16(as, 23) != UAC_FORMAT_TYPE_I_PCM) return fail(err, err_cap, "AS format tag");
    if (as[25] != UAC_AS_FORMAT_SIZE || as[26] != UAC_CS_INTERFACE || as[27] != UAC_AS_FORMAT_TYPE) return fail(err, err_cap, "format header");
    if (as[28] != 1 || as[29] != UAC_CHANNELS || as[30] != UAC_SUBFRAME_SIZE || as[31] != UAC_BIT_DEPTH) {
        return fail(err, err_cap, "format fields");
    }
    if (as[32] != 1 || get24(as, 33) != UAC_SAMPLE_RATE) return fail(err, err_cap, "format rate");

    // Isochronous endpoint and its class-specific companion.
    if (as[36] != USB_DT_ENDPOINT_SIZE || as[37] != USB_DT_ENDPOINT) return fail(err, err_cap, "endpoint header");
    if (!(as[38] & USB_ENDPOINT_IN) || as[38] == USB_ENDPOINT_IN) return fail(err, err_cap, "endpoint address");
    if (as[39] != (USB_TRANSFER_TYPE_ISOCHRONOUS | UAC_ISO_SYNC_TYPE_ASYNC | UAC_ISO_USAGE_DATA)) {
        return fail(err, err_cap, "endpoint attributes");
    }
    if (get16(as, 40) != UAC_ISO_PACKET_SIZE || as[42] != 4) return fail(err, err_cap, "endpoint rate");
    if (as[43] != 7 || as[44] != UAC_CS_ENDPOINT || as[45] != UAC_EP_GENERAL) return fail(err, err_cap, "class endpoint");
    if (as[46] != 0 || get16(as, 47) != 0) return fail(err, err_cap, "class endpoint fields");

    if (as_len == UAC_AS_SS_CONFIGURATION_SIZE) {
        if (as[50] != 6 || as[51] != USB_DT_SS_ENDPOINT_COMPANION) return fail(err, err_cap, "SS companion header");
        if (as[52] != 0 || as[53] != 0 || get16(as, 54) != UAC_ISO_PACKET_SIZE) {
            return fail(err, err_cap, "SS companion fields");
        }
    }

    if (err && err_cap) err[0] = '\0';
    return true;
}
