#import "a23_waiting_receiver.h"
#include <IOKit/IOMessage.h>
#include <mach/mach_time.h>
#include <signal.h>
#include <stdlib.h>
#include <string.h>
static volatile sig_atomic_t exitWanted;
static void signalExit(int s){(void)s;exitWanted=1;}
static uint64_t unusedNow(void *p){(void)p;return mach_absolute_time();}
static bool unusedEmit(void *p,const A23WaitEvent *e){(void)p;(void)e;return false;}
static int printJSON(NSDictionary *value)
{
    NSData *raw=[NSJSONSerialization dataWithJSONObject:value options:NSJSONWritingSortedKeys|NSJSONWritingWithoutEscapingSlashes error:NULL];
    if(!raw)return 2;fwrite(raw.bytes,1,raw.length,stdout);puts("");return 0;
}
int main(int argc,const char *argv[])
{
    @autoreleasepool {
        if(argc==2 && !strcmp(argv[1],"--describe"))return printJSON(A23WaitingReceiverDescription());
        BOOL buildOnly=argc==3 && !strcmp(argv[1],"--check-build");
        BOOL receiptOnly=argc==4 && !strcmp(argv[1],"--check-consumed");
        BOOL acquire=argc==4 && !strcmp(argv[1],"--acquire-once");
        if(!buildOnly && !receiptOnly && !acquire){fputs("Use --describe; capture requires a new consumed receipt and verified build. No device accessed.\n",stderr);return 2;}
        char *resolved=realpath(argv[0],NULL);if(!resolved)return 2;NSString *binary=@(resolved);free(resolved);
        NSString *build=@(argv[buildOnly?2:3]),*run=buildOnly ? nil : @(argv[2]);NSError *error=nil;
        NSDictionary *checked=buildOnly ? A23CheckWaitingBuild(build,binary,&error) : A23CheckWaitingConsumed(run,build,binary,&error);
        if(!checked){fprintf(stderr,"%s\n",error.localizedDescription.UTF8String);return 2;}
        if(buildOnly || receiptOnly)return printJSON(checked); // file-only modes, never claim
        // All build/source/receipt checks and a durable exclusive process claim
        // precede SDK object construction, port creation and registry access.
        if(!A23ClaimWaitingProcess(run,checked)){fputs("Process claim exists or is not durable; no device accessed.\n",stderr);return 2;}
        if(@available(macOS 26.4,*)){}else{fputs("Mapped SDK requires macOS 26.4+.\n",stderr);return 2;}
        signal(SIGINT,signalExit);signal(SIGTERM,signalExit);
        NSString *host=[run stringByAppendingPathComponent:@"host"];
        if(![[NSFileManager defaultManager] createDirectoryAtPath:host withIntermediateDirectories:NO attributes:nil error:NULL])return 2;
        dispatch_queue_t q=dispatch_queue_create("a23.waiting.receiver",DISPATCH_QUEUE_SERIAL);
        __block A23WaitingReceiverLoop *loop=nil;__block BOOL retainedReported=NO;
        dispatch_source_t timer=dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER,0,0,q);
        dispatch_source_set_timer(timer,dispatch_time(DISPATCH_TIME_NOW,10000000),10000000,1000000);
        dispatch_source_set_event_handler(timer,^{
            [loop tick];NSDictionary *r=loop.result;
            if([r[@"unresolved"] boolValue] && !retainedReported){
                retainedReported=YES;A23SaveBurstEntryResult(run,@"waiting-retained.json",r);
                fputs("Unresolved I/O retained; leave receiver alive, no retry.\n",stderr);fflush(stderr);
            }
            if([r[@"finished"] boolValue]){
                BOOL saved=A23SaveBurstEntryResult(host,@"waiting-entry-result.json",r);
                int code=[r[@"preflight_failed"] boolValue] ? 1 : [r[@"host_result"][@"exit_code"] intValue];
                exit(saved ? code : 1);
            }
        });
        dispatch_async(q,^{
            A23WaitOps ops;a23_wait_native_ops(&ops,NULL,unusedNow,unusedEmit);
            A23DormantSDKOperations *sdk=[A23DormantSDKOperations new];
            A23AdapterSDKProvider *provider=[[A23AdapterSDKProvider alloc] initWithOperations:sdk queue:q interest:^(uint32_t message){
                if(message==kIOMessageServiceIsTerminated)[loop detachedRegistryID:loop.selectedInterfaceID];
                else if(message==kIOMessageServiceIsRequestingClose)[loop requestExit];
            }];
            id<A23WaitingPermit> permit=A23MakeWaitingBoundPermit(run,build,binary,checked);
            loop=[[A23WaitingReceiverLoop alloc] initWithHost:host queue:q clock:[A23LocalMachClock new] ops:&ops provider:provider permit:permit];
            if(!loop){fputs("Waiting entry setup failed; no retry.\n",stderr);exit(2);}
            loop.interruptionRequested=^BOOL{return exitWanted!=0;};[loop begin];
        });
        dispatch_resume(timer);dispatch_main();
    }
}
