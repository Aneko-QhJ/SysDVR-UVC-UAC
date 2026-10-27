/* Appended to a sealed native service fixture by the audit tool. The five
 * ISO/dispatch functions are copied from the deployed candidate source.
 * Prefix metadata, terminal reports and all USB services are injected. */
static void seed_prefix(unsigned count) {
    assert(count<=EP0_TRACE_CAPACITY && Ep0CandidateEnter());
    /* Reconstruct the observed first-session cost:18 trace records plus one
     * completed control identity. This does not replay actual enumeration. */
    Ep0CandidateObservePost(2,0,true,9000);
    Ep0CandidateGuardPost(2,0,true,9000,g_controlBuffer,0);
    UsbDsReportData report={0};report.report_count=1;report.report[0].id=9000;report.report[0].urb_status=3;
    Ep0CandidateObserveReports(2,0,&report);
    for(unsigned i=0;i<count;i++)trace_emit(EP0_T_DEVICE_STATE,NULL,0,0,0,0,NULL,now_ns,now_ns);
    Ep0CandidateLeave();
}
static void trigger_sequence(unsigned sequence) {
    iso_report_count=0;iso_report_id=0;iso_report_status=3;iso_report_rc=0;
    burst.wValue=(u16)sequence;model_setup(&burst);
}
static void terminal_status(unsigned status_value) {
    iso_report_count=1;iso_report_status=status_value;iso_report_id=last_iso_id;
    model_setup(&status);
}
int main(int argc,char **argv) {
    assert(argc==2);const char *name=argv[1];unsigned prefix=18;
    bool sweep=sscanf(name,"prefix-%u",&prefix)==1;assert(prefix<=EP0_TRACE_CAPACITY);
    trace_probe_begin("01000000000000000000000000000000","02000000000000000000000000000000");
    g_uvcCtx.controlInterface=&interfaces[0];g_uvcCtx.streamingInterface=&interfaces[1];g_uvcCtx.state=1;
    for(unsigned i=0;i<3;i++) { interfaces[i].interface_index=i;interfaces[i].CtrlInCompletionEvent.kind=1;interfaces[i].CtrlOutCompletionEvent.kind=2; }
    g_isoStatus.magic=ISO_PROBE_STATUS_MAGIC;g_isoStatus.version=1;g_isoStatus.endpoint=0x83;
    seed_prefix(prefix);model_setup(&status);trigger_sequence(81);
    if(!sweep && !strcmp(name,"pending")) {
        unsigned before=posts;burst.wValue=97;model_setup(&burst);assert(posts==before);
    } else if(!sweep && !strcmp(name,"foreign-terminal")) {
        iso_report_count=1;iso_report_id=last_iso_id+999;iso_report_status=3;model_setup(&status);
        burst.wValue=97;model_setup(&burst);
    } else if(!sweep && !strcmp(name,"report-error")) {
        iso_report_count=1;iso_report_rc=93;model_setup(&status);burst.wValue=97;model_setup(&burst);
    } else if(!sweep && !strcmp(name,"duplicate-id")) {
        terminal_status(3);next_urb=last_iso_id;trigger_sequence(97);
    } else {
        terminal_status(!strcmp(name,"terminal4") ? 4:!strcmp(name,"terminal5") ? 5:3);
        unsigned rounds=!strcmp(name,"single") ? 1:!strcmp(name,"chained-three") ? 3:
            !strcmp(name,"full-four") ? 4:(!strcmp(name,"chained-five") || !strcmp(name,"five-extra")) ? 5:
            !strcmp(name,"chained-six") ? 6:2;
        for(unsigned round=1;round<rounds;round++) {
            if(!strcmp(name,"full-two") || !strcmp(name,"full-four"))model_setup(&status);
            trigger_sequence(81+round*16);terminal_status(3);
        }
        if(!strcmp(name,"chained-extra") || !strcmp(name,"five-extra"))model_setup(&status);
        if(!strcmp(name,"disconnect")) { device_state=0;UvcDeviceProcessRequests(); }
    }
    unsigned sequence=g_isoStatus.sequence,state=g_isoStatus.state,records=Ep0CandidateObservation()->trace.count;
    unsigned pending=ep0_owner_pending(Ep0CandidateObservation()),used=Ep0CandidateObservation()->used;
    bool stop_before=Ep0CandidateStopRequested();unsigned fault=Ep0CandidateObservation()->fault;
    Ep0CandidateRequestStop();assert(Ep0CandidateStop(svcGetSystemTick()));bool exported=Ep0CandidateFinish(22,0);
    assert(!model_copy_overlaps && !model_pointer_reposts);
    printf("{\"case\":\"%s\",\"prefix\":%u,\"records\":%u,\"used\":%u,\"pending\":%u,\"fault\":%u,"
        "\"sequence\":%u,\"state\":%u,\"iso_posts\":%u,\"trace_refusals\":%u,\"stalls\":%u,\"dropped\":%u,"
        "\"stop_requested\":%s,\"normal_export\":%s,\"model_copy_overlaps\":%u,\"model_pointer_reposts\":%u,"
        "\"simulation\":true,\"hardware_verified\":false}\n",name,prefix,records,used,pending,fault,sequence,state,posts,
        Ep0CandidateAdmissionObservation()->trace_refusals,stalls,Ep0CandidateObservation()->trace.dropped,
        stop_before ? "true":"false",exported ? "true":"false",model_copy_overlaps,model_pointer_reposts);
    return 0;
}
