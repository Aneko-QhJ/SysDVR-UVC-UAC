#import "a23_two_epoch_entry.h"
#include <CommonCrypto/CommonDigest.h>
#include <errno.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

static NSString *digest(NSData *raw){unsigned char h[32];CC_SHA256(raw.bytes,(CC_LONG)raw.length,h);NSMutableString *s=[NSMutableString new];for(unsigned i=0;i<32;++i)[s appendFormat:@"%02x",h[i]];return s;}
static NSData *encode(id v){return [NSJSONSerialization dataWithJSONObject:v options:NSJSONWritingSortedKeys error:NULL];}
static id freeze(id v){NSData *r=encode(v);return r && r.length<=16384 ? [NSJSONSerialization JSONObjectWithData:r options:0 error:NULL] : nil;}
static BOOL hex(id s){return [s isKindOfClass:NSString.class] && [s length]==64 && [s rangeOfCharacterFromSet:[[NSCharacterSet characterSetWithCharactersInString:@"0123456789abcdef"] invertedSet]].location==NSNotFound;}
static BOOL integer(id n){return [n isKindOfClass:NSNumber.class] && CFGetTypeID((__bridge CFTypeRef)n)!=CFBooleanGetTypeID() && !CFNumberIsFloatType((__bridge CFNumberRef)n) && [n compare:@0]!=NSOrderedAscending;}
static BOOL put(int dir,NSString *name,NSData *raw){
    if(!raw)return NO;int fd=openat(dir,name.fileSystemRepresentation,O_CREAT|O_EXCL|O_NOFOLLOW|O_RDWR,0600);if(fd<0)return NO;
    BOOL ok=YES;NSUInteger at=0;while(at<raw.length){ssize_t n=write(fd,(const uint8_t *)raw.bytes+at,raw.length-at);if(n<0 && errno==EINTR)continue;if(n<=0){ok=NO;break;}at+=(NSUInteger)n;}
    if(ok)ok=fsync(fd)==0;NSMutableData *copy=[NSMutableData dataWithLength:raw.length];at=0;
    while(ok && at<raw.length){ssize_t n=pread(fd,(uint8_t *)copy.mutableBytes+at,raw.length-at,(off_t)at);if(n<0 && errno==EINTR)continue;if(n<=0){ok=NO;break;}at+=(NSUInteger)n;}
    char extra;if(ok)ok=pread(fd,&extra,1,(off_t)raw.length)==0 && [raw isEqual:copy];if(close(fd))ok=NO;return ok;
}
static BOOL file(NSString *directory,NSString *name,NSData *raw){int fd=open(directory.fileSystemRepresentation,O_RDONLY|O_DIRECTORY|O_NOFOLLOW);if(fd<0)return NO;BOOL ok=put(fd,name,raw) && fsync(fd)==0;if(close(fd))ok=NO;return ok;}
static BOOL checkpoint(NSString *directory,NSDictionary *files){
    int parent=open(directory.fileSystemRepresentation,O_RDONLY|O_DIRECTORY|O_NOFOLLOW);if(parent<0)return NO;
    if(mkdirat(parent,"entry-final",0700)){close(parent);return NO;}int fd=openat(parent,"entry-final",O_RDONLY|O_DIRECTORY|O_NOFOLLOW);if(fd<0){close(parent);return NO;}
    BOOL ok=YES;NSMutableString *s=[NSMutableString new];for(NSString *name in [[files allKeys] sortedArrayUsingSelector:@selector(compare:)]){if(ok)ok=put(fd,name,files[name]);[s appendFormat:@"%@  %@\n",digest(files[name]),name];}
    NSData *raw=[s dataUsingEncoding:NSUTF8StringEncoding];if(ok)ok=put(fd,@"SHA256SUMS",raw) && fsync(fd)==0 && put(fd,@"COMMITTED",[[digest(raw) stringByAppendingString:@"\n"] dataUsingEncoding:NSUTF8StringEncoding]) && fsync(fd)==0 && fsync(parent)==0;
    if(close(fd))ok=NO;if(close(parent))ok=NO;return ok;
}
@interface A23TwoEpochEntry ()
- (uint64_t)now;
- (BOOL)adapterEvent:(const A23WaitEvent *)event;
@end
typedef struct {void *owner;A23WaitOps ops;} EntryBridge;
static uint64_t entryNow(void *p){EntryBridge *b=p;return [(__bridge A23TwoEpochEntry *)b->owner now];}
static bool entryEmit(void *p,const A23WaitEvent *e){EntryBridge *b=p;return [(__bridge A23TwoEpochEntry *)b->owner adapterEvent:e];}
static IONotificationPortRef entryCreate(void *p){EntryBridge *b=p;return b->ops.create(b->ops.context);}
static kern_return_t entryMatching(void *p,IONotificationPortRef n,IOServiceMatchingCallback c,void *r,io_iterator_t *o){EntryBridge *b=p;return b->ops.matching(b->ops.context,n,c,r,o);}
static bool entryValid(void *p,io_iterator_t i){EntryBridge *b=p;return b->ops.valid(b->ops.context,i);}
static io_service_t entryNext(void *p,io_iterator_t i){EntryBridge *b=p;return b->ops.next(b->ops.context,i);}
static bool entryIdentity(void *p,io_service_t s,A23WaitIdentity *i){EntryBridge *b=p;return b->ops.identity(b->ops.context,s,i);}
static kern_return_t entryInterest(void *p,IONotificationPortRef n,io_service_t s,IOServiceInterestCallback c,void *r,io_object_t *o){EntryBridge *b=p;return b->ops.interest(b->ops.context,n,s,c,r,o);}
static int entryPump(void *p,IONotificationPortRef n){EntryBridge *b=p;return b->ops.pump(b->ops.context,n);}
static kern_return_t entryRelease(void *p,io_object_t s){EntryBridge *b=p;return b->ops.release(b->ops.context,s);}
static void entryDestroy(void *p,IONotificationPortRef n){EntryBridge *b=p;b->ops.destroy(b->ops.context,n);}
@implementation A23TwoEpochEntry {
    NSString *_directory,*_contextSHA;NSDictionary *_context,*_binding;dispatch_queue_t _queue;id<A23RuntimeClock> _clock;
    A23WaitOps _original;EntryBridge _bridge;A23PassiveWaitAdapter _adapter;A23PairedSimulationProvider *_provider;id<A23TwoEpochEntryPermit> _permit;
    A23SimulationJournal *_journal,*_driverJournal;A23TwoEpochSDKDriver *_driver;id<A23PairedResources> _lease;
    BOOL _begun,_prepared,_started,_stopped,_busy,_journalFailed,_processClaimed,_selectionClaimed,_finalAttempted,_finalSaved,_finalStale;
    NSUInteger _index;NSMutableArray *_reasons;NSData *_finalSnapshot;A23TwoEpochEntry *_hold;
}
- (instancetype)initWithDirectory:(NSString *)directory queue:(dispatch_queue_t)queue clock:(id<A23RuntimeClock>)clock
    ops:(const A23WaitOps *)ops provider:(A23PairedSimulationProvider *)provider permit:(id<A23TwoEpochEntryPermit>)permit
    context:(NSDictionary *)context binding:(NSDictionary *)binding {
    if(![directory isKindOfClass:NSString.class] || ![context isKindOfClass:NSDictionary.class] || ![binding isKindOfClass:NSDictionary.class] || !queue || !clock || !clock.numerator || !clock.denominator || !ops || !ops->create || !ops->matching || !ops->valid || !ops->next || !ops->identity || !ops->interest || !ops->pump || !ops->release || !ops->destroy || !provider || !permit)return nil;dispatch_assert_queue(queue);
    NSDictionary *b=freeze(binding),*c=freeze(context);char *resolved=realpath(directory.fileSystemRepresentation,NULL);BOOL canonical=resolved && [directory isEqual:@(resolved)];free(resolved);
    NSSet *keys=[NSSet setWithArray:@[@"schema",@"build_manifest_sha256",@"receiver_sha256",@"authorization_receipt_sha256",@"first_sequence",@"last_sequence"]];
    if(!canonical || ![b isKindOfClass:NSDictionary.class] || ![c isKindOfClass:NSDictionary.class] || ![[NSSet setWithArray:b.allKeys] isEqual:keys] || ![b[@"schema"] isEqual:@"A23-two-epoch-entry-binding-1"])return nil;
    for(NSString *k in @[@"build_manifest_sha256",@"receiver_sha256",@"authorization_receipt_sha256"])if(!hex(b[k]))return nil;
    if(!integer(b[@"first_sequence"]) || !integer(b[@"last_sequence"]))return nil;
    uint64_t first=[b[@"first_sequence"] unsignedLongLongValue];if(first<81 || first>65504 || first%16!=1 || [b[@"last_sequence"] unsignedLongLongValue]!=first+31)return nil;
    if((self=[super init])){_directory=[directory copy];_queue=queue;_clock=clock;_original=*ops;_provider=provider;_permit=permit;_context=c;_binding=b;_contextSHA=digest(encode(c));_reasons=[NSMutableArray new];
        _journal=[[A23SimulationJournal alloc] initWithPath:[directory stringByAppendingPathComponent:@"entry.jsonl"] error:NULL];if(!_journal)return nil;}
    return self;
}
- (uint64_t)now{return _clock.nowTicks;}
- (BOOL)emit:(NSString *)event details:(NSDictionary *)details {
    if(_journalFailed)return NO;
    NSDictionary *row=@{@"schema":@"A23-two-epoch-entry-event-1",@"index":@(++_index),@"ticks":@(_clock.nowTicks),@"event":event,@"details":details,@"hardware_verified":@NO};
    if(_index>128 || ![_journal append:row error:NULL]){_journalFailed=YES;_stopped=YES;[_reasons addObject:@"entry_journal_failed"];return NO;}return YES;
}
- (BOOL)adapterEvent:(const A23WaitEvent *)e {
    return [self emit:@"adapter" details:@{@"adapter_index":@(e->index),@"event":@(e->event),@"phase":@(e->phase),@"reason":@(e->reason),@"ticks":@(e->ticks),@"interface_id":@(e->interface_id),@"device_id":@(e->device_id),@"count":@(e->count),@"native_result":@(e->native_result)}];
}
- (void)stop:(NSString *)why {
    _stopped=YES;if(![_reasons containsObject:why]){[_reasons addObject:why];[self emit:@"stop" details:@{@"reason":why}];}
}
- (void)closeWaiter {
    if(_adapter.initialized && !_adapter.closed)a23_adapter_close(&_adapter,A23_W_REASON_NONE);
    if(_adapter.journal_failed || _adapter.failed_releases || (_adapter.initialized && !_adapter.closed))[self stop:@"waiter_close_failed"];
}
- (BOOL)contextValid {
    return A23ValidateExecutionContext(_context,_binding[@"receiver_sha256"]) && [_context[@"sample_end_ticks"] unsignedLongLongValue]<=_clock.nowTicks;
}
- (BOOL)begin {
    dispatch_assert_queue(_queue);if(_begun || _busy || _stopped)return NO;_begun=YES;_busy=YES;_hold=self;
    BOOL ok=file(_directory,@"context.json",encode(_context)) && [self emit:@"context" details:@{@"sha256":_contextSHA,@"binding":_binding}];
    if(!ok || ![self contextValid]){[self stop:@"invalid_context"];_busy=NO;return NO;}
    if(![_permit claimProcess:_binding context:_context] || _stopped){[self stop:@"process_permit_rejected"];_busy=NO;return NO;}
    uint64_t now=_clock.nowTicks;NSDictionary *claim=@{@"schema":@"A23-two-epoch-entry-process-claim-1",@"binding":_binding,@"context_sha256":_contextSHA,@"pid":_context[@"pid"],@"ticks":@(now),@"hardware_verified":@NO};
    if(!file(_directory,@"process-claim.json",encode(claim)) || ![self emit:@"process_claim" details:claim]){[self stop:@"process_claim_save_failed"];_busy=NO;return NO;}_processClaimed=YES;
    __uint128_t delta=((__uint128_t)120000000000ULL*_clock.denominator+_clock.numerator-1)/_clock.numerator;
    if(delta>UINT64_MAX-now){[self stop:@"wait_deadline_overflow"];_busy=NO;return NO;}
    _bridge=(EntryBridge){.owner=(__bridge void *)self,.ops=_original};
    A23WaitOps ops={.context=&_bridge,.now=entryNow,.emit=entryEmit,.create=entryCreate,.matching=entryMatching,.valid=entryValid,.next=entryNext,.identity=entryIdentity,.interest=entryInterest,.pump=entryPump,.release=entryRelease,.destroy=entryDestroy};
    ok=a23_adapter_start(&_adapter,&ops,now+(uint64_t)delta);if(!ok){[self stop:@"wait_begin_failed"];[self closeWaiter];}
    _busy=NO;return ok && !_stopped;
}
- (void)tick {
    dispatch_assert_queue(_queue);if(!_begun || _busy)return;_busy=YES;
    if(_driver && _started){[_driver poll];if([_driver.result[@"stopped"] boolValue])[self stop:@"sdk_driver_stopped"];_busy=NO;return;}
    if(_stopped){[self closeWaiter];_busy=NO;return;}
    if(_prepared){
        if(![self contextValid] || !_adapter.closed || _adapter.failed_releases || ![self emit:@"start" details:@{}]){[self stop:@"start_gate_failed"];_busy=NO;return;}
        _started=YES;if(![_driver start])[self stop:@"sdk_start_failed"];_busy=NO;return;
    }
    if(!a23_adapter_poll(&_adapter)){[self stop:@"wait_poll_failed"];[self closeWaiter];_busy=NO;return;}
    if(_adapter.policy.phase!=A23_W_SELECTED){_busy=NO;return;}
    io_service_t service=0;A23WaitIdentity identity={0};
    if(!a23_adapter_take(&_adapter,&service,&identity) || ![self contextValid] || ![_permit claimSelection:identity binding:_binding context:_context] || _stopped){[self stop:@"selection_permit_rejected"];[self closeWaiter];_busy=NO;return;}
    NSDictionary *claim=@{@"schema":@"A23-two-epoch-entry-sdk-claim-1",@"binding":_binding,@"context_sha256":_contextSHA,@"pid":_context[@"pid"],@"ticks":@(_clock.nowTicks),@"interface_id":@(identity.interface_id),@"device_id":@(identity.device_id),@"hardware_verified":@NO};
    if(!file(_directory,@"sdk-claim.json",encode(claim)) || ![self emit:@"sdk_claim" details:claim]){[self stop:@"sdk_claim_save_failed"];[self closeWaiter];_busy=NO;return;}_selectionClaimed=YES;
    NSDictionary *candidate=@{@"service_token":@(service),@"interface_id":@(identity.interface_id),@"device_id":@(identity.device_id),@"parent_device_id":@(identity.device_id),@"connection_speed":@(identity.speed)};
    _lease=[_provider openCandidate:candidate error:NULL];
    if(!_lease){[self stop:@"sdk_prepare_failed"];[self closeWaiter];_busy=NO;return;}
    [self closeWaiter];if(_stopped){_busy=NO;return;}
    _driverJournal=[[A23SimulationJournal alloc] initWithPath:[_directory stringByAppendingPathComponent:@"session.jsonl"] error:NULL];
    if(_driverJournal)_driver=[[A23TwoEpochSDKDriver alloc] initWithResources:_lease firstSequence:[_binding[@"first_sequence"] unsignedShortValue] directory:_directory queue:_queue clock:_clock journal:_driverJournal error:NULL];
    if(!_driver || ![self emit:@"prepared" details:@{}])[self stop:@"sdk_driver_prepare_failed"];else _prepared=YES;
    _busy=NO;
}
- (void)requestExit {
    dispatch_assert_queue(_queue);[self stop:@"exit_requested"];if(_driver && _started)[_driver requestStop];[self closeWaiter];
}
- (void)detachedRegistryID:(uint64_t)identity {
    dispatch_assert_queue(_queue);if(identity && (identity==_adapter.identity.interface_id || identity==_adapter.identity.device_id)){
        [self stop:@"detached"];if(_driver)[_driver detachedRegistryID:identity];[self closeWaiter];}
}
- (NSDictionary *)result {
    dispatch_assert_queue(_queue);NSDictionary *driver=_driver ? _driver.result : nil,*receipt=_driver ? _driver.receiptStatus : nil;
    if([driver[@"stopped"] boolValue] && !_stopped)[self stop:@"sdk_driver_stopped"];
    BOOL complete=_started && !_stopped && !_journalFailed && [driver[@"complete"] boolValue] && [receipt[@"saved"] boolValue] && ![receipt[@"stale"] boolValue];
    return @{@"schema":@"A23-two-epoch-entry-result-1",@"binding":_binding,@"context_sha256":_contextSHA,@"begun":@(_begun),@"process_claimed":@(_processClaimed),@"selection_claimed":@(_selectionClaimed),@"prepared":@(_prepared),@"started":@(_started),@"stopped":@(_stopped),@"complete":@(complete),@"journal_failed":@(_journalFailed),@"failure_reasons":[_reasons copy],@"waiter_closed":@((BOOL)_adapter.closed),@"waiter_failed_releases":@(_adapter.failed_releases),@"waiter_events":@(_adapter.events),@"driver":driver ?: NSNull.null,@"driver_receipt":receipt ?: NSNull.null,@"resources_retained":@((BOOL)(_lease!=nil || _provider.retainedFailure!=nil)),@"active_resources_released":@NO,@"callback_drain_verified":@NO,@"hardware_verified":@NO,@"hardware_entry_enabled":@NO,@"process_origin_authenticated":@NO};
}
- (BOOL)finalizeOnce {
    dispatch_assert_queue(_queue);if(!_begun || _busy || _finalAttempted)return NO;
    if(_driver && _started){[_driver poll];if([_driver.result[@"stopped"] boolValue])[self stop:@"sdk_driver_stopped"];}
    if(!_stopped && ![_driver.result[@"complete"] boolValue])return NO;
    _finalAttempted=YES;[self closeWaiter];
    if(_driver && ![_driver saveReceiptOnce])[self stop:@"sdk_receipt_failed"];
    if(![self emit:@"final_checkpoint" details:@{}]){[self stop:@"final_journal_failed"];return NO;}
    NSDictionary *r=self.result;NSData *raw=encode(r),*d=encode(_driver ? _driver.result : @{}),*s=encode(_driver ? _driver.receiptStatus : @{});
    if(!raw || !d || !s || !checkpoint(_directory,@{@"entry.json":raw,@"driver.json":d,@"receipt-status.json":s})){[self stop:@"final_checkpoint_failed"];return NO;}
    _finalSnapshot=raw;if(![raw isEqual:encode(self.result)]){_finalStale=YES;[self stop:@"changed_during_final_checkpoint"];return NO;}
    _finalSaved=YES;return YES;
}
- (NSDictionary *)finalStatus {
    dispatch_assert_queue(_queue);if(_finalSnapshot && ![_finalSnapshot isEqual:encode(self.result)])_finalStale=YES;
    return @{@"schema":@"A23-two-epoch-entry-final-status-1",@"attempted":@(_finalAttempted),@"saved":@((BOOL)(_finalSaved && !_finalStale)),@"stale":@(_finalStale),@"hardware_verified":@NO};
}
@end
