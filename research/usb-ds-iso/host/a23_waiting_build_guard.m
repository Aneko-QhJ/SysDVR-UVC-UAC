#import "a23_waiting_receiver.h"
#include "a23_waiting_build_binding.h" // generated frozen JSON bytes, no runtime IO
#include <CommonCrypto/CommonDigest.h>
#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static id fail(NSError **e,NSString *reason)
{if(e)*e=[NSError errorWithDomain:@"A23WaitingBuild" code:1 userInfo:@{NSLocalizedDescriptionKey:reason}];return nil;}
static BOOL equal(id a,id b)
{
    if([b isKindOfClass:NSDictionary.class]){
        if(![a isKindOfClass:NSDictionary.class] || ![[NSSet setWithArray:[a allKeys]] isEqual:[NSSet setWithArray:[b allKeys]]])return NO;
        for(id k in b)if(!equal(a[k],b[k]))return NO;return YES;
    }
    if([b isKindOfClass:NSNumber.class]){
        if(![a isKindOfClass:NSNumber.class])return NO;
        BOOL ab=CFGetTypeID((__bridge CFTypeRef)a)==CFBooleanGetTypeID(),bb=CFGetTypeID((__bridge CFTypeRef)b)==CFBooleanGetTypeID();
        return ab==bb && (ab || !CFNumberIsFloatType((__bridge CFNumberRef)a)) && [a isEqual:b];
    }
    return [a isKindOfClass:NSString.class] && [b isKindOfClass:NSString.class] && [a isEqual:b];
}
static NSString *sha(NSData *raw)
{
    unsigned char bytes[CC_SHA256_DIGEST_LENGTH];CC_SHA256(raw.bytes,(CC_LONG)raw.length,bytes);
    NSMutableString *s=[NSMutableString string];for(unsigned i=0;i<sizeof(bytes);++i)[s appendFormat:@"%02x",bytes[i]];return s;
}
static BOOL hex(NSString *s)
{return [s isKindOfClass:NSString.class] && s.length==64 && [s rangeOfCharacterFromSet:[[NSCharacterSet characterSetWithCharactersInString:@"0123456789abcdef"] invertedSet]].location==NSNotFound;}
static BOOL canonical(NSString *p)
{char *r=realpath(p.fileSystemRepresentation,NULL);BOOL ok=r && [p isEqual:@(r)];free(r);return ok;}
static BOOL relative(NSString *p)
{
    if(![p isKindOfClass:NSString.class] || !p.length || p.isAbsolutePath || [p containsString:@"\n"] || [p containsString:@"\r"] || strlen(p.UTF8String)!=[p lengthOfBytesUsingEncoding:NSUTF8StringEncoding])return NO;
    for(NSString *part in [p componentsSeparatedByString:@"/"])if(!part.length || [part isEqual:@"."] || [part isEqual:@".."])return NO;
    return YES;
}
static NSData *readFile(NSString *p,NSUInteger max)
{
    if(!canonical(p))return nil;
    int fd=open(p.fileSystemRepresentation,O_RDONLY|O_NOFOLLOW|O_NONBLOCK);struct stat st;if(fd<0)return nil;
    if(fstat(fd,&st) || !S_ISREG(st.st_mode) || st.st_size<0 || (uint64_t)st.st_size>max){close(fd);return nil;}
    NSMutableData *raw=[NSMutableData dataWithLength:(NSUInteger)st.st_size];NSUInteger n=0;
    while(n<raw.length){ssize_t r=read(fd,(uint8_t *)raw.mutableBytes+n,raw.length-n);if(r<0 && errno==EINTR)continue;
        if(r<=0){close(fd);return nil;}n+=(NSUInteger)r;}
    char extra;BOOL ok=read(fd,&extra,1)==0;close(fd);return ok ? raw : nil;
}
static NSData *encodePart(id value)
{
    if([value isKindOfClass:NSDictionary.class]){
        // Foundation SortedKeys orders filename punctuation differently from
        // Python. Sort UTF-8 keys explicitly; scalar escaping stays with JSON.
        NSArray *keys=[[value allKeys] sortedArrayUsingComparator:^NSComparisonResult(NSString *a,NSString *b){
            int n=strcmp(a.UTF8String,b.UTF8String);return n<0?NSOrderedAscending:n>0?NSOrderedDescending:NSOrderedSame;
        }];
        NSMutableData *raw=[NSMutableData dataWithBytes:"{" length:1];BOOL first=YES;
        for(NSString *key in keys){
            if(strlen(key.UTF8String)!=[key lengthOfBytesUsingEncoding:NSUTF8StringEncoding])return nil;
            NSData *k=encodePart(key),*v=encodePart(value[key]);if(!k || !v)return nil;
            if(!first)[raw appendBytes:"," length:1];first=NO;[raw appendData:k];[raw appendBytes:":" length:1];[raw appendData:v];
        }[raw appendBytes:"}" length:1];return raw;
    }
    if([value isKindOfClass:NSArray.class]){
        NSMutableData *raw=[NSMutableData dataWithBytes:"[" length:1];BOOL first=YES;
        for(id item in value){NSData *v=encodePart(item);if(!v)return nil;if(!first)[raw appendBytes:"," length:1];first=NO;[raw appendData:v];}
        [raw appendBytes:"]" length:1];return raw;
    }
    return [NSJSONSerialization dataWithJSONObject:value options:NSJSONWritingFragmentsAllowed|NSJSONWritingWithoutEscapingSlashes error:NULL];
}
static NSData *encode(id value)
{
    NSMutableData *raw=[encodePart(value) mutableCopy];if(raw)[raw appendBytes:"\n" length:1];return raw;
}
static id parse(NSData *raw)
{
    id value=raw ? [NSJSONSerialization JSONObjectWithData:raw options:0 error:NULL] : nil;
    return value && [encode(value) isEqual:raw] ? value : nil; // rejects duplicate/noncanonical JSON
}
static BOOL sourceCheck(NSDictionary *binding,NSString *build)
{
    NSString *root=binding[@"source_root"];NSDictionary *hashes=binding[@"source_hashes"];
    if(!canonical(root) || ![hashes isKindOfClass:NSDictionary.class] || !hashes.count || hashes.count>200)return NO;
    for(NSString *name in hashes){
        if(!relative(name) || !hex(hashes[name]))return NO;
        NSData *live=readFile([root stringByAppendingPathComponent:name],2*1024*1024);
        NSData *frozen=readFile([[build stringByAppendingPathComponent:@"source"] stringByAppendingPathComponent:name],2*1024*1024);
        if(!live || !frozen || ![sha(live) isEqual:hashes[name]] || ![sha(frozen) isEqual:hashes[name]])return NO;
    }return YES;
}
NSDictionary *A23CheckWaitingBuild(NSString *build,NSString *binary,NSError **error)
{
    if(!canonical(build) || !canonical(binary) || ![binary isEqual:[build stringByAppendingPathComponent:@"receiver"]])return fail(error,@"receiver/build path mismatch; no device accessed");
    NSData *bindingRaw=[NSData dataWithBytes:A23WaitingBuildBinding length:sizeof(A23WaitingBuildBinding)];
    NSDictionary *binding=parse(bindingRaw),*meta=parse(readFile([build stringByAppendingPathComponent:@"manifest.json"],131072));
    if(!binding || !equal(meta,binding) || !equal(meta[@"description"],A23WaitingReceiverDescription()) ||
        ![readFile([build stringByAppendingPathComponent:@"describe.json"],16384) isEqual:encode(A23WaitingReceiverDescription())])return fail(error,@"embedded build binding mismatch; no device accessed");
    NSData *sums=readFile([build stringByAppendingPathComponent:@"SHA256SUMS"],1024*1024);
    NSString *digest=sums ? sha(sums) : nil;
    if(!digest || ![readFile([build stringByAppendingPathComponent:@"COMMITTED"],65) isEqual:[[digest stringByAppendingString:@"\n"] dataUsingEncoding:NSUTF8StringEncoding]])return fail(error,@"uncommitted build; no device accessed");
    NSString *text=[[NSString alloc] initWithData:sums encoding:NSUTF8StringEncoding];
    NSMutableArray *names=[NSMutableArray array];
    if(!text.length || ![text hasSuffix:@"\n"])return fail(error,@"invalid manifest encoding");
    for(NSString *line in [[text substringToIndex:text.length-1] componentsSeparatedByString:@"\n"]){
        if(line.length<67 || ![[line substringWithRange:NSMakeRange(64,2)] isEqual:@"  "])return fail(error,@"invalid manifest row");
        NSString *h=[line substringToIndex:64],*name=[line substringFromIndex:66];
        if(!hex(h) || !relative(name) || [names containsObject:name])return fail(error,@"invalid manifest path/hash");
        NSData *raw=readFile([build stringByAppendingPathComponent:name],32*1024*1024);
        if(!raw || ![sha(raw) isEqual:h])return fail(error,@"changed build file; no device accessed");[names addObject:name];
    }
    NSMutableSet *expected=[NSMutableSet setWithArray:@[@"manifest.json",@"describe.json",@"build-command.json",@"build.log",@"receiver",@"a23_waiting_build_binding.h"]];
    for(NSString *name in binding[@"source_hashes"])[expected addObject:[@"source/" stringByAppendingString:name]];
    if(names.count>256 || ![[NSSet setWithArray:names] isEqual:expected] || ![names isEqual:[names sortedArrayUsingSelector:@selector(compare:)]])return fail(error,@"build inventory mismatch");
    NSMutableSet *actual=[NSMutableSet set];NSDirectoryEnumerator *iterator=[[NSFileManager defaultManager] enumeratorAtPath:build];
    NSUInteger entries=0;
    for(NSString *name in iterator){
        if(++entries>512 || !relative(name))return fail(error,@"invalid build tree");
        NSDictionary *a=[[NSFileManager defaultManager] attributesOfItemAtPath:[build stringByAppendingPathComponent:name] error:NULL];
        if([a[NSFileType] isEqual:NSFileTypeDirectory])continue;
        if(![a[NSFileType] isEqual:NSFileTypeRegular])return fail(error,@"nonregular build entry");
        if(![name isEqual:@"SHA256SUMS"] && ![name isEqual:@"COMMITTED"])[actual addObject:name];
    }
    if(![actual isEqual:expected] || !sourceCheck(binding,build) || !sourceCheck(binding,build) ||
        ![sums isEqual:readFile([build stringByAppendingPathComponent:@"SHA256SUMS"],1024*1024)])return fail(error,@"current/frozen source drift; no device accessed");
    NSData *program=readFile(binary,32*1024*1024);if(!program)return fail(error,@"receiver disappeared during check");
    return @{@"build_manifest_sha256":digest,@"recipe_sha256":binding[@"recipe_sha256"],@"receiver_sha256":sha(program),@"source_closure_checked":@YES};
}
NSDictionary *A23CheckWaitingConsumed(NSString *run,NSString *build,NSString *binary,NSError **error)
{
    NSDictionary *checked=A23CheckWaitingBuild(build,binary,error);if(!checked)return nil;
    if(!canonical(run))return fail(error,@"invalid run directory");
    NSData *raw=readFile([run stringByAppendingPathComponent:@"waiting-authorization.json"],16384);NSDictionary *receipt=parse(raw);
    if(![receipt isKindOfClass:NSDictionary.class])return fail(error,@"missing waiting consumed receipt; no device accessed");
    NSDictionary *expected=@{@"schema":@"A23-waiting-burst-consumed-receipt-1",@"backend":@"a23-waiting-burst-1",@"attempt_consumed":@YES,
        @"receiver_sha256":checked[@"receiver_sha256"],@"build_manifest_sha256":checked[@"build_manifest_sha256"],@"recipe_sha256":checked[@"recipe_sha256"],
        @"plan":A23WaitingBurstPlan(),@"preparation_id":receipt[@"preparation_id"] ?: @""};
    if(!equal(receipt,expected) || ![receipt[@"preparation_id"] isKindOfClass:NSString.class] || ![[NSUUID alloc] initWithUUIDString:receipt[@"preparation_id"]])return fail(error,@"changed waiting consumed receipt; no device accessed");
    NSMutableDictionary *result=[checked mutableCopy];result[@"receipt_sha256"]=sha(raw);return result;
}
BOOL A23ClaimWaitingProcess(NSString *run,NSDictionary *checked)
{return A23SaveBurstEntryResult(run,@"WAIT_PROCESS_CLAIMED",@{@"schema":@"A23-waiting-process-claim-1",@"checked":checked});}

