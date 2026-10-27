#import "a23_live_two_epoch.h"
#include <CommonCrypto/CommonDigest.h>
#include <signal.h>
#include <string.h>
#include <stdlib.h>
#include <IOKit/IOMessage.h>
static NSMutableArray *liveSources;
#include <sys/stat.h>
#include <unistd.h>
static NSString *canonical(NSString *path){char *p=realpath(path.fileSystemRepresentation,NULL);NSString *s=p?@(p):nil;free(p);return [s isEqual:path]?s:nil;}
static NSString *digest(NSData *r){unsigned char h[32];CC_SHA256(r.bytes,(CC_LONG)r.length,h);NSMutableString *s=[NSMutableString new];for(unsigned i=0;i<32;i++)[s appendFormat:@"%02x",h[i]];return s;}
static int print(id value){NSData *r=[NSJSONSerialization dataWithJSONObject:value options:NSJSONWritingSortedKeys error:NULL];if(!r)return 2;fwrite(r.bytes,1,r.length,stdout);puts("");fflush(stdout);return 0;}
static BOOL powerOffReceipt(NSString *run,NSString *job){
    NSString *p=[run stringByAppendingPathComponent:@"device-off-confirmed.json"];if(!canonical(p))return NO;
    NSData *raw=[NSData dataWithContentsOfFile:p options:0 error:NULL];if(!raw || raw.length>8192)return NO;
    id v=[NSJSONSerialization JSONObjectWithData:raw options:0 error:NULL];
    NSDictionary *wanted=@{@"schema":@"A23-live-device-off-confirmation-1",@"run":run,@"job":job,@"operator_power_off_confirmed":@YES};
    NSMutableData *encoded=[[NSJSONSerialization dataWithJSONObject:wanted options:NSJSONWritingSortedKeys|NSJSONWritingWithoutEscapingSlashes error:NULL] mutableCopy];[encoded appendBytes:"\n" length:1];
    return [v isKindOfClass:NSDictionary.class] && [v isEqual:wanted] && [raw isEqual:encoded];
}
static uint64_t unusedNow(void *p){(void)p;return 0;}
static bool unusedEmit(void *p,const A23WaitEvent *e){(void)p;(void)e;return false;}
int main(int argc,const char *argv[]){@autoreleasepool {
    if(argc==2 && !strcmp(argv[1],"--describe"))return print(A23VerifiedEntryDescription());
    if(argc==2 && !strcmp(argv[1],"--inspect-context")){char *p=realpath(argv[0],NULL);if(!p)return 2;NSString *binary=@(p);free(p);NSDictionary *c=A23ReadExecutionContext(binary);return print(@{@"context":c,@"policy_pass":@(A23ValidateExecutionContext(c,c[@"receiver_sha256"])),@"usb_open_permission_proven":@NO});}
    BOOL archive=argc==3 && !strcmp(argv[1],"--check-archive"),check=argc==3 && !strcmp(argv[1],"--check-build"),acquire=argc==5 && !strcmp(argv[1],"--acquire-once");
    if(!archive && !check && !acquire){fputs("Expected file check, context inspection, or --acquire-once BUILD CONSUMED_JOB RUN.\n",stderr);return 2;}
    NSString *build=canonical(@(argv[2]));char *p=realpath(argv[0],NULL);NSString *binary=p?@(p):nil;free(p);
    if(!build || ![binary isEqual:[build stringByAppendingPathComponent:@"verified-entry"]])return 2;
    A23ReadOnlyScopeVerifier *verifier=archive?[[A23ReadOnlyScopeVerifier alloc] initWithArchive:build]:[[A23ReadOnlyScopeVerifier alloc] initWithBuild:build];
    if(!(archive?[verifier verifyArchive]:[verifier verifyCore]))return 2;
    if(archive || check)return print(@{@"schema":@"A23-live-two-epoch-build-check-1",@"scope":verifier.scope,@"verifier":verifier.result});
    NSString *job=canonical(@(argv[3])),*run=canonical(@(argv[4]));
    NSString *jobs=@"/Users/livcm/Documents/Developer/Git/SysDVR-UVC-Capture/research/usb-ds-iso/private/sequence-reservations32/jobs";
    NSString *runs=@"/Users/livcm/Documents/Developer/Git/SysDVR-UVC-Capture/research/usb-ds-iso/private/runs";
    if(!job || !run || ![job.stringByDeletingLastPathComponent isEqual:jobs] || ![run.stringByDeletingLastPathComponent isEqual:runs] || ![run.lastPathComponent isEqual:[@"A-two-epoch-" stringByAppendingString:job.lastPathComponent]])return 2;
    NSDictionary *context=A23ReadExecutionContext(binary),*scope=verifier.scope;
    if(!A23ValidateExecutionContext(context,scope[@"receiver_sha256"]))return 2;
    A23SharedSequencePermit *permit=[[A23SharedSequencePermit alloc] initWithJob:job expectedScope:scope verifier:^BOOL(NSDictionary *s){return [verifier verifyScope:s job:job];}];if(!permit)return 2;
    NSData *used=[NSData dataWithContentsOfFile:[job stringByAppendingPathComponent:@"consumed.json"] options:NSDataReadingMappedIfSafe error:NULL];if(!used)return 2;
    NSDictionary *binding=@{@"schema":@"A23-two-epoch-entry-binding-1",@"build_manifest_sha256":scope[@"build_manifest_sha256"],@"receiver_sha256":scope[@"receiver_sha256"],@"authorization_receipt_sha256":digest(used),@"first_sequence":@81,@"last_sequence":@112};
    NSString *host=[run stringByAppendingPathComponent:@"host"];if(mkdir(host.fileSystemRepresentation,0700))return 2;
    dispatch_queue_t queue=dispatch_get_main_queue();__block A23TwoEpochEntry *entry=nil;__block A23LiveTwoEpochRun *loop=nil;
    __block BOOL unresolved=NO;liveSources=[NSMutableArray new];
    dispatch_async(queue,^{@autoreleasepool {
        A23LocalMachClock *clock=[A23LocalMachClock new];A23WaitOps ops;a23_wait_native_ops(&ops,NULL,unusedNow,unusedEmit);
        A23PairedSDKOperations *operations=[A23PairedSDKOperations new];
        A23PairedSDKProvider *provider=[[A23PairedSDKProvider alloc] initWithOperations:operations queue:queue interest:^(uint32_t message){if(message==kIOMessageServiceIsTerminated)[entry requestExit];} firstSequence:81];
        entry=[[A23TwoEpochEntry alloc] initWithDirectory:host queue:queue clock:clock ops:&ops provider:provider permit:permit context:context binding:binding];
        if(!entry){print(@{@"stage":@"entry_initialization_failed",@"receiver_launched":@YES});exit(1);}
        A23VerifiedEntryCoordinator *coordinator=[[A23VerifiedEntryCoordinator alloc] initWithEntry:entry verifier:verifier permit:permit scope:scope job:job];
        loop=[[A23LiveTwoEpochRun alloc] initWithTarget:(id<A23LiveEntryTarget>)coordinator directory:host stop:^{[entry requestExit];}];
        if(!loop){[entry requestExit];print(@{@"stage":@"controller_initialization_failed",@"resources_retained":entry.result[@"resources_retained"]});exit(1);}
        BOOL begun=[loop begin];if(begun)print(@{@"stage":@"WAITING",@"job":job,@"run":run});
        dispatch_source_t timer=dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER,0,0,queue);
        [liveSources addObject:timer];dispatch_source_set_timer(timer,dispatch_time(DISPATCH_TIME_NOW,0),1000000,100000);
        dispatch_source_set_event_handler(timer,^{@autoreleasepool {
            [loop tick];NSDictionary *s=loop.status;
            if(!unresolved && [s[@"unresolved_keep_alive"] boolValue]){unresolved=YES;print(@{@"stage":@"unresolved_keep_alive",@"loop":s,@"run":run});}
            if([s[@"finished"] boolValue]){print(@{@"stage":[s[@"success"] boolValue]?@"captured_logs_pending":@"failed_no_retry",@"loop":s,@"run":run});exit([s[@"exit_code"] intValue]);}
        }});dispatch_resume(timer);
        for(NSNumber *number in @[@(SIGINT),@(SIGTERM),@(SIGUSR1)]){int n=number.intValue;signal(n,SIG_IGN);dispatch_source_t source=dispatch_source_create(DISPATCH_SOURCE_TYPE_SIGNAL,(uintptr_t)n,0,queue);[liveSources addObject:source];dispatch_source_set_event_handler(source,^{if(n==SIGUSR1){if(powerOffReceipt(run,job))[loop finishAfterOperatorPowerOff];}else [loop requestExit];});dispatch_resume(source);}
    }});
    dispatch_main();
}}
