#import "io_usb_host_burst_entry.h"
#include <CommonCrypto/CommonDigest.h>
#include <errno.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

static NSData *canonical(id value)
{
    return value && [NSJSONSerialization isValidJSONObject:value] ? [NSJSONSerialization dataWithJSONObject:value
        options:NSJSONWritingSortedKeys|NSJSONWritingWithoutEscapingSlashes error:NULL] : nil;
}
static NSString *digest(NSData *raw)
{
    unsigned char bytes[CC_SHA256_DIGEST_LENGTH];CC_SHA256(raw.bytes,(CC_LONG)raw.length,bytes);
    NSMutableString *s=[NSMutableString string];for(unsigned i=0;i<sizeof(bytes);++i)[s appendFormat:@"%02x",bytes[i]];return s;
}
static BOOL fail(NSError **error,NSString *reason)
{ if(error)*error=[NSError errorWithDomain:@"A23BurstEntry" code:1 userInfo:@{NSLocalizedDescriptionKey:reason}];return NO; }
static BOOL sameTyped(id value,id expected)
{
    if([expected isKindOfClass:NSDictionary.class]){
        if(![value isKindOfClass:NSDictionary.class] || ![[NSSet setWithArray:[value allKeys]] isEqual:[NSSet setWithArray:[expected allKeys]]])return NO;
        for(id key in expected)if(!sameTyped(value[key],expected[key]))return NO;
        return YES;
    }
    if([expected isKindOfClass:NSNumber.class]){
        if(![value isKindOfClass:NSNumber.class])return NO;
        BOOL eBool=CFGetTypeID((__bridge CFTypeRef)expected)==CFBooleanGetTypeID();
        BOOL vBool=CFGetTypeID((__bridge CFTypeRef)value)==CFBooleanGetTypeID();
        return eBool==vBool && (eBool || !CFNumberIsFloatType((__bridge CFNumberRef)value)) && [value isEqual:expected];
    }
    return [expected isKindOfClass:NSString.class] && [value isKindOfClass:NSString.class] && [value isEqual:expected];
}
NSDictionary *A23BurstDiagnosticScope(void)
{
    return @{@"kind":@"single_fresh_A23_diagnostic",@"runtime_record":@21,@"video_disabled_required":@YES,
        @"connection_speed_required":@3,@"baseline_accepted":@NO,@"allow_next_burst":@NO};
}
static NSData *readFileAt(int parent,const char *name,NSUInteger maximum)
{
    int fd=openat(parent,name,O_RDONLY|O_NOFOLLOW|O_NONBLOCK);struct stat st;
    if(fd<0)return nil;
    if(fstat(fd,&st)!=0 || !S_ISREG(st.st_mode) || st.st_size<=0 || (uint64_t)st.st_size>maximum){close(fd);return nil;}
    NSMutableData *raw=[NSMutableData dataWithLength:(NSUInteger)st.st_size];NSUInteger done=0;
    while(done<raw.length){ssize_t n=read(fd,(uint8_t *)raw.mutableBytes+done,raw.length-done);
        if(n<0 && errno==EINTR)continue;if(n<=0){close(fd);return nil;}done+=(NSUInteger)n;}
    char extra;BOOL end=read(fd,&extra,1)==0;close(fd);return end ? raw : nil;
}
BOOL A23ClaimBurstReceipt(NSString *directory,NSString *binary,NSError **error)
{
    int parent=open(directory.fileSystemRepresentation,O_RDONLY|O_DIRECTORY|O_NOFOLLOW);
    if(parent<0)return fail(error,@"Invalid run directory; no USB accessed");
    NSData *raw=readFileAt(parent,"authorization.json",16384);
    NSDictionary *r=raw ? [NSJSONSerialization JSONObjectWithData:raw options:0 error:NULL] : nil;
    NSData *program=[NSData dataWithContentsOfFile:binary];
    NSSet *keys=[NSSet setWithArray:@[@"schema",@"backend",@"attempt_consumed",@"receiver_sha256",@"build_manifest_sha256",@"preparation_id",@"plan",@"diagnostic_scope"]];
    NSMutableData *encoded=[canonical(r) mutableCopy];[encoded appendBytes:"\n" length:1];
    BOOL valid=[r isKindOfClass:NSDictionary.class] && [[NSSet setWithArray:r.allKeys] isEqual:keys] &&
        [raw isEqual:encoded] && sameTyped(r[@"schema"],@"A23-burst-sdk-consumed-receipt-1") &&
        sameTyped(r[@"backend"],@"iousbhost-single-burst-1") && sameTyped(r[@"attempt_consumed"],@YES) &&
        sameTyped(r[@"plan"],A23DormantBurstSDKPlan()) && sameTyped(r[@"diagnostic_scope"],A23BurstDiagnosticScope()) &&
        [r[@"receiver_sha256"] isKindOfClass:NSString.class] && program.length>0 && [r[@"receiver_sha256"] isEqual:digest(program)] &&
        [r[@"build_manifest_sha256"] isKindOfClass:NSString.class] && [r[@"build_manifest_sha256"] length]==64 &&
        [r[@"preparation_id"] isKindOfClass:NSString.class] && [[NSUUID alloc] initWithUUIDString:r[@"preparation_id"]]!=nil;
    if(valid){NSCharacterSet *bad=[[NSCharacterSet characterSetWithCharactersInString:@"0123456789abcdef"] invertedSet];
        valid=[r[@"build_manifest_sha256"] rangeOfCharacterFromSet:bad].location==NSNotFound;}
    if(!valid){close(parent);return fail(error,@"Missing/changed consumed burst receipt; no USB accessed");}
    int claim=openat(parent,"RECEIVER_CLAIMED",O_CREAT|O_EXCL|O_NOFOLLOW|O_WRONLY,0600);
    if(claim<0){close(parent);return fail(error,@"Burst receipt already claimed; no USB accessed");}
    BOOL claimed=fsync(claim)==0 && fsync(parent)==0;close(claim);close(parent);
    return claimed ? YES : fail(error,@"Burst claim not durable; no USB accessed");
}
BOOL A23SaveBurstEntryResult(NSString *directory,NSString *name,NSDictionary *result)
{
    NSData *raw=canonical(result);if(!raw || [name containsString:@"/"])return NO;
    int parent=open(directory.fileSystemRepresentation,O_RDONLY|O_DIRECTORY|O_NOFOLLOW);
    int fd=parent>=0 ? openat(parent,name.fileSystemRepresentation,O_CREAT|O_EXCL|O_NOFOLLOW|O_WRONLY,0600) : -1;
    if(fd<0){if(parent>=0)close(parent);return NO;}
    NSUInteger done=0;BOOL ok=YES;
    while(done<raw.length){ssize_t n=write(fd,(const uint8_t *)raw.bytes+done,raw.length-done);
        if(n<0 && errno==EINTR)continue;if(n<=0){ok=NO;break;}done+=(NSUInteger)n;}
    ok=ok && fsync(fd)==0;close(fd);
    ok=ok && [readFileAt(parent,name.fileSystemRepresentation,16384) isEqual:raw] && fsync(parent)==0;
    close(parent);return ok;
}
@implementation A23BurstEntry {
    NSString *_directory;dispatch_queue_t _queue;id<A23RuntimeClock> _clock;
    A23DormantBurstSDKDriver *_driver;BOOL _attempted,_stopped,_detached,_preflightFinished;
    uint64_t _interfaceID;NSString *_failure;NSDictionary *_preparationError;
}
- (instancetype)initWithDirectory:(NSString *)directory queue:(dispatch_queue_t)queue clock:(id<A23RuntimeClock>)clock
{
    if(!directory || !queue || !clock)return nil;
    if((self=[super init])){_directory=[directory copy];_queue=queue;_clock=clock;}return self;
}
- (BOOL)interrupted { return _stopped || _detached || (_interruptionRequested && _interruptionRequested()); }
- (BOOL)preflightFailure:(NSString *)reason error:(NSError *)error resources:(id<A23SessionResources>)resources
{
    // Called only before driver start: no ISO/control request can exist yet.
    [resources closeWhenNoIO];_preflightFinished=YES;_failure=reason;
    _preparationError=error ? A23PreparationErrorDetails(error) : nil;return NO;
}
- (BOOL)startCandidates:(NSArray<NSDictionary *> *)candidates provider:(id<A23SessionProvider>)provider
{
    dispatch_assert_queue(_queue);if(_attempted)return NO;_attempted=YES;
    if([self interrupted])return [self preflightFailure:@"interrupted_before_open" error:nil resources:nil];
    if(candidates.count!=1)return [self preflightFailure:@"missing_or_ambiguous_interface" error:nil resources:nil];
    _interfaceID=[candidates.firstObject[@"interface_id"] unsignedLongLongValue];
    NSError *error=nil;
    A23SimulationJournal *journal=[[A23SimulationJournal alloc] initWithPath:[_directory stringByAppendingPathComponent:@"session.jsonl"] error:&error];
    if(!journal)return [self preflightFailure:@"journal_create_failed" error:error resources:nil];
    id<A23SessionResources> resources=[provider openCandidate:candidates.firstObject error:&error];
    if(!resources)return [self preflightFailure:@"sdk_prepare_failed" error:error resources:nil];
    if([self interrupted])return [self preflightFailure:@"interrupted_after_open" error:nil resources:resources];
    if(![resources conformsToProtocol:@protocol(A23PreparedBurstResources)])
        return [self preflightFailure:@"missing_burst_capability" error:nil resources:resources];
    _driver=[[A23DormantBurstSDKDriver alloc] initWithResources:(id<A23PreparedBurstResources>)resources
        directory:_directory queue:_queue clock:_clock journal:journal error:&error];
    if(!_driver)return [self preflightFailure:@"coordinator_prepare_failed" error:error resources:resources];
    __weak A23BurstEntry *weak=self;_driver.interruptionRequested=^BOOL{return [weak interrupted];};
    return [_driver start];
}
- (void)poll { dispatch_assert_queue(_queue);[_driver poll]; }
- (void)requestExit { dispatch_assert_queue(_queue);_stopped=YES;[_driver requestExit]; }
- (void)detachedRegistryID:(uint64_t)registryID
{
    dispatch_assert_queue(_queue);
    if(registryID && registryID==_interfaceID){_detached=YES;[_driver detachedRegistryID:registryID];}
}
- (NSDictionary *)result
{
    dispatch_assert_queue(_queue);NSDictionary *host=_driver.result;
    return @{@"schema":@"A23-burst-sdk-entry-result-1",@"backend":@"iousbhost-single-burst-1",
        @"attempted":@(_attempted),@"preflight_failed":@(_preflightFinished),@"failure":_failure ?: (id)NSNull.null,
        @"preparation_error":_preparationError ?: (id)NSNull.null,@"host_result":host ?: (id)NSNull.null,
        @"finished":@((BOOL)(_preflightFinished || [host[@"finished"] boolValue])),@"unresolved":@([host[@"unresolved"] boolValue]),
        @"exit_code":@(_preflightFinished ? 1 : host ? [host[@"exit_code"] intValue] : 1),
        @"hardware_verified":@NO,@"usb_strict_pass":@NO,@"baseline_accepted":@NO,@"allow_next_burst":@NO,@"callback_drain_verified":@NO};
}
@end
