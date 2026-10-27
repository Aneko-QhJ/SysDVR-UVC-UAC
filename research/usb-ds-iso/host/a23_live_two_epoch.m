#import "a23_live_two_epoch.h"
#include <CommonCrypto/CommonDigest.h>
#include <errno.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
static NSData *encode(id v){return [NSJSONSerialization dataWithJSONObject:v options:NSJSONWritingSortedKeys error:NULL];}
static NSString *sha(NSData *r){unsigned char h[32];CC_SHA256(r.bytes,(CC_LONG)r.length,h);NSMutableString *s=[NSMutableString new];for(unsigned i=0;i<32;i++)[s appendFormat:@"%02x",h[i]];return s;}
static BOOL put(int dir,NSString *name,NSData *raw){
    if(!raw)return NO;int fd=openat(dir,name.fileSystemRepresentation,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,0600);if(fd<0)return NO;
    BOOL ok=YES;NSUInteger p=0;while(p<raw.length){ssize_t n=write(fd,(const uint8_t *)raw.bytes+p,raw.length-p);if(n<0 && errno==EINTR)continue;if(n<=0){ok=NO;break;}p+=(NSUInteger)n;}
    if(ok)ok=fsync(fd)==0;if(close(fd))ok=NO;return ok;
}
static BOOL exportFiles(NSString *root,NSString *name,NSDictionary *values){
    int parent=open(root.fileSystemRepresentation,O_RDONLY|O_DIRECTORY|O_NOFOLLOW);if(parent<0)return NO;
    if(mkdirat(parent,name.fileSystemRepresentation,0700)){close(parent);return NO;}
    int fd=openat(parent,name.fileSystemRepresentation,O_RDONLY|O_DIRECTORY|O_NOFOLLOW);if(fd<0){close(parent);return NO;}
    BOOL ok=YES;NSMutableString *sums=[NSMutableString new];
    for(NSString *n in [values.allKeys sortedArrayUsingSelector:@selector(compare:)]){NSData *r=[values[n] isKindOfClass:NSData.class]?values[n]:encode(values[n]);if(!r || !put(fd,n,r)){ok=NO;break;}[sums appendFormat:@"%@  %@\n",sha(r),n];}
    NSData *raw=[sums dataUsingEncoding:NSUTF8StringEncoding];if(ok)ok=put(fd,@"SHA256SUMS",raw) && fsync(fd)==0 && put(fd,@"COMMITTED",[[sha(raw) stringByAppendingString:@"\n"] dataUsingEncoding:NSUTF8StringEncoding]) && fsync(fd)==0 && fsync(parent)==0;
    if(close(fd))ok=NO;if(close(parent))ok=NO;return ok;
}
@implementation A23LiveTwoEpochRun {id<A23LiveEntryTarget> _target;NSString *_directory;void (^_stop)(void);BOOL _begun,_finished,_unresolved,_exportAttempted,_exportSaved,_success,_snapshotAttempted[2],_snapshotSaved[2],_operatorOffAcknowledged;NSUInteger _exitRequests;}
- (instancetype)initWithTarget:(id<A23LiveEntryTarget>)target directory:(NSString *)directory stop:(void (^)(void))stop {
    char *p=realpath(directory.fileSystemRepresentation,NULL);BOOL canonical=p && [directory isEqual:@(p)];free(p);
    if(!target || !stop || !canonical)return nil;if((self=[super init])){_target=target;_directory=[directory copy];_stop=[stop copy];}return self;
}
- (BOOL)begin {if(_begun)return NO;_begun=YES;BOOL ok=[_target begin];if(!ok){_stop();[self tick];}return ok;}
- (void)requestExit {if(_finished)return;++_exitRequests;_stop();}
- (BOOL)finishAfterOperatorPowerOff {
    if(!_unresolved || _finished)return NO;
    _operatorOffAcknowledged=YES;_unresolved=NO;_finished=YES;
    exportFiles(_directory,@"operator-stop",@{@"stop.json":@{@"schema":@"A23-live-operator-stop-1",@"operator_power_off_confirmed":@YES,@"device_power_observed_by_software":@NO,@"pending_sdk_work_unverified":@YES,@"callback_drain_verified":@NO,@"resources_destroyed":@NO}});
    return YES;
}
- (NSDictionary *)files:(NSDictionary *)r {
    id driver=r[@"driver"],receipt=r[@"driver_receipt"];
    return @{@"entry-current.json":r,@"entry-final-status.json":_target.finalStatus,
        @"result.json":[driver isKindOfClass:NSDictionary.class]?driver:@{},
        @"receipt-status.json":[receipt isKindOfClass:NSDictionary.class]?receipt:@{},
        @"live.json":@{@"schema":@"A23-live-two-epoch-export-1",@"raw_inflight_buffers_copied":@NO,@"callback_drain_verified":@NO,@"hardware_verified":@NO}};
}
- (void)saveAvailableSnapshots {
    if(![_target respondsToSelector:@selector(liveFailureSnapshots)])return;
    for(NSDictionary *snapshot in [_target liveFailureSnapshots]){
        NSUInteger epoch=[snapshot[@"epoch"] unsignedIntegerValue];if(epoch>=2 || _snapshotAttempted[epoch])continue;
        NSDictionary *e=snapshot[@"evidence"];NSData *raw=e[@"raw"],*rows=e[@"transactions"];
        if(![raw isKindOfClass:NSData.class] || ![rows isKindOfClass:NSData.class])continue;
        _snapshotAttempted[epoch]=YES;NSMutableDictionary *meta=[e mutableCopy];[meta removeObjectsForKeys:@[@"raw",@"transactions"]];
        meta[@"epoch"]=@(epoch);meta[@"source"]=@"retained_owner_snapshot";meta[@"active_sdk_buffers_read"]=@NO;
        _snapshotSaved[epoch]=exportFiles(_directory,[NSString stringWithFormat:@"live-evidence-epoch-%lu",(unsigned long)epoch],@{@"raw.bin":raw,@"transactions.bin":rows,@"owner.json":meta});
    }
}
- (void)fail:(NSDictionary *)r {
    // Any retained lease may contain unresolved native work. Preserve it even
    // when a callback count looks complete; counts do not establish drain.
    _unresolved=[r[@"resources_retained"] boolValue];[self saveAvailableSnapshots];
    if(!_exportAttempted){_exportAttempted=YES;_exportSaved=exportFiles(_directory,@"live-failure",[self files:r]);}
    if(!_unresolved)_finished=YES;
}
- (void)tick {
    if(!_begun || _finished)return;[_target tick];NSDictionary *r=_target.result;
    if([r[@"stopped"] boolValue]){[self fail:r];return;}
    NSDictionary *d=[r[@"driver"] isKindOfClass:NSDictionary.class]?r[@"driver"]:nil;
    if(![d[@"complete"] boolValue])return;
    if(![_target finalizeOnce]){_stop();[self fail:_target.result];return;}
    r=_target.result;NSDictionary *final=_target.finalStatus;
    if(![r[@"complete"] boolValue] || ![final[@"saved"] boolValue] || [final[@"stale"] boolValue]){_stop();[self fail:_target.result];return;}
    _exportAttempted=YES;_exportSaved=exportFiles(_directory,@"live-final",[self files:r]);
    NSDictionary *latest=_target.result,*lastFinal=_target.finalStatus;
    if(!_exportSaved || ![latest[@"complete"] boolValue] || ![lastFinal[@"saved"] boolValue] || [lastFinal[@"stale"] boolValue]){_stop();_unresolved=[latest[@"resources_retained"] boolValue];if(!_unresolved)_finished=YES;return;}
    _success=_finished=YES;
}
- (NSDictionary *)status {return @{@"schema":@"A23-live-two-epoch-loop-1",@"begun":@(_begun),@"finished":@(_finished),@"success":@(_success),@"exit_code":@(_success?0:1),@"unresolved_keep_alive":@(_unresolved),@"exit_requests":@(_exitRequests),@"export_attempted":@(_exportAttempted),@"export_saved":@(_exportSaved),@"owner_evidence_snapshots_saved":@((unsigned)_snapshotSaved[0]+(unsigned)_snapshotSaved[1]),@"operator_power_off_acknowledged":@(_operatorOffAcknowledged),@"pending_sdk_work_unverified":@(_operatorOffAcknowledged || _unresolved),@"forced_exit":@NO,@"automatic_retry":@NO,@"callback_drain_verified":@NO,@"hardware_verified":@NO};}
@end
