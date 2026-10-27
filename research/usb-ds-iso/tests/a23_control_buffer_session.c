static void model_setup(const UsbSetupPacket *s) {
    shared_setup=*s;for(unsigned i=0;i<3;i++)interfaces[i].SetupEvent.signaled=true;
    UvcDeviceProcessRequests();
}
int main(int argc,char **argv) {
    assert(argc==2);const char *name=argv[1];
    trace_probe_begin("01000000000000000000000000000000","02000000000000000000000000000000");
    g_uvcCtx.controlInterface=&interfaces[0];g_uvcCtx.streamingInterface=&interfaces[1];g_uvcCtx.state=1;
    for(unsigned i=0;i<3;i++) {
        interfaces[i].interface_index=i;
        interfaces[i].CtrlInCompletionEvent.kind=1;interfaces[i].CtrlOutCompletionEvent.kind=2;
    }
    assert(_ctrlBufferFor(&interfaces[1])==_ctrlBufferFor(&interfaces[2]));
    assert(_ctrlBufferFor(&interfaces[0])!=_ctrlBufferFor(&interfaces[2]));
    g_isoStatus.magic=ISO_PROBE_STATUS_MAGIC;g_isoStatus.version=1;g_isoStatus.endpoint=0x83;
    if(!strcmp(name,"in-timeout") || !strcmp(name,"cross-vs") || !strcmp(name,"cross-vc") ||
       !strcmp(name,"late-report-after-copy") || !strcmp(name,"cancel-control-pending") ||
       !strcmp(name,"disconnect-reconnect") || !strcmp(name,"burst-ack-timeout"))ack_wait_rc=94;
    else if(!strcmp(name,"in-report-error"))ack_report_rc=93;
    else if(!strcmp(name,"in-wrong-id"))ctrl_report_id_offset=1000;
    else if(!strcmp(name,"in-status-1"))ctrl_report_status=1;
    else if(!strcmp(name,"in-status-2"))ctrl_report_status=2;
    else if(!strcmp(name,"in-status-unknown"))ctrl_report_status=99;
    else if(!strcmp(name,"in-terminal-4") || !strcmp(name,"burst-ack-terminal-4"))ctrl_report_status=4;
    else if(!strcmp(name,"in-terminal-5"))ctrl_report_status=5;
    else if(!strcmp(name,"out-status-timeout") || !strcmp(name,"out-data-timeout"))model_out_wait_rc=94;
    else if(!strcmp(name,"out-data-report-error"))model_out_report_rc=93;
    else assert(!strcmp(name,"drained"));
    if(!strncmp(name,"burst-ack",9))model_setup(&burst);
    else if(!strncmp(name,"out-data",8)) {
        u8 data[32]={0};assert(Ep0CandidateEnter());
        assert(!_ctrlRead(&interfaces[2],data,sizeof(data)));Ep0CandidateLeave();
    } else model_setup(&status);
    u32 old_id=last_ctrl_id[2][0];
    ack_wait_rc=ack_report_rc=ctrl_report_id_offset=model_out_wait_rc=model_out_report_rc=0;
    ctrl_report_status=3;iso_report_count=1;g_isoStatus.sequence=9;
    if(!strcmp(name,"late-report-after-copy"))late_ctrl_id=old_id;
    if(!strcmp(name,"cross-vs") || !strcmp(name,"cross-vc")) {
        UsbSetupPacket get_alt={0x81,USB_REQUEST_GET_INTERFACE,0,!strcmp(name,"cross-vs") ? 1:0,1};
        model_setup(&get_alt);
    } else if(!strcmp(name,"cancel-control-pending")) {
        UsbSetupPacket cancel={0x41,ISO_PROBE_CANCEL,0,2,0};model_setup(&cancel);
    } else {
        if(!strcmp(name,"disconnect-reconnect")) { device_state=0;UvcDeviceProcessRequests();device_state=5; }
        model_setup(&status);
    }
    unsigned pending=0,nonzero=0,zero=0;
    for(unsigned i=0;i<model_used;i++)if(model_spans[i].active) {
        pending++;if(model_spans[i].length)nonzero++;else zero++;
    }
    Ep0CandidateRequestStop();assert(Ep0CandidateStop(svcGetSystemTick()));
    bool safe=Ep0CandidateFinish(22,0);const Ep0TraceOwner *o=Ep0CandidateObservation();
    printf("{\"case\":\"%s\",\"pending_spans\":%u,\"pending_nonzero_spans\":%u,\"pending_zero_spans\":%u,"
           "\"cpu_write_overlaps\":%u,\"cpu_write_overlap_bytes\":%u,\"changed_pending_bytes\":%u,\"same_address_reposts\":%u,"
           "\"iso_posts\":%u,\"in_posts\":%u,\"out_posts\":%u,\"ctrl_reports\":%u,\"stalls\":%u,"
           "\"ledger_pending\":%u,\"ledger_fault\":%u,\"ledger_export_allowed\":%s,\"hardware_verified\":false}\n",
           name,pending,nonzero,zero,model_copy_overlaps,model_copy_bytes,model_changed_bytes,model_pointer_reposts,
           posts,in_posts,out_posts,ctrl_report_calls,stalls,ep0_owner_pending(o),o->fault,safe ? "true":"false");
    return 0;
}
