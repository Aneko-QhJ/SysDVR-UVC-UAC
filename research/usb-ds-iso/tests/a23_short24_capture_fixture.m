#import "../host/a23_short24_capture.h"
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
static atomic_uint_fast64_t tick;
static NSData *modelRaw,*modelTransactions,*modelAfter;
static uint64_t now(void){return atomic_load(&tick);}
static void advance(uint64_t n){atomic_fetch_add(&tick,n);}
#define check(b) do {if(!(b)){fprintf(stderr,"fixture assertion line %d: %s\n",__LINE__,#b);abort();}} while(0)
static void json(NSString *path,id object) {
    NSError *e=nil;NSData *d=[NSJSONSerialization dataWithJSONObject:object options:NSJSONWritingSortedKeys error:&e];
    check(d && !e && [d writeToFile:path options:NSDataWritingWithoutOverwriting error:&e] && !e);
}
@interface FixtureIO:NSObject<A23Short24IO>
@property NSMutableData *dataStorage,*transactionStorage;
@property NSString *scenario;
@property NSUInteger isoCalls,burstCalls,abortCalls,statusCalls;
@property uint64_t firstFrame;
@property(copy) IOUSBHostIsochronousTransactionCompletionHandler iso;
@property(copy) IOUSBHostCompletionHandler control;
@end
@implementation FixtureIO
- (instancetype)init {if((self=[super init])){_dataStorage=[NSMutableData dataWithLength:3072];_transactionStorage=[NSMutableData dataWithLength:3584];}return self;}
- (BOOL)simulation{return YES;}
- (NSDictionary *)readStatus {
    BOOL after=_statusCalls++>0;NSMutableData *bytes;
    if(after)bytes=[modelAfter mutableCopy];else {
        bytes=[NSMutableData dataWithLength:168];uint32_t *p=bytes.mutableBytes;p[0]=0x31505349;p[1]=1;p[11]=0x83;
    }
    if([_scenario isEqual:after?@"short-after":@"short-before"])[bytes setLength:167];
    uint64_t begin=now();advance(1000);
    return @{@"data":bytes,@"observation":@{@"accepted":@YES,@"bytes_transferred":@(bytes.length),@"begin_ns":@(begin),
        @"end_ns":@(now()),@"control":@[@0xc1,@0x51,@0,@2,@168],@"source":@"sdk_control_reply"}};
}
- (NSDictionary *)frameSample {uint64_t begin=now();advance(1000);return @{@"current_frame":[_scenario isEqual:@"bad-frame"]?@0:@1000,
    @"begin_ns":@(begin),@"end_ns":@(now())};}
- (BOOL)enqueueISO:(uint64_t)frame completion:(IOUSBHostIsochronousTransactionCompletionHandler)completion error:(NSError **)error {
    _isoCalls++;_firstFrame=frame;_iso=[completion copy];
    IOUSBHostIsochronousTransaction *r=_transactionStorage.mutableBytes;
    for(unsigned i=0;i<128;i++)check(r[i].requestCount==24 && r[i].offset==24*i && !r[i].completeCount &&
        !r[i].timeStamp && !r[i].options && r[i].status==kIOReturnInvalid);
    if([_scenario isEqual:@"iso-rejected"]){if(error)*error=[NSError errorWithDomain:@"injected" code:7 userInfo:nil];return NO;}
    return YES;
}
- (BOOL)enqueueBurst:(uint16_t)first completion:(IOUSBHostCompletionHandler)completion error:(NSError **)error {
    check(first==1);_burstCalls++;_control=[completion copy];
    if([_scenario isEqual:@"burst-rejected"]){if(error)*error=[NSError errorWithDomain:@"injected" code:8 userInfo:nil];return NO;}
    if([_scenario isEqual:@"inline-control"])completion(kIOReturnSuccess,0);
    return YES;
}
- (BOOL)abortISO:(NSError **)error {
    _abortCalls++;if([_scenario isEqual:@"abort-rejected"]){if(error)*error=[NSError errorWithDomain:@"injected" code:9 userInfo:nil];return NO;}return YES;
}
- (void)emitISO {
    check(_iso!=nil);memcpy(_dataStorage.mutableBytes,modelRaw.bytes,3072);memcpy(_transactionStorage.mutableBytes,modelTransactions.bytes,3584);
    if([_scenario isEqual:@"native-empty-error"])((IOUSBHostIsochronousTransaction *)_transactionStorage.mutableBytes)[127].status=kIOReturnError;
    _iso([_scenario isEqual:@"overall-error"]?kIOReturnError:kIOReturnSuccess,
         [_scenario isEqual:@"foreign-pointer"]?(IOUSBHostIsochronousTransaction *)1:_transactionStorage.mutableBytes);
}
- (void)emitControl {check(_control!=nil);_control([_scenario isEqual:@"control-error"]?kIOReturnError:kIOReturnSuccess,0);}
@end

