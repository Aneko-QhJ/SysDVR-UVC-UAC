/* Shared setup/event services modeled from the bound HOS disassembly.
 * Scheduling and bus arrival are injected hypotheses, not hardware evidence.
 * The generator supplies the existing service stubs and the real client source. */
static UsbSetupPacket shared_setup;
static u64 replacement_ns, status_reply_ns;
static bool replacement_enabled, replacement_delivered;
static unsigned first_request[3], setup_reads[3];

static void deliver_setup(void) {
    if (replacement_enabled && !replacement_delivered && now_ns >= replacement_ns) {
        shared_setup=status;
        for (unsigned i=0;i<3;i++) interfaces[i].SetupEvent.signaled=true;
        replacement_delivered=true;
    }
}
static void record_log(const char *format, ...) {
    legacy_record_log(format);
    deliver_setup();
}
static Result eventWait(Event *e, u64 timeout) {
    (void)timeout;
    deliver_setup();
    return e->signaled ? 0 : 1;
}
static Result waitMulti(s32 *index, u64 timeout, Event *a, Event *b, Event *c) {
    Event *events[]={a,b,c};
    deliver_setup();
    for (unsigned i=0;i<3;i++) if(events[i]->signaled) { *index=(s32)i;return 0; }
    if (replacement_enabled && !replacement_delivered && replacement_ns<=now_ns+timeout) {
        now_ns=replacement_ns;
        deliver_setup();
        return waitMulti(index,0,a,b,c);
    }
    now_ns+=timeout;
    return 1;
}
static Result usbDsInterface_GetSetupPacket(UsbDsInterface *i, void *buffer, size_t size) {
    deliver_setup();
    assert(size==8);
    unsigned idx=i->interface_index;
    if(setup_reads[idx]++==0)first_request[idx]=shared_setup.bRequest;
    if(idx==2) { iso_gets++;entered_ns=now_ns; }
    memcpy(buffer,&shared_setup,size);
    i->SetupEvent.signaled=false;
    return 0;
}
static Result usbDsInterface_CtrlInPostBufferAsync(UsbDsInterface *i, void *b, size_t n, u32 *id) {
    if(n==168 && status_reply_ns==0)status_reply_ns=now_ns;
    return legacy_CtrlInPost(i,b,n,id);
}

/* INSERT_ACTUAL_SOURCE */

int main(int argc, char **argv) {
    assert(argc==2);const char *name=argv[1];
    g_uvcCtx.controlInterface=&interfaces[0];g_uvcCtx.streamingInterface=&interfaces[1];g_uvcCtx.state=1;
    for(unsigned i=0;i<3;i++) {
        interfaces[i].interface_index=i;interfaces[i].SetupEvent=(Event){0,true};
        interfaces[i].CtrlInCompletionEvent.kind=1;interfaces[i].CtrlOutCompletionEvent.kind=2;
    }
    shared_setup=burst;
    g_isoStatus.magic=ISO_PROBE_STATUS_MAGIC;g_isoStatus.version=1;g_isoStatus.endpoint=0x83;
    replacement_enabled=true;replacement_ns=STATUS_BEGIN_NS;
    if(!strcmp(name,"no-delay"))log_ns=0;
    else if(!strcmp(name,"20ms-kept"))log_ns=5000000;
    else if(!strcmp(name,"28ms-kept"))log_ns=7000000;
    else if(!strcmp(name,"32ms-replaced"))log_ns=8000000;
    else if(!strcmp(name,"32ms-delayed-arrival")){log_ns=8000000;replacement_ns+=5000000;}
    else if(!strcmp(name,"32ms-no-replacement")){log_ns=8000000;replacement_enabled=false;}
    else assert(false);
    IsoProbeStatus before=g_isoStatus;
    UvcDeviceProcessRequests();
    bool replaced=!strcmp(name,"32ms-replaced");
    assert(first_request[0]==ISO_PROBE_BURST && first_request[1]==ISO_PROBE_BURST);
    assert(first_request[2]==(replaced ? ISO_PROBE_STATUS : ISO_PROBE_BURST));
    assert(posts==(replaced ? 0u : 1u) && submits==posts);
    assert(g_isoStatus.sequence==(replaced ? 0u : 1u));
    assert(!memcmp(&before,&g_isoStatus,sizeof(before))==replaced);
    if(replaced) {
        assert(status_writes==1 && status_reply_ns==32000000);
        assert(status_reply_ns>=STATUS_BEGIN_NS && status_reply_ns<=STATUS_END_NS);
        assert(setup_reads[0]==2 && setup_reads[1]==2 && setup_reads[2]==1);
    }
    if(!replacement_enabled)assert(status_writes==0 && first_request[2]==ISO_PROBE_BURST);
    printf("{\"scenario\":\"%s\",\"sequence\":%u,\"posts\":%u,\"status_writes\":%u,"
        "\"first_requests\":[%u,%u,%u],\"setup_reads\":[%u,%u,%u],\"log_delay_ns\":%llu,"
        "\"assumed_replacement_ns\":%llu,\"status_reply_ns\":%llu,\"status_unchanged\":%s,"
        "\"hardware_observation\":false,\"hos_machine_code_emulated\":false}\n",
        name,g_isoStatus.sequence,posts,status_writes,first_request[0],first_request[1],first_request[2],
        setup_reads[0],setup_reads[1],setup_reads[2],(unsigned long long)log_ns,
        (unsigned long long)replacement_ns,(unsigned long long)status_reply_ns,
        !memcmp(&before,&g_isoStatus,sizeof(before)) ? "true" : "false");
    return 0;
}
