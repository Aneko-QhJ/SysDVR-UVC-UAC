#import "a23_scope_verifier.h"
#include "a23_verified_binding.h"
#include <CommonCrypto/CommonDigest.h>
#include <errno.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
static NSString *digest(NSData *r){unsigned char h[32];CC_SHA256(r.bytes,(CC_LONG)r.length,h);NSMutableString *s=[NSMutableString new];for(unsigned i=0;i<32;i++)[s appendFormat:@"%02x",h[i]];return s;}
static NSString *at(NSString *p,NSString *n){return [p stringByAppendingPathComponent:n];}
static NSData *encode(id v){if(![NSJSONSerialization isValidJSONObject:v])return nil;NSMutableData *r=[[NSJSONSerialization dataWithJSONObject:v options:NSJSONWritingSortedKeys|NSJSONWritingWithoutEscapingSlashes error:NULL] mutableCopy];[r appendBytes:"\n" length:1];return r;}
static BOOL equal(id a,id b){NSData *x=encode(a),*y=encode(b);return x && y && [x isEqual:y];}
static BOOL canonical(NSString *p){if(![p isKindOfClass:NSString.class])return NO;char *q=realpath(p.fileSystemRepresentation,NULL);BOOL ok=q && [p isEqual:@(q)];free(q);return ok;}
static BOOL relative(NSString *p){if(![p isKindOfClass:NSString.class] || !p.length || p.isAbsolutePath || [p containsString:@"\n"] || [p containsString:@"\r"])return NO;for(NSString *s in [p componentsSeparatedByString:@"/"])if(!s.length || [s isEqual:@"."] || [s isEqual:@".."])return NO;return YES;}
static NSData *readFile(NSString *p,NSUInteger limit){
    if(!canonical(p))return nil;int fd=open(p.fileSystemRepresentation,O_RDONLY|O_NOFOLLOW|O_NONBLOCK);if(fd<0)return nil;struct stat st;
    if(fstat(fd,&st) || !S_ISREG(st.st_mode) || st.st_size<0 || (uint64_t)st.st_size>limit){close(fd);return nil;}
    NSMutableData *r=[NSMutableData dataWithLength:(NSUInteger)st.st_size];NSUInteger n=0;
    while(n<r.length){ssize_t k=read(fd,(uint8_t *)r.mutableBytes+n,r.length-n);if(k<0 && errno==EINTR)continue;if(k<=0){close(fd);return nil;}n+=(NSUInteger)k;}
    char extra;BOOL ok=read(fd,&extra,1)==0;if(close(fd))ok=NO;return ok ? r : nil;
}
static NSDictionary *parseDict(NSData *r){id v=r ? [NSJSONSerialization JSONObjectWithData:r options:0 error:NULL] : nil;return [v isKindOfClass:NSDictionary.class] ? v : nil;}
static BOOL hashes(NSString *root,NSDictionary *expected){for(NSString *name in expected){if(!relative(name))return NO;NSData *r=readFile(at(root,name),64*1024*1024);if(!r || ![digest(r) isEqual:expected[name]])return NO;}return YES;}
static NSDictionary *files(NSString *root){
    if(!canonical(root))return nil;NSMutableDictionary *out=[NSMutableDictionary new];NSDirectoryEnumerator *e=[[NSFileManager defaultManager] enumeratorAtPath:root];if(!e)return nil;NSString *name;
    while((name=e.nextObject)){
        if(!relative(name) || out.count>4096)return nil;NSString *p=at(root,name);NSDictionary *a=[[NSFileManager defaultManager] attributesOfItemAtPath:p error:NULL];NSString *type=a[NSFileType];
        if(!canonical(p))return nil;if([type isEqual:NSFileTypeDirectory]){out[[name stringByAppendingString:@"/"]]=@"directory";continue;}
        if(![type isEqual:NSFileTypeRegular])return nil;NSData *r=readFile(p,64*1024*1024);if(!r)return nil;out[name]=digest(r);
    }return out;
}
static BOOL sealed(NSString *root,NSSet *expected){
    NSData *raw=readFile(at(root,@"SHA256SUMS"),2*1024*1024);NSString *text=raw ? [[NSString alloc] initWithData:raw encoding:NSUTF8StringEncoding] : nil;
    if(!text || ![text hasSuffix:@"\n"] || ![readFile(at(root,@"COMMITTED"),65) isEqual:[[digest(raw) stringByAppendingString:@"\n"] dataUsingEncoding:NSUTF8StringEncoding]])return NO;
    NSMutableDictionary *seen=[NSMutableDictionary new];NSString *last=@"";for(NSString *line in [[text substringToIndex:text.length-1] componentsSeparatedByString:@"\n"]){
        if(line.length<67 || ![[line substringWithRange:NSMakeRange(64,2)] isEqual:@"  "])return NO;NSString *n=[line substringFromIndex:66],*h=[line substringToIndex:64];
        if(!relative(n) || seen[n] || strcmp(last.UTF8String,n.UTF8String)>=0 || h.length!=64)return NO;NSData *r=readFile(at(root,n),64*1024*1024);if(!r || ![digest(r) isEqual:h])return NO;seen[n]=h;last=n;
    }
    if(![[NSSet setWithArray:seen.allKeys] isEqual:expected])return NO;NSDictionary *actual=files(root);if(!actual)return NO;
    NSMutableSet *allowed=[expected mutableCopy];[allowed addObjectsFromArray:@[@"SHA256SUMS",@"COMMITTED"]];
    for(NSString *name in actual){if([name hasSuffix:@"/"]){BOOL prefix=NO;for(NSString *n in allowed)if([n hasPrefix:name]){prefix=YES;break;}if(!prefix)return NO;}else if(![allowed containsObject:name])return NO;}return YES;
}
static NSData *descriptorBytes(void){return [NSData dataWithBytes:A23VerifiedDescriptor length:sizeof(A23VerifiedDescriptor)];}
static NSDictionary *descriptor(void){return parseDict(descriptorBytes());}
NSDictionary *A23VerifiedEntryDescription(void){return descriptor()[@"description"];}
@interface A23ReadOnlyScopeVerifier ()
- (nullable instancetype)initCommon:(NSString *)build roots:(NSDictionary *)roots model:(BOOL)model;
@end
@implementation A23ReadOnlyScopeVerifier {
    NSString *_build;NSDictionary *_roots,*_scope,*_witness;BOOL _failed,_model;NSUInteger _checks;
}
- (instancetype)initWithArchive:(NSString *)build {if(!canonical(build))return nil;if((self=[super init])){_build=[build copy];_roots=@{};}return self;}
- (instancetype)initWithBuild:(NSString *)build{return [self initCommon:build roots:descriptor()[@"live_roots"] model:NO];}
- (instancetype)initCommon:(NSString *)build roots:(NSDictionary *)roots model:(BOOL)model {
    if(!canonical(build) || ![roots isKindOfClass:NSDictionary.class] || ![[NSSet setWithArray:roots.allKeys] isEqual:[NSSet setWithArray:@[@"repository",@"cards",@"ledger",@"records"]]])return nil;
    for(NSString *p in roots.allValues)if(!canonical(p) || (model && ![p hasPrefix:@"/private/tmp/"]))return nil;
    if((self=[super init])){_build=[build copy];_roots=[roots copy];_model=model;}return self;
}
- (BOOL)archive {
    NSDictionary *d=descriptor();if(![descriptorBytes() isEqual:readFile(at(_build,@"descriptor.json"),2*1024*1024)])return NO;
    NSMutableString *header=[NSMutableString stringWithString:@"static const unsigned char A23VerifiedDescriptor[]={"];NSData *raw=descriptorBytes();const uint8_t *b=raw.bytes;
    for(NSUInteger i=0;i<raw.length;i++)[header appendFormat:@"%s%u",i?",":"",b[i]];[header appendString:@"};\n"];
    if(![[header dataUsingEncoding:NSUTF8StringEncoding] isEqual:readFile(at(_build,@"a23_verified_binding.h"),2*1024*1024)])return NO;
    NSMutableSet *expected=[NSMutableSet setWithArray:@[@"descriptor.json",@"a23_verified_binding.h",@"verified-entry",@"binary.json",@"compile.log",@"build-command.json"]];
    NSDictionary *groups=@{@"source":d[@"source_hashes"],@"baseline":d[@"baseline_files"],@"history":d[@"history_files"],@"recovery-index":d[@"recovery_index"]};
    for(NSString *group in groups){if(!hashes(at(_build,group),groups[group]))return NO;for(NSString *n in groups[group])[expected addObject:[group stringByAppendingFormat:@"/%@",n]];}
    if(!sealed(_build,expected))return NO;
    NSData *binary=readFile(at(_build,@"verified-entry"),64*1024*1024);NSDictionary *record=parseDict(readFile(at(_build,@"binary.json"),16384));
    NSDictionary *wanted=@{@"schema":@"A23-verified-entry-binary-1",@"receiver_sha256":digest(binary),@"descriptor_sha256":digest(descriptorBytes())};
    if(!binary || !equal(record,wanted) || ![encode(record) isEqual:readFile(at(_build,@"binary.json"),16384)])return NO;
    _scope=@{@"schema":@"A23-shared32-scope-1",@"baseline_manifest_sha256":d[@"baseline_manifest_sha256"],@"baseline_inventory_sha256":d[@"baseline_inventory_sha256"],@"workflow_source_sha256":d[@"workflow_source_sha256"],@"build_manifest_sha256":digest(readFile(at(_build,@"SHA256SUMS"),2*1024*1024)),@"receiver_sha256":digest(binary),@"device_binding_sha256":d[@"device_binding_sha256"],@"recipe_sha256":d[@"recipe_sha256"],@"history_sha256":d[@"history_sha256"],@"first_sequence":@81,@"last_sequence":@112,@"formal_issuance_available":@NO,@"acquisition_mode_implemented":@NO,@"hardware_entry_enabled":@NO};return YES;
}
- (BOOL)verifyArchive {if(_failed)return NO;_checks++;if(![self archive])_failed=YES;return !_failed;}
- (BOOL)verifyCore {
    if(_failed)return NO;_checks++;BOOL ok=_roots.count==4 && [self archive];NSDictionary *d=descriptor();
    if(ok)ok=hashes(_roots[@"repository"],d[@"source_hashes"]);
    if(ok){
        NSMutableDictionary *index=[NSMutableDictionary new];NSArray *children=[[NSFileManager defaultManager] contentsOfDirectoryAtPath:_roots[@"cards"] error:NULL];if(!children)ok=NO;
        for(NSString *child in children){NSString *name=[child stringByAppendingString:@"/snapshot.json"],*p=at(_roots[@"cards"],name);if(![[NSFileManager defaultManager] fileExistsAtPath:p])continue;NSData *r=readFile(p,2*1024*1024);if(!r){ok=NO;break;}index[name]=digest(r);}
        ok=ok && equal(index,d[@"recovery_index"]);
    }
    if(ok){NSString *anchor=at(_roots[@"cards"],d[@"baseline_directory"]);ok=sealed(anchor,[NSSet setWithArray:[d[@"baseline_files"] allKeys]]) && hashes(anchor,d[@"baseline_files"]) && [digest(readFile(at(anchor,@"SHA256SUMS"),2*1024*1024)) isEqual:d[@"baseline_manifest_sha256"]];}
    if(ok){
        for(NSString *name in d[@"history_files"]){NSString *root=[name hasPrefix:@"ledger/"]?_roots[@"ledger"]:_roots[@"records"],*relativeName=[name substringFromIndex:[name rangeOfString:@"/"].location+1];NSData *r=readFile(at(root,relativeName),2*1024*1024);if(!r || ![digest(r) isEqual:d[@"history_files"][name]]){ok=NO;break;}}
        NSArray *names=[[NSFileManager defaultManager] contentsOfDirectoryAtPath:_roots[@"ledger"] error:NULL];NSMutableSet *expected=[NSMutableSet new];for(NSString *n in d[@"history_files"])if([n hasPrefix:@"ledger/"])[expected addObject:[n substringFromIndex:7]];ok=ok && names && [[NSSet setWithArray:names] isEqual:expected];
    }
    if(!ok)_failed=YES;return ok;
}
- (BOOL)verifyScope:(NSDictionary *)scope job:(NSString *)job {
    if(![self verifyCore] || !equal(scope,_scope) || !canonical(job)){_failed=YES;return NO;}
    NSString *root=job.stringByDeletingLastPathComponent.stringByDeletingLastPathComponent;
    if(![at(root,@"jobs") isEqual:job.stringByDeletingLastPathComponent] || (_model ? ![root hasPrefix:@"/private/tmp/"] : ![root isEqual:@"/Users/livcm/Documents/Developer/Git/SysDVR-UVC-Capture/research/usb-ds-iso/private/sequence-reservations32"])) {_failed=YES;return NO;}
    NSMutableDictionary *now=[files(root) mutableCopy];if(!now){_failed=YES;return NO;}
    for(NSString *n in @[@"native-process-attempt",@"native-context.json",@"native-process-claim.json",@"native-selection-attempt",@"native-sdk-claim.json"])[now removeObjectForKey:[@"jobs/" stringByAppendingFormat:@"%@/%@",job.lastPathComponent,n]];
    if(!_witness)_witness=[now copy];else if(!equal(now,_witness)){_failed=YES;return NO;}return YES;
}
- (NSDictionary *)scope {return _scope;}
- (NSDictionary *)result {return @{@"schema":@"A23-readonly-scope-verifier-result-1",@"checks":@(_checks),@"failed":@(_failed),@"model_roots":@(_model),@"hardware_entry_enabled":@NO,@"hardware_verified":@NO,@"binary_origin_authenticated":@NO};}
@end
@implementation A23ModelScopeVerifier
- (instancetype)initWithBuild:(NSString *)build repository:(NSString *)repository cards:(NSString *)cards ledger:(NSString *)ledger records:(NSString *)records {
    return [self initCommon:build roots:@{@"repository":repository,@"cards":cards,@"ledger":ledger,@"records":records} model:YES];
}
@end
@implementation A23VerifiedEntryCoordinator {A23TwoEpochEntry *_entry;A23ReadOnlyScopeVerifier *_verifier;A23SharedSequencePermit *_permit;NSDictionary *_scope;NSString *_job;}
- (instancetype)initWithEntry:(A23TwoEpochEntry *)entry verifier:(A23ReadOnlyScopeVerifier *)verifier permit:(A23SharedSequencePermit *)permit scope:(NSDictionary *)scope job:(NSString *)job {if((self=[super init])){_entry=entry;_verifier=verifier;_permit=permit;_scope=[scope copy];_job=[job copy];}return self;}
- (BOOL)inflight {NSDictionary *d=_entry.result[@"driver"];return [d isKindOfClass:NSDictionary.class] && [d[@"iso_attempts"] unsignedIntegerValue]>[d[@"saved_epochs"] unsignedIntegerValue];}
- (BOOL)guard {if(![_verifier verifyScope:_scope job:_job] || [_permit.result[@"stale"] boolValue]){[_entry requestExit];return NO;}return YES;}
- (BOOL)begin {return [self guard] && [_entry begin];}
- (void)tick {if(![self inflight] && ![self guard])return;[_entry tick];if(![self inflight])[self guard];}
- (BOOL)finalizeOnce {if([self inflight] || ![self guard])return NO;BOOL ok=[_entry finalizeOnce];return [self guard] && ok;}
- (NSDictionary *)result {if(![self inflight])[self guard];return _entry.result;}
- (NSDictionary *)finalStatus {if(![self inflight])[self guard];return _entry.finalStatus;}
@end