@interface A23WaitingBoundPermit : NSObject <A23WaitingPermit>
@property NSString *run,*build,*binary;
@property NSDictionary *checked;
@property BOOL attempted;
@end
@implementation A23WaitingBoundPermit
- (BOOL)claimForIdentity:(A23WaitIdentity)identity error:(NSError **)error
{
    if(_attempted){fail(error,@"bound permit already attempted");return NO;}_attempted=YES;
    NSDictionary *now=A23CheckWaitingConsumed(_run,_build,_binary,error);
    // Existing exclusive-result writer emits JSON without a trailing newline.
    NSMutableData *processLine=[readFile([_run stringByAppendingPathComponent:@"WAIT_PROCESS_CLAIMED"],16384) mutableCopy];
    [processLine appendBytes:"\n" length:1];NSDictionary *process=parse(processLine);
    NSDictionary *expected=@{@"schema":@"A23-waiting-process-claim-1",@"checked":_checked};
    if(!now || !equal(now,_checked) || !equal(process,expected)){fail(error,@"changed handoff build/receipt/process claim");return NO;}
    A23WaitingReceiptPermit *permit=[[A23WaitingReceiptPermit alloc] initWithDirectory:_run binary:_binary
        buildManifest:_checked[@"build_manifest_sha256"] recipe:_checked[@"recipe_sha256"]];
    if(!permit || ![permit claimForIdentity:identity error:error])return NO;
    if(!equal(A23CheckWaitingConsumed(_run,_build,_binary,error),_checked)){
        fail(error,@"handoff inputs changed after claim; no SDK opened, no retry");return NO;}
    return YES;
}
@end
id<A23WaitingPermit> A23MakeWaitingBoundPermit(NSString *run,NSString *build,NSString *binary,NSDictionary *checked)
{
    A23WaitingBoundPermit *p=[A23WaitingBoundPermit new];p.run=[run copy];p.build=[build copy];p.binary=[binary copy];p.checked=[checked copy];return p;
}
