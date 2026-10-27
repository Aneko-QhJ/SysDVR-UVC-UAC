#include "a23_passive_wait_adapter.h"
#include <IOKit/IOMessage.h>
#include <string.h>

static void fail(A23PassiveWaitAdapter *a,unsigned why) { (void)a23_wait_stop(&a->policy,why); }
static bool running(const A23PassiveWaitAdapter *a) { return a->policy.phase!=A23_W_STOPPED && !a->closed; }
static bool emit(A23PassiveWaitAdapter *a,unsigned event) {
    A23WaitEvent row={.index=++a->events,.event=event,.phase=a->policy.phase,.reason=a->policy.reason,
        .ticks=a->policy.last,.interface_id=a->identity.interface_id,.device_id=a->identity.device_id,
        .count=a->count,.native_result=a->native_result};
    if(a->journal_failed || a->events>128 || !a->ops.emit(a->ops.context,&row)) {
        a->journal_failed=true;fail(a,A23_A_JOURNAL);return false;
    }
    return running(a);
}
static void release(A23PassiveWaitAdapter *a,io_object_t token) {
    if(!token)return;
    kern_return_t rc=a->ops.release(a->ops.context,token);
    if(rc) {
        if(a->failed_releases<5)a->unreleased[a->failed_releases]=token;
        a->failed_releases++;
        if(!a->native_result)a->native_result=(uint32_t)rc;
        fail(a,A23_A_IO);
    }
}
static void cleanup(A23PassiveWaitAdapter *a) {
    if(a->busy || a->closed || running(a))return;
    /* No asynchronous notification source exists. Release notifier refs and
     * destroy the receive port only AFTER pump/callouts have returned. */
    release(a,a->interest);a->interest=0;
    release(a,a->iterator);a->iterator=0;
    if(a->port)a->ops.destroy(a->ops.context,a->port);
    a->port=NULL;
    release(a,a->selected);a->selected=0;a->closed=true;
    if(!a->journal_failed) {
        A23WaitEvent row={.index=++a->events,.event=A23_E_STOP,.phase=a->policy.phase,
            .reason=a->policy.reason,.ticks=a->policy.last,.interface_id=a->identity.interface_id,
            .device_id=a->identity.device_id,.count=a->count,.native_result=a->native_result};
        if(!a->ops.emit(a->ops.context,&row))a->journal_failed=true;
    }
}
static bool clock_ok(A23PassiveWaitAdapter *a) {
    return a23_wait_clock(&a->policy,a->ops.now(a->ops.context));
}
static bool identity_ok(const A23WaitIdentity *id) {
    return id->interface_id && id->device_id && id->interface_id!=id->device_id && id->speed==3;
}
static void interest(void *context,io_service_t service,uint32_t message,void *argument) {
    (void)argument;A23PassiveWaitAdapter *a=context;
    if(!running(a))return;
    if(!a->busy || service!=a->selected) { fail(a,A23_A_IO);return; }
    if(message==kIOMessageServiceIsTerminated || message==kIOMessageServiceIsRequestingClose)
        fail(a,A23_W_REASON_DETACHED);
}
static void drain(A23PassiveWaitAdapter *a,bool initial) {
    io_service_t first=0;size_t count=0;
    if(!clock_ok(a) || !a->ops.valid(a->ops.context,a->iterator)) { fail(a,A23_A_IO);return; }
    for(;;) {
        if(!clock_ok(a))break;
        io_service_t service=a->ops.next(a->ops.context,a->iterator);
        if(!service)break;
        ++count;
        if(!initial && count==1)first=service;else release(a,service);
        if(count>64) { fail(a,A23_A_LIMIT);break; }
        if(!running(a))break;
    }
    a->count=(unsigned)count;
    if(running(a) && !a->ops.valid(a->ops.context,a->iterator))fail(a,A23_A_IO);
    if(!running(a)) { release(a,first);return; }
    if(initial) {
        if(a23_wait_initial_drained(&a->policy,a->ops.now(a->ops.context),count)) (void)emit(a,A23_E_WAITING);
        return;
    }
    if(count!=1 || !first) { release(a,first);fail(a,A23_W_REASON_AMBIGUOUS);return; }
    if(a->selected) { release(a,first);fail(a,A23_W_REASON_EXTRA_ARRIVAL);return; }
    A23WaitIdentity id={0};
    if(!a->ops.identity(a->ops.context,first,&id) || !identity_ok(&id)) {
        release(a,first);fail(a,A23_A_IDENTITY);return;
    }
    if(!a23_wait_arrival(&a->policy,a->ops.now(a->ops.context),&id.interface_id,1)) { release(a,first);return; }
    a->selected=first;a->identity=id;
    a->native_result=(uint32_t)a->ops.interest(a->ops.context,a->port,first,interest,a,&a->interest);
    if(a->native_result || !a->interest) { fail(a,A23_A_IO);return; }
    A23WaitIdentity checked={0};
    if(!running(a))return;
    if(!a->ops.identity(a->ops.context,first,&checked) || !identity_ok(&checked) ||
       checked.interface_id!=id.interface_id || checked.device_id!=id.device_id || checked.speed!=id.speed) {
        fail(a,A23_A_IDENTITY);return;
    }
    if(clock_ok(a)) (void)emit(a,A23_E_SELECTED);
}
static void matching(void *context,io_iterator_t iterator) {
    A23PassiveWaitAdapter *a=context;
    if(!running(a))return;
    if(!a->busy || iterator!=a->iterator) { fail(a,A23_A_IO);return; }
    if(a->policy.phase<A23_W_WAITING) { fail(a,A23_W_REASON_ORDER);return; }
    drain(a,false);
}
bool a23_adapter_start(A23PassiveWaitAdapter *a,const A23WaitOps *ops,uint64_t deadline) {
    if(!a || a->initialized || !ops || !ops->now || !ops->create || !ops->matching || !ops->valid ||
       !ops->next || !ops->identity || !ops->interest || !ops->pump || !ops->release || !ops->destroy || !ops->emit)return false;
    a->initialized=true;a->ops=*ops;a->busy=true;
    if(!a23_wait_begin(&a->policy,ops->now(ops->context),deadline))goto done;
    if(!emit(a,A23_E_BEGIN))goto done;
    a->port=ops->create(ops->context);
    if(!a->port) { fail(a,A23_A_IO);goto done; }
    a->native_result=(uint32_t)ops->matching(ops->context,a->port,matching,a,&a->iterator);
    if(!running(a))goto done;
    if(!a23_wait_registered(&a->policy,ops->now(ops->context),a->native_result==0 && a->iterator))goto done;
    if(emit(a,A23_E_REGISTERED))drain(a,true);
done:
    a->busy=false;cleanup(a);return running(a);
}
bool a23_adapter_poll(A23PassiveWaitAdapter *a) {
    if(!a || !a->initialized || a->closed)return false;
    if(a->busy) { fail(a,A23_A_REENTRANT);return false; }
    a->busy=true;
    for(unsigned i=0;running(a) && i<16;i++) {
        if(!clock_ok(a))break;
        int result=a->ops.pump(a->ops.context,a->port);
        if(result<0 || result>1) { fail(a,A23_A_IO);break; }
        if(!running(a) || result==0)break;
        if(i==15)fail(a,A23_A_LIMIT);
    }
    a->busy=false;cleanup(a);return running(a);
}
bool a23_adapter_take(A23PassiveWaitAdapter *a,io_service_t *service,A23WaitIdentity *id) {
    if(!a || !service || !id || !a23_adapter_poll(a))return false;
    a->busy=true;uint64_t selected=0;A23WaitIdentity checked={0};
    if(!a->selected || !a->ops.identity(a->ops.context,a->selected,&checked) ||
       checked.interface_id!=a->identity.interface_id || checked.device_id!=a->identity.device_id || checked.speed!=3)
        fail(a,A23_A_IDENTITY);
    bool ok=running(a) && a23_wait_handoff(&a->policy,a->ops.now(a->ops.context),&selected);
    if(ok)ok=emit(a,A23_E_HANDOFF);
    if(ok) { *service=a->selected;*id=a->identity; }
    a->busy=false;cleanup(a);return ok;
}
void a23_adapter_close(A23PassiveWaitAdapter *a,unsigned why) {
    if(!a || !a->initialized || a->closed)return;
    fail(a,why);cleanup(a);
}
