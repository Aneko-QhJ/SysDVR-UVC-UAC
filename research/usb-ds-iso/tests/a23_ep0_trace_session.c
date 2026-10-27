/* Full simulated before STATUS -> BURST -> after STATUS window.
 * Uses the shared HOS services and the original/traced A23 source above it. */
static void session_setup(const UsbSetupPacket *setup) {
    shared_setup=*setup;
    for(unsigned i=0;i<3;i++)interfaces[i].SetupEvent.signaled=true;
}
int main(int argc,char **argv) {
    assert(argc==5);const char *name=argv[1];trace_probe_begin(argv[3],argv[4]);
    bool replaced=!strcmp(name,"session-replaced");
    assert(replaced || !strcmp(name,"session-kept"));
    g_uvcCtx.controlInterface=&interfaces[0];g_uvcCtx.streamingInterface=&interfaces[1];g_uvcCtx.state=1;
    for(unsigned i=0;i<3;i++) {
        interfaces[i].interface_index=i;
        interfaces[i].CtrlInCompletionEvent.kind=1;interfaces[i].CtrlOutCompletionEvent.kind=2;
    }
    g_isoStatus.magic=ISO_PROBE_STATUS_MAGIC;g_isoStatus.version=1;g_isoStatus.endpoint=0x83;
    session_setup(&status);UvcDeviceProcessRequests();
    assert(status_writes==1 && posts==0 && g_isoStatus.sequence==0);
    now_ns+=1290375;u64 trigger=now_ns;
    session_setup(&burst);
    if(replaced) {
        log_ns=8000000;replacement_enabled=true;replacement_ns=trigger+STATUS_BEGIN_NS;
    }
    UvcDeviceProcessRequests();
    if(!replaced) {
        assert(now_ns<trigger+STATUS_BEGIN_NS);
        now_ns=trigger+STATUS_BEGIN_NS;session_setup(&status);UvcDeviceProcessRequests();
    }
    assert(status_writes==2 && broadcasts==12);
    assert(posts==(replaced ? 0u : 1u) && g_isoStatus.sequence==(replaced ? 0u : 1u));
    trace_probe_export(argv[2]);
    printf("{\"scenario\":\"%s\",\"sequence\":%u,\"posts\":%u,\"status_writes\":%u,"
           "\"broadcast_logs\":%u,\"virtual_end_ns\":%llu,\"hardware_observation\":false}\n",
           name,g_isoStatus.sequence,posts,status_writes,broadcasts,(unsigned long long)now_ns);
    return 0;
}
