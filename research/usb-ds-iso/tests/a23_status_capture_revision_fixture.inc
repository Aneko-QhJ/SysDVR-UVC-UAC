// No SDK devices or IOKit objects: the real controller/entry and revised SDK
// driver run against the existing injected provider and wait operations.
#include "../host/a23_status_capture_revision.h"
#import "../host/a23_live_two_epoch.h"
@interface StatusCaptureInterface : SDKModelInterface
@property NSMutableArray *returned;
@end
@implementation StatusCaptureInterface
- (NSDictionary *)readStatus {
    NSDictionary *reply=[super readStatus];NSMutableData *raw=[reply[@"data"] mutableCopy];
    NSMutableDictionary *o=[reply[@"observation"] mutableCopy];NSUInteger n=self.statusReads-1;
    IsoProbeStatus *s=raw.mutableBytes;NSString *f=self.fault;
    if(n && raw.length==168){
        if([f isEqual:@"count0"])s->report_count=0;
        if([f isEqual:@"count10"])s->report_count=n==1?1:0;
        if([f isEqual:@"count01"])s->report_count=n==1?0:1;
        if([f isEqual:@"before-count2"] && n==2)s->report_count=2;
        if([f isEqual:@"before-drift"] && n==2)((uint8_t *)raw.mutableBytes)[167]^=1;
    }
    if(n==1 && raw.length==168){
        if([f isEqual:@"bad-magic"])s->magic=0;
        if([f isEqual:@"bad-version"])s->version=2;
        if([f isEqual:@"bad-sequence"])s->sequence=65;
        if([f isEqual:@"bad-state"])s->state=ISO_PROBE_PENDING;
        if([f isEqual:@"bad-post"])s->post_result=1;
        if([f isEqual:@"bad-urb"])s->urb_id=0;
        if([f isEqual:@"bad-report-id"])s->report_id=999;
        if([f isEqual:@"bad-requested"])s->requested=3071;
        if([f isEqual:@"bad-transferred"])s->transferred=0;
        if([f isEqual:@"bad-urb-status"])s->urb_status=4;
        if([f isEqual:@"bad-speed"])s->speed=4;
        if([f isEqual:@"bad-endpoint"])s->endpoint=0x84;
        if([f isEqual:@"bad-count"])s->report_count=2;
        if([f isEqual:@"bad-report-result"])s->report_result=1;
        IsoProbeBurstContextDiagnostics *d=(void *)&s->diagnostics;
        if([f isEqual:@"bad-diag-magic"])d->magic=0;
        if([f isEqual:@"bad-terminal"])d->terminal=0;
        if([f isEqual:@"bad-bitmap"])d->completed_bitmap=65534;
        if([f isEqual:@"bad-actual"])d->actual_sum=0;
        if([f isEqual:@"bad-context"])d->context_valid=0;
        if([f isEqual:@"bad-mfi"])d->frame_select_mfi=16384;
        if([f isEqual:@"bad-type"])d->first_control^=1<<10;
        if([f isEqual:@"bad-sia"])d->first_control|=1u<<31;
        if([f isEqual:@"bad-frame-id"])d->first_control^=1<<20;
        if([f isEqual:@"bad-observation"])o[@"accepted"]=@NO;
        if([f isEqual:@"bad-observation-json"])o[@"extra"]=[NSData data];
        if([f isEqual:@"short-after"])raw.length=167;
    }
    o[@"bytes_transferred"]=@(raw.length);
    if(!self.returned)self.returned=[NSMutableArray new];[self.returned addObject:[raw copy]];
    return @{@"data":raw,@"observation":o};
}
@end

