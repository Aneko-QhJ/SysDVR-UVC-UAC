/* Test-only bridge. Types and USB fixtures precede this fragment. */
#include "research/usb-ds-iso/device/ep0_trace.h"
static Ep0Trace trace_storage;
static uint32_t trace_request_counter, trace_request_ids[4];
static void trace_poll(UsbDsInterface *iface,uint32_t result) {
    (void)ep0_trace_poll(&trace_storage,iface->interface_index,result);
}
static void trace_emit(uint16_t stage,UsbDsInterface *iface,uint32_t result,
                       uint32_t arg0,uint32_t arg1,uint8_t flags,const void *setup,
                       uint64_t begin,uint64_t end) {
    unsigned index=iface ? iface->interface_index : 255;
    Ep0TraceRecord r={.begin=begin,.end=end,.result=result,.arg0=arg0,.arg1=arg1,
        .stage=stage,.interface_index=(uint8_t)index,.flags=flags,
        .request_id=iface && index<4 ? trace_request_ids[index] : 0};
    if(setup) { memcpy(r.setup,setup,8);r.flags|=EP0_TRACE_SETUP_VALID; }
    /* Loss is recorded by the bounded core. Observation must not change the
     * original service return value or cause an early return in client code. */
    (void)ep0_trace_append(&trace_storage,&r);
}
static void trace_request(UsbDsInterface *iface) {
    assert(iface->interface_index<4 && trace_request_counter!=UINT32_MAX);
    trace_request_ids[iface->interface_index]=++trace_request_counter;
}
static void trace_id(const char *hex,uint8_t out[16]) {
    assert(strlen(hex)==32);
    for(unsigned i=0;i<16;i++) {
        unsigned value=0;
        for(unsigned j=0;j<2;j++) {
            char c=hex[i*2+j];assert((c>='0' && c<='9') || (c>='a' && c<='f'));
            value=value*16+(unsigned)(c<='9' ? c-'0' : c-'a'+10);
        }
        out[i]=(uint8_t)value;
    }
}
static void trace_probe_begin(const char *boot,const char *session) {
    uint8_t boot_id[16],session_id[16];trace_id(boot,boot_id);trace_id(session,session_id);
    assert(ep0_trace_init(&trace_storage,armGetSystemTickFreq(),svcGetSystemTick(),boot_id,session_id));
}
static void trace_probe_export(const char *path) {
    assert(ep0_trace_freeze(&trace_storage,svcGetSystemTick(),EP0_TRACE_FINISHED));
    static uint8_t bytes[EP0_TRACE_EXPORT_MAX];
    size_t size=ep0_trace_export(&trace_storage,bytes,sizeof(bytes));assert(size);
    /* Only the offline fixture writes files; the recording core has no I/O. */
    FILE *f=fopen(path,"wb");assert(f);assert(fwrite(bytes,1,size,f)==size);assert(fclose(f)==0);
}
