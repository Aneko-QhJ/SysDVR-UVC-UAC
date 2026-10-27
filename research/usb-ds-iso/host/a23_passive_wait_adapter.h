#pragma once
/* Dormant adapter, no capture entry. All calls (including synchronous callbacks)
 * stay on ONE caller queue. Keep this object and its ops/context alive until
 * close returns outside a callback. No dispatch/runloop source is installed.
 * poll pumps at most 16 messages; callback teardown is deferred until it returns.
 * The service returned by take is BORROWED until close: provider must retain it.
 */
#include <IOKit/IOKitLib.h>
#include "a23_passive_wait_policy.h"
typedef struct { uint64_t interface_id,device_id;uint32_t speed; } A23WaitIdentity;
enum { A23_A_IO=100,A23_A_JOURNAL,A23_A_IDENTITY,A23_A_LIMIT,A23_A_REENTRANT };
typedef struct {
    unsigned index,event,phase,reason;uint64_t ticks,interface_id,device_id;
    unsigned count;uint32_t native_result;
} A23WaitEvent;
enum { A23_E_BEGIN=1,A23_E_REGISTERED,A23_E_WAITING,A23_E_SELECTED,A23_E_HANDOFF,A23_E_STOP };
typedef struct {
    void *context;
    uint64_t (*now)(void *);
    IONotificationPortRef (*create)(void *);
    kern_return_t (*matching)(void *,IONotificationPortRef,IOServiceMatchingCallback,void *,io_iterator_t *);
    bool (*valid)(void *,io_iterator_t);
    io_service_t (*next)(void *,io_iterator_t); /* returned service owns one ref */
    bool (*identity)(void *,io_service_t,A23WaitIdentity *);
    kern_return_t (*interest)(void *,IONotificationPortRef,io_service_t,IOServiceInterestCallback,void *,io_object_t *);
    int (*pump)(void *,IONotificationPortRef); /* -1 error, 0 empty, 1 dispatched; SYNCHRONOUS */
    kern_return_t (*release)(void *,io_object_t);
    void (*destroy)(void *,IONotificationPortRef);
    bool (*emit)(void *,const A23WaitEvent *); /* durable/read-back acknowledgement */
} A23WaitOps;
typedef struct {
    A23PassiveWaitPolicy policy;A23WaitOps ops;A23WaitIdentity identity;
    IONotificationPortRef port;io_iterator_t iterator;io_object_t interest;
    io_service_t selected;
    bool initialized,busy,closed,journal_failed;
    unsigned events,count,failed_releases;
    /* A failed release while draining can leave two local services plus the
     * selected service, iterator and interest: keep every one of these five. */
    io_object_t unreleased[5];
    uint32_t native_result;
} A23PassiveWaitAdapter;
bool a23_adapter_start(A23PassiveWaitAdapter *,const A23WaitOps *,uint64_t deadline);
bool a23_adapter_poll(A23PassiveWaitAdapter *);
bool a23_adapter_take(A23PassiveWaitAdapter *,io_service_t *,A23WaitIdentity *);
void a23_adapter_close(A23PassiveWaitAdapter *,unsigned reason);
/* Factory fills real IOKit bindings but performs no calls. Never used by the
 * injected native fixtures. emit and now are mandatory caller callbacks. */
void a23_wait_native_ops(A23WaitOps *,void *context,uint64_t (*now)(void *),
                         bool (*emit)(void *,const A23WaitEvent *));
bool a23_wait_message_valid(const mach_msg_header_t *,size_t available);
