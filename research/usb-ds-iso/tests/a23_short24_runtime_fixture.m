// Reuse the tested injected IO, never execute its former main or SDK classes.
#define main prior_short24_fixture_main
#include "a23_short24_capture_fixture.m"
#undef main
#import "../host/a23_short24_runtime.h"
#include <sys/resource.h>
#include <signal.h>
int main(int argc,char **argv) {@autoreleasepool {
    if(argc==3 && !strcmp(argv[1],"--partial-write")){
        NSString *parent=@(argv[2]);struct rlimit previous,limited;check(!getrlimit(RLIMIT_FSIZE,&previous));
        limited=previous;limited.rlim_cur=16;signal(SIGXFSZ,SIG_IGN);check(!setrlimit(RLIMIT_FSIZE,&limited));
        NSError *error=nil;BOOL saved=A23Short24WriteObservation(parent,@"observation",@{@"raw":[NSMutableData dataWithLength:3072],
            @"transactions":[NSMutableData dataWithLength:3584],@"before":[NSMutableData dataWithLength:168],@"after":[NSMutableData dataWithLength:168],@"metadata":@{}},&error);
        check(!setrlimit(RLIMIT_FSIZE,&previous));
        check(!saved && error && [NSData dataWithContentsOfFile:[parent stringByAppendingPathComponent:@"observation/after.bin"]].length==16 &&
            ![[NSFileManager defaultManager] fileExistsAtPath:[parent stringByAppendingPathComponent:@"observation/COMMITTED"]]);
        puts("{\"partial_file_bytes_retained\":16,\"saved\":false,\"sdk_objects_created\":0}");return 0;
    }
    check(argc==4);NSString *models=@(argv[1]),*output=@(argv[2]),*recipe=@(argv[3]);
    modelRaw=[NSData dataWithContentsOfFile:[models stringByAppendingPathComponent:@"MODEL-raw.bin"]];
    modelTransactions=[NSData dataWithContentsOfFile:[models stringByAppendingPathComponent:@"MODEL-transactions.bin"]];
    modelAfter=[NSData dataWithContentsOfFile:[models stringByAppendingPathComponent:@"MODEL-after.bin"]];
    check(modelRaw.length==3072 && modelTransactions.length==3584 && modelAfter.length==168);
    NSMutableDictionary *summary=[NSMutableDictionary dictionary];
    for(NSString *scenario in @[@"complete",@"late-duplicate",@"notice-capacity",@"notice-write-failure",@"pending",@"existing-observation",@"existing-intent"]){
        NSString *folder=[output stringByAppendingPathComponent:scenario];NSError *e=nil;
        check([[NSFileManager defaultManager] createDirectoryAtPath:folder withIntermediateDirectories:NO attributes:nil error:&e]);
        NSData *sentinel=[@"PRESERVE" dataUsingEncoding:NSUTF8StringEncoding];
        if([scenario isEqual:@"existing-intent"])check([sentinel writeToFile:[folder stringByAppendingPathComponent:@"start-intent.json"] atomically:NO]);
        if([scenario isEqual:@"existing-observation"]){
            check([[NSFileManager defaultManager] createDirectoryAtPath:[folder stringByAppendingPathComponent:@"observation"]
                withIntermediateDirectories:NO attributes:nil error:&e]);
            check([sentinel writeToFile:[folder stringByAppendingPathComponent:@"observation/keep"] atomically:NO]);
        }
        atomic_store(&tick,1000000000);FixtureIO *io=[FixtureIO new];io.scenario=@"iso-first";
        dispatch_queue_t q=dispatch_queue_create("short24.runtime.fixture",DISPATCH_QUEUE_SERIAL);
        __block A23Short24Capture *capture;__block A23Short24Runtime *runtime;__block BOOL started;
        dispatch_sync(q,^{
            capture=[[A23Short24Capture alloc] initWithIO:io queue:q clockNanoseconds:^uint64_t{return now();} recipe:recipe firstSequence:1];
            runtime=[[A23Short24Runtime alloc] initWithCapture:capture queue:q directory:folder
                context:@{@"model_only":@YES,@"recipe":recipe} clockNanoseconds:^uint64_t{return now();}];
            check(runtime);started=[runtime start];check(![runtime start]);
        });
        if([scenario isEqual:@"existing-intent"]){
            check(!started && io.isoCalls==0 && io.burstCalls==0);
            check([[NSData dataWithContentsOfFile:[folder stringByAppendingPathComponent:@"start-intent.json"]] isEqual:sentinel]);
        }else if([scenario isEqual:@"pending"]){advance(2100000000);dispatch_sync(q,^{[runtime poll];});}
        else{check(started);[io emitISO];[io emitControl];dispatch_sync(q,^{[runtime poll];});}
        NSData *original=[NSData dataWithContentsOfFile:[folder stringByAppendingPathComponent:@"observation/metadata.json"]];
        if([scenario isEqual:@"notice-write-failure"])check([sentinel writeToFile:[folder stringByAppendingPathComponent:@"later-0001.json"] atomically:NO]);
        if([scenario isEqual:@"late-duplicate"] || [scenario isEqual:@"notice-capacity"] || [scenario isEqual:@"notice-write-failure"]){
            unsigned repeat=[scenario isEqual:@"notice-capacity"]?9:1;
            for(unsigned i=0;i<repeat;i++){[io emitISO];dispatch_sync(q,^{[runtime poll];});}
            check([[NSData dataWithContentsOfFile:[folder stringByAppendingPathComponent:@"observation/metadata.json"]] isEqual:original]);
        }
        __block NSDictionary *result;dispatch_sync(q,^{[runtime poll];result=runtime.result;});
        BOOL fail=[scenario hasPrefix:@"existing-"];
        check([result[@"observation_saved"] boolValue]==!fail && ![result[@"process_exit_authorized"] boolValue] && [result[@"holding_runtime_resources"] boolValue]);
        if([scenario isEqual:@"existing-observation"]){
            check([[NSData dataWithContentsOfFile:[folder stringByAppendingPathComponent:@"observation/keep"]] isEqual:sentinel]);
            check([result[@"error"] count] && [result[@"holding_runtime_resources"] boolValue]);
        }
        if([scenario isEqual:@"pending"])check(io.abortCalls==1 && [result[@"capture"][@"io_unresolved"] boolValue]);
        if([scenario isEqual:@"late-duplicate"])check([result[@"later_records"] unsignedIntegerValue]==1 && [result[@"capture"][@"stopped"] boolValue]);
        if([scenario isEqual:@"notice-capacity"])check([result[@"later_records"] unsignedIntegerValue]==8 && [result[@"later_write_failed"] boolValue]);
        if([scenario isEqual:@"notice-write-failure"])check([result[@"later_records"] unsignedIntegerValue]==0 &&
            [result[@"later_attempts"] unsignedIntegerValue]==1 && [result[@"later_write_failed"] boolValue] &&
            [[NSData dataWithContentsOfFile:[folder stringByAppendingPathComponent:@"later-0001.json"]] isEqual:sentinel]);
        check(io.isoCalls<=1 && io.burstCalls<=1 && io.abortCalls<=1);
        json([folder stringByAppendingPathComponent:@"runtime-result.json"],result);
        summary[scenario]=@{@"iso_calls":@(io.isoCalls),@"burst_calls":@(io.burstCalls),@"abort_calls":@(io.abortCalls),@"sdk_objects_created":@0};
    }
    json([output stringByAppendingPathComponent:@"calls.json"],summary);
    puts("{\"runtime_scenarios\":7,\"sdk_objects_created\":0}");return 0;
}}
