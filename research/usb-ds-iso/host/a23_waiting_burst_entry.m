#import "a23_waiting_burst_entry.h"
#include <CommonCrypto/CommonDigest.h>
#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static BOOL errorOut(NSError **error,NSString *message)
{ if(error)*error=[NSError errorWithDomain:@"A23WaitingEntry" code:1 userInfo:@{NSLocalizedDescriptionKey:message}];return NO; }
static NSData *json(id value)
{ return value && [NSJSONSerialization isValidJSONObject:value] ? [NSJSONSerialization dataWithJSONObject:value options:NSJSONWritingSortedKeys|NSJSONWritingWithoutEscapingSlashes error:NULL] : nil; }
static NSString *sha(NSData *raw)
{
    unsigned char bytes[CC_SHA256_DIGEST_LENGTH];CC_SHA256(raw.bytes,(CC_LONG)raw.length,bytes);
    NSMutableString *s=[NSMutableString string];for(unsigned i=0;i<sizeof(bytes);++i)[s appendFormat:@"%02x",bytes[i]];return s;
}
static BOOL hex(id s)
{ return [s isKindOfClass:NSString.class] && [s length]==64 && [s rangeOfCharacterFromSet:[[NSCharacterSet characterSetWithCharactersInString:@"0123456789abcdef"] invertedSet]].location==NSNotFound; }
static BOOL typed(id a,id b)
{
    if([b isKindOfClass:NSDictionary.class]){
        if(![a isKindOfClass:NSDictionary.class] || ![[NSSet setWithArray:[a allKeys]] isEqual:[NSSet setWithArray:[b allKeys]]])return NO;
        for(id k in b)if(!typed(a[k],b[k]))return NO;return YES;
    }
    if([b isKindOfClass:NSNumber.class]){
        if(![a isKindOfClass:NSNumber.class])return NO;
        BOOL ab=CFGetTypeID((__bridge CFTypeRef)a)==CFBooleanGetTypeID(),bb=CFGetTypeID((__bridge CFTypeRef)b)==CFBooleanGetTypeID();
        return ab==bb && (ab || !CFNumberIsFloatType((__bridge CFNumberRef)a)) && [a isEqual:b];
    }
    return [a isKindOfClass:NSString.class] && [b isKindOfClass:NSString.class] && [a isEqual:b];
}
static NSData *readBounded(int parent,const char *name,NSUInteger maximum)
{
    int fd=openat(parent,name,O_RDONLY|O_NOFOLLOW|O_NONBLOCK);struct stat st;
    if(fd<0)return nil;
    if(fstat(fd,&st) || !S_ISREG(st.st_mode) || st.st_size<=0 || (uint64_t)st.st_size>maximum){close(fd);return nil;}
    NSMutableData *raw=[NSMutableData dataWithLength:(NSUInteger)st.st_size];NSUInteger n=0;
    while(n<raw.length){ssize_t r=read(fd,(uint8_t *)raw.mutableBytes+n,raw.length-n);if(r<0 && errno==EINTR)continue;
        if(r<=0){close(fd);return nil;}n+=(NSUInteger)r;}
    char extra;BOOL ok=read(fd,&extra,1)==0;close(fd);return ok ? raw : nil;
}
static BOOL canonicalPath(NSString *path)
{
    if(!path.isAbsolutePath || strlen(path.fileSystemRepresentation)!=[path lengthOfBytesUsingEncoding:NSUTF8StringEncoding])return NO;
    // Foundation folds /private/tmp into /tmp on this host; use POSIX realpath
    // so the frozen Python inventory and native guard share the same spelling.
    char *resolved=realpath(path.fileSystemRepresentation,NULL);int pathError=errno;
    NSString *expected=resolved ? @(resolved) : nil;free(resolved);
    if(!expected && pathError==ENOENT){
        resolved=realpath(path.stringByDeletingLastPathComponent.fileSystemRepresentation,NULL);
        if(resolved)expected=[@(resolved) stringByAppendingPathComponent:path.lastPathComponent];free(resolved);
    }
    return expected && [path isEqual:expected];
}

NSDictionary *A23WaitingBurstPlan(void)
{
    return @{@"schema":@"A23-waiting-burst-plan-1",@"backend":@"a23-waiting-burst-1",
        @"sdk_plan":A23DormantBurstSDKPlan(),@"diagnostic_scope":A23BurstDiagnosticScope(),
        @"max_handoffs":@1,@"repeat":@0,@"initial_matches":@"reject",
        @"gate_order":@"claim_before_sdk_open",@"start_order":@"prepare_close_waiter_start",
        @"notification_pump_during_sdk_start":@NO,@"hardware_entry_enabled":@NO,@"allow_next_burst":@NO};
}

