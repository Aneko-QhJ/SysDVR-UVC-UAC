#pragma once
/* Offline cleanup authorization. Only main may publish success AFTER both joins,
 * Finish, save and handle close. Callback reads ONLY this atomic phase. */
#include <stdatomic.h>
#include <stdbool.h>
enum { EP0_CLEAN_INITIAL,EP0_CLEAN_JOINING,EP0_CLEAN_AUTHORIZED,EP0_CLEAN_CLAIMED,EP0_CLEAN_DONE };
typedef struct { atomic_uint phase; } Ep0CleanupGate;
static inline bool ep0_cleanup_begin(Ep0CleanupGate *g) {
    unsigned expected=EP0_CLEAN_INITIAL;
    return atomic_compare_exchange_strong_explicit(&g->phase,&expected,EP0_CLEAN_JOINING,memory_order_acq_rel,memory_order_acquire);
}
static inline bool ep0_cleanup_authorize(Ep0CleanupGate *g) {
    unsigned expected=EP0_CLEAN_JOINING;
    return atomic_compare_exchange_strong_explicit(&g->phase,&expected,EP0_CLEAN_AUTHORIZED,memory_order_release,memory_order_relaxed);
}
static inline bool ep0_cleanup_claim(Ep0CleanupGate *g) {
    unsigned expected=EP0_CLEAN_AUTHORIZED;
    return atomic_compare_exchange_strong_explicit(&g->phase,&expected,EP0_CLEAN_CLAIMED,memory_order_acq_rel,memory_order_acquire);
}
static inline bool ep0_cleanup_done(const Ep0CleanupGate *g) { return atomic_load_explicit(&g->phase,memory_order_acquire)==EP0_CLEAN_DONE; }
static inline bool ep0_cleanup_complete(Ep0CleanupGate *g) {
    unsigned expected=EP0_CLEAN_CLAIMED;
    return atomic_compare_exchange_strong_explicit(&g->phase,&expected,EP0_CLEAN_DONE,memory_order_release,memory_order_relaxed);
}
