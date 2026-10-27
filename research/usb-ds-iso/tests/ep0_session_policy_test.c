#include <assert.h>
#include <stdio.h>
#define EP0_CANDIDATE_NATIVE
typedef unsigned Result;
typedef struct { unsigned unused; } UsbDsInterface;
typedef struct { unsigned unused; } UsbDsReportData;
#include "research/usb-ds-iso/device/ep0_session_capture.h"
static Ep0SessionWork work;static uint8_t out[EP0_REL_MAX];
static Ep0StartupJournal journal;static Ep0SessionContext context;
static Ep0TraceOwner owner;static Ep0GuardObservation guard;
static Ep0AdmissionObservation admission;static Ep0SaveReceipt receipt;
static uint8_t recipe[32]={3},boot[16]={1},session[16]={2};
static void file(const char *prefix,const char *name,size_t n) {
    assert(n);char path[1024];snprintf(path,sizeof(path),"%s-%s.bin",prefix,name);
    FILE *f=fopen(path,"wb");assert(f);assert(fwrite(out,1,n,f)==n);assert(!fclose(f));
}
static size_t capture(bool want,uint32_t video,uint32_t audio,bool returned,const Ep0SaveReceipt *r) {
    return ep0_session_capture(&journal,&context,2,0,recipe,want,video,audio,22,&owner,&guard,&admission,returned,r,&work,out,sizeof(out));
}
static void untouched(void) { for(unsigned i=0;i<sizeof(out);i++)assert(out[i]==0xa5); }
int main(int argc,char **argv) {
    assert(argc==2);unsigned tests=0;
    assert(ep0_startup_init(&journal,22,recipe));assert(ep0_startup_record(&journal,22,EP0_I_SM_INIT,EP0_I_CALL,0));
    assert(ep0_startup_record(&journal,22,EP0_I_SM_INIT,EP0_I_RESULT,0));assert(ep0_startup_seal(&journal,22));
    assert(ep0_session_publish(&context,22,11,boot,session,recipe));assert(!ep0_session_publish(&context,22,11,boot,session,recipe));tests++;
    assert(ep0_owner_init(&owner,11,1000,0,boot,session));owner.fault=1;
    assert(ep0_owner_freeze(&owner,11,10,EP0_TRACE_STOPPED));assert(ep0_owner_stop(&owner,11));assert(ep0_owner_handoff(&owner,22,0));
    admission.trace_refusals=1;admission.largest_request=17;
    Ep0TraceOwner before=owner;Ep0GuardObservation g_before=guard;Ep0AdmissionObservation a_before=admission;
    size_t n=capture(true,0,0,false,(void*)1);file(argv[1],"combined",n);tests++;
    assert(!memcmp(&before,&owner,sizeof(owner)) && !memcmp(&g_before,&guard,sizeof(guard)) && !memcmp(&a_before,&admission,sizeof(admission)));tests++;
    n=ep0_session_capture(&journal,&context,2,0,recipe,true,78,0,22,(void*)1,(void*)1,(void*)1,true,(void*)1,&work,out,sizeof(out));file(argv[1],"video-join-failed",n);tests++;
    n=ep0_session_capture(&journal,&context,2,0,recipe,true,0,79,22,(void*)1,(void*)1,(void*)1,true,(void*)1,&work,out,sizeof(out));file(argv[1],"audio-join-failed",n);tests++;
    n=ep0_session_capture(&journal,NULL,2,0,recipe,true,0,0,22,(void*)1,(void*)1,(void*)1,true,(void*)1,&work,out,sizeof(out));file(argv[1],"unbound",n);tests++;
    Ep0StartupJournal live={0};assert(ep0_startup_init(&live,22,recipe));assert(ep0_startup_record(&live,22,EP0_I_SM_INIT,EP0_I_CALL,0));
    n=ep0_session_capture(&live,NULL,2,0,recipe,false,0,0,0,(void*)1,(void*)1,(void*)1,true,(void*)1,&work,out,sizeof(out));file(argv[1],"live-startup",n);tests++;
    Ep0SessionContext publishing={0};atomic_store(&publishing.phase,1);
    n=ep0_session_capture(&journal,&publishing,2,0,recipe,true,0,0,22,(void*)1,(void*)1,(void*)1,true,(void*)1,&work,out,sizeof(out));file(argv[1],"context-publishing",n);tests++;
    n=ep0_session_capture(NULL,NULL,3,97,recipe,false,0,0,0,(void*)1,(void*)1,(void*)1,true,(void*)1,&work,out,sizeof(out));file(argv[1],"metadata",n);assert(n==EP0_REL_HEADER);tests++;
    uint8_t dia[EP0_DIAGNOSTIC_MAX];size_t bytes=ep0_diagnostic_capture(&owner,&guard,22,0,0,recipe,dia,sizeof(dia));assert(bytes);
    Ep0SinkState failed={.phase=EP0_SINK_COMMIT,.result=98,.attempted=true,.file_may_exist=true,.content_verified=true,.verified_bytes=bytes};
    assert(!ep0_save_receipt_publish(&receipt,false,(void*)1,(void*)1,bytes));assert(!atomic_load(&receipt.phase));tests++;
    assert(ep0_save_receipt_publish(&receipt,true,&failed,dia,bytes));assert(!ep0_save_receipt_publish(&receipt,true,&failed,dia,bytes));
    n=capture(true,0,0,true,&receipt);file(argv[1],"commit-error",n);tests++;
    n=capture(true,0,0,false,(void*)1);file(argv[1],"save-not-returned",n);tests++;
    Ep0SaveReceipt receipt_busy={0};atomic_store(&receipt_busy.phase,1);
    n=capture(true,0,0,true,&receipt_busy);file(argv[1],"receipt-publishing",n);tests++;
    Ep0SaveReceipt acknowledged={0};failed.phase=EP0_SINK_ACKNOWLEDGED;failed.result=0;failed.commit_acknowledged=true;
    assert(ep0_save_receipt_publish(&acknowledged,true,&failed,dia,bytes));n=capture(true,0,0,true,&acknowledged);file(argv[1],"acknowledged",n);tests++;
    uint8_t other[EP0_DIAGNOSTIC_MAX];memcpy(other,dia,bytes);other[bytes-1]^=1;
    Ep0SaveReceipt wrong={0};assert(ep0_save_receipt_publish(&wrong,true,&failed,other,bytes));
    memset(out,0xa5,sizeof(out));assert(!capture(true,0,0,true,&wrong));untouched();tests++;
    Ep0SessionContext mismatch={0};uint8_t wrong_boot[16]={9};assert(ep0_session_publish(&mismatch,22,11,wrong_boot,session,recipe));
    memset(out,0xa5,sizeof(out));assert(!ep0_session_capture(&journal,&mismatch,2,0,recipe,true,0,0,22,&owner,&guard,&admission,false,NULL,&work,out,sizeof(out)));untouched();tests++;
    Ep0SessionContext wrong_writer={0};assert(ep0_session_publish(&wrong_writer,23,11,boot,session,recipe));
    assert(!ep0_session_capture(&journal,&wrong_writer,2,0,recipe,false,0,0,22,(void*)1,(void*)1,(void*)1,false,NULL,&work,out,sizeof(out)));untouched();tests++;
    Ep0SessionContext wrong_worker={0};assert(ep0_session_publish(&wrong_worker,22,12,boot,session,recipe));
    assert(!ep0_session_capture(&journal,&wrong_worker,2,0,recipe,true,0,0,22,&owner,&guard,&admission,false,NULL,&work,out,sizeof(out)));untouched();tests++;
    admission.active=true;assert(!capture(true,0,0,false,NULL));untouched();admission.active=false;tests++;
    uint8_t other_recipe[32]={4};assert(!ep0_session_capture(&journal,&context,2,0,other_recipe,false,0,0,22,NULL,NULL,NULL,false,NULL,&work,out,sizeof(out)));untouched();tests++;
    assert(!ep0_session_capture(&journal,&context,2,0,recipe,true,0,0,22,&owner,&guard,&admission,false,NULL,&work,out,192));untouched();tests++;
    assert(!ep0_session_capture(&journal,&context,2,0,recipe,false,0,0,22,NULL,NULL,NULL,false,NULL,&work,(uint8_t*)&work,sizeof(work)));tests++;
    Ep0SessionContext no_starter={0};assert(ep0_session_publish(&no_starter,0,11,boot,session,recipe));
    n=ep0_session_capture(NULL,&no_starter,3,97,recipe,true,0,0,22,&owner,&guard,NULL,false,NULL,&work,out,sizeof(out));file(argv[1],"ep0-only",n);tests++;
    Ep0StartupJournal full={0};assert(ep0_startup_init(&full,22,recipe));
    for(unsigned i=0;i<64;i++)assert(ep0_startup_record(&full,22,EP0_I_FS_INIT,(i&1) ? EP0_I_RESULT:EP0_I_CALL,0));assert(ep0_startup_seal(&full,22));
    Ep0TraceOwner max={0};assert(ep0_owner_init(&max,11,1000,0,boot,session));
    for(unsigned i=0;i<16;i++)assert(ep0_owner_post(&max,11,4,0,true,100+i));
    for(unsigned i=0;i<128;i++) { Ep0TraceRecord r={.stage=EP0_T_DEVICE_STATE,.interface_index=255,.begin=1,.end=1};assert(ep0_trace_append(&max.trace,&r)); }
    max.trace.dropped=1;max.fault=1;assert(ep0_owner_freeze(&max,11,10,EP0_TRACE_STOPPED));assert(ep0_owner_stop(&max,11));assert(ep0_owner_handoff(&max,22,0));
    n=ep0_session_capture(&full,&context,2,0,recipe,true,0,0,22,&max,&guard,NULL,false,NULL,&work,out,sizeof(out));assert(n==EP0_REL_MAX);file(argv[1],"maximum",n);tests++;
    printf("{\"passed\":true,\"cases\":%u,\"maximum\":%u,\"work_bytes\":%zu,\"failed_join_poison_inputs_rejected\":true,\"source_immutable\":true,\"fs_calls\":0,\"hardware_verified\":false}\n",tests,EP0_REL_MAX,sizeof(work));
}
