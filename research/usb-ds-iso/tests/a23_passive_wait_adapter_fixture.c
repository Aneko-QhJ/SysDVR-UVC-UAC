/* Actual adapter + real bindings are linked. Only this injected ops table is
 * invoked. No IOKit/SDK requests, receive-port creation or device enumeration. */
#include "a23_passive_wait_adapter.h"
#include <IOKit/IOMessage.h>
#include <IOKit/OSMessageNotification.h>
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef struct {
    const char *mode;A23PassiveWaitAdapter *adapter;
    IOServiceMatchingCallback match;IOServiceInterestCallback interest;void *ref;
    uint64_t tick;unsigned clocks,valids,identities,pumps,creates,destroys;
    unsigned batch,left,next_service,refs[256],release_calls[256],watch_calls;
    bool in_pump,active,initial,empty_seen;
    A23WaitEvent rows[128];bool acknowledged[128];unsigned events;
} Fixture;
static bool is(Fixture *f,const char *s) { return !strcmp(f->mode,s); }
static uint64_t now(void *p) {
    Fixture *f=p;f->clocks++;
    return is(f,"clock-backwards") && f->clocks>=6 ? 99:f->tick;
}
static IONotificationPortRef create(void *p) {
    Fixture *f=p;f->creates++;if(is(f,"create-error"))return NULL;
    f->active=true;return (IONotificationPortRef)(uintptr_t)1;
}
static kern_return_t matching(void *p,IONotificationPortRef port,IOServiceMatchingCallback cb,void *ref,io_iterator_t *out) {
    Fixture *f=p;assert(port && f->active);f->match=cb;f->ref=ref;*out=1;f->refs[1]++;
    f->initial=true;f->left=is(f,"existing")?1:is(f,"initial-flood")?65:0;f->next_service=10;
    if(is(f,"early-callback"))cb(ref,1);
    return is(f,"matching-error")?41:0;
}
static bool valid(void *p,io_iterator_t iterator) {
    Fixture *f=p;assert(iterator==1);f->valids++;
    return !(is(f,"invalid-initial-before") && f->valids==1) &&
           !(is(f,"invalid-initial-after") && f->valids==2) &&
           !(is(f,"invalid-arrival-before") && f->valids==3) &&
           !(is(f,"invalid-arrival-after") && f->valids==4);
}
static io_service_t next(void *p,io_iterator_t iterator) {
    Fixture *f=p;assert(iterator==1);
    if(!f->left) { f->initial=false;f->empty_seen=true;return 0; }
    f->left--;unsigned token=f->next_service++;assert(token<256);f->refs[token]++;
    if(is(f,"deadline-in-drain"))f->tick=200;
    return token;
}
static bool identity(void *p,io_service_t service,A23WaitIdentity *out) {
    Fixture *f=p;f->identities++;assert(service>=10 && f->refs[service]);
    *out=(A23WaitIdentity){.interface_id=10000+service,.device_id=20000+service,.speed=3};
    if(is(f,"bad-identity"))return false;
    if(is(f,"zero-identity"))out->interface_id=0;
    if(is(f,"same-parent"))out->device_id=out->interface_id;
    if(is(f,"wrong-speed"))out->speed=2;
    if((is(f,"identity-changed-watch") && f->identities>=2) ||
       (is(f,"identity-changed-take") && f->identities>=3))out->device_id++;
    return true;
}
static kern_return_t interest(void *p,IONotificationPortRef port,io_service_t service,
    IOServiceInterestCallback cb,void *ref,io_object_t *out) {
    Fixture *f=p;assert(port && f->refs[service]);f->watch_calls++;f->interest=cb;
    *out=2;f->refs[2]++;
    if(is(f,"detach-during-watch"))cb(ref,service,kIOMessageServiceIsTerminated,NULL);
    if(is(f,"deadline-after-watch"))f->tick=200;
    return is(f,"interest-error")?42:0;
}
static int pump(void *p,IONotificationPortRef port) {
    Fixture *f=p;assert(port && f->active);f->pumps++;f->in_pump=true;
    int result=0;
    if(is(f,"pump-error"))result=-1;
    else if(is(f,"bad-pump-result"))result=2;
    else if(is(f,"message-flood"))result=1;
    else if(f->pumps==1) {
        f->left=f->batch;f->next_service=10;f->empty_seen=false;
        f->match(f->ref,is(f,"wrong-iterator")?99:1);result=1;
    } else if(f->pumps==2 && (is(f,"detach-before-take") || is(f,"close-before-take"))) {
        assert(f->interest);f->interest(f->ref,10,is(f,"close-before-take")?
            kIOMessageServiceIsRequestingClose:kIOMessageServiceIsTerminated,NULL);result=1;
    } else if(f->pumps==2 && (is(f,"extra-arrival") || is(f,"release-all-extra-arrival"))) {
        f->left=is(f,"release-all-extra-arrival")?2:1;f->next_service=11;f->match(f->ref,1);result=1;
    } else if(f->pumps==4 && is(f,"detach-after-take")) {
        f->interest(f->ref,10,kIOMessageServiceIsTerminated,NULL);result=1;
    }
    f->in_pump=false;return result;
}
static kern_return_t release(void *p,io_object_t token) {
    Fixture *f=p;assert(token<256 && f->refs[token]);f->release_calls[token]++;
    if((is(f,"release-service-error") && token==10) || (is(f,"release-iterator-error") && token==1) ||
       (is(f,"release-interest-error") && token==2) || is(f,"release-all-error") || is(f,"release-all-extra-arrival"))return 88;
    f->refs[token]--;return 0;
}
static void destroy(void *p,IONotificationPortRef port) {
    Fixture *f=p;assert(port && f->active && !f->in_pump && !f->adapter->busy);
    f->active=false;f->destroys++;
}
static bool emit(void *p,const A23WaitEvent *row) {
    Fixture *f=p;assert(f->events<128);bool ok=true;
    if((is(f,"journal-begin") && row->event==A23_E_BEGIN) ||
       (is(f,"journal-registered") && row->event==A23_E_REGISTERED) ||
       (is(f,"journal-waiting") && row->event==A23_E_WAITING) ||
       (is(f,"journal-selected") && row->event==A23_E_SELECTED) ||
       (is(f,"journal-handoff") && row->event==A23_E_HANDOFF) ||
       (is(f,"journal-stop") && row->event==A23_E_STOP))ok=false;
    f->rows[f->events]=*row;f->acknowledged[f->events++]=ok;
    if((is(f,"stop-waiting") && row->event==A23_E_WAITING) ||
       (is(f,"stop-selected") && row->event==A23_E_SELECTED) ||
       (is(f,"stop-handoff") && row->event==A23_E_HANDOFF))
        a23_adapter_close(f->adapter,A23_W_REASON_INTERRUPTED);
    if(is(f,"reentrant-poll") && row->event==A23_E_SELECTED)assert(!a23_adapter_poll(f->adapter));
    return ok;
}
static unsigned messages(void) {
    union { mach_msg_header_t head;uint8_t bytes[256]; } msg={0};
    struct OSNotificationHeader64 h={.type=kIOServiceMatchedNotificationType};
    msg.head.msgh_id=kOSNotificationMessageID;msg.head.msgh_size=sizeof(msg.head)+sizeof(h);
    memcpy(msg.bytes+sizeof(msg.head),&h,sizeof(h));unsigned checked=0;
    for(size_t n=0;n<=msg.head.msgh_size+1;n++) { assert(a23_wait_message_valid(&msg.head,n)==(n>=msg.head.msgh_size));checked++; }
    msg.head.msgh_id++;assert(!a23_wait_message_valid(&msg.head,sizeof(msg)));checked++;
    msg.head.msgh_id=kOSNotificationMessageID;h.type=kIOAsyncCompletionNotificationType;
    memcpy(msg.bytes+sizeof(msg.head),&h,sizeof(h));assert(!a23_wait_message_valid(&msg.head,sizeof(msg)));checked++;
    msg.head.msgh_bits=MACH_MSGH_BITS_COMPLEX;mach_msg_body_t body={.msgh_descriptor_count=2};
    memcpy(msg.bytes+sizeof(msg.head),&body,sizeof(body));assert(!a23_wait_message_valid(&msg.head,sizeof(msg)));checked++;
    body.msgh_descriptor_count=1;memcpy(msg.bytes+sizeof(msg.head),&body,sizeof(body));
    size_t at=sizeof(msg.head)+sizeof(body);mach_msg_port_descriptor_t descriptor={.name=10,.type=MACH_MSG_PORT_DESCRIPTOR};
    memcpy(msg.bytes+at,&descriptor,sizeof(descriptor));at+=sizeof(descriptor);
    h.type=kIOServiceMessageNotificationType;memcpy(msg.bytes+at,&h,sizeof(h));at+=sizeof(h);
    struct IOServiceInterestContent64 content={.messageType=kIOMessageServiceIsTerminated};
    memcpy(msg.bytes+at,&content,sizeof(content));msg.head.msgh_size=(mach_msg_size_t)(at+sizeof(content));
    for(size_t n=0;n<=msg.head.msgh_size+1;n++) { assert(a23_wait_message_valid(&msg.head,n)==(n>=msg.head.msgh_size));checked++; }
    descriptor.type=MACH_MSG_OOL_DESCRIPTOR;memcpy(msg.bytes+sizeof(msg.head)+sizeof(body),&descriptor,sizeof(descriptor));
    assert(!a23_wait_message_valid(&msg.head,sizeof(msg)));checked++;
    descriptor.type=MACH_MSG_PORT_DESCRIPTOR;memcpy(msg.bytes+sizeof(msg.head)+sizeof(body),&descriptor,sizeof(descriptor));
    msg.head.msgh_size--;assert(!a23_wait_message_valid(&msg.head,sizeof(msg)));checked++;
    msg.head.msgh_size=sizeof(msg.bytes)+1;assert(!a23_wait_message_valid(&msg.head,sizeof(msg)));checked++;
    return checked;
}
int main(int argc,char **argv) {
    assert(argc==3);A23PassiveWaitAdapter adapter={0};Fixture f={.mode=argv[1],.adapter=&adapter,.tick=100,.batch=(unsigned)strtoul(argv[2],NULL,10)};
    A23WaitOps ops={.context=&f,.now=now,.create=create,.matching=matching,.valid=valid,.next=next,
        .identity=identity,.interest=interest,.pump=pump,.release=release,.destroy=destroy,.emit=emit};
    bool started=a23_adapter_start(&adapter,&ops,200),taken=false;io_service_t selected=777;
    A23WaitIdentity id={0};
    if(started) {
        if(is(&f,"timeout"))f.tick=200;
        (void)a23_adapter_poll(&adapter);
        if(is(&f,"deadline-before-take"))f.tick=200;
        taken=a23_adapter_take(&adapter,&selected,&id);
        if(taken) {
            assert(selected==10 && id.interface_id==10010);f.refs[selected]++; /* provider retains borrowed lease */
            if(is(&f,"detach-after-take")) (void)a23_adapter_poll(&adapter);
            if(is(&f,"second-take"))assert(!a23_adapter_take(&adapter,&selected,&id));
        } else assert(selected==777);
    }
    unsigned before_handoffs=adapter.policy.handoffs;
    a23_adapter_close(&adapter,A23_W_REASON_INTERRUPTED);
    assert(adapter.closed && !adapter.busy && !f.active && adapter.policy.handoffs<=1);
    assert(adapter.policy.handoffs==before_handoffs);
    if(taken) { assert(f.refs[10]>=1);f.refs[10]--; } /* provider owns a distinct reference */
    unsigned left=0;for(unsigned i=0;i<256;i++)left+=f.refs[i];
    assert(left==adapter.failed_releases && adapter.failed_releases<=5);
    for(unsigned i=0;i<adapter.failed_releases;i++)assert(adapter.unreleased[i] && f.refs[adapter.unreleased[i]]);
    unsigned after=f.events;if(f.match)f.match(f.ref,1);if(f.interest)f.interest(f.ref,10,kIOMessageServiceIsTerminated,NULL);
    assert(f.events==after);assert(!a23_adapter_poll(&adapter));assert(!a23_adapter_start(&adapter,&ops,300));
    assert(f.destroys<=1 && f.release_calls[1]<=1 && f.release_calls[2]<=1);
    unsigned message_cases=messages();
    printf("{\"mode\":\"%s\",\"batch\":%u,\"started\":%s,\"taken\":%s,\"handoffs\":%u,"
        "\"reason\":%u,\"journal_failed\":%s,\"failed_releases\":%u,\"unreleased_refs\":%u,"
        "\"destroy_count\":%u,\"pump_count\":%u,\"message_cases\":%u,\"simulation\":true,"
        "\"real_iokit_calls\":0,\"usb_requests\":0,\"events\":[",
        f.mode,f.batch,started?"true":"false",taken?"true":"false",adapter.policy.handoffs,
        adapter.policy.reason,adapter.journal_failed?"true":"false",adapter.failed_releases,left,f.destroys,f.pumps,message_cases);
    for(unsigned i=0;i<f.events;i++) {
        A23WaitEvent *r=&f.rows[i];
        printf("%s{\"index\":%u,\"event\":%u,\"phase\":%u,\"reason\":%u,\"ticks\":%llu,"
            "\"interface_id\":%llu,\"device_id\":%llu,\"count\":%u,\"native_result\":%u,\"injected_ack\":%s}",
            i?",":"",r->index,r->event,r->phase,r->reason,(unsigned long long)r->ticks,
            (unsigned long long)r->interface_id,(unsigned long long)r->device_id,r->count,r->native_result,f.acknowledged[i]?"true":"false");
    }
    puts("]}");
}
