#import "a23_two_epoch_entry.h"
#include "a23_two_epoch_entry_binding.h"
#include <CommonCrypto/CommonDigest.h>
#include <errno.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
static NSString *sha(NSData *raw){unsigned char h[32];CC_SHA256(raw.bytes,(CC_LONG)raw.length,h);NSMutableString *s=[NSMutableString new];for(unsigned i=0;i<32;i++)[s appendFormat:@"%02x",h[i]];return s;}
static BOOL canonical(NSString *p){char *q=realpath(p.fileSystemRepresentation,NULL);BOOL ok=q && [p isEqual:@(q)];free(q);return ok;}
static NSData *readFile(NSString *p,NSUInteger limit){
    if(!canonical(p))return nil;int fd=open(p.fileSystemRepresentation,O_RDONLY|O_NOFOLLOW|O_NONBLOCK);if(fd<0)return nil;struct stat st;
    if(fstat(fd,&st) || !S_ISREG(st.st_mode) || st.st_size<0 || (uint64_t)st.st_size>limit){close(fd);return nil;}
    NSMutableData *d=[NSMutableData dataWithLength:(NSUInteger)st.st_size];NSUInteger at=0;
    while(at<d.length){ssize_t n=read(fd,(uint8_t *)d.mutableBytes+at,d.length-at);if(n<0 && errno==EINTR)continue;if(n<=0){close(fd);return nil;}at+=(NSUInteger)n;}
    char extra;BOOL ok=read(fd,&extra,1)==0;if(close(fd))ok=NO;return ok ? d : nil;
}
static NSDictionary *meta(void){NSData *d=[NSData dataWithBytes:A23EntryMetadata length:sizeof(A23EntryMetadata)];id m=[NSJSONSerialization JSONObjectWithData:d options:0 error:NULL];return [m isKindOfClass:NSDictionary.class] ? m : nil;}
NSDictionary *A23TwoEpochEntryDescription(void){return meta()[@"description"];}
NSDictionary *A23TwoEpochEntryCheckBuild(NSString *build,NSString *binary){
    if(!canonical(build) || !canonical(binary) || ![binary isEqual:[build stringByAppendingPathComponent:@"entry-inspector"]])return nil;
    NSData *raw=[NSData dataWithBytes:A23EntryMetadata length:sizeof(A23EntryMetadata)];if(![raw isEqual:readFile([build stringByAppendingPathComponent:@"manifest.json"],1024*1024)])return nil;
    NSMutableString *header=[NSMutableString stringWithString:@"static const unsigned char A23EntryMetadata[]={"];const uint8_t *bytes=raw.bytes;for(NSUInteger i=0;i<raw.length;++i)[header appendFormat:@"%s%u",i ? "," : "",bytes[i]];[header appendString:@"};\n"];
    if(![[header dataUsingEncoding:NSUTF8StringEncoding] isEqual:readFile([build stringByAppendingPathComponent:@"a23_two_epoch_entry_binding.h"],1024*1024)])return nil;
    NSDictionary *m=meta(),*hashes=m[@"source_hashes"];if(![hashes isKindOfClass:NSDictionary.class] || hashes.count<336)return nil;
    for(NSString *name in hashes){
        if(name.isAbsolutePath || [name containsString:@".."] || [name containsString:@"\n"])return nil;
        NSData *d=readFile([[build stringByAppendingPathComponent:@"source"] stringByAppendingPathComponent:name],2*1024*1024);if(!d || ![sha(d) isEqual:hashes[name]])return nil;
    }
    NSData *record=readFile([build stringByAppendingPathComponent:@"binary.json"],16384),*executable=readFile(binary,64*1024*1024);if(!record || !executable)return nil;
    NSDictionary *b=[NSJSONSerialization JSONObjectWithData:record options:0 error:NULL];
    if(![b isKindOfClass:NSDictionary.class])return nil;
    NSMutableData *canonicalRecord=[[NSJSONSerialization dataWithJSONObject:b ?: @{} options:NSJSONWritingSortedKeys error:NULL] mutableCopy];[canonicalRecord appendBytes:"\n" length:1];
    if(![record isEqual:canonicalRecord] || b.count!=3 || ![b isKindOfClass:NSDictionary.class] || ![b[@"schema"] isEqual:@"A23-two-epoch-entry-binary-1"] || ![b[@"receiver_sha256"] isEqual:sha(executable)] || ![b[@"metadata_sha256"] isEqual:sha(raw)])return nil;
    return @{@"schema":@"A23-two-epoch-entry-build-check-1",@"metadata_sha256":sha(raw),@"receiver_sha256":sha(executable),@"source_count":@(hashes.count),@"frozen_source_consistent":@YES,@"hardware_entry_enabled":@NO,@"formal_issuance_available":@NO,@"binary_origin_authenticated":@NO};
}
