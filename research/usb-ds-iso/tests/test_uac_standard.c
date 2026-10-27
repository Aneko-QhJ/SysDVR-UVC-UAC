#include "uac_standard.h"

#include <stdio.h>
#include <string.h>

static int failures;

#define CHECK(cond)                                                            \
    do {                                                                       \
        if (!(cond)) {                                                         \
            printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);             \
            failures++;                                                        \
        }                                                                      \
    } while (0)

static UacActionResult call(UacStandardState *state, uint8_t type, uint8_t req,
                            uint16_t value, uint16_t index, uint16_t length,
                            const uint8_t *payload, size_t payload_len)
{
    UacSetupPacket setup = { type, req, value, index, length };
    return UacStandardHandle(state, &setup, payload, payload_len);
}

static void test_descriptors(void)
{
    uint8_t ac[64] = { 0 };
    uint8_t hs[64] = { 0 };
    uint8_t ss[64] = { 0 };
    uint8_t bad[64];
    char err[128];

    size_t ac_len = UacBuildAcConfiguration(3, 4, ac, sizeof(ac));
    size_t hs_len = UacBuildAsConfiguration(4, 0x84, false, hs, sizeof(hs));
    size_t ss_len = UacBuildAsConfiguration(4, 0x84, true, ss, sizeof(ss));

    CHECK(ac_len == UAC_AC_CONFIGURATION_SIZE);
    CHECK(hs_len == UAC_AS_HS_CONFIGURATION_SIZE);
    CHECK(ss_len == UAC_AS_SS_CONFIGURATION_SIZE);
    CHECK(ac[2] == 3 && ac[10] == 3 && ac[25] == 4);
    CHECK(ac[13] == 1 && ac[14] == 1);
    CHECK(hs[2] == 4 && hs[11] == 4 && hs[38] == 0x84);
    CHECK(hs[40] == 192 && hs[41] == 0 && hs[42] == 4);
    CHECK(ss[51] == 0x30 && ss[54] == 192 && ss[55] == 0);
    CHECK(UacLintConfiguration(ac, ac_len, hs, hs_len, err, sizeof(err)));
    CHECK(err[0] == '\0');
    CHECK(UacLintConfiguration(ac, ac_len, ss, ss_len, err, sizeof(err)));

    CHECK(UacBuildAcConfiguration(3, 4, ac, 16) == 0);
    CHECK(UacBuildAsConfiguration(4, 0x04, false, hs, sizeof(hs)) == 0);

    memcpy(bad, ac, ac_len);
    bad[25] = 3;
    CHECK(!UacLintConfiguration(bad, ac_len, hs, hs_len, err, sizeof(err)));
    CHECK(err[0] != '\0');

    {
        uint8_t ac5[64];
        uint8_t as5[64];
        size_t ac5_len = UacBuildAcConfiguration(3, 5, ac5, sizeof(ac5));
        size_t as5_len = UacBuildAsConfiguration(5, 0x84, false, as5, sizeof(as5));
        CHECK(!UacLintConfiguration(ac5, ac5_len, as5, as5_len, err, sizeof(err)));
    }

    memcpy(bad, ac, ac_len);
    bad[22] = 29;
    CHECK(!UacLintConfiguration(bad, ac_len, hs, hs_len, err, sizeof(err)));

    memcpy(bad, ac, ac_len);
    bad[29] = 12;
    CHECK(!UacLintConfiguration(bad, ac_len, hs, hs_len, err, sizeof(err)));

    memcpy(bad, hs, hs_len);
    bad[40] = 191;
    CHECK(!UacLintConfiguration(ac, ac_len, bad, hs_len, err, sizeof(err)));

    memcpy(bad, hs, hs_len);
    bad[38] = 0x04;
    CHECK(!UacLintConfiguration(ac, ac_len, bad, hs_len, err, sizeof(err)));

    memcpy(bad, hs, hs_len);
    bad[39] = 0x00;
    CHECK(!UacLintConfiguration(ac, ac_len, bad, hs_len, err, sizeof(err)));

    memcpy(bad, hs, hs_len);
    bad[42] = 1;
    CHECK(!UacLintConfiguration(ac, ac_len, bad, hs_len, err, sizeof(err)));

    memcpy(bad, hs, hs_len);
    bad[12] = 0;
    CHECK(!UacLintConfiguration(ac, ac_len, bad, hs_len, err, sizeof(err)));

    memcpy(bad, ss, ss_len);
    bad[50] = 5;
    CHECK(!UacLintConfiguration(ac, ac_len, bad, ss_len, err, sizeof(err)));

    CHECK(!UacLintConfiguration(ac, ac_len - 1, hs, hs_len, err, sizeof(err)));
    CHECK(!UacLintConfiguration(NULL, ac_len, hs, hs_len, err, sizeof(err)));
}

