// Appended to frozen fake SDK/entry fixture prefixes. One actual context hello,
// one explicitly bound stdin command, fake operations only. No acquisition CLI.
#import "../host/a23_scope_verifier.h"
#import <CommonCrypto/CommonDigest.h>
static NSData *brokerJSON(id v){NSMutableData *r=[[NSJSONSerialization dataWithJSONObject:v options:NSJSONWritingSortedKeys|NSJSONWritingWithoutEscapingSlashes error:NULL] mutableCopy];[r appendBytes:"\n" length:1];return r;}
static NSString *brokerSHA(NSData *r){unsigned char h[32];CC_SHA256(r.bytes,(CC_LONG)r.length,h);NSMutableString *s=[NSMutableString new];for(unsigned i=0;i<32;i++)[s appendFormat:@"%02x",h[i]];return s;}
static NSDictionary *brokerLoad(NSString *p){NSData *r=[NSData dataWithContentsOfFile:p];id v=r ? [NSJSONSerialization JSONObjectWithData:r options:0 error:NULL] : nil;return [v isKindOfClass:NSDictionary.class]?v:nil;}
@interface BrokerClock : TwoClock
@end
@implementation BrokerClock {atomic_uint_fast64_t _value;}
- (instancetype)init {if((self=[super init]))atomic_init(&_value,mach_absolute_time()+100);return self;}
- (uint64_t)nowTicks{return atomic_fetch_add(&_value,100);}
- (uint32_t)numerator{return 1;}
- (uint32_t)denominator{return 1;}
- (void)advanceNS:(uint64_t)n{atomic_fetch_add(&_value,n);}
@end
int main(int argc,const char *argv[]){@autoreleasepool {
    if(argc!=4 || strcmp(argv[1],"--model") || strcmp(argv[2],"normal"))return 2;
    NSString *handoffPath=@(argv[3]),*root=handoffPath.stringByDeletingLastPathComponent.stringByDeletingLastPathComponent,*execution=[root stringByAppendingPathComponent:@"execution"],*host=[execution stringByAppendingPathComponent:@"host"];
    NSDictionary *plan=brokerLoad([root stringByAppendingPathComponent:@"plan.json"]),*handoff=brokerLoad(handoffPath);if(!plan || !handoff)return 3;NSString *name=plan[@"case"];
    if([@[@"timeout-before-hello",@"hello-timeout-before-hello"] containsObject:name])(void)getchar();
    char *p=realpath(argv[0],NULL);if(!p)return 3;NSDictionary *actual=A23ReadExecutionContext(@(p));free(p);
    NSMutableDictionary *environment=[NSMutableDictionary new];for(NSString *key in @[@"LANG",@"LC_ALL",@"PATH",@"TMPDIR"]){const char *q=getenv(key.UTF8String);if(!q)return 3;environment[key]=@(q);}
    BOOL forbidden=NO;for(NSString *key in @[@"PYTHONPATH",@"PYTHONHOME",@"DYLD_INSERT_LIBRARIES",@"DYLD_LIBRARY_PATH",@"LD_PRELOAD"])if(getenv(key.UTF8String))forbidden=YES;
    NSDictionary *hello=@{@"schema":@"A23-supervisor-model-hello-1",@"nonce":handoff[@"nonce"],@"handoff_sha256":brokerSHA([NSData dataWithContentsOfFile:handoffPath]),@"environment_sha256":brokerSHA(brokerJSON(environment)),@"forbidden_environment_present":@(forbidden),@"context":actual,@"hardware_entry_enabled":@NO};NSData *helloRaw=brokerJSON(hello);fwrite(helloRaw.bytes,1,helloRaw.length,stdout);fflush(stdout);
    char line[4097];BOOL got=fgets(line,sizeof(line),stdin)!=NULL;NSData *controlRaw=got?[NSData dataWithBytes:line length:strlen(line)]:nil;NSDictionary *control=got?[NSJSONSerialization JSONObjectWithData:controlRaw options:0 error:NULL]:nil;
    BOOL command=control && [controlRaw isEqual:[NSData dataWithContentsOfFile:[root stringByAppendingPathComponent:@"control.json"]]] && [control[@"nonce"] isEqual:handoff[@"nonce"]] && [brokerJSON(control[@"actual_context"]) isEqual:brokerJSON(actual)];
    BOOL inject=[plan[@"inject_policy"] isEqual:@YES] && CFGetTypeID((__bridge CFTypeRef)plan[@"inject_policy"])==CFBooleanGetTypeID();
    NSMutableDictionary *context=[actual mutableCopy];if(inject){context[@"sandbox_query_available"]=@YES;context[@"sandbox_query_result"]=@0;context[@"sandbox_query_errno"]=@0;}
    if([name isEqual:@"context-substitution"])context[@"pid"]=@123;
    BOOL execute=command && [control[@"action"] isEqual:@"execute_model"] && (inject || A23ValidateExecutionContext(actual,actual[@"receiver_sha256"]));
    if([name isEqual:@"timeout-after-command"] && execute){assert([[@"seen\n" dataUsingEncoding:NSUTF8StringEncoding] writeToFile:[execution stringByAppendingPathComponent:@"command-seen"] options:NSDataWritingWithoutOverwriting error:NULL]);(void)getchar();}
    execute=execute && ![[NSFileManager defaultManager] fileExistsAtPath:[root stringByAppendingPathComponent:@"STOP"]];
    NSDictionary *roots=plan[@"roots"];A23ModelScopeVerifier *v=[[A23ModelScopeVerifier alloc] initWithBuild:plan[@"receiver_build"] repository:roots[@"repository"] cards:roots[@"cards"] ledger:roots[@"ledger"] records:roots[@"records"]];assert(v);BOOL core=[v verifyCore];NSDictionary *scope=v.scope;
    __block A23SharedSequenceModelPermit *permit=nil;__block A23TwoEpochEntry *entry=nil;__block A23VerifiedEntryCoordinator *coordinator=nil;
    PairOperations *op=pairOperations(name,NO);SDKModelInterface *r=[SDKModelInterface new];r.fault=[name isEqual:@"injected-queued-delay"]?@"queued-delay":name;r.clock=[BrokerClock new];op.interface=r;
    assert([pairCandidate()[@"service_token"] intValue]==7 && !pairZero(r.dataStores[0]) && [efContext(actual[@"receiver_sha256"])[@"pid"] intValue]==123);
    NSMutableData *storage=[NSMutableData dataWithLength:sizeof(EntryFixture)];EntryFixture *f=storage.mutableBytes;f->interface=r;
    A23WaitOps ops={.context=f,.create=efCreate,.matching=efMatching,.valid=efValid,.next=efNext,.identity=efIdentity,.interest=efInterest,.pump=efPump,.release=efRelease,.destroy=efDestroy};dispatch_queue_t queue=dispatch_queue_create("a23.broker.fake-sdk",DISPATCH_QUEUE_SERIAL);
    NSDictionary *config=brokerLoad([execution stringByAppendingPathComponent:@"config.json"]);NSString *job=control[@"job_path"];
    if(execute && core)dispatch_sync(queue,^{
        permit=[[A23SharedSequenceModelPermit alloc] initWithJob:job expectedScope:scope verifier:^BOOL(NSDictionary *s){return ![[NSFileManager defaultManager] fileExistsAtPath:[root stringByAppendingPathComponent:@"STOP"]] && [v verifyScope:s job:job];}];
        if(!permit)return;A23PairedSimulationProvider *provider=pairProvider(op,queue,YES,^(uint32_t mask){(void)mask;[entry detachedRegistryID:102];});entry=[[A23TwoEpochEntry alloc] initWithDirectory:host queue:queue clock:r.clock ops:&ops provider:provider permit:permit context:context binding:config[@"binding"]];assert(entry);
        coordinator=[[A23VerifiedEntryCoordinator alloc] initWithEntry:entry verifier:v permit:permit scope:scope job:job];[coordinator begin];[coordinator tick];[coordinator tick];
    });
    __block BOOL started=NO;if(entry)dispatch_sync(queue,^{started=[entry.result[@"started"] boolValue];});
    if(started){for(NSUInteger n=0;n<2;n++){__block BOOL stopped;dispatch_sync(queue,^{stopped=[entry.result[@"stopped"] boolValue];});if(stopped)break;
        if([name isEqual:@"injected-queued-delay"])dispatch_sync(queue,^{[r deliver:n];[r.clock advanceNS:25000000];});else [r deliver:n];dispatch_sync(queue,^{[coordinator tick];});if(!n)dispatch_sync(queue,^{[coordinator tick];});}
        [r.clock advanceNS:250000001];dispatch_sync(queue,^{[coordinator tick];});}
    __block NSDictionary *result=@{},*final=@{},*native=@{};
    dispatch_sync(queue,^{if(coordinator){[coordinator finalizeOnce];result=coordinator.result;final=coordinator.finalStatus;efExport(host,@"entry-current.json",result);efExport(host,@"entry-final-status.json",final);if([result[@"driver"] isKindOfClass:NSDictionary.class]){efExport(host,@"result.json",result[@"driver"]);efExport(host,@"receipt-status.json",result[@"driver_receipt"]);}}
        NSDictionary *pr=permit?permit.result:@{};BOOL replay=YES;if(permit)replay=![permit claimProcess:config[@"binding"] context:context] && ![permit claimSelection:(A23WaitIdentity){.device_id=101,.interface_id=102,.speed=3} binding:config[@"binding"] context:context];
        native=@{@"schema":@"A23-shared32-native-fixture-1",@"init_accepted":@((BOOL)(permit!=nil)),@"process_returned":pr[@"process_claimed"]?:@NO,@"selection_returned":pr[@"selection_claimed"]?:@NO,@"replay_blocked":@(replay),@"permit":pr,@"real_sdk_objects":@0,@"usb_requests":@0,@"sd_accesses":@0};});
    NSDictionary *report=@{@"schema":@"A23-verified-scope-fixture-1",@"case":name,@"verifier":v.result,@"native":native,@"entry":result,@"final":final,@"actual_context":actual,@"execution_context":context,@"execution_context_injected":@(inject),@"command_valid":@(command),@"model_execute_admitted":@(execute),@"calls":@{@"wait_creates":@(f->creates),@"opens":@(op.opens),@"iso_submissions":@(r.submissions),@"burst_triggers":@(r.triggers),@"aborts":@(r.aborts)},@"real_sdk_objects":@0,@"usb_requests":@0,@"sd_accesses":@0};
    NSData *raw=brokerJSON(report);if(![raw writeToFile:[execution stringByAppendingPathComponent:@"report.json"] options:NSDataWritingWithoutOverwriting error:NULL])return 3;return 0;
}}
