"""One-call archive byte reuse; isolated derivation, no acquisition entry."""
from pathlib import Path
import build_a23_live91_checked as parent
w=parent.w
PARENT=w.A/'A23-live91-critical-path-closeout-20261023'
NEW=('host/a23_archive_read_view.h','host/a23_archive_read_view.m',
     'tools/a23_archive_read_view.py','tools/audit_a23_archive_read_view.py')

def sources():
    w.card.seal_verify(PARENT)
    old=parent.sources();w.require(old==w.load(PARENT/'source-hashes.json') and len(old)==611,'original611 drift')
    return dict(sorted(dict(old,**{'research/usb-ds-iso/'+n:parent.sha(w.plain(w.ROOT/n)) for n in NEW}).items()))

def render(raw):
    one=parent.one
    # Keep the complete ordinary functions for all live inputs. Only archive's
    # derived helper copies see a view scoped to that single method invocation.
    start=raw.index('static BOOL hashes(');end=raw.index('static NSData *descriptorBytes',start)
    helpers=raw[start:end]
    helpers=helpers.replace('static BOOL hashes(NSString *root,NSDictionary *expected)', 'static BOOL viewHashes(NSString *root,NSDictionary *expected,A23ArchiveReader reader)')
    helpers=helpers.replace('static NSDictionary *files(NSString *root)', 'static NSDictionary *viewFiles(NSString *root,A23ArchiveReader reader)')
    helpers=helpers.replace('static BOOL sealed(NSString *root,NSSet *expected)', 'static BOOL viewSealed(NSString *root,NSSet *expected,A23ArchiveReader reader)')
    helpers=helpers.replace('readFile(', 'reader(').replace('files(root)','viewFiles(root,reader)')
    raw=raw[:end]+'typedef NSData *(^A23ArchiveReader)(NSString *,NSUInteger);\n'+helpers+raw[end:]
    raw='#import "a23_archive_read_view.h"\n'+raw
    raw=one(raw,'NSUInteger _checks,_liveJobChecks;', 'NSDictionary *_archiveReadMetrics;NSUInteger _checks,_liveJobChecks;')
    start=raw.index('- (BOOL)archive {');end=raw.index('- (BOOL)verifyArchive',start)
    method=raw[start:end].replace('- (BOOL)archive {','- (BOOL)archiveUsingReader:(A23ArchiveReader)reader {')
    method=method.replace('readFile(', 'reader(')
    method=one(method,'hashes(at(_build,group),groups[group])','viewHashes(at(_build,group),groups[group],reader)')
    method=one(method,'sealed(_build,expected)','viewSealed(_build,expected,reader)')
    wrapper='''- (BOOL)archive {
    A23ArchiveReadView *view=[[A23ArchiveReadView alloc] initWithRoot:_build];if(!view)return NO;
    BOOL ok=[self archiveUsingReader:^NSData *(NSString *path,NSUInteger limit){return [view readFile:path maximumBytes:limit];}];
    BOOL unchanged=[view validateUnchanged];_archiveReadMetrics=view.metrics;return ok && unchanged;
}
'''
    raw=raw[:start]+method+wrapper+raw[end:]
    raw=one(raw,'@"clock_domain":@"host_CLOCK_MONOTONIC_RAW",','@"archive_read_view":_archiveReadMetrics?:@{},@"clock_domain":@"host_CLOCK_MONOTONIC_RAW",')
    return raw