static void test_state(void)
{
    UacStandardState state;
    UacStandardInit(&state, 3, 4, 0x84);
    CHECK(state.alt_setting == 0 && !state.streaming);
    CHECK(state.sample_rate == 48000);

    UacActionResult r = call(&state, 0x01, 0x0B, 1, 4, 0, NULL, 0);
    CHECK(r.action == UAC_ACT_START && state.alt_setting == 1 && state.streaming);

    r = call(&state, 0x81, 0x0A, 0, 4, 1, NULL, 0);
    CHECK(r.action == UAC_ACT_WRITE && r.data_len == 1 && r.data[0] == 1);

    r = call(&state, 0x01, 0x0B, 0, 4, 0, NULL, 0);
    CHECK(r.action == UAC_ACT_STOP && state.alt_setting == 0 && !state.streaming);

    CHECK(call(&state, 0x01, 0x0B, 2, 4, 0, NULL, 0).action == UAC_ACT_STALL);
    CHECK(call(&state, 0x01, 0x0B, 1, 5, 0, NULL, 0).action == UAC_ACT_STALL);
    CHECK(call(&state, 0x01, 0x0B, 1, 4, 1, NULL, 0).action == UAC_ACT_STALL);
    CHECK(call(&state, 0x01, 0x0B, 1, 3, 0, NULL, 0).action == UAC_ACT_STALL);
    CHECK(call(&state, 0x01, 0x0B, 0, 3, 0, NULL, 0).action == UAC_ACT_ACK);
    r = call(&state, 0x81, 0x0A, 0, 3, 1, NULL, 0);
    CHECK(r.action == UAC_ACT_WRITE && r.data_len == 1 && r.data[0] == 0);
    CHECK(call(&state, 0x81, 0x0A, 0, 4, 2, NULL, 0).action == UAC_ACT_STALL);

    const uint8_t rate48[3] = { 0x80, 0xBB, 0x00 };
    const uint8_t rate44[3] = { 0x44, 0xAC, 0x00 };

    r = call(&state, 0x22, 0x01, 0x0101, 0x84, 3, rate48, sizeof(rate48));
    CHECK(r.action == UAC_ACT_ACK && state.sample_rate == 48000);

    r = call(&state, 0x22, 0x01, 0x0101, 0x84, 3, rate44, sizeof(rate44));
    CHECK(r.action == UAC_ACT_STALL && state.sample_rate == 48000);

    CHECK(call(&state, 0x22, 0x01, 0x0101, 0x84, 2, rate48, 3).action == UAC_ACT_STALL);
    CHECK(call(&state, 0x22, 0x01, 0x0101, 0x85, 3, rate48, 3).action == UAC_ACT_STALL);
    CHECK(call(&state, 0xA2, 0x01, 0x0101, 0x84, 3, rate48, 3).action == UAC_ACT_STALL);
    CHECK(call(&state, 0x22, 0x01, 0x0101, 0x84, 3, NULL, 0).action == UAC_ACT_STALL);

    r = call(&state, 0xA2, 0x81, 0x0101, 0x84, 3, NULL, 0);
    CHECK(r.action == UAC_ACT_WRITE && r.data_len == 3);
    CHECK(r.data[0] == 0x80 && r.data[1] == 0xBB && r.data[2] == 0x00);

    CHECK(call(&state, 0xA2, 0x82, 0x0101, 0x84, 3, NULL, 0).action == UAC_ACT_WRITE);
    CHECK(call(&state, 0xA2, 0x83, 0x0101, 0x84, 3, NULL, 0).action == UAC_ACT_WRITE);
    CHECK(call(&state, 0xA2, 0x84, 0x0101, 0x84, 3, NULL, 0).action == UAC_ACT_WRITE);

    r = call(&state, 0xA2, 0x85, 0x0101, 0x84, 2, NULL, 0);
    CHECK(r.action == UAC_ACT_WRITE && r.data_len == 2 && r.data[0] == 3 && r.data[1] == 0);

    CHECK(call(&state, 0xA1, 0x81, 0x0101, 4, 3, NULL, 0).action == UAC_ACT_WRITE);
    CHECK(call(&state, 0xA1, 0x81, 0x0101, 3, 3, NULL, 0).action == UAC_ACT_STALL);
    CHECK(call(&state, 0x21, 0x01, 0x0101, 3, 3, rate48, 3).action == UAC_ACT_STALL);
    CHECK(call(&state, 0x21, 0x01, 0x0201, 4, 3, rate48, 3).action == UAC_ACT_STALL);
    CHECK(call(&state, 0x41, 0x01, 0x0101, 4, 3, rate48, 3).action == UAC_ACT_STALL);
}

int main(void)
{
    test_descriptors();
    test_state();
    if (failures) {
        printf("uac_standard: %d failure(s)\n", failures);
        return 1;
    }
    printf("uac_standard: ok\n");
    return 0;
}
