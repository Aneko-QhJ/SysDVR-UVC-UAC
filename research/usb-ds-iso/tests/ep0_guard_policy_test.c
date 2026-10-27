#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "research/usb-ds-iso/device/ep0_buffer_guard.h"
#include "research/usb-ds-iso/device/ep0_cleanup_gate.h"
int main(int argc,char **argv) {
    assert(argc==2);const char *name=argv[1];
    Ep0TraceOwner o={0};Ep0BufferSpan spans[16]={0};uint8_t b[16]={1},s[16]={2};
    assert(ep0_owner_init(&o,11,1000,0,b,s));assert(ep0_owner_enter(&o,11));
    unsigned reason=0;
    if(!strcmp(name,"range")) {
        assert(!ep0_bg_range(0,0));assert(!ep0_bg_range(UINTPTR_MAX,1));
        assert(ep0_bg_range(UINTPTR_MAX,0));
        assert(ep0_bg_allow(&o,spans,UINTPTR_MAX,1,1)==EP0_BG_RANGE);
        assert(ep0_bg_allow(&o,spans,0x1000,4097,1)==EP0_BG_RANGE);
    } else if(!strcmp(name,"overlap")) {
        assert(ep0_bg_overlap(0x1000,32,0x1010,64));
        assert(ep0_bg_overlap(0x1010,64,0x1000,32));
        assert(!ep0_bg_overlap(0x1000,32,0x1020,32));
        assert(ep0_bg_overlap(0x101f,0,0x1000,32));
        assert(!ep0_bg_overlap(0x1020,0,0x1000,32));
        assert(ep0_bg_overlap(0x1000,0,0x1000,0));
        assert(!ep0_bg_overlap(0x1001,0,0x1000,0));
    } else if(!strcmp(name,"missing")) {
        assert(ep0_owner_post(&o,11,4,0,true,0));
        reason=ep0_bg_allow(&o,spans,0x2000,1,1);assert(reason==EP0_BG_UNTRACKED);
    } else if(!strcmp(name,"active")) {
        assert(ep0_owner_post(&o,11,4,0,true,0));spans[0]=(Ep0BufferSpan){0x1000,32,0,4,1};
        reason=ep0_bg_allow(&o,spans,0x1010,1,1);assert(reason==EP0_BG_OVERLAP);
        assert(ep0_bg_allow(&o,spans,0x2000,1,1)==0);
        spans[0].id=1;assert(ep0_bg_allow(&o,spans,0x2000,1,1)==EP0_BG_UNTRACKED);
    } else if(!strcmp(name,"zero")) {
        assert(ep0_owner_post(&o,11,5,0,true,123));spans[0]=(Ep0BufferSpan){0x1000,0,123,5,1};
        assert(ep0_bg_allow(&o,spans,0x1000,168,2)==EP0_BG_OVERLAP);
        assert(ep0_bg_allow(&o,spans,0x1000,0,1)==EP0_BG_OVERLAP);
        assert(ep0_bg_allow(&o,spans,0x1001,1,1)==0);
    } else if(!strcmp(name,"terminal")) {
        assert(ep0_owner_post(&o,11,4,0,true,0));spans[0]=(Ep0BufferSpan){0x1000,32,0,4,1};
        Ep0OwnerReport r={0,4};assert(ep0_owner_reports(&o,11,4,0,&r,1));
        assert(ep0_bg_allow(&o,spans,0x1000,32,2)==0);
    } else if(!strcmp(name,"capacity")) {
        for(unsigned i=0;i<15;i++) { assert(ep0_owner_post(&o,11,4,0,true,i));o.urbs[i].active=0; }
        assert(ep0_bg_allow(&o,spans,0x1000,32,2)==EP0_BG_CAPACITY);
        assert(ep0_bg_allow(&o,spans,0x1000,0,1)==0);
        o.fault=1;assert(ep0_bg_allow(&o,spans,0x1000,0,1)==EP0_BG_FAULT);
    } else if(!strcmp(name,"writer")) {
        assert(ep0_owner_leave(&o,11));assert(ep0_bg_allow(&o,spans,0x1000,0,1)==EP0_BG_OWNER);
    } else {
        assert(!strcmp(name,"cleanup"));Ep0CleanupGate g={0};
        assert(!ep0_cleanup_claim(&g));assert(!ep0_cleanup_authorize(&g));
        assert(ep0_cleanup_begin(&g));assert(!ep0_cleanup_begin(&g));
        assert(!ep0_cleanup_claim(&g));assert(ep0_cleanup_authorize(&g));
        assert(!ep0_cleanup_authorize(&g));assert(ep0_cleanup_claim(&g));
        assert(!ep0_cleanup_claim(&g));assert(!ep0_cleanup_done(&g));
        assert(ep0_cleanup_complete(&g));assert(ep0_cleanup_done(&g));
        assert(!ep0_cleanup_complete(&g));assert(!ep0_cleanup_begin(&g));
    }
    printf("{\"case\":\"%s\",\"passed\":true,\"reason\":%u,\"hardware_verified\":false}\n",name,reason);
    return 0;
}
