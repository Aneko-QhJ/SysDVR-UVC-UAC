#pragma once
/* Compile/link adapter only; not attached to the A23 handler. Reports MUST be
 * passed immediately after existing Get*ReportData calls, without extra IPC.
 * This does not infer release from usbDsParseReportData's Result. */
#include <switch.h>
#include "ep0_trace_owner.h"

static inline bool ep0_trace_libnx_reports(Ep0TraceOwner *s,uint64_t who,unsigned channel,
                                          Result result,const UsbDsReportData *report) {
    if(R_FAILED(result))return ep0_owner_reports(s,who,channel,result,NULL,0);
    if(!report)return ep0_owner_reports(s,who,channel,0,NULL,1);
    if(report->report_count>8)return ep0_owner_reports(s,who,channel,0,NULL,report->report_count);
    Ep0OwnerReport entries[8];
    for(u32 i=0;i<report->report_count;i++)
        entries[i]=(Ep0OwnerReport){report->report[i].id,report->report[i].urb_status};
    return ep0_owner_reports(s,who,channel,0,entries,report->report_count);
}
