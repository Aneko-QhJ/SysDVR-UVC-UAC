/* Full actual handler calls under explicit fault/report injection. New report
 * arrival times and terminal statuses are hypotheses, not HOS execution. */
static void session_setup(const UsbSetupPacket *setup) {
    shared_setup=*setup;for(unsigned i=0;i<3;i++)interfaces[i].SetupEvent.signaled=true;
}
int main(int argc,char **argv) {
    assert(argc==5);const char *name=argv[1];trace_probe_begin(argv[3],argv[4]);
    g_uvcCtx.controlInterface=&interfaces[0];g_uvcCtx.streamingInterface=&interfaces[1];g_uvcCtx.state=1;
    for(unsigned i=0;i<3;i++) {
        interfaces[i].interface_index=i;
        interfaces[i].CtrlInCompletionEvent.kind=1;interfaces[i].CtrlOutCompletionEvent.kind=2;
    }
    g_isoStatus.magic=ISO_PROBE_STATUS_MAGIC;g_isoStatus.version=1;g_isoStatus.endpoint=0x83;
    session_setup(&status);UvcDeviceProcessRequests();assert(status_writes==1);
    if(!strcmp(name,"ctrl-terminal-4"))ctrl_report_status=4;
    else if(!strcmp(name,"ctrl-terminal-5"))ctrl_report_status=5;
    else if(!strcmp(name,"ctrl-timeout") || !strcmp(name,"ctrl-late-terminal"))ack_wait_rc=94;
    else if(!strcmp(name,"ctrl-report-error"))ack_report_rc=93;
    else if(!strcmp(name,"ctrl-wrong-id"))ctrl_report_id_offset=1000;
    else if(!strcmp(name,"ctrl-unknown-status"))ctrl_report_status=99;
    else if(!strcmp(name,"ctrl-duplicate"))ctrl_report_count=2;
    else if(!strcmp(name,"failed-post"))post_rc=96;
    else if(!strcmp(name,"stop-inside-wait"))inject_stop_in_wait=true;
    session_setup(&burst);UvcDeviceProcessRequests();assert(posts==1 && g_isoStatus.sequence==1);
    if(!strcmp(name,"ctrl-late-terminal"))late_ctrl_id=last_ctrl_id[2][0];
    ctrl_report_status=3;ctrl_report_count=1;ctrl_report_id_offset=0;ack_wait_rc=0;ack_report_rc=0;
    iso_report_count=1;
    if(!strcmp(name,"iso-pending"))iso_report_count=0;
    else if(!strcmp(name,"iso-wrong-id"))iso_report_id=last_iso_id+1000;
    else if(!strcmp(name,"iso-state-1"))iso_report_status=1;
    else if(!strcmp(name,"iso-state-2"))iso_report_status=2;
    else if(!strcmp(name,"iso-terminal-4"))iso_report_status=4;
    else if(!strcmp(name,"iso-terminal-5"))iso_report_status=5;
    else if(!strcmp(name,"iso-report-error"))iso_report_rc=77;
    else if(!strcmp(name,"iso-duplicate"))iso_report_count=2;
    else if(!strcmp(name,"iso-count-9"))iso_report_count=9;
    else if(!strcmp(name,"join-error"))injected_join_result=78;
    if(strcmp(name,"stop-inside-wait")) {
        now_ns+=10000000;session_setup(&status);UvcDeviceProcessRequests();assert(status_writes==2);
    }
    if(!strcmp(name,"capacity-storm")) {
        for(unsigned i=0;i<10;i++) { session_setup(&status);UvcDeviceProcessRequests(); }
    }
    if(!strcmp(name,"trace-overflow")) {
        for(unsigned i=0;i<200;i++) {
            now_ns++;trace_emit(EP0_T_DEVICE_STATE,NULL,0,0,0,0,NULL,now_ns,now_ns);
        }
    }
    trace_probe_export(argv[2]);
    printf("{\"scenario\":\"%s\",\"sequence\":%u,\"posts\":%u,\"state\":%u,\"stalls\":%u,"
           "\"status_writes\":%u,\"virtual_end_ns\":%llu,\"hardware_observation\":false}\n",
           name,g_isoStatus.sequence,posts,g_isoStatus.state,stalls,status_writes,(unsigned long long)now_ns);
    return 0;
}
