"""Bounded file-only native audit for one-call archive read reuse."""
import argparse,json,shutil,subprocess,tempfile
from pathlib import Path
import a23_archive_read_view as candidate
import audit_a23_live91_checked as old
b=candidate.parent;w=candidate.w
CASES=('normal','mid-persistent','mid-restored','mid-extra','after-inventory','mid-replaced',
       'late-after-validation','between-source','between-baseline','between-index','between-history',
       'between-job','pre-symlink','pre-empty-directory','pre-content','reader-contract')

PRELUDE='''
static NSDictionary *fixture;static BOOL changed;static NSUInteger ordinaryReads;
static void mutate(NSString *path,BOOL restore,BOOL atomic){
    assert([path hasPrefix:@"/private/tmp/"]);NSData *before=[NSData dataWithContentsOfFile:path];assert(before.length);
    NSMutableData *raw=[before mutableCopy];((uint8_t *)raw.mutableBytes)[raw.length-1]^=1;
    assert([raw writeToFile:path atomically:atomic]);if(restore)assert([before writeToFile:path atomically:NO]);
}
static void passHook(NSString *stage){
    NSString *name=fixture[@"case"];if(changed)return;
    BOOL groups=[stage isEqual:@"groups"],inventory=[stage isEqual:@"inventory"],late=[stage isEqual:@"after_validation"];
    if(groups && [@[@"mid-persistent",@"mid-restored",@"mid-replaced"] containsObject:name]){
        changed=YES;mutate(fixture[@"archive_target"],[name isEqual:@"mid-restored"],[name isEqual:@"mid-replaced"]);
        if([name isEqual:@"mid-replaced"]){NSData *original=[NSData dataWithContentsOfFile:fixture[@"original_target"]];assert([original writeToFile:fixture[@"archive_target"] atomically:YES]);}
    }else if(groups && [name isEqual:@"mid-extra"]){changed=YES;assert([[@"extra" dataUsingEncoding:NSUTF8StringEncoding] writeToFile:[fixture[@"build"] stringByAppendingPathComponent:@"extra"] atomically:NO]);}
    else if(inventory && [name isEqual:@"after-inventory"]){changed=YES;mutate(fixture[@"archive_target"],NO,NO);}
    else if(late && [name isEqual:@"late-after-validation"]){changed=YES;mutate(fixture[@"archive_target"],NO,NO);}
}
'''

MAIN='''
int main(int argc,const char *argv[]){@autoreleasepool {assert(argc==2);
fixture=[NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:@(argv[1])] options:0 error:NULL];assert(fixture);
NSString *root=fixture[@"root"],*name=fixture[@"case"];
if([name isEqual:@"reader-contract"]){
    NSString *tiny=[root stringByAppendingPathComponent:@"tiny"];assert([[NSFileManager defaultManager] createDirectoryAtPath:tiny withIntermediateDirectories:NO attributes:nil error:NULL]);
    NSString *file=[tiny stringByAppendingPathComponent:@"data"];assert([[@"abc" dataUsingEncoding:NSUTF8StringEncoding] writeToFile:file atomically:NO]);
    A23ArchiveReadView *v=[[A23ArchiveReadView alloc] initWithRoot:tiny];assert(v && [v readFile:file maximumBytes:3] && [v readFile:file maximumBytes:3]);
    assert([v.metrics[@"opened_files"] intValue]==1 && [v.metrics[@"cache_hits"] intValue]==1);
    assert([v validateUnchanged] && [v.metrics[@"cached_files"] intValue]==0 && ![v validateUnchanged] && ![v readFile:file maximumBytes:3]);
    A23ArchiveReadView *small=[[A23ArchiveReadView alloc] initWithRoot:tiny];assert(small && ![small readFile:file maximumBytes:2] && ![small validateUnchanged]);
    A23ArchiveReadView *fresh=[[A23ArchiveReadView alloc] initWithRoot:tiny];assert([fresh readFile:file maximumBytes:3]);mutate(file,NO,NO);assert(![fresh validateUnchanged]);
    NSString *huge=[tiny stringByAppendingPathComponent:@"huge"];int fd=open(huge.fileSystemRepresentation,O_CREAT|O_EXCL|O_WRONLY,0600);assert(fd>=0 && !ftruncate(fd,64*1024*1024+1) && !close(fd));assert(![[A23ArchiveReadView alloc] initWithRoot:tiny]);
    puts("{\\"contract_passed\\":true}");return 0;
}
A23ReadOnlyScopeVerifier *v=[[A23ModelScopeVerifier alloc] initWithBuild:fixture[@"build"] repository:[root stringByAppendingPathComponent:@"repository"] cards:[root stringByAppendingPathComponent:@"cards"] ledger:[root stringByAppendingPathComponent:@"ledger"] records:[root stringByAppendingPathComponent:@"records"]];assert(v);
NSMutableArray *runs=[NSMutableArray new];NSUInteger count=[name isEqual:@"normal"]?3:2;
for(NSUInteger n=0;n<count;n++){
    NSUInteger before=ordinaryReads;BOOL ok=[v verifyCore];NSMutableDictionary *row=[@{@"accepted":@(ok),@"ordinary_read_file_calls":@(ordinaryReads-before),@"cadence":v.cadenceMetrics} mutableCopy];
    if([name isEqual:@"between-job"]){BOOL job=[v verifyLiveJob:v.scope job:fixture[@"job"]];row[@"job_accepted"]=@(job);}
    [runs addObject:row];
    if(!n && [name hasPrefix:@"between-"]){assert(ok);mutate(fixture[@"between_target"],NO,NO);}
}
NSData *raw=[NSJSONSerialization dataWithJSONObject:@{@"case":name,@"runs":runs,@"changed_hook":@(changed),@"usb_requests":@0,@"real_sdk_objects":@0} options:0 error:NULL];fwrite(raw.bytes,1,raw.length,stdout);puts("");return 0;
}}
'''

