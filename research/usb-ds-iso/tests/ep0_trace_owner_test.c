#include <assert.h>
#include <stdio.h>
#include "research/usb-ds-iso/device/ep0_trace_owner.h"

static Ep0TraceOwner s;
static const uint8_t boot[16]={1},session[16]={2};
static bool is(const char *a,const char *b) { return strcmp(a,b)==0; }
static void post(unsigned channel,uint32_t id) { assert(ep0_owner_post(&s,11,channel,0,true,id)); }
static void report(unsigned channel,uint32_t id,uint32_t status) {
    Ep0OwnerReport r={id,status};assert(ep0_owner_reports(&s,11,channel,0,&r,1));
}
int main(int argc,char **argv) {
    assert(argc==3);const char *c=argv[1];bool expected=false,joined=true;
    assert(!ep0_owner_init(&s,0,1,0,boot,session));
    assert(ep0_owner_init(&s,11,1000000000,0,boot,session));
    assert(!ep0_owner_init(&s,11,1,0,boot,session));
    uint8_t bytes[EP0_TRACE_EXPORT_MAX];memset(bytes,0xa5,sizeof(bytes));
    assert(!ep0_owner_export(&s,22,bytes,sizeof(bytes)) && bytes[0]==0xa5);
    post(8,17);
    if(is(c,"happy") || is(c,"prejoin") || is(c,"failed-join") || is(c,"immutable") ||
       is(c,"wrong-writer") || is(c,"inside-call") || is(c,"trace-overflow")) {
        report(8,17,3);expected=true;
        if(is(c,"prejoin") || is(c,"failed-join")) { joined=false;expected=false; }
        if(is(c,"wrong-writer")) {
            Ep0TraceOwner before=s;
            assert(!ep0_owner_post(&s,99,8,0,true,90));
            assert(!ep0_owner_reports(&s,99,8,0,NULL,0));
            assert(!ep0_owner_enter(&s,99));assert(!memcmp(&before,&s,sizeof(s)));
        }
        if(is(c,"inside-call")) {
            assert(ep0_owner_enter(&s,11));
            assert(!ep0_owner_freeze(&s,11,0,EP0_TRACE_STOPPED));
            assert(!ep0_owner_stop(&s,11));assert(ep0_owner_leave(&s,11));
        }
        if(is(c,"trace-overflow")) {
            for(unsigned i=0;i<EP0_TRACE_CAPACITY+1;i++) {
                assert(ep0_trace_poll(&s.trace,2,0));
                Ep0TraceRecord r={.begin=i,.end=i,.request_id=i+1,.stage=EP0_T_EVENT,.interface_index=2};
                (void)ep0_trace_append(&s.trace,&r);
            }
            assert(s.trace.dropped==1);
        }
    } else if(is(c,"terminal-4") || is(c,"terminal-5")) {
        report(8,17,is(c,"terminal-4") ? 4 : 5);expected=true;
    } else if(is(c,"wait-timeout") || is(c,"cancel-only") || is(c,"disconnect")) {
        /* These are NOT ownership evidence and have no policy operation. */
        assert(ep0_owner_pending(&s)==1);
    } else if(is(c,"wrong-id"))report(8,18,3);
    else if(is(c,"wrong-channel"))report(0,17,3);
    else if(is(c,"state-1") || is(c,"state-2") || is(c,"unknown-status"))
        report(8,17,is(c,"state-1") ? 1 : is(c,"state-2") ? 2 : 99);
    else if(is(c,"failed-report")) {
        Ep0OwnerReport r={17,3};assert(!ep0_owner_reports(&s,11,8,123,&r,1));
    } else if(is(c,"count-9"))assert(!ep0_owner_reports(&s,11,8,0,NULL,9));
    else if(is(c,"duplicate-report")) {
        Ep0OwnerReport r[]={{17,3},{17,1}};
        assert(!ep0_owner_reports(&s,11,8,0,r,2));assert(ep0_owner_pending(&s)==1);
    } else if(is(c,"failed-post") || is(c,"missing-id")) {
        assert(!ep0_owner_post(&s,11,4,is(c,"failed-post") ? 123 : 0,!is(c,"missing-id"),20));
        report(8,17,3); /* Cannot undo the uncertain post. */
    } else if(is(c,"reuse")) {
        report(8,17,3);assert(!ep0_owner_post(&s,11,8,0,true,17));
        report(8,17,3); /* Old terminal must never bless the reused ID. */
    } else if(is(c,"capacity")) {
        report(8,17,3);
        for(unsigned i=1;i<EP0_OWNER_SLOTS;i++) { post(8,17+i);report(8,17+i,3); }
        assert(!ep0_owner_post(&s,11,8,0,true,100));
    } else if(is(c,"same-id-other-channel")) {
        post(4,17);report(8,17,3);assert(ep0_owner_pending(&s)==1);
        report(4,17,4);expected=true;
    } else if(is(c,"zero-id")) {
        report(8,17,3);post(4,0);report(4,0,3);expected=true;
    } else if(is(c,"late-terminal")) {
        assert(ep0_owner_freeze(&s,11,0,EP0_TRACE_STOPPED));
        Ep0Trace frozen=s.trace;report(8,17,2);report(8,17,5);
        assert(!memcmp(&frozen,&s.trace,sizeof(frozen)));expected=true;
    } else if(is(c,"reentrant")) {
        assert(ep0_owner_enter(&s,11));assert(!ep0_owner_enter(&s,11));
        assert(ep0_owner_leave(&s,11));report(8,17,3);
    } else assert(!"Unknown case");

    if(s.trace.lifecycle==1)assert(ep0_owner_freeze(&s,11,s.trace.last_end,EP0_TRACE_STOPPED));
    assert(!ep0_owner_handoff(&s,22,0)); /* Not stopped yet. */
    assert(ep0_owner_stop(&s,11));
    assert(!ep0_owner_handoff(&s,11,0)); /* Writer cannot represent a join. */
    if(is(c,"failed-join"))assert(!ep0_owner_handoff(&s,22,123));
    if(joined)assert(ep0_owner_handoff(&s,22,0));
    Ep0TraceOwner before=s;
    assert(!ep0_owner_post(&s,11,8,0,true,99));
    assert(!ep0_owner_reports(&s,11,8,0,NULL,0));
    assert(!ep0_owner_enter(&s,11));assert(!ep0_owner_freeze(&s,11,1000,EP0_TRACE_FINISHED));
    assert(!memcmp(&before,&s,sizeof(s)));
    assert(!ep0_owner_export(&s,99,bytes,sizeof(bytes)) && bytes[0]==0xa5);
    assert(!ep0_owner_export(&s,22,bytes,1) && bytes[0]==0xa5);
    size_t n=ep0_owner_export(&s,22,bytes,sizeof(bytes));assert((n!=0)==expected);
    if(!n)assert(bytes[0]==0xa5);
    if(n) {
        uint8_t again[EP0_TRACE_EXPORT_MAX];assert(ep0_owner_export(&s,22,again,sizeof(again))==n);
        assert(!memcmp(bytes,again,n));FILE *f=fopen(argv[2],"wb");assert(f);
        assert(fwrite(bytes,1,n,f)==n);assert(fclose(f)==0);
    }
    assert(!memcmp(&before,&s,sizeof(s)));
    printf("{\"case\":\"%s\",\"pending\":%u,\"fault\":%u,\"unmatched\":%u,\"joined\":%s,"
           "\"exported_bytes\":%zu,\"trace_dropped\":%u,\"owner_storage_bytes\":%zu,"
           "\"hardware_verified\":false}\n",c,ep0_owner_pending(&s),s.fault,s.unmatched,
           s.joined ? "true" : "false",n,s.trace.dropped,sizeof(s));
    return 0;
}