int main(int argc,const char *argv[]){@autoreleasepool {
    assert(argc==3);NSData *historical=[NSData dataWithContentsOfFile:@(argv[2])];assert(historical.length==168);
    IsoProbeStatus history;memcpy(&history,historical.bytes,sizeof(history));assert(history.sequence==65 && history.report_count==0);
    assert(A23StatusAfterFailures(&history,65)==0);
    NSString *root=@(argv[1]);NSMutableDictionary *matrix=[NSMutableDictionary new];
    NSArray *names=@[@"normal",@"count0",@"count10",@"count01",@"before-count2",@"before-drift",
        @"bad-magic",@"bad-version",@"bad-sequence",@"bad-state",@"bad-post",@"bad-urb",@"bad-report-id",
        @"bad-requested",@"bad-transferred",@"bad-urb-status",@"bad-speed",@"bad-endpoint",@"bad-count",@"bad-report-result",
        @"bad-diag-magic",@"bad-terminal",@"bad-bitmap",@"bad-actual",@"bad-context",@"bad-mfi",@"bad-type",@"bad-sia",@"bad-frame-id",
        @"bad-observation",@"bad-observation-json",@"short-after",@"same-urb",@"status-before-collision",@"status-after-collision",@"bad-payload",@"control-timeout"];
    NSArray *successes=@[@"normal",@"count0",@"count10",@"count01"];
    for(NSString *name in names){
        NSString *directory=[root stringByAppendingPathComponent:name];assert([[NSFileManager defaultManager] createDirectoryAtPath:directory withIntermediateDirectories:NO attributes:nil error:NULL]);
        for(NSString *phase in @[@"before",@"after"])if([name isEqual:[NSString stringWithFormat:@"status-%@-collision",phase]])
            assert(([[NSFileManager defaultManager] createDirectoryAtPath:[directory stringByAppendingPathComponent:[NSString stringWithFormat:@"status-%@-epoch-0",phase]] withIntermediateDirectories:NO attributes:nil error:NULL]));
        PairOperations *op=pairOperations(name,NO);StatusCaptureInterface *r=[StatusCaptureInterface new];r.fault=name;r.clock=[TwoClock new];op.interface=r;
        assert([pairCandidate()[@"service_token"] intValue]==7 && !pairZero(r.dataStores[0]));
        EntryFixture initial={.interface=r};NSMutableData *storage=[NSMutableData dataWithLength:sizeof(EntryFixture)];EntryFixture *f=storage.mutableBytes;*f=initial;
        A23WaitOps wait={.context=f,.create=efCreate,.matching=efMatching,.valid=efValid,.next=efNext,.identity=efIdentity,.interest=efInterest,.pump=efPump,.release=efRelease,.destroy=efDestroy};
        dispatch_queue_t q=dispatch_queue_create("a23.status.capture.model",DISPATCH_QUEUE_SERIAL);
        __block A23TwoEpochEntry *entry=nil;__block A23LiveTwoEpochRun *loop=nil;
        EntryPermit *permit=[EntryPermit new];permit.fault=name;permit.directory=directory;permit.fixtureStorage=storage;
        NSString *hash=[@"a" stringByPaddingToLength:64 withString:@"a" startingAtIndex:0];
        NSDictionary *binding=@{@"schema":@"A23-two-epoch-entry-binding-1",@"build_manifest_sha256":hash,@"receiver_sha256":hash,@"authorization_receipt_sha256":hash,@"first_sequence":@81,@"last_sequence":@112};
        dispatch_sync(q,^{
            A23PairedSDKProvider *provider=(id)pairProvider(op,q,YES,^(uint32_t m){(void)m;[entry detachedRegistryID:102];});
            entry=[[A23TwoEpochEntry alloc] initWithDirectory:directory queue:q clock:r.clock ops:&wait provider:provider permit:permit context:efContext(hash) binding:binding];assert(entry);
            loop=[[A23LiveTwoEpochRun alloc] initWithTarget:(id<A23LiveEntryTarget>)entry directory:directory stop:^{[entry requestExit];}];assert(loop);assert([loop begin]);[loop tick];[loop tick];
        });
        if([name isEqual:@"control-timeout"]){dispatch_sync(q,^{[r.clock advanceNS:17000000];[loop tick];});}
        else for(NSUInteger n=0;n<2;n++){
            __block BOOL stopped;dispatch_sync(q,^{stopped=[entry.result[@"stopped"] boolValue];});if(stopped)break;
            [r deliver:n];dispatch_sync(q,^{[loop tick];});if(n==0)dispatch_sync(q,^{[loop tick];});
        }
        [r.clock advanceNS:250000001];dispatch_sync(q,^{[loop tick];
            NSDictionary *s=loop.status;BOOL normal=[successes containsObject:name];assert([s[@"success"] boolValue]==normal);
            assert([s[@"unresolved_keep_alive"] boolValue]==!normal);assert(!r.destroys && r.submissions<=2 && r.triggers<=2);
            if(!normal && ![name isEqual:@"same-urb"])assert(r.submissions<=1);
            for(NSUInteger n=0;n<r.returned.count;n++){
                NSString *phase=n%2?@"after":@"before";NSString *path=[directory stringByAppendingPathComponent:[NSString stringWithFormat:@"status-%@-epoch-%lu/raw.bin",phase,(unsigned long)(n/2)]];
                if(![name containsString:@"collision"])assert([[NSData dataWithContentsOfFile:path] isEqual:r.returned[n]]);
            }
            NSDictionary *row=@{@"loop":s,@"entry":entry.result,@"opens":@(op.opens),@"iso_submissions":@(r.submissions),@"burst_triggers":@(r.triggers),@"status_reads":@(r.statusReads),@"aborts":@(r.aborts),@"sdk_destroys":@(r.destroys)};
            efExport(directory,@"controller-observation.json",row);matrix[name]=row;
        });
    }
    NSData *raw=[NSJSONSerialization dataWithJSONObject:@{@"cases":matrix,@"case_count":@(names.count),@"historical_native_status65_passed":@YES,@"real_sdk_objects":@0,@"usb_requests":@0} options:NSJSONWritingSortedKeys error:NULL];fwrite(raw.bytes,1,raw.length,stdout);puts("");return 0;
}}
