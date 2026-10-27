/* Included after the exact V2 handler and injected services. These direct
 * boundary states are native policy probes, not exported USB observations. */
#include <stdlib.h>
int main(int argc,char **argv) {
    assert(argc==3);unsigned n=(unsigned)strtoul(argv[2],NULL,10);
    trace_probe_begin("01000000000000000000000000000000","02000000000000000000000000000000");
    g_uvcCtx.controlInterface=&interfaces[0];g_uvcCtx.streamingInterface=&interfaces[1];g_uvcCtx.state=1;
    for(unsigned i=0;i<3;i++) {
        interfaces[i].interface_index=i;interfaces[i].CtrlInCompletionEvent.kind=1;
        interfaces[i].CtrlOutCompletionEvent.kind=2;
    }
    g_isoStatus.magic=ISO_PROBE_STATUS_MAGIC;g_isoStatus.version=1;g_isoStatus.endpoint=0x83;
    memset(g_isoBuffer,0xa5,sizeof(g_isoBuffer));
    if(!strcmp(argv[1],"records")) {
        assert(n<=EP0_TRACE_CAPACITY);
        for(unsigned i=0;i<n;i++)trace_emit(EP0_T_DEVICE_STATE,NULL,0,0,0,0,NULL,0,0);
        assert(Ep0CandidateEnter());bool entered=Ep0CandidateAdmissionBegin(),accepted=false;
        if(entered) { shared_setup=status;interfaces[2].SetupEvent.signaled=true;accepted=_serviceSetup(&interfaces[2]); }
        assert(accepted==(n<=EP0_TRACE_CAPACITY-EP0_REQUEST_RECORD_RESERVE));
        assert(Ep0CandidateObservation()->trace.count==n+(accepted ? 17u:0u));
        assert(status_writes==(accepted ? 1u:0u));Ep0CandidateLeave();
    } else {
        assert(!strcmp(argv[1],"identities") && (n==30 || n==31));
        assert(Ep0CandidateEnter());
        for(unsigned i=0;i<n;i++) {
            Ep0CandidateObservePost(4,0,true,1000+i);
            Ep0CandidateGuardPost(4,0,true,1000+i,g_controlBuffer,0);
            UsbDsReportData report={0};report.report_count=1;
            report.report[0]=(UsbDsReportEntry){1000+i,0,0,3};
            Ep0CandidateObserveReports(4,0,&report);
        }
        Ep0CandidateLeave();shared_setup=burst;
        for(unsigned i=0;i<3;i++)interfaces[i].SetupEvent.signaled=true;
        UvcDeviceProcessRequests();
        assert(posts==(n==30 ? 1u:0u));assert(g_isoStatus.sequence==(n==30 ? 1u:0u));
        assert(Ep0CandidateObservation()->used==(n==30 ? 32u:31u));
        if(n==31)for(unsigned i=0;i<sizeof(g_isoBuffer);i++)assert(g_isoBuffer[i]==0xa5);
    }
    const Ep0TraceOwner *o=Ep0CandidateObservation();
    assert(!o->trace.dropped && !o->trace.invalid);
    printf("{\"kind\":\"%s\",\"input\":%u,\"records\":%u,\"slots\":%u,"
           "\"sequence\":%u,\"iso_posts\":%u,\"trace_refusals\":%u,"
           "\"guard_reason\":%u,\"events_left_signaled\":%s,\"passed\":true}\n",
        argv[1],n,o->trace.count,o->used,g_isoStatus.sequence,posts,
        Ep0CandidateAdmissionObservation()->trace_refusals,
        Ep0CandidateGuardObservation()->last_reason,
        interfaces[2].SetupEvent.signaled?"true":"false");
}
