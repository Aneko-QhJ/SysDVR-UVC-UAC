/* Exercise the actual receiver callback: buffer contents alone cannot pass. */
#define main iso_probe_cli_main
#ifndef ISO_RECEIVER_SOURCE
#define ISO_RECEIVER_SOURCE "../host/iso-probe.c"
#endif
#include ISO_RECEIVER_SOURCE
#undef main
#include <assert.h>

int main(int argc, char **argv) {
    assert(argc == 2);
    logpath = argv[1];
    logfile = fopen(logpath, "wx");
    assert(logfile);
    struct libusb_transfer *t = libusb_alloc_transfer(1);
    assert(t);
    unsigned char data[ISO_PROBE_PACKET_SIZE];
    libusb_fill_iso_transfer(t, NULL, 0x83, data, sizeof(data), 1, received, NULL, 1000);
    libusb_set_iso_packet_lengths(t, sizeof(data));
    for (sequence = 1; sequence <= 3; ++sequence) {
        for (unsigned j = 0; j < sizeof(data); ++j) data[j] = isoProbeByte(sequence, j);
        t->status = LIBUSB_TRANSFER_ERROR;
        t->iso_packet_desc[0].actual_length = sequence == 1 ? 0 : sizeof(data);
        t->iso_packet_desc[0].status = sequence == 3 ? LIBUSB_TRANSFER_ERROR : LIBUSB_TRANSFER_COMPLETED;
        done = false;
        received(t);
        assert(done && payload_ok == (sequence == 2));
        char path[4096];
        snprintf(path, sizeof(path), "%s.seq%u.buffer.bin", logpath, sequence);
        FILE *raw = fopen(path, "rb");
        assert(raw);
        unsigned char saved[ISO_PROBE_PACKET_SIZE];
        assert(fread(saved, 1, sizeof(saved), raw) == sizeof(saved));
        assert(fgetc(raw) == EOF && memcmp(saved, data, sizeof(data)) == 0);
        fclose(raw);
    }
    fclose(logfile);
    libusb_free_transfer(t);
    puts("Receiver: zero/error packet is rejected; native packet evidence and raw buffers preserved");
    return 0;
}
