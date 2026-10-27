#import "../host/io_usb_host_burst_executor.h"
#import "../../../source/uvc/iso_probe_protocol.h"
#include <assert.h>
#include <mach/mach_time.h>
#include <stdio.h>
#include <unistd.h>
#include <string.h>
@interface BurstClock : A23LocalMachClock
@property uint64_t offset;
- (void)advance:(uint64_t)ns;
@end
@implementation BurstClock
- (uint64_t)nowTicks { return mach_absolute_time()+_offset; }
- (void)advance:(uint64_t)ns { _offset+=(uint64_t)(((__uint128_t)ns*self.denominator+self.numerator-1)/self.numerator); }
@end
@interface BurstMock : NSObject <A23BurstMockOperations>
@property NSString *name;
@property NSMutableData *data;
@property IOUSBHostIsochronousTransaction *rows;
@property(copy) IOUSBHostIsochronousTransactionCompletionHandler iso;
@property(copy) IOUSBHostCompletionHandler control;
@property NSUInteger submissions,triggers,aborts,closes,afterCalls;
@property BOOL disallowSimulation;
@end
@implementation BurstMock
- (BOOL)simulationOnly { return !_disallowSimulation; }
- (void)finishISO:(BOOL)foreign
{
    for (unsigned i=0;i<960;++i) { _rows[i].status=0;_rows[i].completeCount=0;_rows[i].timeStamp=mach_absolute_time(); }
    for (unsigned p=0;p<16;++p) {
        unsigned i=512+p;_rows[i].completeCount=192;
        uint8_t *b=(uint8_t *)_data.mutableBytes+i*192;
        for (unsigned j=0;j<192;++j) b[j]=isoProbeByte((uint16_t)(p+1),j);
    }
    _iso(0,foreign ? (IOUSBHostIsochronousTransaction *)(uintptr_t)1 : _rows);
}
- (BOOL)enqueueIORequestWithData:(NSMutableData *)data transactionList:(IOUSBHostIsochronousTransaction *)rows
    transactionListCount:(NSUInteger)count firstFrameNumber:(uint64_t)frame options:(IOUSBHostIsochronousTransferOptions)options
    error:(NSError **)error completionHandler:(IOUSBHostIsochronousTransactionCompletionHandler)completion
{
    assert(++_submissions==1 && count==960 && frame==100 && options==0);_data=data;_rows=rows;_iso=completion;
    if ([_name isEqual:@"iso-rejected"]) { if(error)*error=[NSError errorWithDomain:@"mock-iso" code:1 userInfo:nil];return NO; }
    if ([_name isEqual:@"inline-iso"]) [self finishISO:NO];return YES;
}
- (BOOL)abortWithOption:(IOUSBHostAbortOption)option error:(NSError **)error
{
    assert(++_aborts==1 && option==IOUSBHostAbortOptionAsynchronous);
    if ([_name isEqual:@"abort-refused"]) { if(error)*error=[NSError errorWithDomain:@"mock-abort" code:2 userInfo:nil];return NO; }return YES;
}
- (BOOL)enqueueBurst:(IOUSBDeviceRequest)request timeout:(NSTimeInterval)timeout completion:(IOUSBHostCompletionHandler)completion error:(NSError **)error
{
    assert(++_triggers==1 && request.bmRequestType==0x41 && request.bRequest==0x54 && request.wValue==1 && request.wIndex==2 && !request.wLength && timeout==0.016);
    _control=completion;
    if ([_name isEqual:@"trigger-rejected"]) { if(error)*error=[NSError errorWithDomain:@"mock-trigger" code:3 userInfo:nil];return NO; }
    if ([_name isEqual:@"inline-control"]) completion(0,0);return YES;
}
- (NSData *)readAfterStatus
{
    assert(++_afterCalls==1);IsoProbeStatus s={0};s.magic=ISO_PROBE_STATUS_MAGIC;s.version=1;s.sequence=1;s.state=2;
    s.urb_id=s.report_id=42;s.requested=s.transferred=3072;s.urb_status=3;s.speed=3;s.endpoint=0x83;
    // Synthetic ISO7 snapshot from the protocol ABI, not a hardware capture.
    s.report_count=1;
    IsoProbeBurstContextDiagnostics diag={0};
    diag.magic=ISO_PROBE_BURST_INTERVAL_MAGIC;diag.first_control=0x47c01411;diag.terminal=1;
    diag.completed_bitmap=0xffff;diag.actual_sum=3072;diag.first_virtual_trb=0xb9ad7d000ULL;
    diag.frame_select_mfi=0x22e3;diag.context_valid=1;
    const uint32_t context[8]={0x10001,0x100002e,0x80023001,0,0x1000c00,0,0,0};
    memcpy(diag.context,context,sizeof(context));
    for (unsigned i=0;i<2;++i) {
        uint64_t tag=diag.first_virtual_trb+(1+2*i)*16;
        diag.td[i].event[0]=(uint32_t)tag;diag.td[i].event[1]=(uint32_t)(tag>>32);
        diag.td[i].event[2]=0x010000c0;diag.td[i].event[3]=0x78005;diag.td[i].mfi=0x23e0+i;
    }
    memcpy(&s.diagnostics,&diag,sizeof(diag));
    return [NSData dataWithBytes:&s length:[_name isEqual:@"short-after"] ? 167 : 168];
}
- (void)closeMockResources { assert(++_closes==1); }
@end
int main(int argc,const char *argv[])
{
    @autoreleasepool {
        assert(argc==2);NSString *root=@(argv[1]);assert([[NSFileManager defaultManager] createDirectoryAtPath:root withIntermediateDirectories:NO attributes:nil error:NULL]);
        NSArray *names=@[@"iso-first",@"control-first",@"inline-iso",@"inline-control",@"iso-rejected",@"trigger-rejected",
            @"control-error",@"control-bytes",@"control-pending",@"iso-pending",@"abort-refused",@"detach-pending",
            @"foreign-pointer",@"save-failed",@"short-before",@"short-after",@"gap-after-intent",@"journal-trigger-failed",
            @"duplicate-iso",@"duplicate-control",@"control-late",@"arrival-during-intent"];
        dispatch_queue_t queue=dispatch_queue_create("a23.mock.burst",DISPATCH_QUEUE_SERIAL);
        for (NSString *name in names) {
            NSString *directory=[root stringByAppendingPathComponent:name];assert([[NSFileManager defaultManager] createDirectoryAtPath:directory withIntermediateDirectories:NO attributes:nil error:NULL]);
            assert([@"Injected BurstMock; no SDK/USB access.\n" writeToFile:[directory stringByAppendingPathComponent:@"MOCK_ONLY.txt"] atomically:NO encoding:NSUTF8StringEncoding error:NULL]);
            FILE *journal=fopen([[directory stringByAppendingPathComponent:@"journal.jsonl"] fileSystemRepresentation],"wx");assert(journal);
            BurstClock *clock=[BurstClock new];BurstMock *ops=[BurstMock new];ops.name=name;
            A23BurstSimulationExecutor *executor=[[A23BurstSimulationExecutor alloc] initWithDirectory:directory queue:queue clock:clock operations:ops journal:^BOOL(NSDictionary *row) {
                NSData *line=[NSJSONSerialization dataWithJSONObject:row options:0 error:NULL];assert(line);
                assert(fwrite(line.bytes,1,line.length,journal)==line.length && fputc('\n',journal)!=EOF && !fflush(journal) && !fsync(fileno(journal)));
                if ([row[@"event"] isEqual:@"trigger_intent"]) {
                    if ([name isEqual:@"gap-after-intent"]) [clock advance:9000000];
                    if ([name isEqual:@"arrival-during-intent"]) [ops finishISO:NO];
                    if ([name isEqual:@"journal-trigger-failed"]) return NO;
                } return YES;
            }];assert(executor);
            dispatch_sync(queue,^{
                IsoProbeStatus s={0};s.magic=ISO_PROBE_STATUS_MAGIC;s.version=1;s.endpoint=0x83;
                NSData *before=[NSData dataWithBytes:&s length:[name isEqual:@"short-before"] ? 167 : 168];
                uint64_t begin=clock.nowTicks,end=clock.nowTicks;
                [executor startBefore:before sample:@{@"current_frame":@36,@"begin_ticks":@(begin),@"end_ticks":@(end)}];
                assert(![executor startBefore:before sample:@{}]);
                if ([name isEqual:@"save-failed"]) assert([[NSFileManager defaultManager] createDirectoryAtPath:[directory stringByAppendingPathComponent:@"transfer"] withIntermediateDirectories:NO attributes:nil error:NULL]);
                if ([name isEqual:@"detach-pending"]) [executor detached];
            });
            IOUSBHostCompletionHandler control=ops.control;IOUSBHostIsochronousTransactionCompletionHandler iso=ops.iso;
            BOOL blocked=[@[@"short-before",@"iso-rejected",@"journal-trigger-failed",@"gap-after-intent",@"inline-iso",@"arrival-during-intent"] containsObject:name];
            if ([name isEqual:@"control-first"] || [name isEqual:@"iso-pending"] || [name isEqual:@"abort-refused"] || [name isEqual:@"detach-pending"]) { control(0,0);dispatch_sync(queue,^{[executor poll];}); }
            BOOL sendISO=!blocked && ![@[@"iso-pending",@"abort-refused",@"detach-pending"] containsObject:name];
            if (sendISO) { [ops finishISO:[name isEqual:@"foreign-pointer"]];dispatch_sync(queue,^{[executor poll];}); }
            if ([name isEqual:@"control-late"]) dispatch_sync(queue,^{[clock advance:17000000];[executor poll];assert(ops.closes==0);});
            if (control && ![@[@"control-first",@"inline-control",@"trigger-rejected",@"control-pending",@"iso-pending",@"abort-refused",@"detach-pending"] containsObject:name]) {
                control([name isEqual:@"control-error"] ? kIOReturnTimeout : 0,[name isEqual:@"control-bytes"] ? 1 : 0);
                dispatch_sync(queue,^{[executor poll];});
            }
            if ([name isEqual:@"duplicate-iso"]) { iso(0,ops.rows);dispatch_sync(queue,^{[executor poll];}); }
            if ([name isEqual:@"duplicate-control"]) { control(0,0);dispatch_sync(queue,^{[executor poll];}); }
            dispatch_sync(queue,^{
                [executor poll];
                if ([name isEqual:@"control-pending"]) { assert(ops.closes==0);[clock advance:17000000];[executor poll];assert(ops.closes==0); }
                if ([name isEqual:@"iso-pending"] || [name isEqual:@"abort-refused"] || [name isEqual:@"detach-pending"]) { [clock advance:2100000000];[executor poll]; }
                if (!ops.closes) { [clock advance:1100000000];[executor poll]; }
            });
            // Deliver the outstanding control only after proving ISO completion
            // and deadline did not destroy the interface.
            if ([name isEqual:@"control-pending"]) { control(0,0);dispatch_sync(queue,^{[executor poll];assert(ops.closes==1);}); }
            dispatch_sync(queue,^{
                NSDictionary *result=executor.result;
                if (blocked) assert(ops.triggers==0);
                if ([@[@"iso-first",@"control-first",@"inline-control"] containsObject:name]) assert(ops.closes==1 && [result[@"failure_reasons"] count]==0);
                if ([@[@"foreign-pointer",@"save-failed",@"iso-pending",@"abort-refused",@"detach-pending",@"journal-trigger-failed"] containsObject:name]) assert(ops.closes==0);
                assert(ops.submissions<=1 && ops.triggers<=1 && ops.aborts<=1 && ops.afterCalls<=1);
                if ([name isEqual:@"detach-pending"]) assert(ops.aborts==0);
                if ([name isEqual:@"inline-iso"] || [name isEqual:@"arrival-during-intent"]) assert(ops.aborts==0);
                NSData *json=[NSJSONSerialization dataWithJSONObject:result options:NSJSONWritingPrettyPrinted error:NULL];assert([json writeToFile:[directory stringByAppendingPathComponent:@"result.json"] atomically:NO]);
            });assert(!fclose(journal));
        }
        BurstMock *forbidden=[BurstMock new];forbidden.disallowSimulation=YES;
        assert(![[A23BurstSimulationExecutor alloc] initWithDirectory:root queue:queue clock:[BurstClock new] operations:forbidden journal:^BOOL(NSDictionary *r){(void)r;return YES;}]);
        assert(!forbidden.submissions && !forbidden.triggers);
        printf("22 injected burst cases passed; real operations rejected; USB requests 0\n");
    }return 0;
}