int main(int argc,char **argv) {@autoreleasepool {
    check(argc==4);NSString *model=[NSString stringWithUTF8String:argv[1]],*output=[NSString stringWithUTF8String:argv[2]],
        *recipe=[NSString stringWithUTF8String:argv[3]];
    modelRaw=[NSData dataWithContentsOfFile:[model stringByAppendingPathComponent:@"MODEL-raw.bin"]];
    modelTransactions=[NSData dataWithContentsOfFile:[model stringByAppendingPathComponent:@"MODEL-transactions.bin"]];
    modelAfter=[NSData dataWithContentsOfFile:[model stringByAppendingPathComponent:@"MODEL-after.bin"]];
    check(modelRaw.length==3072 && modelTransactions.length==3584 && modelAfter.length==168);
    NSArray *scenarios=@[@"iso-first",@"control-first",@"inline-control",@"queue-delay",@"late-control",@"timeout",
        @"abort-rejected",@"iso-rejected",@"burst-rejected",@"foreign-pointer",@"duplicate-iso",@"duplicate-control",
        @"interest-pending",@"short-before",@"short-after",@"bad-frame",@"overall-error",@"control-error",@"native-empty-error",
        @"arrival-during-intent",@"gap-during-intent"];
    NSMutableDictionary *summary=[NSMutableDictionary dictionary];
    for(NSString *scenario in scenarios) {
        atomic_store(&tick,1000000000);FixtureIO *io=[FixtureIO new];io.scenario=scenario;
        dispatch_queue_t q=dispatch_queue_create("short24-fixture",DISPATCH_QUEUE_SERIAL);
        __block A23Short24Capture *capture;__block BOOL started,injected=NO;__block unsigned clocksAfterISO=0;
        dispatch_sync(q,^{capture=[[A23Short24Capture alloc] initWithIO:io queue:q clockNanoseconds:^uint64_t{
            // Inject a native completion or scheduling gap while the intent
            // timestamp is sampled, after the earlier admission observation.
            if(io.isoCalls && !io.burstCalls && !injected && ++clocksAfterISO==6) {
                injected=YES;
                if([scenario isEqual:@"arrival-during-intent"])[io emitISO];
                if([scenario isEqual:@"gap-during-intent"])advance(9000000);
            }
            return now();}
            recipe:recipe firstSequence:1];check(capture!=nil);started=[capture start];check(![capture start]);});
        BOOL noSubmit=[@[@"short-before",@"bad-frame"] containsObject:scenario];
        BOOL admissionBlocked=[@[@"arrival-during-intent",@"gap-during-intent"] containsObject:scenario];
        BOOL timeout=[@[@"timeout",@"abort-rejected",@"interest-pending"] containsObject:scenario];
        if(timeout) {
            if([scenario isEqual:@"interest-pending"])[capture providerInterest:0x1234];else advance(2100000000);
            dispatch_sync(q,^{[capture poll];[capture poll];});
        } else if(!noSubmit && !admissionBlocked && ![scenario isEqual:@"iso-rejected"] && ![scenario isEqual:@"burst-rejected"]) {
            if([scenario isEqual:@"control-first"]){[io emitControl];dispatch_sync(q,^{[capture poll];check([capture.result[@"after_reads"] unsignedIntegerValue]==0);});[io emitISO];}
            else if([scenario isEqual:@"queue-delay"]) {
                dispatch_sync(q,^{[io emitControl];advance(25000000);[capture poll];});[io emitISO];
            } else {
                [io emitISO];dispatch_sync(q,^{[capture poll];if(![scenario isEqual:@"inline-control"])check([capture.result[@"after_reads"] unsignedIntegerValue]==0);});
                if([scenario isEqual:@"late-control"])advance(17000000);
                if(![scenario isEqual:@"inline-control"])[io emitControl];
            }
            dispatch_sync(q,^{[capture poll];});
            if([scenario isEqual:@"duplicate-iso"])[io emitISO];
            if([scenario isEqual:@"duplicate-control"])[io emitControl];
        }
        __block NSDictionary *snap;
        dispatch_sync(q,^{[capture poll];snap=capture.snapshot;});
        NSDictionary *result=snap[@"metadata"];
        check(io.isoCalls<=1 && io.burstCalls<=1 && io.abortCalls<=1 && io.statusCalls<=2);
        check([result[@"resources_retained"] boolValue] && ![result[@"process_exit_authorized"] boolValue]);
        if(noSubmit)check(io.isoCalls==0 && io.burstCalls==0 && !started);
        if(admissionBlocked)check(io.isoCalls==1 && io.burstCalls==0 && !started);
        if([scenario isEqual:@"iso-rejected"])check(io.isoCalls==1 && io.burstCalls==0 && [result[@"io_unresolved"] boolValue]);
        if(timeout)check(io.abortCalls==1 && [result[@"io_unresolved"] boolValue]);
        if([@[@"iso-first",@"control-first",@"inline-control",@"queue-delay",@"native-empty-error"] containsObject:scenario])
            check([result[@"observation_complete"] boolValue] && [result[@"failure_reasons"] count]==0);
        else check(![result[@"observation_complete"] boolValue] && [result[@"failure_reasons"] count]>0);
        NSString *folder=[output stringByAppendingPathComponent:scenario];NSError *e=nil;
        check([[NSFileManager defaultManager] createDirectoryAtPath:folder withIntermediateDirectories:NO attributes:nil error:&e]);
        for(NSString *name in @[@"raw",@"transactions",@"before",@"after"])
            check([snap[name] writeToFile:[folder stringByAppendingPathComponent:[name stringByAppendingString:@".bin"]]
                options:NSDataWritingWithoutOverwriting error:&e]);
        json([folder stringByAppendingPathComponent:@"metadata.json"],result);
        summary[scenario]=@{@"iso_calls":@(io.isoCalls),@"burst_calls":@(io.burstCalls),@"abort_calls":@(io.abortCalls),
            @"status_calls":@(io.statusCalls),@"first_frame":@(io.firstFrame),@"real_sdk_objects_created":@0};
    }
    json([output stringByAppendingPathComponent:@"calls.json"],summary);
    printf("{\"native_injected_scenarios\":%lu,\"real_sdk_objects_created\":0}\n",(unsigned long)scenarios.count);
    return 0;
}}
