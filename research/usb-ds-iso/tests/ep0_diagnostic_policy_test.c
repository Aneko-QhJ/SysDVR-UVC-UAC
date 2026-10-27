#include <assert.h>
#include <stdio.h>
#define EP0_CANDIDATE_NATIVE
typedef unsigned Result;
typedef struct { unsigned unused; } UsbDsInterface;
typedef struct { unsigned unused; } UsbDsReportData;
#include "research/usb-ds-iso/device/ep0_diagnostic_capture.h"
int main(void) {
    Ep0TraceOwner o={0};Ep0GuardObservation g={0};uint8_t b[16]={1},s[16]={2},recipe[32]={3},out[EP0_DIAGNOSTIC_MAX];
    assert(ep0_owner_init(&o,11,1000,0,b,s));
    memset(out,0xa5,sizeof(out));
    assert(!ep0_diagnostic_capture((void*)1,(void*)1,22,1,0,recipe,out,sizeof(out)));
    assert(!ep0_diagnostic_capture((void*)1,(void*)1,22,0,1,recipe,out,sizeof(out)));
    assert(!ep0_diagnostic_capture(&o,&g,22,0,0,recipe,out,sizeof(out)));
    assert(ep0_owner_post(&o,11,4,0,true,0));
    assert(ep0_owner_freeze(&o,11,10,EP0_TRACE_STOPPED));assert(ep0_owner_stop(&o,11));
    assert(!ep0_diagnostic_capture(&o,&g,22,0,0,recipe,out,sizeof(out)));
    assert(ep0_owner_handoff(&o,22,0));
    Ep0TraceOwner alias_before=o;
    assert(!ep0_diagnostic_capture(&o,&g,22,0,0,recipe,(uint8_t*)&o,sizeof(o)));
    assert(!ep0_diagnostic_capture(&o,&g,22,0,0,recipe,(uint8_t*)&g,sizeof(out)));
    assert(!ep0_diagnostic_capture(&o,&g,22,0,0,recipe,recipe,sizeof(out)));
    assert(!memcmp(&o,&alias_before,sizeof(o)) && !g.denials && !g.last_reason && recipe[0]==3);
    assert(!ep0_diagnostic_capture(&o,&g,11,0,0,recipe,out,sizeof(out)));
    assert(!ep0_diagnostic_capture(&o,&g,22,0,0,recipe,out,271));
    g.denials=1;assert(!ep0_diagnostic_capture(&o,&g,22,0,0,recipe,out,sizeof(out)));g.denials=0;
    o.urbs[0].status=3;assert(!ep0_diagnostic_capture(&o,&g,22,0,0,recipe,out,sizeof(out)));o.urbs[0].status=0;
    for(unsigned i=0;i<sizeof(out);i++)assert(out[i]==0xa5);
    Ep0TraceOwner before=o;
    assert(ep0_diagnostic_capture(&o,&g,22,0,0,recipe,out,sizeof(out))==272);
    assert(!memcmp(&o,&before,sizeof(o)));assert(ep0_owner_pending(&o)==1 && !ep0_owner_export(&o,22,out,sizeof(out)));
    o.urbs[0].status=3;o.urbs[0].active=0;
    memset(out,0xa5,sizeof(out));assert(!ep0_diagnostic_capture(&o,&g,22,0,0,recipe,out,sizeof(out)));
    for(unsigned i=0;i<sizeof(out);i++)assert(out[i]==0xa5);
    printf("{\"passed\":true,\"failed_join_rejected_before_read\":true,\"short_output_untouched\":true,\"output_alias_rejected\":true,\"owner_immutable\":true}\n");
}