@implementation A23WaitingJournal { int _parent,_fd;BOOL _failed;NSUInteger _rows; }
- (instancetype)initWithPath:(NSString *)path
{
    if((self=[super init])){
        _parent=-1;_fd=-1;if(!canonicalPath(path))return nil;
        _parent=open(path.stringByDeletingLastPathComponent.fileSystemRepresentation,O_RDONLY|O_DIRECTORY|O_NOFOLLOW);
        if(_parent<0)return nil;
        _fd=openat(_parent,path.lastPathComponent.fileSystemRepresentation,O_CREAT|O_EXCL|O_NOFOLLOW|O_RDWR,0600);
        if(_fd<0 || fsync(_parent))return nil;
    }return self;
}
- (void)dealloc { if(_fd>=0)close(_fd);if(_parent>=0)close(_parent); }
- (BOOL)append:(NSDictionary *)event error:(NSError **)error
{
    if(_failed || _rows>=128)return errorOut(error,@"wait journal failed or full");
    NSData *raw=json(event);if(!raw || raw.length>4095){_failed=YES;return errorOut(error,@"invalid wait row");}
    NSMutableData *line=[raw mutableCopy];[line appendBytes:"\n" length:1];off_t start=lseek(_fd,0,SEEK_END);BOOL ok=start>=0;
    NSUInteger done=0;
    while(ok && done<line.length){ssize_t n=write(_fd,(const uint8_t *)line.bytes+done,line.length-done);
        if(n<0 && errno==EINTR)continue;if(n<=0){ok=NO;break;}done+=(NSUInteger)n;}
    ok=ok && fsync(_fd)==0;NSMutableData *copy=[NSMutableData dataWithLength:line.length];done=0;
    while(ok && done<copy.length){ssize_t n=pread(_fd,(uint8_t *)copy.mutableBytes+done,copy.length-done,start+(off_t)done);
        if(n<0 && errno==EINTR)continue;if(n<=0){ok=NO;break;}done+=(NSUInteger)n;}
    ok=ok && [copy isEqual:line] && fsync(_parent)==0;
    if(!ok){_failed=YES;return errorOut(error,@"wait journal write/fsync/readback failed");}++_rows;return YES;
}
@end

@implementation A23WaitingReceiptPermit { NSString *_directory,*_binary,*_manifest,*_recipe;BOOL _attempted; }
- (instancetype)initWithDirectory:(NSString *)directory binary:(NSString *)binary buildManifest:(NSString *)manifest recipe:(NSString *)recipe
{
    if(!canonicalPath(directory) || !canonicalPath(binary) || !hex(manifest) || !hex(recipe))return nil;
    if((self=[super init])){_directory=[directory copy];_binary=[binary copy];_manifest=[manifest copy];_recipe=[recipe copy];}return self;
}
- (BOOL)claimForIdentity:(A23WaitIdentity)identity error:(NSError **)error
{
    if(_attempted)return errorOut(error,@"permit already attempted");_attempted=YES;
    if(!identity.interface_id || !identity.device_id || identity.interface_id==identity.device_id || identity.speed!=3)
        return errorOut(error,@"invalid handoff identity");
    int parent=open(_directory.fileSystemRepresentation,O_RDONLY|O_DIRECTORY|O_NOFOLLOW);
    if(parent<0)return errorOut(error,@"invalid receipt directory");
    NSData *raw=readBounded(parent,"waiting-authorization.json",16384);
    NSDictionary *r=raw ? [NSJSONSerialization JSONObjectWithData:raw options:0 error:NULL] : nil;
    int binaryParent=open(_binary.stringByDeletingLastPathComponent.fileSystemRepresentation,O_RDONLY|O_DIRECTORY|O_NOFOLLOW);
    NSData *program=binaryParent>=0 ? readBounded(binaryParent,_binary.lastPathComponent.fileSystemRepresentation,64*1024*1024) : nil;
    if(binaryParent>=0)close(binaryParent);
    BOOL valid=[r isKindOfClass:NSDictionary.class];
    if(valid){
        NSDictionary *expected=@{@"schema":@"A23-waiting-burst-consumed-receipt-1",@"backend":@"a23-waiting-burst-1",
            @"attempt_consumed":@YES,@"receiver_sha256":program ? sha(program) : @"",
            @"build_manifest_sha256":_manifest,@"recipe_sha256":_recipe,@"plan":A23WaitingBurstPlan(),
            @"preparation_id":r[@"preparation_id"] ?: @""};
        NSMutableData *encoded=[json(r) mutableCopy];[encoded appendBytes:"\n" length:1];
        valid=program.length>0 && typed(r,expected) && [encoded isEqual:raw] &&
            [r[@"preparation_id"] isKindOfClass:NSString.class] && [[NSUUID alloc] initWithUUIDString:r[@"preparation_id"]]!=nil;
    }
    close(parent);if(!valid)return errorOut(error,@"invalid waiting consumed receipt; no SDK opened");
    // Exclusive durable file is the irreversible single-use point. An error
    // after create still leaves the use burned; no remove/retry path exists.
    NSDictionary *claim=@{@"schema":@"A23-waiting-burst-claim-1",@"receipt_sha256":sha(raw),
        @"interface_id":@(identity.interface_id),@"device_id":@(identity.device_id),@"speed":@(identity.speed),
        @"build_manifest_sha256":_manifest,@"recipe_sha256":_recipe};
    return A23SaveBurstEntryResult(_directory,@"WAIT_RECEIVER_CLAIMED",claim) ? YES : errorOut(error,@"waiting receipt claimed or not durable");
}
@end

