#import "a23_archive_read_view.h"
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <dirent.h>

static const NSUInteger NodeLimit=4096,ByteLimit=64*1024*1024;
static BOOL canonical(NSString *path){char *p=realpath(path.fileSystemRepresentation,NULL);BOOL ok=p && [path isEqual:@(p)];free(p);return ok;}
static NSDictionary *identity(const struct stat *s){
    return @{@"device":@((uint64_t)s->st_dev),@"inode":@((uint64_t)s->st_ino),@"mode":@((uint64_t)s->st_mode),
        @"uid":@((uint64_t)s->st_uid),@"gid":@((uint64_t)s->st_gid),@"links":@((uint64_t)s->st_nlink),@"size":@(s->st_size),
        @"mtime_s":@(s->st_mtimespec.tv_sec),@"mtime_ns":@(s->st_mtimespec.tv_nsec),
        @"ctime_s":@(s->st_ctimespec.tv_sec),@"ctime_ns":@(s->st_ctimespec.tv_nsec)};
}
static NSDictionary *node(NSString *path){struct stat s;if(!canonical(path) || lstat(path.fileSystemRepresentation,&s) || (!S_ISREG(s.st_mode) && !S_ISDIR(s.st_mode)))return nil;return identity(&s);}
static NSDictionary *census(NSString *root){
    struct stat s;if(!canonical(root) || lstat(root.fileSystemRepresentation,&s) || !S_ISDIR(s.st_mode))return nil;
    NSMutableDictionary *rows=[NSMutableDictionary dictionaryWithObject:identity(&s) forKey:root];
    NSUInteger bytes=0;NSMutableArray *directories=[NSMutableArray arrayWithObject:root];
    while(directories.count){NSString *directory=directories.lastObject;[directories removeLastObject];DIR *d=opendir(directory.fileSystemRepresentation);if(!d)return nil;BOOL ok=YES;
        for(;;){errno=0;struct dirent *entry=readdir(d);if(!entry){if(errno)ok=NO;break;}
            if(!strcmp(entry->d_name,".") || !strcmp(entry->d_name,".."))continue;
            NSString *name=[[NSString alloc] initWithUTF8String:entry->d_name];if(!name){ok=NO;break;}
            NSString *path=[directory stringByAppendingPathComponent:name];NSDictionary *row=node(path);if(!row || rows.count>=NodeLimit){ok=NO;break;}
            mode_t mode=[row[@"mode"] unsignedShortValue];int64_t size=[row[@"size"] longLongValue];
            if(S_ISREG(mode)){if(size<0 || (uint64_t)size>ByteLimit-bytes){ok=NO;break;}bytes+=(NSUInteger)size;}
            else [directories addObject:path];rows[path]=row;
        }
        if(closedir(d))ok=NO;if(!ok)return nil;
    }
    return [rows copy];
}
@implementation A23ArchiveReadView {
    NSString *_root;NSDictionary *_initial;NSMutableDictionary<NSString *,NSData *> *_cache;
    BOOL _failed,_closed,_validated;NSUInteger _opens,_hits,_bytes,_requests;NSString *_reason,*_path;
}
- (instancetype)initWithRoot:(NSString *)root {
    NSDictionary *tree=census(root);if(!tree)return nil;
    if((self=[super init])){_root=[root copy];_initial=tree;_cache=[NSMutableDictionary new];}return self;
}
- (NSData *)reject:(NSString *)reason {_failed=YES;_reason=reason;[_cache removeAllObjects];return nil;}
- (NSData *)readFile:(NSString *)path maximumBytes:(NSUInteger)limit {
    ++_requests;_path=[path hasPrefix:_root]?[path substringFromIndex:_root.length]:@"outside_root";
    if(_closed || _failed || ![path hasPrefix:[_root stringByAppendingString:@"/"]] || !limit || limit>ByteLimit)return [self reject:@"view_or_path_or_limit"];
    NSDictionary *wanted=_initial[path];mode_t mode=[wanted[@"mode"] unsignedShortValue];int64_t size=[wanted[@"size"] longLongValue];
    if(!wanted)return [self reject:@"not_in_initial_inventory"];
    if(!S_ISREG(mode) || size<0 || (uint64_t)size>limit)return [self reject:@"file_type_or_size"];
    NSData *cached=_cache[path];if(cached){++_hits;return cached;}
    if(![node(path) isEqual:wanted])return [self reject:@"before_read_metadata"];
    int fd=open(path.fileSystemRepresentation,O_RDONLY|O_NOFOLLOW|O_NONBLOCK);if(fd<0)return [self reject:@"open"];++_opens;
    struct stat before,after;BOOL ok=!fstat(fd,&before) && [identity(&before) isEqual:wanted];
    NSMutableData *raw=ok?[NSMutableData dataWithLength:(NSUInteger)size]:nil;NSUInteger at=0;
    while(ok && at<raw.length){ssize_t n=read(fd,(uint8_t *)raw.mutableBytes+at,raw.length-at);if(n<0 && errno==EINTR)continue;if(n<=0){ok=NO;break;}at+=(NSUInteger)n;}
    char extra;if(ok)ok=read(fd,&extra,1)==0 && !fstat(fd,&after) && [identity(&after) isEqual:wanted];
    if(close(fd))ok=NO;if(!ok || ![node(path) isEqual:wanted] || raw.length>ByteLimit-_bytes)return [self reject:@"read_or_after_metadata_or_budget"];
    NSData *copy=[raw copy];_cache[path]=copy;_bytes+=copy.length;return copy;
}
- (BOOL)validateUnchanged {
    if(_closed)return NO;
    _closed=YES;BOOL ok=!_failed && [census(_root) isEqual:_initial];_validated=ok;_failed=!ok;[_cache removeAllObjects];return ok;
}
- (NSDictionary *)metrics {
    return @{@"schema":@"A23-archive-read-view-metrics-1",@"requests":@(_requests),@"opened_files":@(_opens),@"cache_hits":@(_hits),@"bytes_loaded":@(_bytes),
        @"closed":@(_closed),@"failed":@(_failed),@"validated_unchanged":@(_validated),@"cached_files":@(_cache.count),@"rejection":_reason?:@"",@"last_path":_path?:@"",
        @"atomic_snapshot_verified":@NO,@"future_freshness_verified":@NO,@"cross_check_cache":@NO};
}
@end
