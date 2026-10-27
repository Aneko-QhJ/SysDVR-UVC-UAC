#include "a23_versioned_clock_candidate.h"

static bool valid(const A23CandidateClockStamp *p)
{
    return p && p->domain==A23CandidateInjectedDriver && p->clock_instance && p->numerator && p->denominator;
}
static void fields(A23VersionedClockStore *s,const A23CandidateClockStamp *p)
{
    atomic_store(&s->domain,(uint32_t)p->domain);atomic_store(&s->clock_instance,p->clock_instance);
    atomic_store(&s->numerator,p->numerator);atomic_store(&s->denominator,p->denominator);
}
A23VersionedClockStatus A23VersionedClockInit(A23VersionedClockStore *s,uint64_t incarnation,const A23CandidateClockStamp *p)
{
    if(!s)return A23VersionedClockArgument;
    atomic_init(&s->generation,0);atomic_init(&s->domain,0);atomic_init(&s->clock_instance,0);
    atomic_init(&s->numerator,0);atomic_init(&s->denominator,0);atomic_init(&s->poisoned,true);s->incarnation=incarnation;
    if(!incarnation || !valid(p))return A23VersionedClockProfile;
    fields(s,p);atomic_store(&s->generation,2);atomic_store(&s->poisoned,false);return A23VersionedClockOK;
}
A23VersionedClockStatus A23VersionedClockBegin(A23VersionedClockStore *s,uint64_t *ticket)
{
    if(ticket)*ticket=0;
    if(!s || !ticket)return A23VersionedClockArgument;
    if(atomic_load(&s->poisoned))return A23VersionedClockPoisoned;
    uint64_t before=atomic_load(&s->generation);
    if(!before){atomic_store(&s->poisoned,true);return A23VersionedClockPoisoned;}
    if(before&1)return A23VersionedClockBusy;
    if(before>UINT64_MAX-2){atomic_store(&s->poisoned,true);return A23VersionedClockExhausted;}
    if(!atomic_compare_exchange_strong(&s->generation,&before,before+1))return A23VersionedClockChanged;
    *ticket=before+1;return A23VersionedClockOK;
}
static A23VersionedClockStatus finish(A23VersionedClockStore *s,uint64_t ticket,const A23CandidateClockStamp *p,bool aborting)
{
    if(!s || !ticket || !(ticket&1))return A23VersionedClockArgument;
    if(atomic_load(&s->poisoned))return A23VersionedClockPoisoned;
    if(atomic_load(&s->generation)!=ticket)return A23VersionedClockChanged;
    if(ticket==UINT64_MAX){atomic_store(&s->poisoned,true);return A23VersionedClockExhausted;}
    if(!aborting && !valid(p)){
        atomic_store(&s->poisoned,true);atomic_store(&s->generation,ticket+1);return A23VersionedClockProfile;
    }
    if(!aborting)fields(s,p);
    atomic_store(&s->generation,ticket+1);return A23VersionedClockOK;
}
A23VersionedClockStatus A23VersionedClockFinish(A23VersionedClockStore *s,uint64_t ticket,const A23CandidateClockStamp *p)
{return finish(s,ticket,p,false);}
A23VersionedClockStatus A23VersionedClockAbort(A23VersionedClockStore *s,uint64_t ticket)
{return finish(s,ticket,0,true);}
A23VersionedClockStatus A23VersionedClockPublish(A23VersionedClockStore *s,const A23CandidateClockStamp *p)
{
    if(!valid(p))return A23VersionedClockProfile;
    uint64_t ticket;A23VersionedClockStatus status=A23VersionedClockBegin(s,&ticket);
    return status==A23VersionedClockOK ? A23VersionedClockFinish(s,ticket,p) : status;
}
static A23VersionedClockStatus capture(const A23VersionedClockStore *s,A23VersionedClockReader reader,void *context,bool ticks,A23VersionedClockSample *out)
{
    if(out)*out=(A23VersionedClockSample){0};
    if(!s || !out || (ticks && !reader))return A23VersionedClockArgument;
    if(atomic_load(&s->poisoned))return A23VersionedClockPoisoned;
    uint64_t before=atomic_load(&s->generation);
    if(!before)return A23VersionedClockPoisoned;
    if(before&1)return A23VersionedClockBusy;
    A23CandidateClockStamp p={0,(A23CandidateClockDomain)atomic_load(&s->domain),atomic_load(&s->clock_instance),atomic_load(&s->numerator),atomic_load(&s->denominator)};
    if(!valid(&p) || !s->incarnation)return A23VersionedClockProfile;
    if(ticks && !reader(context,&p.ticks))return A23VersionedClockReaderFailed;
    if(atomic_load(&s->poisoned))return A23VersionedClockPoisoned;
    if(atomic_load(&s->generation)!=before)return A23VersionedClockChanged;
    *out=(A23VersionedClockSample){p,s,s->incarnation,before};return A23VersionedClockOK;
}
A23VersionedClockStatus A23VersionedClockReadProfile(const A23VersionedClockStore *s,A23VersionedClockSample *out)
{return capture(s,0,0,false,out);}
A23VersionedClockStatus A23VersionedClockCapture(const A23VersionedClockStore *s,A23VersionedClockReader reader,void *context,A23VersionedClockSample *out)
{return capture(s,reader,context,true,out);}
A23CandidateClockStatus A23VersionedClockEvaluate(const A23VersionedClockSample *begin,const A23VersionedClockSample *end,uint64_t minimum,A23CandidateClockResult *out)
{
    if(out)*out=(A23CandidateClockResult){0};
    if(!out || !begin || !end)return A23CandidateClockInvalidArgument;
    if(!begin->store_identity || begin->store_identity!=end->store_identity || !begin->incarnation || begin->incarnation!=end->incarnation ||
       !begin->generation || (begin->generation&1) || begin->generation!=end->generation)return A23CandidateClockMismatch;
    return A23CandidateClockEvaluate(&begin->stamp,&end->stamp,minimum,UINT64_MAX,out);
}
