#include "ep0_session_runtime.h"
#include "ep0_diagnostic_file.h"
static Ep0SessionContext session_context;
static Ep0SaveReceipt session_receipt;
static Ep0SessionWork session_work;
static uint8_t session_bytes[EP0_REL_MAX];
static size_t session_size;
static atomic_uint session_phase; /* 0 unattempted, 1 capturing, 2 immutable, 3 rejected. */
bool Ep0SessionBind(uint64_t writer,const uint8_t boot[16],const uint8_t session[16],const uint8_t recipe[32]) {
    unsigned status=Ep0StartupStatus();
    if(status!=2 && status!=3)return false;
    return ep0_session_publish(&session_context,Ep0StartupWriterForSession(),writer,boot,session,recipe);
}
static bool session_capture(const uint8_t recipe[32],bool request,uint64_t exporter,uint32_t video,uint32_t audio,bool returned) {
    unsigned expected=0;
    if(!atomic_compare_exchange_strong_explicit(&session_phase,&expected,1,memory_order_acq_rel,memory_order_acquire))return false;
    unsigned status=Ep0StartupStatus();uint32_t rc=status>=2 ? Ep0StartupIdentityResult():0;
    const Ep0TraceOwner *owner=NULL;const Ep0GuardObservation *guard=NULL;const Ep0AdmissionObservation *admission=NULL;
    /* Never fetch possibly live EP0 getters on failed joins or absent context. */
    if(request && !video && !audio && atomic_load_explicit(&session_context.phase,memory_order_acquire)==2) {
        owner=Ep0CandidateObservation();guard=Ep0CandidateGuardObservation();admission=Ep0CandidateAdmissionObservation();
        if(returned) {
            size_t n=0;const uint8_t *input=Ep0CandidateDiagnosticBytes(&n);
            if(input && n)(void)ep0_save_receipt_publish(&session_receipt,true,Ep0CandidateDiagnosticFileObservation(),input,n);
        }
    }
    session_size=ep0_session_capture(Ep0StartupJournalForSession(),&session_context,status,rc,recipe,request,
        video,audio,exporter,owner,guard,admission,returned,&session_receipt,&session_work,session_bytes,sizeof(session_bytes));
    atomic_store_explicit(&session_phase,session_size ? 2:3,memory_order_release);return session_size!=0;
}
bool Ep0SessionStartupOnly(const uint8_t recipe[32]) { return session_capture(recipe,false,0,0,0,false); }
bool Ep0SessionJoined(const uint8_t recipe[32],uint64_t exporter,uint32_t video,uint32_t audio,bool returned) {
    return session_capture(recipe,true,exporter,video,audio,returned);
}
const uint8_t *Ep0SessionBytes(size_t *n) {
    bool ready=atomic_load_explicit(&session_phase,memory_order_acquire)==2;
    if(n)*n=ready ? session_size:0;
    return ready ? session_bytes:NULL;
}
