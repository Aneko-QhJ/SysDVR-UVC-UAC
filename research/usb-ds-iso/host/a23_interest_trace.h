#pragma once
/* One provider, at most eight immutable rows. No allocation/IO in ingress.
 * Reservation order is not a total order of concurrent callback arrival.
 * SDK messageArgument was discarded before this provider boundary. */
#include <stdatomic.h>
#include <stdint.h>
#include <stdbool.h>
#define A23_INTEREST_CAPACITY 8u
typedef struct { uint32_t message;uint64_t ticks;atomic_bool ready; } A23InterestRow;
typedef struct { atomic_uint claimed;atomic_bool overflow;A23InterestRow rows[A23_INTEREST_CAPACITY]; } A23InterestTrace;
typedef struct { unsigned claimed,committed,pending;bool overflow,complete;uint32_t message[A23_INTEREST_CAPACITY];uint64_t ticks[A23_INTEREST_CAPACITY];bool present[A23_INTEREST_CAPACITY]; } A23InterestSnapshot;
static inline void a23_interest_init(A23InterestTrace *t) {
    atomic_init(&t->claimed,0);atomic_init(&t->overflow,false);
    for(unsigned i=0;i<A23_INTEREST_CAPACITY;++i)atomic_init(&t->rows[i].ready,false);
}
/* UINT32_MAX is a refusal token. The bounded CAS loop never wraps or spins.
 * Uncommitted reserved slots remain explicit pending evidence forever. */
static inline unsigned a23_interest_begin(A23InterestTrace *t,uint32_t message,uint64_t ticks) {
    unsigned n=atomic_load(&t->claimed);
    for(unsigned tries=0;tries<=A23_INTEREST_CAPACITY;++tries){
        if(n>=A23_INTEREST_CAPACITY){atomic_store(&t->overflow,true);return UINT32_MAX;}
        if(atomic_compare_exchange_strong(&t->claimed,&n,n+1)){
            t->rows[n].message=message;t->rows[n].ticks=ticks;return n;
        }
    }
    atomic_store(&t->overflow,true);return UINT32_MAX;
}
static inline void a23_interest_commit(A23InterestTrace *t,unsigned token) {
    if(token<A23_INTEREST_CAPACITY)atomic_store_explicit(&t->rows[token].ready,true,memory_order_release);
}
static inline void a23_interest_record(A23InterestTrace *t,uint32_t message,uint64_t ticks) {
    a23_interest_commit(t,a23_interest_begin(t,message,ticks));
}
static inline A23InterestSnapshot a23_interest_snapshot(const A23InterestTrace *t) {
    A23InterestSnapshot s={0};s.claimed=atomic_load(&t->claimed);s.overflow=atomic_load(&t->overflow);
    if(s.claimed>A23_INTEREST_CAPACITY){s.claimed=A23_INTEREST_CAPACITY;s.overflow=true;}
    for(unsigned i=0;i<s.claimed;++i)if(atomic_load_explicit(&t->rows[i].ready,memory_order_acquire)){
        s.present[i]=true;s.message[i]=t->rows[i].message;s.ticks[i]=t->rows[i].ticks;++s.committed;
    }
    s.pending=s.claimed-s.committed;s.complete=!s.overflow && !s.pending;return s;
}
#ifdef __OBJC__
#import <Foundation/Foundation.h>
static inline NSDictionary *a23_interest_dictionary(const A23InterestTrace *t,bool latched) {
    A23InterestSnapshot s=a23_interest_snapshot(t);NSMutableArray *rows=[NSMutableArray new];
    for(unsigned i=0;i<s.claimed;++i)if(s.present[i])[rows addObject:@{@"ordinal":@(i+1),@"message_u32":@(s.message[i]),@"provider_ingress_ticks":@(s.ticks[i])}];
    bool gap=latched && !s.claimed;
    return @{@"schema":@"A23-provider-interest-trace-1",@"capacity":@A23_INTEREST_CAPACITY,@"claimed":@(s.claimed),@"committed":@(s.committed),@"pending":@(s.pending),@"overflow":@(s.overflow),@"complete":@((bool)(s.complete && !gap)),@"latch_observed":@(latched),@"latch_without_slot":@(gap),@"rows":rows,@"clock_domain":@"mach_absolute_time",@"clock_timebase_in_driver":@YES,@"argument_captured":@NO,@"message_labels_authenticate_origin":@NO,@"atomic_snapshot_verified":@NO,@"future_events_excluded":@NO};
}
#endif
