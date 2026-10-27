#import "../host/a23_shared_sequence_permit.h"
#include <assert.h>
static id parse(const char *p){NSData *r=[@(p) dataUsingEncoding:NSUTF8StringEncoding];return [NSJSONSerialization JSONObjectWithData:r options:0 error:NULL];}
static void corrupt(NSString *p){assert([[@"changed\n" dataUsingEncoding:NSUTF8StringEncoding] writeToFile:p options:0 error:NULL]);}
int main(int argc,const char *argv[]){@autoreleasepool {
    assert(argc==7);NSString *root=@(argv[1]),*job=@(argv[2]),*name=@(argv[6]);NSString *folder=[[root stringByAppendingPathComponent:@"jobs"] stringByAppendingPathComponent:job];
    NSDictionary *scope=parse(argv[3]),*binding=parse(argv[4]);NSMutableDictionary *context=[parse(argv[5]) mutableCopy];
    __block BOOL fresh=YES;__block NSUInteger checks=0;
    A23SharedScopeVerifier verifier=^BOOL(NSDictionary *s){checks++;return fresh && [scope isEqual:s] && !([name isEqual:@"fail-after-process-save"] && checks>=3) && !([name isEqual:@"fail-after-selection-save"] && checks>=5);};
    Class cls=[name isEqual:@"production-rejects-model"] ? A23SharedSequencePermit.class : A23SharedSequenceModelPermit.class;
    A23SharedSequencePermit *permit=[[cls alloc] initWithJob:folder expectedScope:scope verifier:verifier];
    BOOL process=NO,selection=NO,replayBlocked=YES;
    if(permit){
        if([name isEqual:@"scope-before-process"])fresh=NO;
        if([name isEqual:@"bad-binding"]){NSMutableDictionary *b=[binding mutableCopy];b[@"first_sequence"]=@97;binding=b;}
        if([name isEqual:@"sandbox-context"])context[@"sandbox_query_result"]=@1;
        if([name isEqual:@"bool-pid"])context[@"pid"]=@YES;
        process=[permit claimProcess:binding context:context];
        if([name isEqual:@"scope-before-selection"])fresh=NO;
        if([name isEqual:@"changed-context"])context[@"pid"]=@124;
        if([name isEqual:@"process-file-tamper"])corrupt([folder stringByAppendingPathComponent:@"native-process-claim.json"]);
        if([name isEqual:@"context-file-tamper"])corrupt([folder stringByAppendingPathComponent:@"native-context.json"]);
        A23WaitIdentity identity={.device_id=101,.interface_id=102,.speed=3};if([name isEqual:@"bad-identity"])identity.interface_id=101;
        selection=[permit claimSelection:identity binding:binding context:context];
        if([name isEqual:@"scope-after-selection"])fresh=NO;
        if([name isEqual:@"scope-restored-after-read"]){fresh=NO;assert([permit.result[@"stale"] boolValue]);fresh=YES;}
        if([name isEqual:@"selection-file-tamper"])corrupt([folder stringByAppendingPathComponent:@"native-sdk-claim.json"]);
        if([name isEqual:@"core-after-selection"])corrupt([folder stringByAppendingPathComponent:@"issue.json"]);
        replayBlocked=![permit claimProcess:binding context:context] && ![permit claimSelection:identity binding:binding context:context];
        if([name isEqual:@"cross-instance-replay"]){A23SharedSequencePermit *other=[[A23SharedSequenceModelPermit alloc] initWithJob:folder expectedScope:scope verifier:verifier];replayBlocked=replayBlocked && other && ![other claimProcess:binding context:context];}
    }
    NSDictionary *result=@{@"schema":@"A23-shared32-native-fixture-1",@"case":name,@"init_accepted":@((BOOL)(permit!=nil)),@"process_returned":@(process),@"selection_returned":@(selection),@"replay_blocked":@(replayBlocked),@"verifier_checks":@(checks),@"permit":permit ? permit.result : @{},@"real_sdk_objects":@0,@"usb_requests":@0,@"sd_accesses":@0};
    NSData *raw=[NSJSONSerialization dataWithJSONObject:result options:NSJSONWritingSortedKeys error:NULL];fwrite(raw.bytes,1,raw.length,stdout);puts("");return 0;
}}
