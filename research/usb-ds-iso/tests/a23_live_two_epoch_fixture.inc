// Frozen fake SDK/IOKit prefixes; the live controller, scope and permit are real.
#import "../host/a23_live_two_epoch.h"
int main(int argc,const char *argv[]){@autoreleasepool {
    assert(argc==2);NSString *root=@(argv[1]);NSMutableDictionary *matrix=[NSMutableDictionary new];
    NSArray *names=@[@"normal",@"bad-payload",@"control-timeout",@"exit-waiting",@"exit-running",@"quiet-incomplete",@"export-collision",@"receipt-collision",@"old-before-final",@"operator-off-after-timeout"];
    for(NSString *name in names){
        NSString *directory=[root stringByAppendingPathComponent:name];assert([[NSFileManager defaultManager] createDirectoryAtPath:directory withIntermediateDirectories:NO attributes:nil error:NULL]);
        PairOperations *op=pairOperations(name,NO);SDKModelInterface *r=[SDKModelInterface new];r.fault=name;r.clock=[TwoClock new];op.interface=r;assert([pairCandidate()[@"service_token"] intValue]==7 && !pairZero(r.dataStores[0]));
        EntryFixture initial={.interface=r,.noArrival=[name isEqual:@"exit-waiting"]};
        NSMutableData *storage=[NSMutableData dataWithLength:sizeof(EntryFixture)];EntryFixture *f=storage.mutableBytes;*f=initial;
        A23WaitOps wait={.context=f,.create=efCreate,.matching=efMatching,.valid=efValid,.next=efNext,.identity=efIdentity,.interest=efInterest,.pump=efPump,.release=efRelease,.destroy=efDestroy};
        dispatch_queue_t q=dispatch_queue_create("a23.live.model",DISPATCH_QUEUE_SERIAL);
        __block A23TwoEpochEntry *entry=nil;__block A23LiveTwoEpochRun *loop=nil;
        EntryPermit *permit=[EntryPermit new];permit.fault=name;permit.directory=directory;permit.fixtureStorage=storage;
        NSString *hash=[@"a" stringByPaddingToLength:64 withString:@"a" startingAtIndex:0];
        NSDictionary *binding=@{@"schema":@"A23-two-epoch-entry-binding-1",@"build_manifest_sha256":hash,@"receiver_sha256":hash,@"authorization_receipt_sha256":hash,@"first_sequence":@81,@"last_sequence":@112};
        dispatch_sync(q,^{
            A23PairedSDKProvider *provider=(id)pairProvider(op,q,YES,^(uint32_t m){(void)m;[entry detachedRegistryID:102];});
            entry=[[A23TwoEpochEntry alloc] initWithDirectory:directory queue:q clock:r.clock ops:&wait provider:provider permit:permit context:efContext(hash) binding:binding];assert(entry);
            loop=[[A23LiveTwoEpochRun alloc] initWithTarget:(id<A23LiveEntryTarget>)entry directory:directory stop:^{[entry requestExit];}];assert(loop);assert([loop begin]);assert(![loop begin]);
            if([name isEqual:@"exit-waiting"])[loop requestExit];[loop tick];[loop tick];
        });
        if([name isEqual:@"exit-running"] || [name isEqual:@"control-timeout"] || [name isEqual:@"operator-off-after-timeout"]){
            dispatch_sync(q,^{[r.clock advanceNS:17000000];if([name isEqual:@"exit-running"])[loop requestExit];[loop tick];});
        }else if(![name isEqual:@"exit-waiting"]){
            for(NSUInteger n=0;n<2;n++){
                __block BOOL stopped;dispatch_sync(q,^{stopped=[entry.result[@"stopped"] boolValue];});if(stopped)break;
                [r deliver:n];dispatch_sync(q,^{[loop tick];});if(n==0)dispatch_sync(q,^{[loop tick];});
            }
            if([name isEqual:@"receipt-collision"] || [name isEqual:@"export-collision"]){NSString *n=[name isEqual:@"receipt-collision"]?@"sdk-receipt":@"live-final";assert([[NSFileManager defaultManager] createDirectoryAtPath:[directory stringByAppendingPathComponent:n] withIntermediateDirectories:NO attributes:nil error:NULL]);}
            if([name isEqual:@"old-before-final"])[r oldISO];
            if(![name isEqual:@"quiet-incomplete"])[r.clock advanceNS:250000001];dispatch_sync(q,^{[loop tick];});
        }
        dispatch_sync(q,^{
            BOOL operatorOff=[name isEqual:@"operator-off-after-timeout"];if(operatorOff){assert([loop finishAfterOperatorPowerOff]);assert(![loop finishAfterOperatorPowerOff]);}
            NSDictionary *s=loop.status;BOOL normal=[name isEqual:@"normal"],early=[name isEqual:@"exit-waiting"],waiting=[name isEqual:@"quiet-incomplete"];
            assert([s[@"success"] boolValue]==normal);assert([s[@"finished"] boolValue]==(normal||early||operatorOff));
            assert([s[@"unresolved_keep_alive"] boolValue]==(!normal&&!early&&!waiting&&!operatorOff));
            assert(r.submissions<=2 && r.triggers<=2 && !r.destroys);
            if(early)assert(!op.opens && !r.submissions);
            if([name isEqual:@"bad-payload"] || [name isEqual:@"control-timeout"] || [name isEqual:@"exit-running"])assert(r.submissions==1);
            efExport(directory,@"controller-observation.json",@{@"loop":s,@"entry":entry.result,@"opens":@(op.opens),@"iso_submissions":@(r.submissions),@"burst_triggers":@(r.triggers),@"aborts":@(r.aborts),@"sdk_destroys":@(r.destroys),@"real_sdk_objects":@0,@"usb_requests":@0});matrix[name]=s;
        });
    }
    NSData *raw=[NSJSONSerialization dataWithJSONObject:@{@"cases":matrix,@"model_cases":@(names.count),@"real_sdk_objects":@0,@"usb_requests":@0} options:NSJSONWritingSortedKeys error:NULL];fwrite(raw.bytes,1,raw.length,stdout);puts("");return 0;
}}
