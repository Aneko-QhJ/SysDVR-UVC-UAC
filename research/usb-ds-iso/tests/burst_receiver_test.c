#define main iso_probe_cli_main
#ifndef ISO_RECEIVER_SOURCE
#define ISO_RECEIVER_SOURCE "../host/iso-probe.c"
#endif
#include ISO_RECEIVER_SOURCE
#undef main
#include <assert.h>
int main(int argc, char **argv) {
    assert(argc == 2);
    logfile = fopen(argv[1], "wx"); assert(logfile);
    logpath = argv[1]; burst_mode = true;
    struct libusb_transfer *t = libusb_alloc_transfer(18); assert(t);
    unsigned char data[18 * ISO_HOST_SLOT_SIZE];
    libusb_fill_iso_transfer(t, NULL, 0x83, data, sizeof(data), 18, received, NULL, 1000);
    libusb_set_iso_packet_lengths(t,ISO_HOST_SLOT_SIZE);
    for (unsigned scenario=0; scenario<8; ++scenario) {
        sequence = (uint16_t)(65530 + scenario); /* include sequence rollover */
        memset(data,0,sizeof(data));
        t->status = LIBUSB_TRANSFER_COMPLETED;
        for (unsigned i=0; i<18; ++i) {
            t->iso_packet_desc[i].actual_length=0;
            t->iso_packet_desc[i].status=LIBUSB_TRANSFER_COMPLETED;
        }
        for (unsigned i=0; i<16; ++i) {
            unsigned slot = i+1;
            if (scenario == 4 && i >= 8) ++slot; /* missing service interval */
            uint16_t seq = (uint16_t)(sequence+i);
            if (scenario == 3 && i==15) seq = sequence; /* duplicate */
            for (unsigned j=0;j<192;++j) data[slot*ISO_HOST_SLOT_SIZE+j]=isoProbeByte(seq,j);
            t->iso_packet_desc[slot].actual_length=192;
        }
        if (scenario==1) t->iso_packet_desc[8].actual_length=0;
        if (scenario==2) t->iso_packet_desc[8].status=LIBUSB_TRANSFER_ERROR;
        if (scenario==5) t->status=LIBUSB_TRANSFER_ERROR;
        if (scenario==6) data[8*ISO_HOST_SLOT_SIZE+30]^=1;
        if (scenario==7) t->iso_packet_desc[8].actual_length=256;
        received(t);
        assert(payload_ok == (scenario==0));
    }
    libusb_free_transfer(t); fclose(logfile);
    puts("Burst receiver: exact ordered 16 packets required; loss/duplicate/gap/error/corruption rejected");
}
