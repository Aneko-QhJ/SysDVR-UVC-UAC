/* Native-only direct boundary inspection. Some metadata/posts are injected;
 * these cases are not exported as ownership captures or hardware observations. */
int main(int argc,char **argv) {
    assert(argc==2);const char *name=argv[1];
    trace_probe_begin("01000000000000000000000000000000","02000000000000000000000000000000");
    g_uvcCtx.controlInterface=&interfaces[0];g_uvcCtx.streamingInterface=&interfaces[1];g_uvcCtx.state=1;
    for(unsigned i=0;i<3;i++) { interfaces[i].interface_index=i;interfaces[i].CtrlInCompletionEvent.kind=1;interfaces[i].CtrlOutCompletionEvent.kind=2; }
    g_isoStatus.magic=ISO_PROBE_STATUS_MAGIC;g_isoStatus.version=1;g_isoStatus.endpoint=0x83;
    memset(g_isoBuffer,0xa5,sizeof(g_isoBuffer));
    unsigned n=0;
    if(sscanf(name,"limit-%u",&n)==1) {
        assert(n<=128);
        for(unsigned i=0;i<n;i++)trace_emit(EP0_T_DEVICE_STATE,NULL,0,0,0,0,NULL,now_ns,now_ns);
        assert(Ep0CandidateEnter());
        bool admitted=Ep0CandidateAdmissionBegin();
        if(admitted) { shared_setup=status;interfaces[2].SetupEvent.signaled=true;admitted=_serviceSetup(&interfaces[2]); }
        assert(admitted==(n<=111));assert(Ep0CandidateObservation()->trace.count==(n<=111 ? n+17:n));
        assert(status_writes==(n<=111 ? 1u:0u));assert(!Ep0CandidateObservation()->trace.dropped);
        Ep0CandidateLeave();
    } else if(!strcmp(name,"slot-one-left")) {
        assert(Ep0CandidateEnter());
        for(unsigned i=0;i<15;i++) {
            Ep0CandidateObservePost(4,0,true,1000+i);Ep0CandidateGuardPost(4,0,true,1000+i,g_controlBuffer,0);
            UsbDsReportData r={0};r.report_count=1;r.report[0].id=1000+i;r.report[0].urb_status=3;
            Ep0CandidateObserveReports(4,0,&r);
        }
        Ep0CandidateLeave();model_setup(&burst);
        assert(!posts && !g_isoStatus.sequence && Ep0CandidateObservation()->used==15);
        assert(Ep0CandidateGuardObservation()->last_reason==EP0_BG_CAPACITY);
    } else if(!strcmp(name,"iso-borrowed")) {
        assert(Ep0CandidateEnter());Ep0CandidateObservePost(8,0,true,77);
        Ep0CandidateGuardPost(8,0,true,77,g_isoBuffer,3072);Ep0CandidateLeave();
        model_setup(&burst);assert(!posts && !g_isoStatus.sequence);
        assert(Ep0CandidateGuardObservation()->last_reason==EP0_BG_OVERLAP);
    } else if(!strcmp(name,"proposed-alias")) {
        assert(Ep0CandidateEnter());assert(!Ep0CandidateAdmissionBurst(g_controlBuffer,32,g_controlBuffer));
        assert(Ep0CandidateGuardObservation()->last_reason==EP0_BG_OVERLAP);Ep0CandidateLeave();
    } else if(!strcmp(name,"ack-out-borrowed") || !strcmp(name,"ack-zero-borrowed")) {
        assert(Ep0CandidateEnter());Ep0CandidateObservePost(5,0,true,77);
        Ep0CandidateGuardPost(5,0,true,77,g_controlBuffer,!strcmp(name,"ack-zero-borrowed") ? 0:32);
        Ep0CandidateLeave();model_setup(&burst);assert(!posts && !g_isoStatus.sequence);
        assert(Ep0CandidateGuardObservation()->last_reason==EP0_BG_OVERLAP);
    } else if(!strcmp(name,"proposed-adjacent")) {
        assert(Ep0CandidateEnter());assert(Ep0CandidateAdmissionBurst(g_isoBuffer,3072,(void*)((uintptr_t)g_isoBuffer+3072)));
        assert(!Ep0CandidateObservation()->fault);Ep0CandidateLeave();
    } else if(!strcmp(name,"followup-flood")) {
        native_followups=100;model_setup(&status);
        assert(native_followups && status_writes==5 && Ep0CandidateObservation()->used==10);
        assert(Ep0CandidateObservation()->trace.count==115 && !Ep0CandidateObservation()->trace.dropped);
        assert(Ep0CandidateStopRequested() && Ep0CandidateAdmissionObservation()->trace_refusals==1);
    } else if(!strcmp(name,"bound-violation")) {
        assert(Ep0CandidateEnter());assert(Ep0CandidateAdmissionBegin());assert(Ep0CandidateAdmissionReady());
        for(unsigned i=0;i<18;i++)trace_emit(EP0_T_DEVICE_STATE,NULL,0,0,0,0,NULL,now_ns,now_ns);
        Ep0CandidateAdmissionEnd();assert(Ep0CandidateObservation()->fault);
        assert(Ep0CandidateAdmissionObservation()->bound_violations==1);Ep0CandidateLeave();
    } else {
        assert(!strcmp(name,"stop-before-followup"));
        Ep0CandidateRequestStop();shared_setup=status;interfaces[2].SetupEvent.signaled=true;
        UvcDeviceProcessRequests();assert(!iso_report_calls && !iso_gets && !in_posts && !out_posts);
        assert(interfaces[2].SetupEvent.signaled);
    }
    for(unsigned i=0;i<sizeof(g_isoBuffer);i++)assert(g_isoBuffer[i]==0xa5);
    assert(!model_copy_overlaps && !model_pointer_reposts);
    printf("{\"case\":\"%s\",\"passed\":true,\"iso_payload_untouched\":true,\"records\":%u,\"admitted\":%u,\"largest_request\":%u,\"trace_refusals\":%u,\"bound_violations\":%u,\"hardware_verified\":false}\n",
           name,Ep0CandidateObservation()->trace.count,Ep0CandidateAdmissionObservation()->admitted,
           Ep0CandidateAdmissionObservation()->largest_request,Ep0CandidateAdmissionObservation()->trace_refusals,
           Ep0CandidateAdmissionObservation()->bound_violations);
}
