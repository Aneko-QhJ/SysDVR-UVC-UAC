/* Called from the exact sealed VideoStreamThread; scheduling, joins and USB
 * results are injected. No real thread, HOS execution, USB or SD operation. */
static const char *session_case;
static unsigned steps,dispatches,ready_calls,planned;
static atomic_bool g_running=true;
typedef struct { void *Data;size_t DataSize;uint64_t Timestamp;bool IsKeyframe; } VideoFrame;
#define CUR_THREAD_HANDLE 0
static Result svcGetThreadId(uint64_t *id,unsigned h) {
    (void)h;*id=11;return !strcmp(session_case,"identity-error") ? 97:0;
}
static void randomGet(void *out,size_t n) {
    static unsigned nonce;memset(out,!strcmp(session_case,"zero-nonce") ? 0:++nonce,n);
}
static Result UvcDeviceWaitReady(uint64_t timeout) {
    (void)timeout;ready_calls++;
    if(!strcmp(session_case,"ready-stop")) { Ep0CandidateRequestStop();return 91; }
    if(!strcmp(session_case,"window-wait")) { now_ns+=31000000000ull;return 91; }
    return 0;
}
static bool UvcDeviceIsStreaming(void) { return false; }
static bool CaptureReadVideoFrame(VideoFrame *f) { (void)f;assert(0);return false; }
static bool UvcDeviceSendFrame(const void *b,size_t n,uint64_t t,bool k) {
    (void)b;(void)n;(void)t;(void)k;assert(0);return false;
}
static void session_dispatch(void) {
    assert(steps<32);
    if(steps==planned) {
        if(!strcmp(session_case,"trace-overflow"))for(unsigned i=0;i<200;i++) {
            now_ns++;trace_emit(EP0_T_DEVICE_STATE,NULL,0,0,0,0,NULL,now_ns,now_ns);
        }
        Ep0CandidateRequestStop();return;
    }
    unsigned step=steps++;dispatches++;
    ack_wait_rc=ack_report_rc=ack_post_rc=post_rc=0;
    ctrl_report_count=1;ctrl_report_status=3;iso_report_count=step>=2 ? 1:0;
    const UsbSetupPacket *packet=&status;
    bool statuses_only=!strncmp(session_case,"statuses-",9);
    if(!statuses_only && step==1) {
        packet=&burst;
        if(!strcmp(session_case,"ack-timeout") || !strcmp(session_case,"late-ack-report"))ack_wait_rc=94;
        if(!strcmp(session_case,"ack-report-error"))ack_report_rc=93;
        if(!strcmp(session_case,"ctrl-duplicate"))ctrl_report_count=2;
        if(!strcmp(session_case,"failed-iso-post"))post_rc=96;
        if(!strcmp(session_case,"failed-ack-post"))ack_post_rc=95;
        if(!strcmp(session_case,"stop-inside-wait"))inject_stop_in_wait=true;
        if(!strcmp(session_case,"reused-control-id"))next_urb=99;
    }
    if(step==0 && !strcmp(session_case,"prestatus-timeout"))ack_wait_rc=94;
    if(step>=2) {
        if(!strcmp(session_case,"iso-pending"))iso_report_count=0;
        if(!strcmp(session_case,"iso-report-error"))iso_report_rc=77;
        if(!strcmp(session_case,"iso-duplicate"))iso_report_count=2;
        if(!strcmp(session_case,"late-ack-report"))late_ctrl_id=last_ctrl_id[2][0];
    }
    shared_setup=*packet;for(unsigned i=0;i<3;i++)interfaces[i].SetupEvent.signaled=true;
    UvcDeviceProcessRequests();
}
/* INSERT_VIDEO_THREAD */
int main(int argc,char **argv) {
    assert(argc==4);session_case=argv[1];planned=3;
    unsigned n=0;
    if(sscanf(session_case,"statuses-%u",&n)==1)planned=n;
    if(sscanf(session_case,"session-extra-%u",&n)==1)planned+=n;
    assert(planned<32);
    g_uvcCtx.controlInterface=&interfaces[0];g_uvcCtx.streamingInterface=&interfaces[1];g_uvcCtx.state=1;
    for(unsigned i=0;i<3;i++) {
        interfaces[i].interface_index=i;interfaces[i].CtrlInCompletionEvent.kind=1;interfaces[i].CtrlOutCompletionEvent.kind=2;
    }
    g_isoStatus.magic=ISO_PROBE_STATUS_MAGIC;g_isoStatus.version=1;g_isoStatus.endpoint=0x83;
    VideoStreamThread(NULL);
    assert(!g_running);
    /* Successful/failed join results are model inputs. Reading for assertions
     * here is native-only; diagnostic serializer rejects failed joins first. */
    Result v=!strcmp(session_case,"video-join-error") ? 78:0;
    Result a=!strcmp(session_case,"audio-join-error") ? 79:0;
    bool accepted=!v && !a && Ep0CandidateFinish(22,v);
    const Ep0TraceOwner *o=Ep0CandidateObservation();const Ep0GuardObservation *g=Ep0CandidateGuardObservation();
    Ep0TraceOwner before=*o;Ep0GuardObservation guard_before=*g;
    uint8_t bytes[EP0_DIAGNOSTIC_MAX];memset(bytes,0xa5,sizeof(bytes));
    size_t diagnostic=ep0_diagnostic_capture(o,g,22,v,a,recipe_digest,bytes,sizeof(bytes));
    assert(!memcmp(o,&before,sizeof(before)) && !memcmp(g,&guard_before,sizeof(guard_before)));
    if(diagnostic) {
        FILE *f=fopen(argv[2],"wb");assert(f);assert(fwrite(bytes,1,diagnostic,f)==diagnostic);assert(!fclose(f));
    } else for(unsigned i=0;i<sizeof(bytes);i++)assert(bytes[i]==0xa5);
    size_t public_size=0;const uint8_t *public_bytes=Ep0CandidateBytes(&public_size);
    assert((public_size!=0)==accepted);
    if(accepted) {
        FILE *f=fopen(argv[3],"wb");assert(f);assert(fwrite(public_bytes,1,public_size,f)==public_size);assert(!fclose(f));
    }
    printf("{\"case\":\"%s\",\"dispatches\":%u,\"planned\":%u,\"ready_calls\":%u,\"used\":%u,"
           "\"pending\":%u,\"fault\":%u,\"guard_denials\":%u,\"guard_reason\":%u,"
           "\"records\":%u,\"dropped\":%u,\"invalid\":%u,\"processing\":%u,\"stopped\":%u,\"joined\":%u,"
           "\"stop_requested\":%s,\"video_join\":%u,\"audio_join\":%u,\"normal_export\":%s,\"diagnostic_bytes\":%zu,"
           "\"sequence\":%u,\"iso_posts\":%u,\"in_posts\":%u,\"out_posts\":%u,\"ctrl_reports\":%u,"
           "\"copy_overlaps\":%u,\"reposts\":%u,\"early_stop_attempted\":%s,\"early_stop_accepted\":%s,"
           "\"cleanup_authorized\":false,\"hardware_verified\":false}\n",
           session_case,dispatches,planned,ready_calls,o->used,ep0_owner_pending(o),o->fault,g->denials,g->last_reason,
           o->trace.count,o->trace.dropped,o->trace.invalid,o->processing,o->stopped,o->joined,
           Ep0CandidateStopRequested()?"true":"false",v,a,accepted?"true":"false",diagnostic,
           g_isoStatus.sequence,posts,in_posts,out_posts,ctrl_report_calls,model_copy_overlaps,model_pointer_reposts,
           early_stop_attempted?"true":"false",early_stop_accepted?"true":"false");
    return 0;
}
