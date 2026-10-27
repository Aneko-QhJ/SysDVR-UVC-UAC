#import "../host/a23_two_epoch_entry.h"
typedef struct {unsigned left,refs[8],pumps,creates,destroys;BOOL arrival,active,existing,ambiguous,noArrival,releaseFault;
    IOServiceMatchingCallback match;void *ref;__unsafe_unretained SDKModelInterface *interface;} EntryFixture;
static IONotificationPortRef efCreate(void *p){EntryFixture *f=p;assert(!f->active);f->active=YES;f->creates++;return (void *)(uintptr_t)1;}
static kern_return_t efMatching(void *p,IONotificationPortRef n,IOServiceMatchingCallback c,void *r,io_iterator_t *out){EntryFixture *f=p;assert(n && f->active);f->match=c;f->ref=r;f->left=f->existing?1:0;f->refs[1]++;*out=1;return 0;}
static bool efValid(void *p,io_iterator_t i){(void)p;assert(i==1);return true;}
static io_service_t efNext(void *p,io_iterator_t i){EntryFixture *f=p;assert(i==1);if(!f->left)return 0;f->left--;f->refs[7]++;return 7;}
static bool efIdentity(void *p,io_service_t s,A23WaitIdentity *i){EntryFixture *f=p;assert(s==7 && f->refs[7]);*i=(A23WaitIdentity){.interface_id=102,.device_id=101,.speed=3};return true;}
static kern_return_t efInterest(void *p,IONotificationPortRef n,io_service_t s,IOServiceInterestCallback c,void *r,io_object_t *o){EntryFixture *f=p;(void)c;(void)r;assert(n && s==7);f->refs[2]++;*o=2;return 0;}
static int efPump(void *p,IONotificationPortRef n){EntryFixture *f=p;assert(n && f->active && !f->interface.statusReads);f->pumps++;
    if(!f->arrival && !f->noArrival){f->arrival=YES;f->left=f->ambiguous?2:1;f->match(f->ref,1);return 1;}return 0;}