typedef struct { A23WaitOps original;void *owner; } WaitBridge;
@interface A23WaitingBurstEntry ()
- (BOOL)record:(NSString *)event details:(NSDictionary *)details;
- (uint64_t)clockTicks;
@end
static uint64_t now(void *p){WaitBridge *b=p;return [(__bridge A23WaitingBurstEntry *)b->owner clockTicks];}
static IONotificationPortRef create(void *p){WaitBridge *b=p;return b->original.create(b->original.context);}
static kern_return_t matching(void *p,IONotificationPortRef n,IOServiceMatchingCallback cb,void *ref,io_iterator_t *out)
{WaitBridge *b=p;return b->original.matching(b->original.context,n,cb,ref,out);}
static bool valid(void *p,io_iterator_t it){WaitBridge *b=p;return b->original.valid(b->original.context,it);}
static io_service_t next(void *p,io_iterator_t it){WaitBridge *b=p;return b->original.next(b->original.context,it);}
static bool identity(void *p,io_service_t s,A23WaitIdentity *out){WaitBridge *b=p;return b->original.identity(b->original.context,s,out);}
static kern_return_t interest(void *p,IONotificationPortRef n,io_service_t s,IOServiceInterestCallback cb,void *ref,io_object_t *out)
{WaitBridge *b=p;return b->original.interest(b->original.context,n,s,cb,ref,out);}
static int pump(void *p,IONotificationPortRef n){WaitBridge *b=p;return b->original.pump(b->original.context,n);}
static kern_return_t release(void *p,io_object_t s){WaitBridge *b=p;return b->original.release(b->original.context,s);}
static void destroy(void *p,IONotificationPortRef n){WaitBridge *b=p;b->original.destroy(b->original.context,n);}
static bool emit(void *p,const A23WaitEvent *e)
{
    WaitBridge *b=p;return [(__bridge A23WaitingBurstEntry *)b->owner record:@"adapter" details:
        @{@"index":@(e->index),@"event":@(e->event),@"phase":@(e->phase),@"reason":@(e->reason),@"ticks":@(e->ticks),
          @"interface_id":@(e->interface_id),@"device_id":@(e->device_id),@"count":@(e->count),@"native_result":@(e->native_result)}];
}
@implementation A23WaitingBurstEntry {
    NSString *_directory,*_sessionID,*_failure;dispatch_queue_t _queue;id<A23RuntimeClock> _clock;
    NSDictionary *_preparationError;
    id<A23SessionJournal> _journal;A23DormantBurstSDKDriver *_driver;id<A23PreparedBurstResources> _resources;
    A23PassiveWaitAdapter _adapter;WaitBridge _bridge;NSUInteger _index;uint64_t _lastTicks;
    BOOL _begun,_busy,_prepareAttempted,_claimed,_prepared,_started,_stopped,_terminal,_journalFailed;
}
- (instancetype)initWithDirectory:(NSString *)directory queue:(dispatch_queue_t)queue clock:(id<A23RuntimeClock>)clock journal:(id<A23SessionJournal>)journal
{
    if(!canonicalPath(directory) || !queue || !clock || !clock.numerator || !clock.denominator || !journal)return nil;
    if((self=[super init])){_directory=[directory copy];_queue=queue;_clock=clock;_journal=journal;_sessionID=NSUUID.UUID.UUIDString;}return self;
}
- (BOOL)record:(NSString *)event details:(NSDictionary *)details
{
    uint64_t tick=_clock.nowTicks;if(_journalFailed || tick<_lastTicks){_journalFailed=YES;return NO;}_lastTicks=tick;
    NSDictionary *row=@{@"schema":@"A23-waiting-burst-event-1",@"session_id":_sessionID,@"index":@(++_index),@"ticks":@(tick),
        @"event":event,@"details":details,@"hardware_verified":@NO,@"allow_next_burst":@NO};
    if(![_journal append:row error:NULL]){_journalFailed=YES;return NO;}return YES;
}
- (uint64_t)clockTicks { return _clock.nowTicks; }
- (BOOL)interrupted { return _stopped || (_interruptionRequested && _interruptionRequested()); }
- (BOOL)fail:(NSString *)reason
{
    if(_terminal)return NO;
    _failure=reason;_terminal=YES;[_resources closeWhenNoIO];_resources=nil;
    a23_adapter_close(&_adapter,A23_W_REASON_INTERRUPTED);[self record:@"preflight_failed" details:@{@"reason":reason,@"preparation_error":_preparationError ?: (id)NSNull.null}];return NO;
}
- (BOOL)beginWithOps:(const A23WaitOps *)ops deadline:(uint64_t)deadline
{
    dispatch_assert_queue(_queue);if(_begun || _busy || _terminal)return NO;_begun=YES;
    if(!ops || !ops->now || !ops->create || !ops->matching || !ops->valid || !ops->next || !ops->identity || !ops->interest || !ops->pump || !ops->release || !ops->destroy)
        return [self fail:@"invalid_wait_ops"];
    if([self interrupted])return [self fail:@"interrupted_before_wait"];
    _bridge=(WaitBridge){.original=*ops,.owner=(__bridge void *)self};
    A23WaitOps wrapped={.context=&_bridge,.now=now,.create=create,.matching=matching,.valid=valid,.next=next,.identity=identity,
        .interest=interest,.pump=pump,.release=release,.destroy=destroy,.emit=emit};
    _busy=YES;BOOL ok=[self record:@"begin" details:@{@"plan":A23WaitingBurstPlan(),@"deadline":@(deadline),
        @"timebase_numerator":@(_clock.numerator),@"timebase_denominator":@(_clock.denominator)}] && ![self interrupted] && a23_adapter_start(&_adapter,&wrapped,deadline);_busy=NO;
    return ok ? YES : [self fail:@"wait_begin_failed"];
}
- (BOOL)pollWaiting
{
    dispatch_assert_queue(_queue);if(!_begun || _busy || _prepareAttempted || _terminal)return NO;
    if([self interrupted])return [self fail:@"interrupted_waiting"];
    _busy=YES;BOOL ok=a23_adapter_poll(&_adapter) && ![self interrupted];_busy=NO;
    return ok ? YES : [self fail:@"wait_stopped"];
}
- (BOOL)prepareWithProvider:(id<A23SessionProvider>)provider permit:(id<A23WaitingPermit>)permit
{
    dispatch_assert_queue(_queue);if(!_begun || _busy || _terminal || _prepareAttempted)return NO;
    // Calling too early burns this entry, never spins/chooses another device.
    _prepareAttempted=YES;_busy=YES;io_service_t service=0;A23WaitIdentity idn={0};
    BOOL ok=provider && permit && ![self interrupted] && a23_adapter_take(&_adapter,&service,&idn) && ![self interrupted];
    _busy=NO;if(!ok)return [self fail:@"handoff_failed"];
    _busy=YES;NSError *error=nil;
    A23WaitingJournal *sdkJournal=[[A23WaitingJournal alloc] initWithPath:[_directory stringByAppendingPathComponent:@"session.jsonl"]];
    ok=sdkJournal && [self record:@"claim_intent" details:@{@"interface_id":@(idn.interface_id),@"device_id":@(idn.device_id)}] && ![self interrupted];
    if(ok)_claimed=[permit claimForIdentity:idn error:&error];
    ok=ok && _claimed && [self record:@"claim_committed" details:@{}] && ![self interrupted];
    if(ok){
        NSDictionary *c=@{@"service_token":@(service),@"interface_id":@(idn.interface_id),@"device_id":@(idn.device_id),
            @"parent_device_id":@(idn.device_id),@"connection_speed":@(idn.speed)};
        if([self record:@"sdk_open_intent" details:c] && ![self interrupted])
            _resources=(id<A23PreparedBurstResources>)[provider openCandidate:c error:&error];
        NSDictionary *expected=@{@"interface_id":@(idn.interface_id),@"device_id":@(idn.device_id),@"parent_device_id":@(idn.device_id)};
        ok=_resources && [_resources conformsToProtocol:@protocol(A23PreparedBurstResources)] && typed(_resources.identity,expected) && ![self interrupted];
    }
    if(ok)ok=a23_adapter_poll(&_adapter); // last pending notifications before close
    a23_adapter_close(&_adapter,A23_W_REASON_NONE);
    ok=ok && _adapter.closed && !_adapter.failed_releases && !_adapter.journal_failed && !_journalFailed && ![self interrupted];
    if(ok)ok=[self record:@"waiter_closed" details:@{@"failed_releases":@(_adapter.failed_releases),@"handoffs":@(_adapter.policy.handoffs)}] && ![self interrupted];
    if(ok)_driver=[[A23DormantBurstSDKDriver alloc] initWithResources:_resources directory:_directory queue:_queue clock:_clock journal:sdkJournal error:&error];
    ok=ok && _driver!=nil;
    if(ok){__weak A23WaitingBurstEntry *weak=self;_driver.interruptionRequested=^BOOL{return [weak interrupted];};
        ok=[self record:@"prepared" details:@{@"binding":_driver.result[@"binding"]}] && ![self interrupted];}
    _busy=NO;if(!ok){_preparationError=error ? A23PreparationErrorDetails(error) : nil;return [self fail:@"prepare_failed"];}
    _prepared=YES;return YES;
}
- (BOOL)startPrepared
{
    dispatch_assert_queue(_queue);if(_busy || !_prepared || _started || _terminal)return NO;
    if([self interrupted])return [self fail:@"interrupted_before_start"];
    _busy=YES;BOOL ok=[self record:@"start_intent" details:@{@"binding":_driver.result[@"binding"]}] && ![self interrupted];
    if(ok){_started=YES;ok=[_driver start];}_busy=NO;
    // Once the driver starts it owns pending/late I/O; never preflight-close it.
    if(!_started)return [self fail:@"start_journal_or_interruption"];
    return ok;
}
- (void)poll { dispatch_assert_queue(_queue);if(_started && !_busy)[_driver poll]; }
- (void)requestExit
{
    dispatch_assert_queue(_queue);_stopped=YES;
    if(_started){[_driver requestExit];return;}
    if(!_busy)[self fail:@"exit_before_start"];
}
- (void)detachedRegistryID:(uint64_t)registryID
{
    dispatch_assert_queue(_queue);if(registryID && registryID==_adapter.identity.interface_id){
        _stopped=YES;if(_started)[_driver detachedRegistryID:registryID];else if(!_busy)[self fail:@"detach_before_start"];
    }
}
- (NSDictionary *)result
{
    dispatch_assert_queue(_queue);NSDictionary *host=_driver.result;NSMutableArray *refs=[NSMutableArray array];
    for(unsigned i=0;i<_adapter.failed_releases && i<5;++i)[refs addObject:@(_adapter.unreleased[i])];
    return @{@"schema":@"A23-waiting-burst-entry-result-1",@"wait_session_id":_sessionID,
        @"begun":@(_begun),@"prepare_attempted":@(_prepareAttempted),@"permit_claimed":@(_claimed),@"prepared":@(_prepared),@"started":@(_started),
        @"waiter_closed":@(_adapter.closed),@"wait_journal_failed":@((BOOL)(_journalFailed || _adapter.journal_failed)),
        @"handoffs":@(_adapter.policy.handoffs),@"failed_releases":@(_adapter.failed_releases),@"unreleased_tokens":refs,
        @"preflight_failed":@(_terminal),@"failure":_failure ?: (id)NSNull.null,@"preparation_error":_preparationError ?: (id)NSNull.null,@"host_result":host ?: (id)NSNull.null,
        @"finished":@((BOOL)(_terminal || [host[@"finished"] boolValue])),@"unresolved":@([host[@"unresolved"] boolValue]),
        @"hardware_verified":@NO,@"usb_strict_pass":@NO,@"allow_next_burst":@NO};
}
@end
