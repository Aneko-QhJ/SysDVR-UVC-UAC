/* Native-only inspection/export glue. It never appears in the ARM candidate.
 * IDs and successful join here are injected; no actual threads or services.
 * Failed ownership export is inspected through the frozen trace core ONLY in
 * this fixture. That debug bypass is labeled and is not a candidate export. */
static void trace_id(const char *hex,uint8_t out[16]) {
    assert(strlen(hex)==32);
    for(unsigned i=0;i<16;i++) {
        unsigned value=0;
        for(unsigned j=0;j<2;j++) {
            char c=hex[i*2+j];assert((c>='0' && c<='9') || (c>='a' && c<='f'));
            value=value*16+(unsigned)(c<='9' ? c-'0' : c-'a'+10);
        }
        out[i]=(uint8_t)value;
    }
}
static void trace_probe_begin(const char *boot,const char *session) {
    uint8_t b[16],s[16];trace_id(boot,b);trace_id(session,s);
    static const uint8_t recipe[32]={/* CANDIDATE_RECIPE_BYTES */};
    assert(Ep0CandidateStart(11,armGetSystemTickFreq(),svcGetSystemTick(),b,s,recipe));
}
static bool early_stop_attempted,early_stop_accepted;
static u32 injected_join_result;
static void candidate_wait_hook(void) {
    if(!inject_stop_in_wait)return;
    inject_stop_in_wait=false;early_stop_attempted=true;
    Ep0CandidateRequestStop();early_stop_accepted=Ep0CandidateStop(svcGetSystemTick());
}
static void trace_probe_export(const char *path) {
    Ep0CandidateRequestStop();
    if(!Ep0CandidateObservation()->stopped)assert(Ep0CandidateStop(svcGetSystemTick()));
    bool safe=Ep0CandidateFinish(22,injected_join_result);size_t public_size=0;
    const uint8_t *public_bytes=Ep0CandidateBytes(&public_size);
    const Ep0TraceOwner *s=Ep0CandidateObservation();
    assert((public_bytes!=NULL)==safe && (public_size!=0)==safe);
    assert(!Ep0CandidateEnter());
    static uint8_t bytes[EP0_TRACE_EXPORT_MAX];
    size_t size=ep0_trace_export(&s->trace,bytes,sizeof(bytes));assert(size);
    static uint8_t short_output[EP0_CAPTURE_MAX];memset(short_output,0xa5,sizeof(short_output));
    size_t needed=EP0_CAPTURE_HEADER+s->used*EP0_CAPTURE_ENTRY+size;
    assert(!ep0_candidate_capture(s,22,recipe_digest,short_output,needed-1));
    for(size_t i=0;i<sizeof(short_output);i++)assert(short_output[i]==0xa5);
    if(safe) {
        size_t offset=EP0_CAPTURE_HEADER+s->used*EP0_CAPTURE_ENTRY;
        assert(size+offset==public_size && !memcmp(bytes,public_bytes+offset,size));
        char capture[1024];assert(snprintf(capture,sizeof(capture),"%s.capture.bin",path)<(int)sizeof(capture));
        FILE *saved=fopen(capture,"wb");assert(saved);
        assert(fwrite(public_bytes,1,public_size,saved)==public_size);assert(fclose(saved)==0);
    }
    FILE *f=fopen(path,"wb");assert(f);assert(fwrite(bytes,1,size,f)==size);assert(fclose(f)==0);
    char meta[1024];assert(snprintf(meta,sizeof(meta),"%s.owner.json",path)<(int)sizeof(meta));
    f=fopen(meta,"w");assert(f);
    fprintf(f,"{\"used\":%u,\"pending\":%u,\"fault\":%u,\"unmatched\":%u,"
              "\"export_allowed\":%s,\"candidate_export_bytes\":%zu,\"native_debug_inspection\":true,"
              "\"injected_join_success\":%s,\"early_stop_attempted\":%s,\"early_stop_accepted\":%s,"
              "\"services\":{\"iso_posts\":%u,\"in_posts\":%u,"
              "\"out_posts\":%u,\"iso_reports\":%u,\"ctrl_reports\":%u,\"stalls\":%u},\"urbs\":[",
              s->used,ep0_owner_pending(s),s->fault,s->unmatched,safe ? "true" : "false",public_size,
              injected_join_result ? "false" : "true",early_stop_attempted ? "true" : "false",early_stop_accepted ? "true" : "false",
              posts,in_posts,out_posts,iso_report_calls,ctrl_report_calls,stalls);
    for(u32 i=0;i<s->used;i++)fprintf(f,"%s{\"channel\":%u,\"id\":%u,\"status\":%u,\"active\":%s}",
        i ? "," : "",s->urbs[i].channel,s->urbs[i].id,s->urbs[i].status,s->urbs[i].active ? "true" : "false");
    fprintf(f,"]}\n");assert(fclose(f)==0);
}
