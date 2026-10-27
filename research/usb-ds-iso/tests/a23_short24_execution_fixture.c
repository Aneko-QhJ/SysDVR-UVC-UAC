/* Fully synthetic EXE3/OWN2/TRC2 using the candidate's actual serializers.
 * Reports, joins and save receipts below are model inputs, not SDK results. */
#include <assert.h>
#include <stdio.h>
#include <stdint.h>
#define EP0_CANDIDATE_NATIVE 1
typedef uint32_t Result;
typedef struct UsbDsReportData UsbDsReportData;
typedef struct UsbDsInterface UsbDsInterface;
#include "ep0_execution_v3.h"
#include "ep0_candidate_recipe.h"
#include "iso_probe_protocol.h"
static Ep0TraceOwner owner;
static uint64_t tick=4;
static uint32_t request_id,control_id;
static uint8_t setup[8];
static void record(unsigned stage,unsigned flags,unsigned a0,unsigned a1) {
    Ep0TraceRecord row={.begin=tick,.end=tick+1,.request_id=request_id,.stage=stage,.interface_index=2,
        .flags=flags,.arg0=a0,.arg1=a1};tick+=2;
    if(flags&1)memcpy(row.setup,setup,8);
    assert(ep0_trace_append(&owner.trace,&row));
}
static void terminal(unsigned channel,unsigned id) {
    Ep0OwnerReport report={.id=id,.status=3};assert(ep0_owner_reports(&owner,11,channel,0,&report,1));
}
static void helper(bool in,unsigned length) {
    unsigned dir=in?8:0,id=++control_id;
    record(8,dir,0,0);record(9,dir|6,length,id);
    assert(ep0_owner_post(&owner,11,in?4:5,0,true,id));
    record(10,dir|2,id,0);record(11,dir,0,0);record(12,dir,0,0);
    record(13,dir|6,length,id);terminal(in?4:5,id);
}
static void request(bool burst,bool after) {
    request_id++;memcpy(setup,burst?(uint8_t[]){0x41,0x54,1,0,2,0,0,0}:
        (uint8_t[]){0xc1,0x51,0,0,2,0,168,0},8);
    assert(ep0_trace_poll(&owner.trace,2,0));assert(ep0_owner_enter(&owner,11));
    record(1,0,0,0);record(2,0,0,0);record(3,1,0,0);record(4,7,after?2:0,after?1:0);
    if(burst) {
        record(5,2,3,0);record(6,6,1,0);
        record(7,6,ISO_PROBE_PACKET_SIZE*ISO_PROBE_BURST_PACKETS,101);
        assert(ep0_owner_post(&owner,11,8,0,true,101));helper(true,0);record(14,8,0,0);terminal(8,101);
    } else {record(15,6,after?2:0,after?1:0);helper(true,168);helper(false,0);}
    assert(ep0_owner_leave(&owner,11));
}
int main(int argc,char **argv) {
    assert(argc==3);uint8_t boot[16]={1},session[16]={2};
    assert(ep0_owner_init(&owner,11,1000,1,boot,session));
    request(false,false);request(true,false);request(false,true);
    assert(ep0_owner_freeze(&owner,11,1000,2));assert(ep0_owner_stop(&owner,11));
    assert(ep0_owner_handoff(&owner,22,0));
    static uint8_t primary[EP0_CAPTURE_MAX],work[EP0_INIT_MAX],execution[EP0_EXEC_MAX];
    size_t n=ep0_candidate_capture(&owner,22,ep0CandidateRecipe,primary,sizeof(primary));assert(n);
    Ep0SessionContext context={.ep0_writer=11};atomic_init(&context.phase,2);
    memcpy(context.boot,boot,16);memcpy(context.session,session,16);memcpy(context.recipe,ep0CandidateRecipe,32);
    Ep0ExecutionWindow window={0};assert(ep0_exec_start(&window,2,1000,30000));
    assert(ep0_exec_ready(&window,3));assert(ep0_exec_stop(&window,1000,2));
    Ep0StartupJournal journal={0};Ep0SinkState receipt={.phase=9,.attempted=true,.file_may_exist=true,
        .content_verified=true,.commit_acknowledged=true,.verified_bytes=n};
    size_t total=ep0_exec_capture(&context,&window,&journal,3,0,22,0,0,1,primary,n,&receipt,true,
        work,execution,sizeof(execution));assert(total);
    FILE *f=fopen(argv[1],"wbx");assert(f);assert(fwrite(execution,1,total,f)==total);assert(!fclose(f));
    f=fopen(argv[2],"wbx");assert(f);assert(fwrite(primary,1,n,f)==n);assert(!fclose(f));
    printf("{\"simulation\":true,\"requests\":3,\"records\":%u,\"execution_bytes\":%zu}\n",owner.trace.count,total);
    return 0;
}
