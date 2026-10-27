#import "a23_short24_runtime.h"
#include <CommonCrypto/CommonDigest.h>
#include <errno.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
static NSString *digest(NSData *data) {
    unsigned char h[32];CC_SHA256(data.bytes,(CC_LONG)data.length,h);NSMutableString *s=[NSMutableString string];
    for(unsigned i=0;i<32;i++)[s appendFormat:@"%02x",h[i]];return s;
}
static BOOL bad(NSError **e,NSString *why){if(e)*e=[NSError errorWithDomain:@"A23Short24Evidence" code:errno userInfo:@{NSLocalizedDescriptionKey:why}];return NO;}
static NSData *encode(NSDictionary *value,NSError **e) {
    NSData *d=[NSJSONSerialization dataWithJSONObject:value options:NSJSONWritingSortedKeys error:e];
    return d.length<=65536?d:nil;
}
static BOOL file(int dir,NSString *name,NSData *data,NSError **error) {
    int fd=openat(dir,name.fileSystemRepresentation,O_RDWR|O_CREAT|O_EXCL|O_NOFOLLOW,0600);
    if(fd<0)return bad(error,@"exclusive file creation");
    BOOL ok=YES;NSUInteger done=0;
    while(done<data.length){ssize_t n=write(fd,(const uint8_t *)data.bytes+done,data.length-done);
        if(n<0 && errno==EINTR)continue;if(n<=0){ok=NO;break;}done+=(NSUInteger)n;}
    if(ok)ok=fsync(fd)==0 && lseek(fd,0,SEEK_SET)==0;
    NSMutableData *check=[NSMutableData dataWithLength:data.length];done=0;
    while(ok && done<check.length){ssize_t n=read(fd,(uint8_t *)check.mutableBytes+done,check.length-done);
        if(n<0 && errno==EINTR)continue;if(n<=0){ok=NO;break;}done+=(NSUInteger)n;}
    struct stat st;if(ok)ok=fstat(fd,&st)==0 && (uint64_t)st.st_size==data.length && [data isEqual:check];
    if(close(fd))ok=NO;return ok?YES:bad(error,@"write/readback failed; partial bytes retained");
}
static BOOL component(NSString *name){return name.length && name.length<96 && ![name isEqual:@"."] && ![name isEqual:@".."] &&
    [name rangeOfCharacterFromSet:[[NSCharacterSet characterSetWithCharactersInString:@"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"] invertedSet]].location==NSNotFound;}
BOOL A23Short24WriteRecord(NSString *parent,NSString *name,NSDictionary *record,NSError **error) {
    if(!component(name))return bad(error,@"invalid record name");NSData *d=encode(record,error);if(!d)return NO;
    int dir=open(parent.fileSystemRepresentation,O_RDONLY|O_DIRECTORY|O_NOFOLLOW);if(dir<0)return bad(error,@"open record parent");
    BOOL ok=file(dir,name,d,error);if(ok)ok=fsync(dir)==0;close(dir);return ok;
}
BOOL A23Short24WriteObservation(NSString *parent,NSString *name,NSDictionary *snapshot,NSError **error) {
    if(!component(name))return bad(error,@"invalid observation name");
    NSMutableDictionary *files=[NSMutableDictionary dictionary];
    for(NSString *n in @[@"raw",@"transactions",@"before",@"after"]){
        NSData *d=snapshot[n];if(![d isKindOfClass:NSData.class])return bad(error,@"missing byte snapshot");
        if(([n isEqual:@"raw"] && d.length!=3072) || ([n isEqual:@"transactions"] && d.length!=3584) ||
           (([n isEqual:@"before"] || [n isEqual:@"after"]) && d.length>168))return bad(error,@"snapshot size");
        files[[n stringByAppendingString:@".bin"]]=d;
    }
    NSData *metadata=encode(snapshot[@"metadata"],error);if(!metadata)return NO;files[@"metadata.json"]=metadata;
    int root=open(parent.fileSystemRepresentation,O_RDONLY|O_DIRECTORY|O_NOFOLLOW);if(root<0)return bad(error,@"open observation parent");
    if(mkdirat(root,name.fileSystemRepresentation,0700)){close(root);return bad(error,@"observation already exists or create failed");}
    int dir=openat(root,name.fileSystemRepresentation,O_RDONLY|O_DIRECTORY|O_NOFOLLOW);BOOL ok=dir>=0;
    NSMutableString *sums=[NSMutableString string];
    for(NSString *n in [[files allKeys] sortedArrayUsingSelector:@selector(compare:)]){
        if(ok)ok=file(dir,n,files[n],error);[sums appendFormat:@"%@  %@\n",digest(files[n]),n];
    }
    NSData *manifest=[sums dataUsingEncoding:NSUTF8StringEncoding];
    if(ok)ok=file(dir,@"SHA256SUMS",manifest,error);
    if(ok)ok=file(dir,@"COMMITTED",[[digest(manifest) stringByAppendingString:@"\n"] dataUsingEncoding:NSUTF8StringEncoding],error);
    if(ok)ok=fsync(dir)==0 && fsync(root)==0;if(dir>=0)close(dir);close(root);return ok;
}

