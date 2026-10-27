/* Actual frozen EP0 functions with injected services. This is a computer
 * experiment: query order, delays, events, joins and results are model inputs. */
#include <stdlib.h>
#include "ep0_diagnostic_capture.h"
#include "ep0_request_admission.h"

typedef struct {
    unsigned step,records,slots,pending,sequence,iso_posts,refusals;
} ReadinessCheckpoint;
static ReadinessCheckpoint checkpoints[16];
static unsigned checkpoint_count,dispatched,target_dispatches;

static void readiness_checkpoint(unsigned step) {
    const Ep0TraceOwner *o=Ep0CandidateObservation();
    const Ep0AdmissionObservation *a=Ep0CandidateAdmissionObservation();
    assert(checkpoint_count<16);
    checkpoints[checkpoint_count++]=(ReadinessCheckpoint){step,o->trace.count,
        o->used,ep0_owner_pending(o),g_isoStatus.sequence,posts,a->trace_refusals};
}
static void readiness_dispatch(const UsbSetupPacket *packet,bool no_iso_event) {
    shared_setup=*packet;now_ns+=1000;
    for(unsigned i=0;i<3;i++)interfaces[i].SetupEvent.signaled=true;
    if(no_iso_event)interfaces[2].SetupEvent.signaled=false;
    dispatched++;UvcDeviceProcessRequests();
}
static void readiness_save(const char *path,const void *bytes,size_t n) {
    FILE *f=fopen(path,"wb");assert(f);
    assert(fwrite(bytes,1,n,f)==n);assert(!fclose(f));
}

