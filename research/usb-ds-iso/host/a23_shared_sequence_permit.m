#import "a23_shared_sequence_permit.h"
#include <CommonCrypto/CommonDigest.h>
#include <errno.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

static NSString *sha(NSData *r){unsigned char h[32];CC_SHA256(r.bytes,(CC_LONG)r.length,h);NSMutableString *s=[NSMutableString new];for(unsigned i=0;i<32;i++)[s appendFormat:@"%02x",h[i]];return s;}
static NSData *encode(id v){if(![NSJSONSerialization isValidJSONObject:v])return nil;NSMutableData *r=[[NSJSONSerialization dataWithJSONObject:v options:NSJSONWritingSortedKeys|NSJSONWritingWithoutEscapingSlashes error:NULL] mutableCopy];[r appendBytes:"\n" length:1];return r;}
static BOOL equal(id a,id b){NSData *x=encode(a),*y=encode(b);return x && y && [x isEqual:y];}
static BOOL flag(id v,BOOL b){return [v isKindOfClass:NSNumber.class] && CFGetTypeID((__bridge CFTypeRef)v)==CFBooleanGetTypeID() && [v boolValue]==b;}
static BOOL number(id v){return [v isKindOfClass:NSNumber.class] && CFGetTypeID((__bridge CFTypeRef)v)!=CFBooleanGetTypeID() && !CFNumberIsFloatType((__bridge CFNumberRef)v) && [v compare:@0]!=NSOrderedAscending;}
static BOOL canonical(NSString *p){char *q=realpath(p.fileSystemRepresentation,NULL);BOOL ok=q && [p isEqual:@(q)];free(q);return ok;}
static NSData *readFile(NSString *p){
    if(!canonical(p))return nil;int fd=open(p.fileSystemRepresentation,O_RDONLY|O_NOFOLLOW|O_NONBLOCK);if(fd<0)return nil;struct stat st;
    if(fstat(fd,&st) || !S_ISREG(st.st_mode) || st.st_size<0 || st.st_size>1024*1024){close(fd);return nil;}
    NSMutableData *r=[NSMutableData dataWithLength:(NSUInteger)st.st_size];NSUInteger at=0;
    while(at<r.length){ssize_t n=read(fd,(uint8_t *)r.mutableBytes+at,r.length-at);if(n<0 && errno==EINTR)continue;if(n<=0){close(fd);return nil;}at+=(NSUInteger)n;}
    char x;BOOL ok=read(fd,&x,1)==0;if(close(fd))ok=NO;return ok ? r : nil;
}
static NSDictionary *load(NSString *p){NSData *raw=readFile(p);id v=raw ? [NSJSONSerialization JSONObjectWithData:raw options:0 error:NULL] : nil;return [v isKindOfClass:NSDictionary.class] && [encode(v) isEqual:raw] ? v : nil;}
static BOOL put(NSString *directory,NSString *name,NSData *raw){
    if(!raw)return NO;int parent=open(directory.fileSystemRepresentation,O_RDONLY|O_DIRECTORY|O_NOFOLLOW);if(parent<0)return NO;
    int fd=openat(parent,name.fileSystemRepresentation,O_CREAT|O_EXCL|O_NOFOLLOW|O_RDWR,0600);if(fd<0){close(parent);return NO;}
    BOOL ok=fsync(fd)==0 && fsync(parent)==0;NSUInteger at=0;
    while(ok && at<raw.length){ssize_t n=write(fd,(const uint8_t *)raw.bytes+at,raw.length-at);if(n<0 && errno==EINTR)continue;if(n<=0){ok=NO;break;}at+=(NSUInteger)n;}
    if(ok)ok=fsync(fd)==0;NSMutableData *copy=[NSMutableData dataWithLength:raw.length];at=0;
    while(ok && at<raw.length){ssize_t n=pread(fd,(uint8_t *)copy.mutableBytes+at,raw.length-at,(off_t)at);if(n<0 && errno==EINTR)continue;if(n<=0){ok=NO;break;}at+=(NSUInteger)n;}
    char extra;if(ok)ok=pread(fd,&extra,1,(off_t)raw.length)==0 && [copy isEqual:raw] && fsync(parent)==0;if(close(fd))ok=NO;if(close(parent))ok=NO;return ok;
}
static NSString *at(NSString *p,NSString *name){return [p stringByAppendingPathComponent:name];}
@implementation A23SharedSequencePermit {
    NSString *_job,*_root,*_id;NSDictionary *_scope,*_binding;A23SharedScopeVerifier _verifier;BOOL _simulation,_processAttempted,_selectionAttempted,_processOK,_selectionOK,_invalid;NSData *_context,*_processRaw,*_selectionRaw;
}
- (BOOL)model {return NO;}
- (instancetype)initWithJob:(NSString *)job expectedScope:(NSDictionary *)scope verifier:(A23SharedScopeVerifier)verifier {
    if(![job isKindOfClass:NSString.class] || !canonical(job) || ![scope isKindOfClass:NSDictionary.class] || !verifier)return nil;
    NSData *frozen=encode(scope);if(!frozen)return nil;
    if((self=[super init])){_job=[job copy];_id=job.lastPathComponent;_root=job.stringByDeletingLastPathComponent.stringByDeletingLastPathComponent;_simulation=[self model];
        if(![at(_root,@"jobs") isEqual:job.stringByDeletingLastPathComponent] || ![[[NSUUID alloc] initWithUUIDString:_id].UUIDString.lowercaseString isEqual:_id])return nil;
        if(_simulation){if(![_root hasPrefix:@"/private/tmp/"])return nil;}
        else if(![_root isEqual:@"/Users/livcm/Documents/Developer/Git/SysDVR-UVC-Capture/research/usb-ds-iso/private/sequence-reservations32"])return nil;
        _scope=[NSJSONSerialization JSONObjectWithData:frozen options:0 error:NULL];_verifier=[verifier copy];if(![self healthy])return nil;
    }return self;
}
- (BOOL)healthy {
    if(!_verifier(_scope) || !equal(load(at(_root,@"scope.json")),_scope))return NO;
    NSSet *keys=[NSSet setWithArray:@[@"schema",@"baseline_manifest_sha256",@"baseline_inventory_sha256",@"workflow_source_sha256",@"build_manifest_sha256",@"receiver_sha256",@"device_binding_sha256",@"recipe_sha256",@"history_sha256",@"first_sequence",@"last_sequence",@"formal_issuance_available",@"acquisition_mode_implemented",@"hardware_entry_enabled"]];
    if(![[NSSet setWithArray:_scope.allKeys] isEqual:keys] || ![_scope[@"schema"] isEqual:@"A23-shared32-scope-1"] || !number(_scope[@"first_sequence"]) || ![_scope[@"first_sequence"] isEqual:@81] || !number(_scope[@"last_sequence"]) || ![_scope[@"last_sequence"] isEqual:@112] || !flag(_scope[@"hardware_entry_enabled"],NO))return NO;
    for(NSString *key in @[@"formal_issuance_available",@"acquisition_mode_implemented"])if(!flag(_scope[key],_simulation ? NO : YES))return NO;
    for(NSString *key in keys)if([key hasSuffix:@"sha256"]){NSString *s=_scope[key];if(![s isKindOfClass:NSString.class] || s.length!=64 || [s rangeOfCharacterFromSet:[[NSCharacterSet characterSetWithCharactersInString:@"0123456789abcdef"] invertedSet]].location!=NSNotFound)return NO;}
    NSDictionary *ns=load(at(_root,@"namespace.json"));NSString *sid=ns[@"id"],*sh=sha(readFile(at(_root,@"scope.json")));
    if(![sid isKindOfClass:NSString.class])return NO;
    NSDictionary *expectedNS=@{@"schema":@"A23-shared32-namespace-1",@"id":sid ?: @"",@"root":_root,@"scope_sha256":sh,@"history_sha256":_scope[@"history_sha256"],@"simulation":@(_simulation)};
    if(![[[NSUUID alloc] initWithUUIDString:sid].UUIDString.lowercaseString isEqual:sid] || !equal(ns,expectedNS) || ![_scope[@"history_sha256"] isEqual:sha(readFile(at(_root,@"history.json")))])return NO;
    NSDictionary *j=@{@"schema":@"A23-shared32-job-1",@"job_id":_id,@"job_path":_job,@"namespace_id":sid,@"scope_sha256":sh};
    NSDictionary *a=@{@"schema":@"A23-shared32-authorization-1",@"job_id":_id,@"scope_sha256":sh,@"maximum_invocations":@1,@"simulation":@(_simulation),@"hardware_test_authorized":@((BOOL)!_simulation)};
    if(!equal(load(at(_job,@"job.json")),j) || !equal(load(at(_job,@"authorization.json")),a))return NO;
    NSData *burn=readFile(at(_root,@"block-00081.json"));NSDictionary *r=@{@"schema":@"A23-shared32-reservation-1",@"namespace_id":sid,@"job_id":_id,@"job_path":_job,@"first":@81,@"last":@112,@"count":@32,@"scope_sha256":sh,@"job_sha256":sha(readFile(at(_job,@"job.json"))),@"authorization_sha256":sha(readFile(at(_job,@"authorization.json"))),@"simulation":@(_simulation)};
    if(!burn || !equal(load(at(_root,@"block-00081.json")),r))return NO;
    NSDictionary *issue=@{@"schema":@"A23-shared32-issue-1",@"namespace_id":sid,@"job_id":_id,@"job_path":_job,@"scope_sha256":sh,@"reservation_sha256":sha(burn),@"authorization_sha256":r[@"authorization_sha256"],@"remaining":@1,@"simulation":@(_simulation)};
    NSData *issued=readFile(at(_job,@"issue.json"));if(!issued || !equal(load(at(_job,@"issue.json")),issue) || ![readFile(at(_job,@"issue-commit")) isEqual:[@"issue durable\n" dataUsingEncoding:NSUTF8StringEncoding]])return NO;
    NSDictionary *consumed=@{@"schema":@"A23-shared32-consumed-1",@"namespace_id":sid,@"job_id":_id,@"job_path":_job,@"scope_sha256":sh,@"reservation_sha256":sha(burn),@"issue_sha256":sha(issued),@"authorization_sha256":r[@"authorization_sha256"],@"remaining":@0,@"receiver_launched":@NO,@"simulation":@(_simulation)};
    NSData *used=readFile(at(_job,@"consumed.json"));if(![readFile(at(_job,@"consume-commit")) isEqual:[@"consumption durable\n" dataUsingEncoding:NSUTF8StringEncoding]])return NO;if(!used || !equal(load(at(_job,@"consumed.json")),consumed) || ![readFile(at(_job,@"consume-attempt")) isEqual:[@"one attempt\n" dataUsingEncoding:NSUTF8StringEncoding]])return NO;
    _binding=@{@"schema":@"A23-two-epoch-entry-binding-1",@"build_manifest_sha256":_scope[@"build_manifest_sha256"],@"receiver_sha256":_scope[@"receiver_sha256"],@"authorization_receipt_sha256":sha(used),@"first_sequence":@81,@"last_sequence":@112};return YES;
}
- (BOOL)claimProcess:(NSDictionary *)binding context:(NSDictionary *)context {
    if(_processAttempted || _invalid)return NO;_processAttempted=YES;
    if(!put(_job,@"native-process-attempt",[@"one attempt\n" dataUsingEncoding:NSUTF8StringEncoding]) || ![self healthy])return NO;
    NSData *raw=encode(context);if(!equal(binding,_binding) || !A23ValidateExecutionContext(context,_scope[@"receiver_sha256"]) || (!_simulation && [context[@"pid"] intValue]!=getpid()) || !raw || !put(_job,@"native-context.json",raw))return NO;
    NSDictionary *claim=@{@"schema":@"A23-shared32-native-process-1",@"job_id":_id,@"consumed_sha256":binding[@"authorization_receipt_sha256"],@"context_sha256":sha(raw),@"pid":context[@"pid"],@"scope_sha256":sha(encode(_scope)),@"simulation":@(_simulation),@"hardware_verified":@NO};
    _processRaw=encode(claim);if(!put(_job,@"native-process-claim.json",_processRaw) || ![self healthy])return NO;_context=raw;_processOK=YES;return YES;
}
- (BOOL)claimSelection:(A23WaitIdentity)identity binding:(NSDictionary *)binding context:(NSDictionary *)context {
    if(_selectionAttempted || !_processOK || _invalid)return NO;_selectionAttempted=YES;
    if(!put(_job,@"native-selection-attempt",[@"one attempt\n" dataUsingEncoding:NSUTF8StringEncoding]) || ![self healthy])return NO;
    if(!equal(binding,_binding) || ![_context isEqual:encode(context)] || !identity.device_id || !identity.interface_id || identity.device_id==identity.interface_id || identity.speed!=3 || ![_context isEqual:readFile(at(_job,@"native-context.json"))] || ![_processRaw isEqual:readFile(at(_job,@"native-process-claim.json"))])return NO;
    NSDictionary *claim=@{@"schema":@"A23-shared32-native-selection-1",@"job_id":_id,@"process_sha256":sha(readFile(at(_job,@"native-process-claim.json"))),@"context_sha256":sha(_context),@"pid":context[@"pid"],@"identity":@{@"device_id":@(identity.device_id),@"interface_id":@(identity.interface_id),@"speed":@(identity.speed)},@"simulation":@(_simulation),@"hardware_verified":@NO};
    _selectionRaw=encode(claim);if(!put(_job,@"native-sdk-claim.json",_selectionRaw) || ![self healthy])return NO;_selectionOK=YES;return YES;
}
- (NSDictionary *)result {BOOL current=[self healthy] && (!_processOK || ([_context isEqual:readFile(at(_job,@"native-context.json"))] && [_processRaw isEqual:readFile(at(_job,@"native-process-claim.json"))])) && (!_selectionOK || [_selectionRaw isEqual:readFile(at(_job,@"native-sdk-claim.json"))]);if(!current)_invalid=YES;return @{@"schema":@"A23-shared32-native-permit-result-1",@"simulation":@(_simulation),@"process_attempted":@(_processAttempted),@"process_claimed":@((BOOL)(_processOK && !_invalid)),@"selection_attempted":@(_selectionAttempted),@"selection_claimed":@((BOOL)(_selectionOK && !_invalid)),@"stale":@(_invalid),@"hardware_verified":@NO,@"hardware_entry_enabled":@NO,@"process_origin_authenticated":@NO};}
@end
@implementation A23SharedSequenceModelPermit
- (BOOL)model{return YES;}
@end