static kern_return_t efRelease(void *p,io_object_t s){EntryFixture *f=p;assert(s<8 && f->refs[s] && !f->interface.statusReads);if(f->releaseFault && s==2)return kIOReturnError;--f->refs[s];return 0;}
static void efDestroy(void *p,IONotificationPortRef n){EntryFixture *f=p;assert(n && f->active && !f->interface.statusReads);f->active=NO;f->destroys++;}
@interface EntryPermit : NSObject <A23TwoEpochEntryPermit>
@property NSString *fault,*directory;
@property NSMutableData *fixtureStorage;
@property NSUInteger processes,selections;
@property BOOL identitiesMatch;
@property(copy) void (^hook)(BOOL selection);
@end
@implementation EntryPermit
- (BOOL)claimProcess:(NSDictionary *)binding context:(NSDictionary *)context {
    assert(++_processes==1 && [binding[@"first_sequence"] intValue]==81 && context[@"pid"]);
    assert([[NSFileManager defaultManager] fileExistsAtPath:[_directory stringByAppendingPathComponent:@"context.json"]]);if(_hook)_hook(NO);return ![_fault isEqual:@"process-reject"];
}
- (BOOL)claimSelection:(A23WaitIdentity)i binding:(NSDictionary *)binding context:(NSDictionary *)context {
    assert(++_selections==1 && _processes==1 && context[@"pid"] && [binding[@"last_sequence"] intValue]==112);_identitiesMatch=i.device_id==101 && i.interface_id==102 && i.speed==3;
    assert([[NSFileManager defaultManager] fileExistsAtPath:[_directory stringByAppendingPathComponent:@"process-claim.json"]]);if(_hook)_hook(YES);return _identitiesMatch && ![_fault isEqual:@"selection-reject"];
}
@end
static NSMutableDictionary *efContext(NSString *binarySHA){return [@{@"schema":@"A23-execution-context-1",@"pid":@123,@"ppid":@122,@"uid":@501,@"euid":@501,@"gid":@20,@"egid":@20,@"os_build":@"26A434",@"os_version":@"27.0.1",@"machine":@"arm64",@"receiver_path":@"/injected/entry-inspector",@"receiver_sha256":binarySHA,@"framework_uuid":@"B0D41EEF-C9BF-39DD-A1C4-226DCB94E78B",@"sandbox_query_available":@YES,@"sandbox_query_result":@0,@"sandbox_query_errno":@0,@"sample_begin_ticks":@1,@"sample_end_ticks":@2,@"usb_open_permission_proven":@NO,@"automatic_privilege_change":@NO} mutableCopy];}
static void efExport(NSString *directory,NSString *name,id value){NSData *d=[NSJSONSerialization dataWithJSONObject:value options:NSJSONWritingSortedKeys error:NULL];assert([d writeToFile:[directory stringByAppendingPathComponent:name] options:NSDataWritingWithoutOverwriting error:NULL]);}
int main(int argc,const char *argv[]){@autoreleasepool {
    assert(argc==2);NSString *root=@(argv[1]);NSMutableDictionary *matrix=[NSMutableDictionary new];
    NSArray *names=@[@"normal",@"queued-delay",@"context-sandbox",@"context-framework",@"context-bool",@"context-future",@"context-digest",@"exit-in-process-permit",@"exit-in-selection-permit",@"process-reject",@"process-collision",@"selection-reject",@"sdk-claim-collision",@"existing",@"ambiguous",@"wait-timeout",@"exit-before-begin",@"exit-waiting",@"exit-prepared",@"detach-prepared",@"wait-release-error",@"open-failed",@"interest-open",@"nil-2",@"mock-provider",@"bad-payload",@"control-timeout",@"exit-running",@"old-during-quiet",@"quiet-incomplete",@"receipt-collision",@"final-collision",@"old-after-final"];
    for(NSString *name in names){
        NSString *directory=[root stringByAppendingPathComponent:name];assert([[NSFileManager defaultManager] createDirectoryAtPath:directory withIntermediateDirectories:NO attributes:nil error:NULL]);
        PairOperations *op=pairOperations(name,[name isEqual:@"mock-provider"]);SDKModelInterface *r=[SDKModelInterface new];r.fault=name;r.clock=[TwoClock new];op.interface=r;
        assert([pairCandidate()[@"service_token"] intValue]==7 && !pairZero(r.dataStores[0]));
        EntryFixture initial={.interface=r,.existing=[name isEqual:@"existing"],.ambiguous=[name isEqual:@"ambiguous"],.noArrival=([name isEqual:@"wait-timeout"] || [name isEqual:@"exit-waiting"]),.releaseFault=[name isEqual:@"wait-release-error"]};
        NSMutableData *fixtureStorage=[NSMutableData dataWithLength:sizeof(EntryFixture)];EntryFixture *f=fixtureStorage.mutableBytes;*f=initial;
        A23WaitOps wait={.context=f,.create=efCreate,.matching=efMatching,.valid=efValid,.next=efNext,.identity=efIdentity,.interest=efInterest,.pump=efPump,.release=efRelease,.destroy=efDestroy};
        dispatch_queue_t q=dispatch_queue_create("a23.entry.model",DISPATCH_QUEUE_SERIAL);__block A23TwoEpochEntry *entry=nil;
        EntryPermit *permit=[EntryPermit new];permit.fault=name;permit.directory=directory;permit.fixtureStorage=fixtureStorage;
        NSString *hash=[@"a" stringByPaddingToLength:64 withString:@"a" startingAtIndex:0];NSMutableDictionary *context=efContext(hash);
        if([name isEqual:@"context-sandbox"])context[@"sandbox_query_result"]=@1;
        if([name isEqual:@"context-framework"])context[@"framework_uuid"]=@"BAD";
        if([name isEqual:@"context-bool"])context[@"pid"]=@YES;
        if([name isEqual:@"context-future"])context[@"sample_end_ticks"]=@(UINT64_MAX);
        if([name isEqual:@"context-digest"])context[@"receiver_sha256"]=[@"b" stringByPaddingToLength:64 withString:@"b" startingAtIndex:0];
        NSDictionary *binding=@{@"schema":@"A23-two-epoch-entry-binding-1",@"build_manifest_sha256":hash,@"receiver_sha256":hash,@"authorization_receipt_sha256":hash,@"first_sequence":@81,@"last_sequence":@112};
        dispatch_sync(q,^{
            A23PairedSimulationProvider *provider=pairProvider(op,q,![name isEqual:@"mock-provider"],^(uint32_t m){(void)m;[entry detachedRegistryID:102];});
            entry=[[A23TwoEpochEntry alloc] initWithDirectory:directory queue:q clock:r.clock ops:&wait provider:provider permit:permit context:context binding:binding];assert(entry);permit.hook=^(BOOL selected){if((selected && [name isEqual:@"exit-in-selection-permit"]) || (!selected && [name isEqual:@"exit-in-process-permit"]))[entry requestExit];};[entry tick];assert(!f->creates);
            if([name isEqual:@"exit-before-begin"])[entry requestExit];
            if([name isEqual:@"process-collision"])assert([@"preserved" writeToFile:[directory stringByAppendingPathComponent:@"process-claim.json"] atomically:NO encoding:NSUTF8StringEncoding error:NULL]);
            if([name isEqual:@"sdk-claim-collision"])assert([@"preserved" writeToFile:[directory stringByAppendingPathComponent:@"sdk-claim.json"] atomically:NO encoding:NSUTF8StringEncoding error:NULL]);
            [entry begin];assert(![entry begin]);
        });
        dispatch_sync(q,^{if([name isEqual:@"wait-timeout"])[r.clock advanceNS:121000000000ULL];if([name isEqual:@"exit-waiting"])[entry requestExit];[entry tick];assert(!r.statusReads && !r.submissions);
            if([entry.result[@"prepared"] boolValue]){assert(!f->active && f->destroys==1 && op.liveReferences==1);}
        });
        dispatch_sync(q,^{if([name isEqual:@"exit-prepared"])[entry requestExit];if([name isEqual:@"detach-prepared"])[entry detachedRegistryID:102];[entry tick];});
        __block BOOL started;dispatch_sync(q,^{started=[entry.result[@"started"] boolValue];});
        if(started){
            if([name isEqual:@"control-timeout"] || [name isEqual:@"exit-running"]){dispatch_sync(q,^{[r.clock advanceNS:17000000];if([name isEqual:@"exit-running"])[entry requestExit];[entry tick];});}
            else for(NSUInteger n=0;n<2;++n){
                __block BOOL stopped;dispatch_sync(q,^{stopped=[entry.result[@"stopped"] boolValue];});if(stopped)break;
                if([name isEqual:@"queued-delay"])dispatch_sync(q,^{[r deliver:n];[r.clock advanceNS:25000000];});else [r deliver:n];
                dispatch_sync(q,^{[entry tick];});if(n==0)dispatch_sync(q,^{[entry tick];});
            }
            if([name isEqual:@"old-during-quiet"])[r oldISO];
            if(![name isEqual:@"quiet-incomplete"])[r.clock advanceNS:250000001];dispatch_sync(q,^{[entry tick];});
        }
        dispatch_sync(q,^{
            if([name isEqual:@"receipt-collision"] || [name isEqual:@"final-collision"]){NSString *child=[name isEqual:@"receipt-collision"]?@"sdk-receipt":@"entry-final";assert([[NSFileManager defaultManager] createDirectoryAtPath:[directory stringByAppendingPathComponent:child] withIntermediateDirectories:NO attributes:nil error:NULL]);}
            [entry finalizeOnce];
        });
        if([name isEqual:@"old-after-final"]){[r oldISO];dispatch_sync(q,^{[entry tick];});}
        dispatch_sync(q,^{
            NSDictionary *result=entry.result,*final=entry.finalStatus;BOOL normal=[@[@"normal",@"queued-delay"] containsObject:name];
            if(normal)assert([result[@"complete"] boolValue] && [final[@"saved"] boolValue]);
            else if([name isEqual:@"quiet-incomplete"])assert(![result[@"complete"] boolValue] && ![final[@"attempted"] boolValue]);
            else assert([result[@"stopped"] boolValue] && ![result[@"complete"] boolValue]);
            if([name isEqual:@"old-after-final"])assert([final[@"stale"] boolValue] && ![final[@"saved"] boolValue]);
            assert(![entry finalizeOnce]);efExport(directory,@"entry-current.json",result);efExport(directory,@"entry-final-status.json",final);
            if([result[@"driver"] isKindOfClass:NSDictionary.class]){efExport(directory,@"result.json",result[@"driver"]);efExport(directory,@"receipt-status.json",result[@"driver_receipt"]);}
            NSDictionary *calls=@{@"process_permits":@(permit.processes),@"selection_permits":@(permit.selections),@"wait_creates":@(f->creates),@"wait_destroys":@(f->destroys),@"wait_pumps":@(f->pumps),@"wait_live_refs":@(f->refs[1]+f->refs[2]+f->refs[7]),@"opens":@(op.opens),@"retains":@(op.retainCalls),@"sdk_live_refs":@(op.liveReferences),@"sdk_destroys":@(r.destroys),@"iso_submissions":@(r.submissions),@"burst_enqueues":@(r.triggers),@"aborts":@(r.aborts)};
            efExport(directory,@"injected-entry.json",@{@"injected_fixture":@YES,@"context_origin_authenticated":@NO,@"calls":calls});matrix[name]=@{@"result":result,@"final_status":final,@"calls":calls};
        });
    }
    NSData *data=[NSJSONSerialization dataWithJSONObject:@{@"case_count":@(names.count),@"cases":matrix,@"real_sdk_objects":@0,@"native_iokit_calls":@0,@"usb_requests":@0,@"sd_accesses":@0} options:NSJSONWritingSortedKeys error:NULL];fwrite(data.bytes,1,data.length,stdout);puts("");return 0;
}}
