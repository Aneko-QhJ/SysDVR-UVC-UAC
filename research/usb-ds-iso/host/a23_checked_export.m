#import "a23_checked_export.h"
#include "a23_checked_export_binding.h"
#include <CommonCrypto/CommonDigest.h>
#include <errno.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#ifdef A23_EXPORT_MODEL_FIXTURE
extern void A23ExportModelCheckpoint(NSString *stage);
#define checkpoint(stage) A23ExportModelCheckpoint(stage)
#else
#define checkpoint(stage) ((void)0)
#endif
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
    BOOL first=YES;
    for(NSString *n in [values.allKeys sortedArrayUsingSelector:@selector(compare:)]){NSData *r=[values[n] isKindOfClass:NSData.class]?values[n]:encode(values[n]);if(!r || !put(fd,n,r)){ok=NO;break;}[sums appendFormat:@"%@  %@\n",sha(r),n];
        if(first && [name isEqual:@"live-final"]){first=NO;checkpoint(@"mid_payload");}}
    NSData *raw=[sums dataUsingEncoding:NSUTF8StringEncoding];if(ok)ok=put(fd,@"SHA256SUMS",raw) && fsync(fd)==0 && put(fd,@"COMMITTED",[[sha(raw) stringByAppendingString:@"\n"] dataUsingEncoding:NSUTF8StringEncoding]) && fsync(fd)==0 && fsync(parent)==0;
    if(close(fd))ok=NO;if(close(parent))ok=NO;return ok;
}
static NSData *readOnlyFile(NSString *path){
    char *p=realpath(path.fileSystemRepresentation,NULL);BOOL canonical=p && [path isEqual:@(p)];free(p);if(!canonical)return nil;
    int fd=open(path.fileSystemRepresentation,O_RDONLY|O_NOFOLLOW|O_NONBLOCK);if(fd<0)return nil;struct stat st;
    if(fstat(fd,&st) || !S_ISREG(st.st_mode) || st.st_size<0 || st.st_size>2*1024*1024){close(fd);return nil;}
    NSMutableData *raw=[NSMutableData dataWithLength:(NSUInteger)st.st_size];NSUInteger at=0;
    while(at<raw.length){ssize_t n=read(fd,(uint8_t *)raw.mutableBytes+at,raw.length-at);if(n<0 && errno==EINTR)continue;if(n<=0){close(fd);return nil;}at+=(NSUInteger)n;}
    char extra;BOOL ok=read(fd,&extra,1)==0;if(close(fd))ok=NO;return ok?raw:nil;
}
static NSData *payloadManifest(NSString *directory,NSDictionary *values){
    NSMutableString *sums=[NSMutableString new];NSMutableSet *names=[NSMutableSet setWithArray:values.allKeys];
    [names addObjectsFromArray:@[@"SHA256SUMS",@"COMMITTED"]];
    NSArray *actual=[[NSFileManager defaultManager] contentsOfDirectoryAtPath:directory error:NULL];
    if(!actual || ![[NSSet setWithArray:actual] isEqual:names])return nil;
    for(NSString *name in [values.allKeys sortedArrayUsingSelector:@selector(compare:)]){
        NSData *expected=[values[name] isKindOfClass:NSData.class]?values[name]:encode(values[name]);
        if(!expected || ![expected isEqual:readOnlyFile([directory stringByAppendingPathComponent:name])])return nil;
        [sums appendFormat:@"%@  %@\n",sha(expected),name];
    }
    NSData *raw=[sums dataUsingEncoding:NSUTF8StringEncoding];
    if(![raw isEqual:readOnlyFile([directory stringByAppendingPathComponent:@"SHA256SUMS"])])return nil;
    return [[[sha(raw) stringByAppendingString:@"\n"] dataUsingEncoding:NSUTF8StringEncoding] isEqual:readOnlyFile([directory stringByAppendingPathComponent:@"COMMITTED"])]?raw:nil;
}
static NSDictionary *candidateBinding(void){
    return [NSJSONSerialization JSONObjectWithData:[NSData dataWithBytes:A23CheckedExportBinding length:sizeof(A23CheckedExportBinding)] options:0 error:NULL];
}
@implementation A23CheckedTwoEpochRun {id<A23CheckedEntryTarget> _target;NSString *_directory;void (^_stop)(void);BOOL _begun,_finished,_unresolved,_exportAttempted,_exportSaved,_acceptanceSaved,_success,_snapshotAttempted[2],_snapshotSaved[2],_operatorOffAcknowledged;NSUInteger _exitRequests;}
- (instancetype)initWithTarget:(id<A23CheckedEntryTarget>)target directory:(NSString *)directory stop:(void (^)(void))stop {
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
    return @{@"entry-current.json":r,@"entry-final-status.json":_target.finalStatus,@"candidate-binding.json":candidateBinding(),
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
    checkpoint(@"before_precheck");
    if(![_target validateFinalExport]){_stop();[self fail:_target.result];return;}
    r=_target.result;NSDictionary *final=_target.finalStatus,*pre=_target.exportEvidence;
    if(![r[@"complete"] boolValue] || ![final[@"saved"] boolValue] || [final[@"stale"] boolValue]){_stop();[self fail:_target.result];return;}
    NSMutableDictionary *values=[[self files:r] mutableCopy];values[@"validation-before.json"]=pre;
    _exportAttempted=YES;_exportSaved=exportFiles(_directory,@"live-final",values);
    checkpoint(@"after_payload");
    BOOL validated=_exportSaved && [_target validateFinalExport];NSDictionary *post=_target.exportEvidence;
    NSDictionary *latest=_target.result,*lastFinal=_target.finalStatus;
    NSData *manifest=_exportSaved?payloadManifest([_directory stringByAppendingPathComponent:@"live-final"],values):nil;
    if(!validated || !manifest || ![encode(r) isEqual:encode(latest)] || ![encode(final) isEqual:encode(lastFinal)] ||
        ![latest[@"complete"] boolValue] || ![lastFinal[@"saved"] boolValue] || [lastFinal[@"stale"] boolValue]){_stop();[self fail:_target.result];return;}
    checkpoint(@"after_postcheck");
    NSDictionary *receipt=@{@"schema":@"A23-checked-export-receipt-1",@"payload_manifest_sha256":sha(manifest),
        @"candidate_binding_sha256":sha(encode(candidateBinding())),@"pre_evidence_sha256":sha(encode(pre)),@"post_evidence_sha256":sha(encode(post)),
        @"entry_snapshot_sha256":sha(encode(r)),@"pre_full_check_index":pre[@"cadence"][@"full_invocations"],
        @"post_full_check_index":post[@"cadence"][@"full_invocations"],@"validated":@YES,@"snapshot_equal":@YES,@"payload_files_equal":@YES,
        @"hardware_verified":@NO,@"physical_run_authenticated":@NO,@"atomic_directory_snapshot_verified":@NO,@"future_disk_freshness_verified":@NO};
    _acceptanceSaved=exportFiles(_directory,@"live-acceptance",@{@"receipt.json":receipt,@"validation-after.json":post});
    if(!_acceptanceSaved){_stop();[self fail:_target.result];return;}
    checkpoint(@"after_receipt");
    _success=_finished=YES;
}
- (NSDictionary *)status {return @{@"schema":@"A23-checked-two-epoch-loop-1",@"begun":@(_begun),@"finished":@(_finished),@"success":@(_success),@"exit_code":@(_success?0:1),@"unresolved_keep_alive":@(_unresolved),@"exit_requests":@(_exitRequests),@"export_attempted":@(_exportAttempted),@"export_saved":@(_exportSaved),@"acceptance_saved":@(_acceptanceSaved),@"owner_evidence_snapshots_saved":@((unsigned)_snapshotSaved[0]+(unsigned)_snapshotSaved[1]),@"operator_power_off_acknowledged":@(_operatorOffAcknowledged),@"pending_sdk_work_unverified":@(_operatorOffAcknowledged || _unresolved),@"forced_exit":@NO,@"automatic_retry":@NO,@"callback_drain_verified":@NO,@"hardware_verified":@NO};}
@end
