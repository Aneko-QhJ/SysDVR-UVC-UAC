#include <assert.h>
#include <pthread.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdatomic.h>
#define EP0_CANDIDATE_NATIVE
#define CUR_THREAD_HANDLE 0
typedef unsigned Result;
typedef struct { unsigned unused; } UsbDsInterface;
typedef struct { unsigned unused; } UsbDsReportData;
#include "research/usb-ds-iso/device/ep0_session_runtime.h"
static const char *scenario;
static uint8_t recipe[32]={3},boot[16]={1},nonce[16]={2};
static atomic_uint identity_queries,owner_reads,guard_reads,admission_reads,receipt_reads,diagnostic_reads,winners;
static atomic_bool reached,resume_capture;
static bool block_status,interrupt_capture,poison_ep0,poison_receipt;
static Result svcGetThreadId(uint64_t *id,unsigned handle) { (void)handle;atomic_fetch_add(&identity_queries,1);*id=22;return 0; }
#define Ep0StartupStatus RawStartupStatus
/* INSERT_STARTUP_RUNTIME */
#undef Ep0StartupStatus
static atomic_bool status_entered;
unsigned Ep0StartupStatus(void) {
    unsigned status=RawStartupStatus();
    bool expected=false;
    if(block_status && atomic_compare_exchange_strong(&status_entered,&expected,true)) {
        atomic_store_explicit(&reached,true,memory_order_release);
        while(!atomic_load_explicit(&resume_capture,memory_order_acquire))sched_yield();
        if(interrupt_capture)pthread_exit(NULL);
    }
    return status;
}
/* INSERT_BRIDGE */
static Ep0TraceOwner test_owner;
static Ep0GuardObservation test_guard;
static Ep0AdmissionObservation test_admission;
static Ep0SinkState test_sink;
static uint8_t test_diagnostic[EP0_DIAGNOSTIC_MAX];static size_t test_diagnostic_n;
const Ep0TraceOwner *Ep0CandidateObservation(void) { atomic_fetch_add(&owner_reads,1);assert(!poison_ep0);return &test_owner; }
const Ep0GuardObservation *Ep0CandidateGuardObservation(void) { atomic_fetch_add(&guard_reads,1);assert(!poison_ep0);return &test_guard; }
const Ep0AdmissionObservation *Ep0CandidateAdmissionObservation(void) { atomic_fetch_add(&admission_reads,1);assert(!poison_ep0);return &test_admission; }
const uint8_t *Ep0CandidateDiagnosticBytes(size_t *n) { atomic_fetch_add(&diagnostic_reads,1);assert(!poison_receipt);*n=test_diagnostic_n;return test_diagnostic; }
const Ep0SinkState *Ep0CandidateDiagnosticFileObservation(void) { atomic_fetch_add(&receipt_reads,1);assert(!poison_receipt);return &test_sink; }
/* INSERT_SESSION_RUNTIME */
static void *capture_owner(void *arg) {
    bool joined=(uintptr_t)arg;
    bool ok=joined ? Ep0SessionJoined(recipe,22,0,0,true):Ep0SessionStartupOnly(recipe);
    if(ok)atomic_fetch_add(&winners,1);
    return NULL;
}
static void *bind_owner(void *arg) { (void)arg;assert(Ep0SessionBind(11,boot,nonce,recipe));return NULL; }
static void *bytes_reader(void *arg) {
    (void)arg;
    size_t n=0;const uint8_t *p;
    do { p=Ep0SessionBytes(&n);if(!p)assert(!n); } while(!p && atomic_load_explicit(&session_phase,memory_order_acquire)<2);
    if(p)assert(n>=EP0_REL_HEADER && !memcmp(p,"EP0REL1",7));
    return NULL;
}
static bool is(const char *s) { return !strcmp(scenario,s); }
int main(int argc,char **argv) {
    assert(argc==3);scenario=argv[1];
    if(!is("failed-bind")) {
        assert(Ep0StartupBegin(recipe));Ep0StartupCall(EP0_I_SM_INIT);Ep0StartupResult(EP0_I_SM_INIT,0);assert(Ep0StartupSeal());
    }
    assert(ep0_owner_init(&test_owner,11,1000,0,boot,nonce));test_owner.fault=1;
    assert(ep0_owner_freeze(&test_owner,11,10,EP0_TRACE_STOPPED));assert(ep0_owner_stop(&test_owner,11));assert(ep0_owner_handoff(&test_owner,22,0));
    test_diagnostic_n=ep0_diagnostic_capture(&test_owner,&test_guard,22,0,0,recipe,test_diagnostic,sizeof(test_diagnostic));assert(test_diagnostic_n==256);
    test_sink=(Ep0SinkState){.phase=9,.attempted=true,.file_may_exist=true,.content_verified=true,.commit_acknowledged=true,.verified_bytes=test_diagnostic_n};
    if(is("capture-busy") || is("capture-interrupted")) {
        block_status=true;interrupt_capture=is("capture-interrupted");poison_ep0=true;poison_receipt=true;
        pthread_t t;assert(!pthread_create(&t,NULL,capture_owner,(void*)0));
        while(!atomic_load_explicit(&reached,memory_order_acquire))sched_yield();
        size_t n=9;assert(!Ep0SessionBytes(&n) && !n);
        assert(!Ep0SessionStartupOnly((void*)1));
        atomic_store_explicit(&resume_capture,true,memory_order_release);assert(!pthread_join(t,NULL));
        if(interrupt_capture)assert(atomic_load(&session_phase)==1 && !atomic_load(&winners));
    } else if(is("context-publishing")) {
        atomic_store(&session_context.phase,1);session_context.ep0_writer=999;poison_ep0=true;poison_receipt=true;
        assert(Ep0SessionJoined(recipe,22,0,0,true));
    } else if(is("receipt-publishing")) {
        assert(Ep0SessionBind(11,boot,nonce,recipe));atomic_store(&session_receipt.phase,1);session_receipt.input_crc=0xbad;
        assert(Ep0SessionJoined(recipe,22,0,0,true));assert(atomic_load(&session_receipt.phase)==1);
    } else if(is("capture-rejected")) {
        uint8_t bad[32]={4};assert(!Ep0SessionStartupOnly(bad));assert(atomic_load(&session_phase)==3);
    } else if(is("failed-join")) {
        assert(Ep0SessionBind(11,boot,nonce,recipe));poison_ep0=true;poison_receipt=true;
        assert(Ep0SessionJoined(recipe,22,78,0,true));
    } else if(is("nonreturned-receipt")) {
        assert(Ep0SessionBind(11,boot,nonce,recipe));poison_receipt=true;
        assert(Ep0SessionJoined(recipe,22,0,0,false));assert(!atomic_load(&receipt_reads) && !atomic_load(&diagnostic_reads));
    } else if(is("startup-during-bind")) {
        poison_ep0=true;poison_receipt=true;pthread_t t;assert(!pthread_create(&t,NULL,bind_owner,NULL));
        assert(Ep0SessionStartupOnly(recipe));assert(!pthread_join(t,NULL));
    } else if(is("full-race")) {
        assert(Ep0SessionBind(11,boot,nonce,recipe));pthread_t a,b,c,d;
        assert(!pthread_create(&a,NULL,capture_owner,(void*)1));assert(!pthread_create(&b,NULL,capture_owner,(void*)1));assert(!pthread_create(&c,NULL,capture_owner,(void*)1));assert(!pthread_create(&d,NULL,bytes_reader,NULL));
        assert(!pthread_join(a,NULL));assert(!pthread_join(b,NULL));assert(!pthread_join(c,NULL));assert(!pthread_join(d,NULL));
        assert(atomic_load(&winners)==1 && atomic_load(&owner_reads)==1 && atomic_load(&receipt_reads)==1);
    } else if(is("pre-bind-snapshot")) {
        poison_ep0=true;poison_receipt=true;assert(Ep0SessionStartupOnly(recipe));assert(Ep0SessionBind(11,boot,nonce,recipe));assert(!Ep0SessionJoined((void*)1,22,0,0,true));
    } else if(is("failed-bind")) {
        poison_ep0=true;poison_receipt=true;assert(!Ep0SessionBind(11,boot,nonce,recipe));assert(Ep0SessionStartupOnly(recipe));
    } else assert(false);
    size_t n=0;const uint8_t *bytes=Ep0SessionBytes(&n);
    assert(!Ep0SessionStartupOnly((void*)1));size_t again=9;assert(Ep0SessionBytes(&again)==bytes && again==n);
    if(bytes) { FILE *f=fopen(argv[2],"wb");assert(f);assert(fwrite(bytes,1,n,f)==n);assert(!fclose(f)); }
    printf("{\"case\":\"%s\",\"passed\":true,\"phase\":%u,\"bytes\":%zu,\"context_phase\":%u,\"receipt_phase\":%u,\"identity_queries\":%u,\"owner_reads\":%u,\"receipt_reads\":%u,\"winners\":%u,\"immutable_output\":true,\"usb_calls\":0,\"fs_calls\":0,\"hardware_verified\":false}\n",scenario,atomic_load(&session_phase),n,atomic_load(&session_context.phase),atomic_load(&session_receipt.phase),atomic_load(&identity_queries),atomic_load(&owner_reads),atomic_load(&receipt_reads),atomic_load(&winners));
}
