#define main iso_probe_cli_main
#include ISO_RECEIVER_SOURCE
#undef main
#include <assert.h>

static void native_batch(FILE *file, struct libusb_transfer *t, unsigned scenario) {
    fprintf(file,"warning and unrelated evidence\n");
    for (unsigned i=0;i<960;++i) {
        if (scenario==7 && i==959) continue;
        if (scenario==8 && i==959) { fputs("{\"kind\":\"darwin_iso_native\",bad}\n",file);continue; }
        unsigned actual=t->iso_packet_desc[i].actual_length;
        unsigned status=actual?0:0xe00002e7;
        if (scenario==2 && i==570) status=0xe00002ed;
        if (scenario==5 && i==570) actual=0;
        fprintf(file,"{\"kind\":\"darwin_iso_native\",\"index\":%u,\"overall\":%u,\"status\":%u,\"requested\":%u,\"actual\":%u}\n",
                scenario==6 && i==958?957:i,scenario==3?0xe000400e:0,status,scenario==4 && i==570?256:192,actual);
    }
    fflush(file);
}
int main(int argc,char **argv) {
    assert(argc==3); logpath=argv[1]; logfile=fopen(logpath,"wx");assert(logfile);
    assert(setenv("ISO_NATIVE_LOG_PATH",argv[2],1)==0);
    FILE *native=fopen(argv[2],"wx");assert(native);
    struct libusb_transfer *t=libusb_alloc_transfer(960);assert(t);
    unsigned char *buffer=calloc(960,192);assert(buffer);burst_mode=true;
    libusb_fill_iso_transfer(t,NULL,0x83,buffer,960*192,960,received,NULL,1000);
    libusb_set_iso_packet_lengths(t,192);
    for (unsigned scenario=1;scenario<=9;++scenario) {
        sequence=(uint16_t)scenario;memset(buffer,0,960*192);t->status=LIBUSB_TRANSFER_COMPLETED;
        for(unsigned i=0;i<960;++i){t->iso_packet_desc[i].actual_length=0;t->iso_packet_desc[i].status=LIBUSB_TRANSFER_COMPLETED;}
        for(unsigned i=0;i<16;++i) {
            unsigned slot=567+i;t->iso_packet_desc[slot].actual_length=192;
            for(unsigned j=0;j<192;++j)buffer[slot*192+j]=isoProbeByte((uint16_t)(sequence+i),j);
        }
        native_batch(native,t,scenario);done=false;received(t);
        assert(done && payload_ok==(scenario==1 || scenario==9));
    }
    sequence=10;assert(unsetenv("ISO_NATIVE_LOG_PATH")==0);received(t);assert(!payload_ok);
    sequence=11;assert(setenv("ISO_NATIVE_LOG_PATH",argv[2],1)==0);assert(ftruncate(fileno(native),0)==0);
    received(t);assert(!payload_ok);
    for(unsigned i=1;i<=11;++i){char path[4096];snprintf(path,sizeof(path),"%s.seq%u.buffer.bin",logpath,i);FILE *raw=fopen(path,"rb");assert(raw);fseek(raw,0,SEEK_END);assert(ftell(raw)==960*192);fclose(raw);}
    fclose(native);fclose(logfile);libusb_free_transfer(t);free(buffer);
    puts("11 real callback cases passed: independent native errors and evidence loss close gate; raw preserved");
}