@implementation A23Short24Runtime {
    A23Short24Capture *_capture;dispatch_queue_t _queue;NSString *_directory;NSDictionary *_context;
    uint64_t (^_clock)(void);uint64_t _start;A23Short24Runtime *_hold;
    BOOL _startAttempted,_started,_saveAttempted,_saved,_noticeFailed;NSUInteger _notices,_noticesSaved;
    NSDictionary *_error,*_lastFacts;
}
- (instancetype)initWithCapture:(A23Short24Capture *)capture queue:(dispatch_queue_t)queue
    directory:(NSString *)directory context:(NSDictionary *)context clockNanoseconds:(uint64_t (^)(void))clock {
    if(!capture || !queue || !directory.isAbsolutePath || !context || !clock)return nil;
    dispatch_assert_queue(queue);if([capture.result[@"started"] boolValue])return nil;
    if((self=[super init])){_capture=capture;_queue=queue;_directory=[directory copy];_context=[context copy];_clock=[clock copy];}
    return self;
}
- (void)error:(NSError *)error { _error=@{@"domain":error.domain ?: @"runtime",@"code":@(error.code),@"description":error.localizedDescription ?: @"failed"}; }
- (NSDictionary *)facts:(NSDictionary *)r {
    return @{@"iso_callbacks":r[@"iso_callbacks"],@"control_callbacks":r[@"control_callbacks"],@"stopped":r[@"stopped"],
        @"io_unresolved":r[@"io_unresolved"],@"failure_reasons":r[@"failure_reasons"]};
}
- (BOOL)start {
    dispatch_assert_queue(_queue);if(_startAttempted)return NO;_startAttempted=YES;_hold=self;NSError *error=nil;
    if(!A23Short24WriteRecord(_directory,@"start-intent.json",@{@"schema":@"A23-short24-start-intent-1",@"context":_context,
        @"hardware_verified":@NO,@"process_exit_authorized":@NO},&error)){[self error:error];return NO;}
    _started=YES;_start=_clock();BOOL ok=[_capture start];[self poll];return ok;
}
- (void)poll {
    dispatch_assert_queue(_queue);if(!_started)return;[_capture poll];NSDictionary *r=_capture.result;
    if(!_saveAttempted && _clock()>=_start && _clock()-_start>=5000000000ULL && ![r[@"observation_complete"] boolValue]){
        [_capture requestStop];r=_capture.result;
    }
    if(!_saveAttempted && ([r[@"observation_complete"] boolValue] || [r[@"stopped"] boolValue])){
        _saveAttempted=YES;NSError *error=nil;_saved=A23Short24WriteObservation(_directory,@"observation",_capture.snapshot,&error);
        if(!_saved){[self error:error];[_capture requestStop];r=_capture.result;}
        _lastFacts=[self facts:r];
    }
    NSDictionary *facts=[self facts:r];
    if(_saveAttempted && ![facts isEqual:_lastFacts] && !_noticeFailed){
        if(_notices>=8){_noticeFailed=YES;return;}
        NSError *error=nil;NSString *name=[NSString stringWithFormat:@"later-%04lu.json",(unsigned long)++_notices];
        BOOL ok=A23Short24WriteRecord(_directory,name,@{@"schema":@"A23-short24-later-observation-1",@"capture":r,
            @"rewrites_original_observation":@NO,@"process_exit_authorized":@NO},&error);
        if(!ok){_noticeFailed=YES;[self error:error];}else ++_noticesSaved;_lastFacts=facts;
    }
}
- (void)requestStop {dispatch_assert_queue(_queue);[_capture requestStop];[self poll];}
- (void)providerInterest:(uint32_t)message {[_capture providerInterest:message];}
- (NSDictionary *)result {
    dispatch_assert_queue(_queue);return @{@"schema":@"A23-short24-runtime-1",@"start_attempted":@(_startAttempted),
        @"started":@(_started),@"observation_attempted":@(_saveAttempted),@"observation_saved":@(_saved),
        @"holding_runtime_resources":@(_startAttempted),@"later_attempts":@(_notices),@"later_records":@(_noticesSaved),@"later_write_failed":@(_noticeFailed),
        @"error":_error ?: @{},@"capture":_capture.result,@"process_exit_authorized":@NO,@"hardware_verified":@NO};
}
@end
