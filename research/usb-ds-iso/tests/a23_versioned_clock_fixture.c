#include "../host/a23_versioned_clock_candidate.h"
#include <assert.h>
#include <inttypes.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>

static const char *names[]={"normal","fractional-short","fractional-equal","fractional-after","zero-tick","backwards","overflow",
    "invalid-domain","invalid-instance","invalid-numerator","invalid-denominator","invalid-incarnation",
    "during-numerator","during-denominator","during-domain","during-instance","start-aba","end-aba",
    "between-aba","between-noop","between-abort","between-numerator","busy-before","busy-during","nested-writer",
    "reader-failure","nil-reader","nil-store","poisoned","zero-generation","last-write","exhaustion","invalid-finish",
    "stale-ticket","wrong-ticket","other-store","other-incarnation","after-end-publish","bypass-aba","bypass-between",
    "thread-start-aba","thread-end-aba","thread-contender"};
typedef struct {
    A23VersionedClockStore *store;
    A23CandidateClockStamp base;
    const char *name;
    unsigned reads,mutations,threads;
    unsigned when;
    uint64_t ticks,ticket;
    A23VersionedClockStatus writer_status;
} Context;
static bool equal(const char *a,const char *b){return strcmp(a,b)==0;}
static bool zero(const A23VersionedClockSample *s)
{
    return !s->stamp.ticks && !s->stamp.domain && !s->stamp.clock_instance && !s->stamp.numerator && !s->stamp.denominator &&
        !s->store_identity && !s->incarnation && !s->generation;
}
static void publish(Context *c,A23CandidateClockStamp profile)
{
    c->writer_status=A23VersionedClockPublish(c->store,&profile);assert(c->writer_status==A23VersionedClockOK);++c->mutations;
}
static void aba(Context *c)
{
    A23CandidateClockStamp changed=c->base;changed.numerator=2;publish(c,changed);publish(c,c->base);
}
static void *worker(void *argument)
{
    Context *c=argument;
    if(equal(c->name,"thread-contender")){
        uint64_t ticket=99;c->writer_status=A23VersionedClockBegin(c->store,&ticket);assert(c->writer_status==A23VersionedClockBusy && !ticket);
    }else aba(c);
    return 0;
}
static void thread(Context *c)
{
    pthread_t t;assert(pthread_create(&t,0,worker,c)==0);++c->threads;assert(pthread_join(t,0)==0);
}
static bool read_ticks(void *argument,uint64_t *ticks)
{
    Context *c=argument;++c->reads;*ticks=c->ticks;
    if(c->reads!=c->when)return true;
    if(equal(c->name,"reader-failure"))return false;
    if(equal(c->name,"start-aba") || equal(c->name,"end-aba"))aba(c);
    if(equal(c->name,"thread-start-aba") || equal(c->name,"thread-end-aba"))thread(c);
    if(strncmp(c->name,"during-",7)==0){
        A23CandidateClockStamp p=c->base;
        if(equal(c->name,"during-numerator"))p.numerator=2;
        if(equal(c->name,"during-denominator"))p.denominator=2;
        if(equal(c->name,"during-domain"))p.domain=A23CandidateNativeOwner;
        if(equal(c->name,"during-instance"))p.clock_instance=2;
        if(equal(c->name,"during-domain")){
            assert(A23VersionedClockBegin(c->store,&c->ticket)==A23VersionedClockOK);
            c->writer_status=A23VersionedClockFinish(c->store,c->ticket,&p);assert(c->writer_status==A23VersionedClockProfile);++c->mutations;
        }else publish(c,p);
    }
    if(equal(c->name,"bypass-aba")){
        // Deliberate contract violation; no version instrumentation can observe
        // an unreported write restored before it reads again.
        atomic_store(&c->store->numerator,2);atomic_store(&c->store->numerator,c->base.numerator);c->mutations+=2;
    }
    if(equal(c->name,"busy-during") || equal(c->name,"nested-writer") || equal(c->name,"thread-contender")){
        assert(A23VersionedClockBegin(c->store,&c->ticket)==A23VersionedClockOK);++c->mutations;
        if(equal(c->name,"nested-writer")){
            uint64_t ticket=99;c->writer_status=A23VersionedClockBegin(c->store,&ticket);assert(c->writer_status==A23VersionedClockBusy && !ticket);
        }
        if(equal(c->name,"thread-contender"))thread(c);
        if(!equal(c->name,"busy-during"))assert(A23VersionedClockAbort(c->store,c->ticket)==A23VersionedClockOK);
    }
    return true;
}
static void pointer_checks(void)
{
    A23VersionedClockStore store;A23CandidateClockStamp p={0,A23CandidateInjectedDriver,1,1,1};
    A23VersionedClockSample sample;A23CandidateClockResult duration;uint64_t ticket=99;
    assert(A23VersionedClockInit(0,1,&p)==A23VersionedClockArgument);
    assert(A23VersionedClockInit(&store,1,&p)==A23VersionedClockOK);
    assert(A23VersionedClockBegin(0,&ticket)==A23VersionedClockArgument && !ticket);
    assert(A23VersionedClockBegin(&store,0)==A23VersionedClockArgument);
    assert(A23VersionedClockReadProfile(0,&sample)==A23VersionedClockArgument && zero(&sample));
    assert(A23VersionedClockReadProfile(&store,0)==A23VersionedClockArgument);
    assert(A23VersionedClockCapture(&store,read_ticks,0,0)==A23VersionedClockArgument);
    assert(A23VersionedClockFinish(&store,0,&p)==A23VersionedClockArgument);
    assert(A23VersionedClockEvaluate(0,0,0,&duration)==A23CandidateClockInvalidArgument && !duration.rounded_up_ns && !duration.minimum_met);
    assert(A23VersionedClockEvaluate(0,0,0,0)==A23CandidateClockInvalidArgument);
}
int main(int argc,char **argv)
{
    (void)argv;if(argc!=1)return 2;pointer_checks();unsigned total_threads=0;
    printf("{\"pointer_checks_passed\":true,\"cases\":{");
    for(unsigned index=0;index<sizeof(names)/sizeof(*names);++index){
        const char *name=names[index];A23VersionedClockStore store,other;
        A23CandidateClockStamp p={0,A23CandidateInjectedDriver,1,1,1};uint64_t incarnation=1;
        if(strncmp(name,"fractional-",11)==0){p.numerator=2;p.denominator=3;}
        if(equal(name,"overflow"))p.numerator=UINT32_MAX;
        if(equal(name,"invalid-domain"))p.domain=A23CandidateNativeOwner;
        if(equal(name,"invalid-instance"))p.clock_instance=0;
        if(equal(name,"invalid-numerator"))p.numerator=0;
        if(equal(name,"invalid-denominator"))p.denominator=0;
        if(equal(name,"invalid-incarnation"))incarnation=0;
        A23VersionedClockStatus init=A23VersionedClockInit(&store,incarnation,&p);
        A23VersionedClockSample pre,b,e;
        A23VersionedClockStatus preflight=A23VersionedClockReadProfile(&store,&pre);
        Context c={.store=&store,.base=p,.name=name,.when=2,.ticks=100};
        if(equal(name,"zero-tick"))c.ticks=0;
        if(equal(name,"overflow"))c.ticks=1;
        if(equal(name,"start-aba") || equal(name,"thread-start-aba"))c.when=1;
        if(equal(name,"busy-before")){assert(A23VersionedClockBegin(&store,&c.ticket)==A23VersionedClockOK);++c.mutations;}
        A23VersionedClockStatus begin=A23VersionedClockCapture(&store,read_ticks,&c,&b);
        if(equal(name,"busy-before"))assert(A23VersionedClockAbort(&store,c.ticket)==A23VersionedClockOK);
        c.ticks=250000100;
        if(strncmp(name,"fractional-",11)==0)c.ticks=equal(name,"fractional-short") ? 375000099 : equal(name,"fractional-equal") ? 375000100 : 375000101;
        if(equal(name,"zero-tick"))c.ticks=250000000;
        if(equal(name,"backwards"))c.ticks=99;
        if(equal(name,"overflow"))c.ticks=UINT64_MAX;
        if(equal(name,"between-aba"))aba(&c);
        if(equal(name,"between-noop") || equal(name,"after-end-publish")){if(equal(name,"between-noop"))publish(&c,p);}
        if(equal(name,"between-numerator")){A23CandidateClockStamp changed=p;changed.numerator=2;publish(&c,changed);}
        if(equal(name,"between-abort")){assert(A23VersionedClockBegin(&store,&c.ticket)==A23VersionedClockOK);assert(A23VersionedClockAbort(&store,c.ticket)==A23VersionedClockOK);++c.mutations;}
        if(equal(name,"bypass-between")){atomic_store(&store.numerator,2);atomic_store(&store.numerator,p.numerator);c.mutations+=2;}
        if(equal(name,"poisoned"))atomic_store(&store.poisoned,true);
        if(equal(name,"zero-generation"))atomic_store(&store.generation,0); // Corrupt-state fixture setup, not a supported write.
        if(equal(name,"last-write")){atomic_store(&store.generation,UINT64_MAX-3);publish(&c,p);}
        if(equal(name,"exhaustion")){atomic_store(&store.generation,UINT64_MAX-1);c.writer_status=A23VersionedClockPublish(&store,&p);assert(c.writer_status==A23VersionedClockExhausted);}
        if(equal(name,"invalid-finish")){assert(A23VersionedClockBegin(&store,&c.ticket)==A23VersionedClockOK);c.writer_status=A23VersionedClockFinish(&store,c.ticket,0);assert(c.writer_status==A23VersionedClockProfile);++c.mutations;}
        if(equal(name,"stale-ticket")){assert(A23VersionedClockBegin(&store,&c.ticket)==A23VersionedClockOK);assert(A23VersionedClockFinish(&store,c.ticket,&p)==A23VersionedClockOK);c.writer_status=A23VersionedClockFinish(&store,c.ticket,&p);assert(c.writer_status==A23VersionedClockChanged);++c.mutations;}
        if(equal(name,"wrong-ticket")){assert(A23VersionedClockBegin(&store,&c.ticket)==A23VersionedClockOK);c.writer_status=A23VersionedClockFinish(&store,c.ticket+2,&p);assert(c.writer_status==A23VersionedClockChanged);assert(A23VersionedClockAbort(&store,c.ticket)==A23VersionedClockOK);++c.mutations;}
        const A23VersionedClockStore *target=&store;
        if(equal(name,"other-store")){assert(A23VersionedClockInit(&other,1,&p)==A23VersionedClockOK);target=&other;}
        if(equal(name,"nil-store"))target=0;
        A23VersionedClockStatus end=A23VersionedClockCapture(target,equal(name,"nil-reader") ? 0 : read_ticks,&c,&e);
        if(equal(name,"busy-during"))assert(A23VersionedClockAbort(&store,c.ticket)==A23VersionedClockOK);
        if(equal(name,"other-incarnation"))++e.incarnation; // Forged endpoint must fail binding.
        if(equal(name,"after-end-publish"))publish(&c,p);
        A23CandidateClockResult duration={0};A23CandidateClockStatus status=A23CandidateClockInvalidArgument;
        if(begin==A23VersionedClockOK && end==A23VersionedClockOK)status=A23VersionedClockEvaluate(&b,&e,250000000,&duration);
        total_threads+=c.threads;
        printf("%s\"%s\":{\"init\":%u,\"preflight\":%u,\"begin\":%u,\"end\":%u,\"evaluate\":%u,\"rounded_ns\":%" PRIu64 ",\"minimum_met\":%s,\"reads\":%u,\"mutations\":%u,\"threads\":%u,\"writer_status\":%u,\"generation\":%" PRIu64 ",\"poisoned\":%s,\"begin_generation\":%" PRIu64 ",\"end_generation\":%" PRIu64 ",\"begin_zeroed\":%s,\"end_zeroed\":%s}",
            index ? "," : "",name,(unsigned)init,(unsigned)preflight,(unsigned)begin,(unsigned)end,(unsigned)status,duration.rounded_up_ns,duration.minimum_met ? "true" : "false",c.reads,c.mutations,c.threads,(unsigned)c.writer_status,atomic_load(&store.generation),atomic_load(&store.poisoned) ? "true" : "false",b.generation,e.generation,zero(&b) ? "true" : "false",zero(&e) ? "true" : "false");
    }
    printf("},\"threads_created\":%u,\"explicit_actual_clock_queries\":0,\"real_sdk_objects\":0,\"usb_requests\":0,\"sd_accesses\":0}\n",total_threads);return 0;
}
