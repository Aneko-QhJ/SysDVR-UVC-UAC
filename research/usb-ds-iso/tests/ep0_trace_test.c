#include <assert.h>
#include <stdio.h>
#include "research/usb-ds-iso/device/ep0_trace.h"
static const uint8_t boot[16]={1},session[16]={2};
static Ep0TraceRecord record(uint64_t tick) {
    return (Ep0TraceRecord){.begin=tick,.end=tick,.stage=EP0_T_EVENT,.interface_index=2,.request_id=(uint32_t)tick+1};
}
int main(int argc,char **argv) {
    assert(argc==2);
    Ep0Trace t={0};uint8_t bytes[EP0_TRACE_EXPORT_MAX];memset(bytes,0xa5,sizeof(bytes));
    assert(!ep0_trace_init(&t,0,0,boot,session));
    uint8_t zero[16]={0};assert(!ep0_trace_init(&t,1,0,zero,session));
    assert(ep0_trace_init(&t,1000000000,0,boot,session));
    assert(!ep0_trace_init(&t,1,0,boot,session));
    assert(!ep0_trace_export(&t,bytes,sizeof(bytes)) && bytes[0]==0xa5);
    Ep0TraceRecord r=record(10);assert(ep0_trace_append(&t,&r));
    r=record(9);assert(!ep0_trace_append(&t,&r) && t.invalid==1 && t.count==1);
    r=record(11);r.flags=EP0_TRACE_ARG0_VALID;r.arg0=7;assert(ep0_trace_append(&t,&r));
    r=record(12);r.stage=EP0_T_ACK;r.begin=0;assert(ep0_trace_append(&t,&r)); /* nested span */
    r=record(13);r.flags=EP0_TRACE_SETUP_VALID;assert(!ep0_trace_append(&t,&r));
    r=record(13);r.interface_index=4;assert(!ep0_trace_append(&t,&r));
    r=record(13);r.arg0=1;assert(!ep0_trace_append(&t,&r));
    r=record(13);r.stage=EP0_T_SETUP;assert(!ep0_trace_append(&t,&r));
    assert(!ep0_trace_freeze(&t,11,EP0_TRACE_FINISHED));
    assert(!ep0_trace_freeze(&t,12,99));
    assert(ep0_trace_freeze(&t,12,EP0_TRACE_STOPPED));
    Ep0Trace frozen=t;r=record(13);assert(!ep0_trace_append(&t,&r));
    assert(!ep0_trace_poll(&t,2,1));
    assert(!ep0_trace_freeze(&t,13,EP0_TRACE_FINISHED));assert(!memcmp(&frozen,&t,sizeof(t)));
    assert(!ep0_trace_export(&t,bytes,1) && bytes[0]==0xa5);
    size_t n=ep0_trace_export(&t,bytes,sizeof(bytes));assert(n==128+3*48);
    uint8_t again[EP0_TRACE_EXPORT_MAX];assert(ep0_trace_export(&t,again,sizeof(again))==n);
    assert(!memcmp(bytes,again,n));assert(ep0_trace_crc32((const uint8_t *)"123456789",9)==0xcbf43926);

    Ep0Trace full={0};assert(ep0_trace_init(&full,1000000000,0,boot,session));
    for(unsigned i=0;i<EP0_TRACE_CAPACITY;i++) {
        assert(ep0_trace_poll(&full,2,0));r=record(i);assert(ep0_trace_append(&full,&r));
    }
    full.polls[2]=UINT16_MAX;assert(ep0_trace_poll(&full,2,0xdeadbeef));
    assert(full.polls[2]==UINT16_MAX && full.last_poll_result[2]==0xdeadbeef);
    Ep0TraceRecord saved[EP0_TRACE_CAPACITY];memcpy(saved,full.records,sizeof(saved));
    r=record(200);assert(!ep0_trace_append(&full,&r) && full.dropped==1);
    assert(!memcmp(saved,full.records,sizeof(saved)) && full.count==128);
    assert(!ep0_trace_freeze(&full,128,EP0_TRACE_FINISHED)); /* dropped event also advances time */
    full.dropped=UINT32_MAX;r=record(201);assert(!ep0_trace_append(&full,&r) && full.dropped==UINT32_MAX);
    full.invalid=UINT32_MAX;r=record(199);assert(!ep0_trace_append(&full,&r) && full.invalid==UINT32_MAX);
    assert(ep0_trace_freeze(&full,201,EP0_TRACE_FINISHED));
    n=ep0_trace_export(&full,bytes,sizeof(bytes));assert(n==EP0_TRACE_EXPORT_MAX);
    FILE *f=fopen(argv[1],"wb");assert(f);assert(fwrite(bytes,1,n,f)==n);assert(fclose(f)==0);
    printf("{\"capacity\":128,\"record_bytes\":48,\"max_export_bytes\":%u,\"storage_bytes\":%zu,\"cases\":9,"
           "\"hardware_observation\":false}\n",EP0_TRACE_EXPORT_MAX,sizeof(Ep0Trace));
    return 0;
}
