/* Offline pthread schedules. Store seeding near exhaustion is test injection. */
#include "a23_versioned_clock_candidate.h"
#include <pthread.h>
#include <stdio.h>
#include <string.h>
#include <inttypes.h>
#include <stdint.h>

typedef struct {
    const char *name;
    A23VersionedClockStore *store;
    A23CandidateClockStamp profile;
    uint64_t ticket;
    int begin_status,finish_status,abort_status;
    bool begin_attempted,tail_reached;
} Work;
static void *worker(void *opaque)
{
    Work *w=opaque;
    if(!strcmp(w->name,"exit-before-begin"))pthread_exit((void *)(uintptr_t)9);
    if(!strcmp(w->name,"error-before-begin")){w->tail_reached=true;return (void *)(uintptr_t)7;}
    if((!strcmp(w->name,"replacement-store") || !strcmp(w->name,"normal-readonly"))){w->tail_reached=true;return NULL;}
    w->begin_attempted=true;
    w->begin_status=(int)A23VersionedClockBegin(w->store,&w->ticket);
    if(w->begin_status==0){
        if(!strcmp(w->name,"unfinished-exit"))pthread_exit((void *)(uintptr_t)9);
        if(!strcmp(w->name,"unfinished-return") || !strcmp(w->name,"explicit-abort-after-join")){
            w->tail_reached=true;return (void *)(uintptr_t)7;
        }
        if(!strcmp(w->name,"abort-error")){
            w->abort_status=(int)A23VersionedClockAbort(w->store,w->ticket);
            w->tail_reached=true;return (void *)(uintptr_t)7;
        }
        if(!strcmp(w->name,"invalid-finish"))w->profile.numerator=0;
        uint64_t ticket=w->ticket+(!strcmp(w->name,"wrong-ticket") ? 2U : 0U);
        w->finish_status=(int)A23VersionedClockFinish(w->store,ticket,&w->profile);
    }
    w->tail_reached=true;return NULL;
}
typedef struct {unsigned calls;uint64_t ticks;} Reader;
static bool read_ticks(void *opaque,uint64_t *ticks)
{Reader *r=opaque;r->calls++;*ticks=r->ticks;return true;}
int main(int argc,char **argv)
{
    (void)argv;if(argc!=1)return 2;
    const char *names[]={"normal-readonly","normal-finish","error-before-begin","exit-before-begin","unfinished-return","unfinished-exit","abort-error","invalid-finish","wrong-ticket","exhausted-begin","last-finish-exhausted","replacement-store","explicit-abort-after-join"};
    printf("{\"schema\":\"A23-worker-failure-native-1\",\"cases\":[");
    for(unsigned i=0;i<sizeof(names)/sizeof(*names);i++){
        A23CandidateClockStamp profile={0,A23CandidateInjectedDriver,1,1,1};
        A23VersionedClockStore store,other;
        if(A23VersionedClockInit(&store,1,&profile)!=0 || A23VersionedClockInit(&other,1,&profile)!=0)return 3;
        if(!strcmp(names[i],"exhausted-begin"))atomic_store(&store.generation,UINT64_MAX-1);
        if(!strcmp(names[i],"last-finish-exhausted"))atomic_store(&store.generation,UINT64_MAX-3);
        Reader reader={0,100};A23VersionedClockSample begin,end;
        int pre=(int)A23VersionedClockCapture(&store,read_ticks,&reader,&begin);
        Work work={.name=names[i],.store=&store,.profile=profile,.begin_status=-1,.finish_status=-1,.abort_status=-1};
        pthread_t thread;int create=pthread_create(&thread,NULL,worker,&work);
        if(create!=0)return 4;
        void *status=NULL;int joined=pthread_join(thread,&status);if(joined!=0)return 5;
        int recovery=-1,retry=-1;
        if(!strcmp(names[i],"explicit-abort-after-join"))recovery=(int)A23VersionedClockAbort(&store,work.ticket);
        if(!strcmp(names[i],"last-finish-exhausted")){uint64_t ticket=0;retry=(int)A23VersionedClockBegin(&store,&ticket);}
        reader.ticks=250000100;
        A23VersionedClockStore *end_store=!strcmp(names[i],"replacement-store") ? &other : &store;
        memset(&end,0x5a,sizeof(end));
        int end_status=(int)A23VersionedClockCapture(end_store,read_ticks,&reader,&end);
        A23CandidateClockResult result={0};int evaluated=-1;
        if(pre==0 && end_status==0)evaluated=(int)A23VersionedClockEvaluate(&begin,&end,250000000,&result);
        bool zeroed=end.stamp.ticks==0 && end.stamp.domain==0 && end.stamp.clock_instance==0 && end.stamp.numerator==0 && end.stamp.denominator==0 && end.store_identity==NULL && end.incarnation==0 && end.generation==0;
        printf("%s{\"case\":\"%s\",\"worker\":{\"created\":true,\"joined\":true,\"join_status\":%d,\"exit_code\":%" PRIuPTR ",\"tail_reached\":%s,\"begin_attempted\":%s,\"begin_status\":%d,\"finish_status\":%d,\"abort_status\":%d,\"ticket\":%" PRIu64 "},",i ? "," : "",names[i],joined,(uintptr_t)status,work.tail_reached?"true":"false",work.begin_attempted?"true":"false",work.begin_status,work.finish_status,work.abort_status,work.ticket);
        printf("\"clock\":{\"pre_status\":%d,\"end_status\":%d,\"pre_generation\":%" PRIu64 ",\"end_generation\":%" PRIu64 ",\"generation\":%" PRIu64 ",\"poisoned\":%s,\"reader_calls\":%u,\"evaluate\":%d,\"minimum_met\":%s,\"end_zeroed\":%s,\"same_store\":%s,\"recovery_status\":%d,\"exhaustion_status\":%d}}",pre,end_status,begin.generation,end.generation,atomic_load(&store.generation),atomic_load(&store.poisoned)?"true":"false",reader.calls,evaluated,result.minimum_met?"true":"false",zeroed?"true":"false",begin.store_identity==end.store_identity?"true":"false",recovery,retry);
    }
    puts("],\"usb_requests\":0,\"sd_accesses\":0,\"real_sdk_objects\":0,\"actual_clock_queries\":0}");return 0;
}
