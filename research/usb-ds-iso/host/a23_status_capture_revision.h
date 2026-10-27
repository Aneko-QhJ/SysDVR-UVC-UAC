#pragma once
#include "../../../source/uvc/iso_probe_protocol.h"
#include <string.h>

/* report_count describes the most recent destructive report query. The
 * retained terminal URB and ISO7 fields must still pass every original gate. */
static const char *const A23StatusFailureNames[]={
    "magic","version","sequence","state","post_result","urb_id","report_id",
    "requested","transferred","urb_status","speed","endpoint","report_count","report_result",
    "iso7.magic","iso7.terminal","iso7.bitmap","iso7.actual_sum","iso7.context_valid",
    "iso7.frame_select_mfi","iso7.trb_type","iso7.sia","iso7.frame_id"
};
static inline uint32_t A23StatusAfterFailures(const IsoProbeStatus *s,uint16_t expected)
{
    IsoProbeBurstContextDiagnostics d;memcpy(&d,&s->diagnostics,sizeof(d));
    const int ok[]={s->magic==ISO_PROBE_STATUS_MAGIC,s->version==1,s->sequence==expected,
        s->state==ISO_PROBE_COMPLETE,!s->post_result,s->urb_id!=0,s->urb_id==s->report_id,
        s->requested==3072,s->transferred==3072,s->urb_status==3,s->speed==3,s->endpoint==0x83,
        s->report_count<=1,!s->report_result,d.magic==ISO_PROBE_BURST_INTERVAL_MAGIC,
        d.terminal==1,d.completed_bitmap==65535,d.actual_sum==3072,d.context_valid==1,
        d.frame_select_mfi<16384,((d.first_control>>10)&63)==5,!(d.first_control>>31),
        ((d.first_control>>20)&2047)==(((d.frame_select_mfi>>3)+32)&2047)};
    uint32_t failed=0;for(unsigned i=0;i<sizeof(ok)/sizeof(ok[0]);++i)if(!ok[i])failed|=1u<<i;
    return failed;
}
static inline int A23StatusPreservedExceptReportCount(const IsoProbeStatus *a,const IsoProbeStatus *b)
{
    IsoProbeStatus x,y;memcpy(&x,a,sizeof(x));memcpy(&y,b,sizeof(y));
    if(x.report_count>1 || y.report_count>1)return 0;
    x.report_count=y.report_count=0;return memcmp(&x,&y,sizeof(x))==0;
}
