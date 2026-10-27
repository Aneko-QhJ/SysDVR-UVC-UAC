/* Appended only to the isolated copy of ep0_session_runtime.c. */
#include "ep0_execution_v3.h"
#include "ep0_candidate_file.h"
static Ep0ExecutionWindow execution_window;
static uint8_t execution_bytes[EP0_EXEC_MAX];
static size_t execution_size;
static atomic_uint execution_phase;
bool Ep0ExecutionWindowStarted(uint64_t start,uint64_t frequency,uint32_t ms) {
    return ep0_exec_start(&execution_window,start,frequency,ms);
}
bool Ep0ExecutionWindowReady(uint64_t at) { return ep0_exec_ready(&execution_window,at); }
bool Ep0ExecutionWindowStopped(uint64_t at,uint32_t reason) { return ep0_exec_stop(&execution_window,at,reason); }
bool Ep0ExecutionBuildJoined(uint64_t exporter,uint32_t video,uint32_t audio,unsigned kind,bool saved) {
    if(video || audio || !exporter || (kind!=1 && kind!=2))return false;
    unsigned expected=0;
    if(!atomic_compare_exchange_strong_explicit(&execution_phase,&expected,1,memory_order_acq_rel,memory_order_acquire))return false;
    size_t n=0;const uint8_t *primary=kind==1 ? Ep0CandidateBytes(&n):Ep0CandidateDiagnosticBytes(&n);
    const Ep0SinkState *sink=kind==1 ? Ep0CandidateFileObservation():Ep0CandidateDiagnosticFileObservation();
    unsigned status=Ep0StartupStatus();uint32_t identity=status>=2 ? Ep0StartupIdentityResult():0;
    execution_size=ep0_exec_capture(&session_context,&execution_window,Ep0StartupJournalForSession(),status,identity,
        exporter,video,audio,kind,primary,n,sink,saved,session_work.startup,execution_bytes,sizeof(execution_bytes));
    atomic_store_explicit(&execution_phase,execution_size?2:3,memory_order_release);return execution_size!=0;
}
const uint8_t *Ep0ExecutionBytes(size_t *n) {
    bool ready=atomic_load_explicit(&execution_phase,memory_order_acquire)==2;
    if(n)*n=ready ? execution_size:0;
    return ready ? execution_bytes:NULL;
}
