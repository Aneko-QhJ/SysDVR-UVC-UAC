#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

// UAC 1.0 standard-layer logic, independent of libnx.
//
// The sysmodule calls this from source/uvc/uvc_device.c.  Host tests compile
// uac_standard.c with -DUAC_STANDALONE, so descriptor layout and the control
// state machine are verified without a Switch or a USB device.

#define UAC_AC_CONFIGURATION_SIZE 47
#define UAC_AS_HS_CONFIGURATION_SIZE 50
#define UAC_AS_SS_CONFIGURATION_SIZE 56

typedef struct {
    uint8_t bmRequestType;
    uint8_t bRequest;
    uint16_t wValue;
    uint16_t wIndex;
    uint16_t wLength;
} UacSetupPacket;

typedef enum {
    UAC_ACT_STALL = 0,
    UAC_ACT_ACK,
    UAC_ACT_WRITE,
    UAC_ACT_START,
    UAC_ACT_STOP,
} UacAction;

typedef struct {
    UacAction action;
    uint8_t data[8];
    uint8_t data_len;
} UacActionResult;

typedef struct {
    uint8_t ac_interface;
    uint8_t as_interface;
    uint8_t ep_address;
    uint8_t alt_setting;
    bool streaming;
    uint32_t sample_rate;
} UacStandardState;

void UacStandardInit(UacStandardState *state, uint8_t ac_interface,
                     uint8_t as_interface, uint8_t ep_address);

// `payload` is the OUT data stage for class SET requests; pass NULL when the
// request has no data stage.  UAC_ACT_START/STOP also require an ACK.
UacActionResult UacStandardHandle(UacStandardState *state,
                                  const UacSetupPacket *setup,
                                  const uint8_t *payload, size_t payload_len);

// Build the bytes appended to the AC and AS interfaces.  Return 0 when `cap`
// is too small.  `ep_address` must be a full IN endpoint address (0x80 bit set).
size_t UacBuildAcConfiguration(uint8_t ac_interface, uint8_t as_interface,
                               uint8_t *out, size_t cap);
size_t UacBuildAsConfiguration(uint8_t as_interface, uint8_t ep_address,
                               bool superspeed, uint8_t *out, size_t cap);

// Parse the two configuration blobs and check UAC1 field relationships.
// Returns false and fills `err` on the first mismatch.
bool UacLintConfiguration(const uint8_t *ac, size_t ac_len,
                          const uint8_t *as, size_t as_len,
                          char *err, size_t err_cap);