int main(int argc,char **argv) {
    assert(argc==6);const char *mode=argv[1];
    unsigned prelude=(unsigned)strtoul(argv[2],NULL,10);assert(prelude<=9);
    bool candidate=atoi(argv[3])!=0;
    g_uvcCtx.controlInterface=&interfaces[0];g_uvcCtx.streamingInterface=&interfaces[1];
    g_uvcCtx.state=UVC_STATE_CONNECTED;
    for(unsigned i=0;i<3;i++) {
        interfaces[i].interface_index=i;
        interfaces[i].CtrlInCompletionEvent.kind=1;
        interfaces[i].CtrlOutCompletionEvent.kind=2;
    }
    g_isoStatus.magic=ISO_PROBE_STATUS_MAGIC;g_isoStatus.version=1;g_isoStatus.endpoint=0x83;
    trace_probe_begin("01000000000000000000000000000000","02000000000000000000000000000000");
    readiness_checkpoint(0);
    for(unsigned j=0;j<prelude && !Ep0CandidateStopRequested();j++) {
        /* Standard GET_INTERFACE uses the actual dispatcher and control
         * helpers; neither class-handler stub is reachable on this input. */
        UsbSetupPacket query={0x81,USB_REQUEST_GET_INTERFACE,0,(u16)(j%2),1};
        bool reconnect=!strcmp(mode,"reconnect") || !strcmp(mode,"log-prefix");
        if(reconnect)
            query=(UsbSetupPacket){0x01,USB_REQUEST_SET_INTERFACE,0,1,0};
        readiness_dispatch(&query,false);
        if(reconnect && (!strcmp(mode,"reconnect") || j+1<prelude) && !Ep0CandidateStopRequested()) {
            device_state=0;now_ns+=1000;UvcDeviceProcessRequests();
            device_state=UsbState_Configured;
        }
        readiness_checkpoint(j+1);
    }
    unsigned prelude_dispatched=dispatched;
    for(unsigned step=0;step<3 && !Ep0CandidateStopRequested();step++) {
        /* The replacement IS the third host setup. Do not create a fourth
         * STATUS just because delivery happened inside the BURST dispatch. */
        if(step==2 && replacement_delivered)break;
        ack_wait_rc=ack_report_rc=ack_post_rc=post_rc=speed_rc=0;
        get_setup_fail=false;speed=UsbDeviceSpeed_High;
        if(step==0 && !strcmp(mode,"prestatus-timeout"))ack_wait_rc=94;
        if(step==1) {
            if(!strcmp(mode,"speed-error"))speed_rc=97;
            if(!strcmp(mode,"full-speed"))speed=2;
            if(!strcmp(mode,"super-speed"))speed=4;
            if(!strcmp(mode,"post-failed"))post_rc=96;
            if(!strcmp(mode,"ack-timeout"))ack_wait_rc=94;
            if(!strcmp(mode,"setup-failed"))get_setup_fail=true;
            if(!strcmp(mode,"replaced")) {
                log_ns=8000000;replacement_enabled=true;
                replacement_ns=now_ns+1000+30565334;
            }
        }
        if(step==2 && strcmp(mode,"iso-pending"))iso_report_count=1;
        target_dispatches++;
        readiness_dispatch(step==1 ? &burst : &status,
                           step==1 && !strcmp(mode,"no-iso-event"));
        readiness_checkpoint(100+step);
        replacement_enabled=false;log_ns=0;
    }
    const Ep0TraceOwner *o=Ep0CandidateObservation();
    const Ep0AdmissionObservation *a=Ep0CandidateAdmissionObservation();
    const Ep0GuardObservation *g=Ep0CandidateGuardObservation();
    unsigned events=0;for(unsigned i=0;i<3;i++)events+=interfaces[i].SetupEvent.signaled;
    bool stopped_before_finish=Ep0CandidateStopRequested();
    size_t diagnostic=0,normal_size=0;bool accepted=false;
    unsigned vjoin=!strcmp(mode,"video-join-error") ? 78:0;
    unsigned ajoin=!strcmp(mode,"audio-join-error") ? 79:0;
    if(candidate) {
        Ep0CandidateRequestStop();assert(Ep0CandidateStop(svcGetSystemTick()));
        if(!vjoin && !ajoin)accepted=Ep0CandidateFinish(22,vjoin);
        const uint8_t *normal=Ep0CandidateBytes(&normal_size);
        if(normal)readiness_save(argv[4],normal,normal_size);
        Ep0TraceOwner before=*o;Ep0GuardObservation guard_before=*g;
        uint8_t bytes[EP0_DIAGNOSTIC_MAX];memset(bytes,0xa5,sizeof(bytes));
        diagnostic=ep0_diagnostic_capture(o,g,22,vjoin,ajoin,recipe_digest,bytes,sizeof(bytes));
        assert(!memcmp(o,&before,sizeof(before)) && !memcmp(g,&guard_before,sizeof(guard_before)));
        if(diagnostic)readiness_save(argv[5],bytes,diagnostic);
        else for(unsigned i=0;i<sizeof(bytes);i++)assert(bytes[i]==0xa5);
        assert((normal_size!=0)==accepted);
    }
    printf("{\"mode\":\"%s\",\"prelude\":%u,\"candidate\":%s,"
        "\"prelude_dispatched\":%u,\"target_dispatches\":%u,\"target_setup_deliveries\":%u,\"sequence\":%u,"
        "\"iso_posts\":%u,\"in_posts\":%u,\"out_posts\":%u,\"stalls\":%u,"
        "\"status_writes\":%u,\"records\":%u,\"slots\":%u,\"pending\":%u,"
        "\"fault\":%u,\"trace_refusals\":%u,\"bound_violations\":%u,"
        "\"guard_reason\":%u,\"events_left_signaled\":%u,\"dropped\":%u,\"invalid\":%u,"
        "\"stopped_before_finish\":%s,\"normal_export\":%s,\"diagnostic_bytes\":%zu,"
        "\"video_join\":%u,\"audio_join\":%u,\"replacement_delivered\":%s,\"checkpoints\":[",
        mode,prelude,candidate?"true":"false",prelude_dispatched,target_dispatches,
        target_dispatches+(replacement_delivered?1u:0u),
        g_isoStatus.sequence,posts,in_posts,out_posts,stalls,status_writes,
        o->trace.count,o->used,ep0_owner_pending(o),o->fault,a->trace_refusals,
        a->bound_violations,g->last_reason,events,o->trace.dropped,o->trace.invalid,
        stopped_before_finish?"true":"false",accepted?"true":"false",diagnostic,
        vjoin,ajoin,replacement_delivered?"true":"false");
    for(unsigned i=0;i<checkpoint_count;i++) {
        ReadinessCheckpoint *c=&checkpoints[i];
        printf("%s{\"step\":%u,\"records\":%u,\"slots\":%u,\"pending\":%u,"
            "\"sequence\":%u,\"iso_posts\":%u,\"trace_refusals\":%u}",i?",":"",
            c->step,c->records,c->slots,c->pending,c->sequence,c->iso_posts,c->refusals);
    }
    puts("],\"hardware_observation\":false,\"actual_class_handlers_executed\":false}");
    return 0;
}