def fixture_scope(raw,optimized):
    raw=raw[:raw.index('@implementation A23VerifiedEntryCoordinator')]
    if optimized:raw=candidate.render(raw)
    raw=b.one(raw,'static NSString *digest(NSData *r)',PRELUDE+'\nstatic NSString *digest(NSData *r)')
    raw=b.one(raw,'static NSData *readFile(NSString *p,NSUInteger limit){','static NSData *readFile(NSString *p,NSUInteger limit){++ordinaryReads;')
    check='if(!viewSealed(_build,expected,reader))return NO;' if optimized else 'if(!sealed(_build,expected))return NO;'
    raw=b.one(raw,check,'passHook(@"groups");'+check+'passHook(@"inventory");')
    if optimized:raw=b.one(raw,'BOOL unchanged=[view validateUnchanged];','BOOL unchanged=[view validateUnchanged];passHook(@"after_validation");')
    else:
        start=raw.index('- (BOOL)archive {');end=raw.index('- (BOOL)verifyArchive',start)
        method=b.one(raw[start:end],'return YES;','passHook(@"after_validation");return YES;');raw=raw[:start]+method+raw[end:]
    return '#include <assert.h>\n#import "a23_archive_read_view.h"\n'+raw+MAIN

def run(out):
    out=w.canonical(out);w.require(not out.exists(),'new native audit required');hashes=candidate.sources()
    parent=w.A/'A23-live91-critical-path-closeout-20261023';actual=w.A/'A23-live91-checked-once-20261022-r1.json';before=w.plain(actual)
    w.require(before==w.plain(parent/'once-record-unchanged.json'),'actual145 drift')
    build=w.A/'A23-live91-checked-review-20261022-r2/build';b.verify(build,current=False)
    out.mkdir(mode=0o700);w.write(out/'source-hashes.json',hashes)
    for n in candidate.NEW:w.card.put(out,'candidate-source/'+n,w.plain(w.ROOT/n))
    completed=[];processes=[]
    try:
        with tempfile.TemporaryDirectory(prefix='a23-archive-view-',dir='/private/tmp') as temporary:
            scratch=Path(temporary);template=scratch/'template';old.template(build,template);executables={}
            for label,optimized in [('control',False),('candidate',True)]:
                source=out/(label+'.m');source.write_text(fixture_scope(w.plain(build/'generated/live_scope.m').decode(),optimized))
                executable=scratch/label;command=['clang','-O2','-fobjc-arc','-fblocks','-Wall','-Wextra','-Werror','-I'+str(build),'-I'+str(build/'source/research/usb-ds-iso/host'),'-I'+str(w.ROOT/'host'),'-framework','Foundation',str(source),str(w.ROOT/'host/a23_archive_read_view.m'),'-o',str(executable)]
                p=subprocess.run(command,capture_output=True,timeout=60);w.card.put(out,label+'-compile.log',p.stdout+p.stderr);w.write(out/(label+'-compile.json'),dict(command=command,returncode=p.returncode,creator_wait_verified=True));w.require(p.returncode==0,label+' compilation failed')
                w.card.put(out,label+'-executable',executable.read_bytes());executables[label]=executable
                libs=subprocess.run(['otool','-L',str(executable)],capture_output=True,timeout=10);w.require(libs.returncode==0 and b'IOUSBHost' not in libs.stdout and b'IOKit.framework' not in libs.stdout,'USB linkage');w.card.put(out,label+'-libraries.txt',libs.stdout)
            results={}
            for name in CASES:
                results[name]={}
                labels=['candidate'] if name.startswith('between-') or name=='reader-contract' else ['control','candidate']
                for label in labels:
                    case=out/'cases'/(name+'-'+label);case.mkdir(parents=True);current=scratch/'current';current_build=scratch/'current-build';shutil.copytree(template,current);shutil.copytree(build,current_build)
                    source='research/usb-ds-iso/tools/a23_live91_checked_workflow.py';target=current_build/'source'/source
                    between=None;job=None
                    if name=='between-source':between=current/'repository'/source
                    if name=='between-baseline':between=current/'cards'/b.ANCHOR.name/'card/logfile.txt'
                    if name=='between-index':between=next(x for x in sorted((current/'cards').glob('*/snapshot.json')) if x.parent.name!=b.ANCHOR.name)
                    if name=='between-history':between=next(x for x in sorted((current/'ledger').iterdir()) if x.is_file() and x.name!='.lock')
                    if name=='between-job':
                        copied=current/'namespace145';shutil.copytree(b.FORMAL_ROOT,copied);job=next((copied/'jobs').iterdir());between=copied/'block-00145.json'
                    config=dict(case=name,root=str(current),build=str(current_build),archive_target=str(target),original_target=str(build/'source'/source),between_target=str(between) if between else None,job=str(job) if job else None)
                    if name=='pre-symlink':target.unlink();target.symlink_to(build/'source'/source)
                    if name=='pre-empty-directory':(current_build/'extra-empty').mkdir()
                    if name=='pre-content':target.write_bytes(b'bad\n')
                    w.write(case/'config.json',config);p=subprocess.run([str(executables[label]),str(case/'config.json')],capture_output=True,timeout=30)
                    process=dict(case=name,variant=label,returncode=p.returncode,creator_wait_verified=True);processes.append(process);w.write(case/'process.json',process);w.card.put(case,'native.stdout',p.stdout);w.card.put(case,'native.stderr',p.stderr)
                    w.require(p.returncode==0 and not p.stderr,'native failure '+name+'/'+label);row=json.loads(p.stdout);results[name][label]=row
                    if name=='reader-contract':w.require(row['contract_passed'] is True,'reader contract failed')
                    else:
                        accepted=[x['accepted'] for x in row['runs']]
                        if name=='normal':expected=[True]*3
                        elif name.startswith('between-'):expected=[True,True] if name=='between-job' else [True,False]
                        elif name in ['mid-restored','mid-replaced','after-inventory']:expected=[True,True] if label=='control' and name!='after-inventory' else ([True,False] if label=='control' else [False,False])
                        elif name=='late-after-validation':expected=[True,False]
                        else:expected=[False,False]
                        w.require(accepted==expected,'unexpected accept pattern '+name+'/'+label+' '+str(accepted))
                        if name=='between-job':w.require([x['job_accepted'] for x in row['runs']]==[True,False],'live job witness stale')
                        if name=='normal' and label=='candidate':
                            metrics=[x['cadence']['archive_read_view'] for x in row['runs']]
                            w.require(all(x['closed'] and x['validated_unchanged'] and x['cached_files']==0 and not x['cross_check_cache'] for x in metrics),'cache lifetime differs')
                            w.require(len(set(x['opened_files'] for x in metrics))==1 and metrics[0]['cache_hits']>0,'view not reread per check')
                    w.card.put(case,'archive-target-after',target.read_bytes())
                    if between:w.card.put(case,'between-target-after',between.read_bytes())
                    shutil.rmtree(current);shutil.rmtree(current_build);completed.append(name+'/'+label)
        w.require(candidate.sources()==hashes and w.plain(actual)==before,'source/actual drift')
        for name,h in w.load(parent/'protected-hashes.json').items():w.require(b.sha(w.plain(Path(name)))==h,'protected drift')
        for name,root in [('namespace81',b.base.PREDECESSOR),('namespace113',b.base.FORMAL_ROOT),('namespace145',b.FORMAL_ROOT)]:
            w.require({x.relative_to(root).as_posix():b.sha(w.plain(x)) for x in root.rglob('*') if x.is_file()}==w.load(parent/(name+'-hashes.json')),'namespace drift')
        b.spent113()
        normal={name:[dict(elapsed_ns=row['cadence']['full_checks'][-1]['elapsed_ns'],ordinary_reads=row['ordinary_read_file_calls'],view=row['cadence'].get('archive_read_view')) for row in results['normal'][name]['runs']] for name in ('control','candidate')}
        w.write(out/'report.json',dict(schema='A23-archive-read-view-audit-1',passed=True,created_at=w.card.now(),source_count=len(hashes),original611_unchanged=True,completed=completed,
            native_compiler_jobs=2,native_processes=processes,normal=normal,results=results,usb_requests=0,sd_accesses=0,real_sdk_objects=0,new_authorizations=0,formal_reservations=0,remaining=0,
            atomic_snapshot_verified=False,hardware_entry_implemented=False,physical_run_authenticated=False,callback_drain_verified=False,continuous_streaming_verified=False))
        w.b.seal(out);w.card.seal_verify(out);print(json.dumps(dict(archive=b.base.old.prior.reference(out),completed=len(completed),normal=normal),indent=2))
    except BaseException as error:
        if not (out/'COMMITTED').exists():w.write(out/'failure.json',dict(type=type(error).__name__,error=str(error),completed=completed,native_processes=processes));w.b.seal(out)
        raise

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path);args=parser.parse_args();run(args.output)
