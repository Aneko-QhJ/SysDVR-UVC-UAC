/* Appended after sealed V2 serialization helpers and candidate file/runtime
 * bodies. The actual generated main EXIT BRANCH is inserted below. All FS,
 * joins, identity results and terminal observations remain simulated. */
static Ep0CleanupGate ep0Cleanup;
static bool g_running=true,normal_kind;
static int g_videoThread,g_audioThread;
static unsigned thread_closes;
static jmp_buf retained_jump;
static Result threadWaitForExit(const int *thread) {
    if(thread==&g_videoThread && !strcmp(primary_fault,"video-join-error"))return 78;
    if(thread==&g_audioThread && !strcmp(primary_fault,"audio-join-error"))return 79;
    return 0;
}
#define CUR_THREAD_HANDLE 0
#define LOG(...) ((void)0)
static Result svcGetThreadId(uint64_t *out,int handle) {
    (void)handle;if(!strcmp(primary_fault,"identity-error"))return 80;*out=22;return 0;
}
static void svcSleepThread(double ns) { assert(ns==1E+9);longjmp(retained_jump,1); }
static void threadClose(const int *thread) { (void)thread;thread_closes++; }
bool Ep0CandidateFinish(uint64_t exporter,uint32_t join) {
    assert(!poison && exporter==22 && join==0);return normal_kind;
}
static const uint8_t ep0CandidateRecipe[32]={3};
static int replay_exit(void) {
/* ACTUAL_EXIT_TAIL */

int main(int argc,char **argv) {
    assert(argc==5);normal_kind=!strcmp(argv[1],"normal");
    assert(normal_kind || !strcmp(argv[1],"diagnostic"));primary_fault=argv[2];execution_fault=argv[3];
    fault="ok";maxima();normal_available=normal_kind;if(normal_kind)owner.fault=0;
    assert(Ep0SessionBind(11,boot,session,recipe));
    assert(Ep0ExecutionWindowStarted(2,1000,30000));assert(Ep0ExecutionWindowReady(4));
    assert(Ep0ExecutionWindowStopped(10,2));
    assert(!Ep0ExecutionWindowStarted(2,1000,30000));assert(!Ep0ExecutionWindowReady(5));
    assert(!Ep0ExecutionWindowStopped(11,2));
    uint32_t normal_crc=ep0_trace_crc32(normal_bytes,normal_n),dia_crc=ep0_trace_crc32(dia_bytes,dia_n);
    poison=!strcmp(primary_fault,"video-join-error") || !strcmp(primary_fault,"audio-join-error");
    image[0]=0x7a;image_n=1;
    bool retained=false;int exit_code=-1;
    if(setjmp(retained_jump))retained=true;else exit_code=replay_exit();
    if(poison || !strcmp(primary_fault,"identity-error")) {
        assert(!fs_open && !owner_reads && !guard_reads && !normal_reads && !thread_closes);
        assert(retained);poison=false;
    }
    size_t n=0;const uint8_t *bytes=Ep0ExecutionBytes(&n);
    if(bytes) {
        assert(n<=EP0_EXEC_MAX);save(argv[4],"execution.bin",bytes,n);
        if(!strcmp(primary_fault,"ok") && !strcmp(execution_fault,"ok")) {
            static uint8_t small[EP0_EXEC_MAX];memset(small,0xa5,sizeof(small));
            size_t primary_n=0;const uint8_t *primary=normal_kind?Ep0CandidateBytes(&primary_n):Ep0CandidateDiagnosticBytes(&primary_n);
            const Ep0SinkState *receipt=normal_kind?Ep0CandidateFileObservation():Ep0CandidateDiagnosticFileObservation();
            assert(!ep0_exec_capture(&session_context,&execution_window,&journal,2,0,22,0,0,normal_kind?1:2,
                primary,primary_n,receipt,true,session_work.startup,small,n-1));
            for(size_t i=0;i<sizeof(small);i++)assert(small[i]==0xa5);
            assert(!ep0_exec_capture((void*)1,(void*)1,(void*)1,2,0,22,1,0,1,(void*)1,100,(void*)1,false,(void*)1,(void*)1,100));
            assert(!ep0_exec_receipt(receipt,primary_n,false));
        }
        unsigned calls=fs_open+creates+writes+reads+commits;
        assert(!Ep0ExecutionBuildJoined(22,0,0,normal_kind?1:2,false));
        assert(!Ep0ExecutionSaveJoined(0,0));assert(calls==fs_open+creates+writes+reads+commits);
    }
    assert(!opened);
    if(fs_open==1) { primary_image_n=image_n;memcpy(primary_image,image,image_n); }
    if(primary_image_n)save(argv[4],"primary.disk.bin",primary_image,primary_image_n);
    if(fs_open>=2)save(argv[4],"execution.disk.bin",image,image_n);
    bool primary_good=!strcmp(primary_fault,"ok") || !strcmp(primary_fault,"short-read");
    bool execution_good=!strcmp(execution_fault,"ok") || !strcmp(execution_fault,"short-read");
    bool expected_cleanup=normal_kind && primary_good && execution_good;
    assert((thread_closes==2)==expected_cleanup);assert(retained!=expected_cleanup);
    assert(ep0_trace_crc32(normal_bytes,normal_n)==normal_crc && ep0_trace_crc32(dia_bytes,dia_n)==dia_crc);
    if(expected_cleanup)assert(exit_code==0);
    const Ep0SinkState *sink=Ep0ExecutionFileObservation();
    printf("{\"kind\":\"%s\",\"primary_fault\":\"%s\",\"execution_fault\":\"%s\","
        "\"retained\":%s,\"thread_closes\":%u,\"fs_open\":%u,\"execution_bytes\":%zu,"
        "\"execution_save_acknowledged\":%s,\"execution_content_verified\":%s,\"simulation\":true}\n",
        argv[1],primary_fault,execution_fault,retained?"true":"false",thread_closes,fs_open,n,
        sink->commit_acknowledged?"true":"false",sink->content_verified?"true":"false");
}
