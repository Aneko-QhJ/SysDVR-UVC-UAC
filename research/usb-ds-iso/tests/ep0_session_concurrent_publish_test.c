#include <assert.h>
#include <pthread.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#define EP0_CANDIDATE_NATIVE
typedef unsigned Result;
typedef struct { unsigned unused; } UsbDsInterface;
typedef struct { unsigned unused; } UsbDsReportData;
static atomic_uint *pause_token;
static atomic_bool reached,resume_publish;
static bool interrupt_publish;
static void publication_boundary(atomic_uint *token) {
    if(token!=pause_token)return;
    atomic_store_explicit(&reached,true,memory_order_release);
    while(!atomic_load_explicit(&resume_publish,memory_order_acquire))sched_yield();
    if(interrupt_publish)pthread_exit(NULL);
}
/* Exact sealed header with two pre-release test hooks, generated beside this file. */
#include "ep0_session_capture.h"
static uint8_t recipe[32]={3},boot[16]={1},session[16]={2};
static Ep0StartupJournal journal;
static Ep0TraceOwner owner;
static Ep0GuardObservation guard;
static Ep0SessionContext bound;
static Ep0SessionWork work;
static uint8_t out[EP0_REL_MAX],dia[EP0_DIAGNOSTIC_MAX];
static size_t dia_n;
static Ep0SinkState ack,error;
static Ep0SessionContext contexts[32];
static Ep0SaveReceipt receipts[32];
static atomic_bool race_start,blank_observed;
static atomic_uint publishers_done,context_wins,receipt_wins;
static unsigned context_reads,receipt_reads,unbound_reads,unpublished_receipt_reads;
static uint32_t u32(const uint8_t *p) { return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24; }
static void save(const char *prefix,const char *name,size_t n) {
    char path[1024];snprintf(path,sizeof(path),"%s-%s.bin",prefix,name);assert(n);
    FILE *f=fopen(path,"wb");assert(f);assert(fwrite(out,1,n,f)==n);assert(!fclose(f));
}
static size_t capture(const Ep0SessionContext *c,bool want,const Ep0SaveReceipt *r,bool returned) {
    return ep0_session_capture(&journal,c,2,0,recipe,want,0,0,22,
        want ? &owner:(void*)1,want ? &guard:(void*)1,NULL,returned,r,&work,out,sizeof(out));
}
static void *context_publisher(void *arg) {
    unsigned role=(unsigned)(uintptr_t)arg;uint8_t b[16]={1+role},s[16]={2+role};
    while(!atomic_load_explicit(&race_start,memory_order_acquire))sched_yield();
    while(!atomic_load_explicit(&blank_observed,memory_order_acquire))sched_yield();
    for(unsigned i=0;i<32;i++)if(ep0_session_publish(&contexts[i],22,11+role,b,s,recipe))atomic_fetch_add(&context_wins,1);
    atomic_fetch_add_explicit(&publishers_done,1,memory_order_release);return NULL;
}
static void *context_reader(void *arg) {
    (void)arg;while(!atomic_load_explicit(&race_start,memory_order_acquire))sched_yield();
    for(unsigned i=0;i<32;i++) { assert(capture(&contexts[i],false,(void*)1,true)==320 && !(out[16]&16));unbound_reads++; }
    atomic_store_explicit(&blank_observed,true,memory_order_release);
    do {
        for(unsigned i=0;i<32;i++) {
            size_t n=capture(&contexts[i],false,(void*)1,true);assert(n==320);
            if(out[16]&16) {
                uint64_t w=ep0_rel_u64(out+104);assert(w==11 || w==12);
                assert(out[112]==w-10 && out[128]==w-9);context_reads++;
            } else { assert(!ep0_rel_u64(out+104));unbound_reads++; }
        }
    } while(atomic_load_explicit(&publishers_done,memory_order_acquire)<2);
    for(unsigned i=0;i<32;i++) { assert(capture(&contexts[i],false,(void*)1,true)==320 && (out[16]&16));context_reads++; }
    return NULL;
}
static void *receipt_publisher(void *arg) {
    const Ep0SinkState *s=(uintptr_t)arg ? &error:&ack;
    while(!atomic_load_explicit(&race_start,memory_order_acquire))sched_yield();
    while(!atomic_load_explicit(&blank_observed,memory_order_acquire))sched_yield();
    for(unsigned i=0;i<32;i++)if(ep0_save_receipt_publish(&receipts[i],true,s,dia,dia_n))atomic_fetch_add(&receipt_wins,1);
    atomic_fetch_add_explicit(&publishers_done,1,memory_order_release);return NULL;
}
static void *receipt_reader(void *arg) {
    (void)arg;while(!atomic_load_explicit(&race_start,memory_order_acquire))sched_yield();
    for(unsigned i=0;i<32;i++) { assert(capture(&bound,true,&receipts[i],true)==576 && !(out[16]&64));unpublished_receipt_reads++; }
    atomic_store_explicit(&blank_observed,true,memory_order_release);
    do {
        for(unsigned i=0;i<32;i++) {
            size_t n=capture(&bound,true,&receipts[i],true);assert(n==576);
            if(out[16]&64) {
                assert(u32(out+188)==ep0_trace_crc32(dia,dia_n));
                assert((u32(out+72)==9 && u32(out+76)==0 && out[80]==15) ||
                       (u32(out+72)==8 && u32(out+76)==98 && out[80]==7));receipt_reads++;
            }
        }
    } while(atomic_load_explicit(&publishers_done,memory_order_acquire)<2);
    for(unsigned i=0;i<32;i++) { assert(capture(&bound,true,&receipts[i],true)==576 && (out[16]&64));receipt_reads++; }
    return NULL;
}
static void run_race(void *(*publisher)(void *),void *(*reader)(void *)) {
    atomic_store(&race_start,false);atomic_store(&blank_observed,false);atomic_store(&publishers_done,0);
    pthread_t a,b,c;assert(!pthread_create(&a,NULL,publisher,(void*)0));assert(!pthread_create(&b,NULL,publisher,(void*)1));assert(!pthread_create(&c,NULL,reader,NULL));
    atomic_store_explicit(&race_start,true,memory_order_release);
    assert(!pthread_join(a,NULL));assert(!pthread_join(b,NULL));assert(!pthread_join(c,NULL));
}
static Ep0SessionContext paused_context;
static Ep0SaveReceipt paused_receipt;
static void *paused_publisher(void *arg) {
    if(arg)assert(ep0_save_receipt_publish(&paused_receipt,true,&ack,dia,dia_n));
    else assert(ep0_session_publish(&paused_context,22,11,boot,session,recipe));
    return NULL;
}
static pthread_t begin_pause(bool receipt,bool interrupt) {
    paused_context=(Ep0SessionContext){0};paused_receipt=(Ep0SaveReceipt){0};
    atomic_store(&reached,false);atomic_store(&resume_publish,false);interrupt_publish=interrupt;
    pause_token=receipt ? &paused_receipt.phase:&paused_context.phase;
    pthread_t t;assert(!pthread_create(&t,NULL,paused_publisher,(void*)(uintptr_t)receipt));
    while(!atomic_load_explicit(&reached,memory_order_acquire))sched_yield();return t;
}
static void end_pause(pthread_t t) { atomic_store_explicit(&resume_publish,true,memory_order_release);assert(!pthread_join(t,NULL));pause_token=NULL; }
int main(int argc,char **argv) {
    assert(argc==2);unsigned cases=0;
    assert(ep0_startup_init(&journal,22,recipe));assert(ep0_startup_record(&journal,22,EP0_I_SM_INIT,EP0_I_CALL,0));assert(ep0_startup_record(&journal,22,EP0_I_SM_INIT,EP0_I_RESULT,0));assert(ep0_startup_seal(&journal,22));
    assert(ep0_session_publish(&bound,22,11,boot,session,recipe));assert(ep0_owner_init(&owner,11,1000,0,boot,session));owner.fault=1;
    assert(ep0_owner_freeze(&owner,11,10,EP0_TRACE_STOPPED));assert(ep0_owner_stop(&owner,11));assert(ep0_owner_handoff(&owner,22,0));
    dia_n=ep0_diagnostic_capture(&owner,&guard,22,0,0,recipe,dia,sizeof(dia));assert(dia_n==256);
    ack=(Ep0SinkState){.phase=9,.attempted=true,.file_may_exist=true,.content_verified=true,.commit_acknowledged=true,.verified_bytes=dia_n};error=ack;error.phase=8;error.result=98;error.commit_acknowledged=false;
    Ep0TraceOwner before=owner;Ep0GuardObservation g_before=guard;
    run_race(context_publisher,context_reader);assert(atomic_load(&context_wins)==32 && context_reads);cases++;
    for(unsigned i=0;i<32;i++) { char name[64];snprintf(name,sizeof(name),"context-%u",i);save(argv[1],name,capture(&contexts[i],false,(void*)1,true)); }
    run_race(receipt_publisher,receipt_reader);assert(atomic_load(&receipt_wins)==32 && receipt_reads);cases++;
    for(unsigned i=0;i<32;i++) { char name[64];snprintf(name,sizeof(name),"receipt-%u",i);save(argv[1],name,capture(&bound,true,&receipts[i],true)); }
    pthread_t t=begin_pause(false,false);assert(atomic_load(&paused_context.phase)==1);
    size_t n=capture(&paused_context,false,(void*)1,true);assert(!(out[16]&16));save(argv[1],"context-before-release",n);cases++;
    n=ep0_session_capture(&journal,&paused_context,2,0,recipe,true,0,0,22,(void*)1,(void*)1,(void*)1,true,(void*)1,&work,out,sizeof(out));assert(n==320 && u32(out+24)==2);cases++;
    assert(!ep0_session_publish(&paused_context,22,11,boot,session,recipe));cases++;end_pause(t);
    t=begin_pause(false,true);end_pause(t);assert(atomic_load(&paused_context.phase)==1);
    n=capture(&paused_context,false,(void*)1,true);assert(!(out[16]&16));save(argv[1],"context-interrupted",n);cases++;
    t=begin_pause(true,false);assert(atomic_load(&paused_receipt.phase)==1);
    n=capture(&bound,true,&paused_receipt,true);assert(!(out[16]&64));save(argv[1],"receipt-before-release",n);cases++;
    n=capture(&bound,true,(void*)1,false);assert(!(out[16]&64));cases++;
    assert(!ep0_save_receipt_publish(&paused_receipt,true,&ack,dia,dia_n));cases++;end_pause(t);
    t=begin_pause(true,true);end_pause(t);assert(atomic_load(&paused_receipt.phase)==1);
    n=capture(&bound,true,&paused_receipt,true);assert(!(out[16]&64));save(argv[1],"receipt-interrupted",n);cases++;
    assert(!memcmp(&owner,&before,sizeof(before)) && !memcmp(&guard,&g_before,sizeof(guard)));
    printf("{\"passed\":true,\"cases\":%u,\"cpu_threads_per_race\":3,\"context_objects\":32,\"receipt_objects\":32,\"context_winners\":%u,\"receipt_winners\":%u,\"context_reads\":%u,\"receipt_reads\":%u,\"unbound_reads\":%u,\"unpublished_receipt_reads\":%u,\"interrupted_phase\":1,\"poison_bypasses_passed\":true,\"owner_immutable\":true,\"usb_calls\":0,\"fs_calls\":0,\"hardware_verified\":false}\n",cases,atomic_load(&context_wins),atomic_load(&receipt_wins),context_reads,receipt_reads,unbound_reads,unpublished_receipt_reads);
}
