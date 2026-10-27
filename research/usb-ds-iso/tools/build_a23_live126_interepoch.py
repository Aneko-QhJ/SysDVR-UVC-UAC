"""Fresh126 fixed-three-epoch candidate with exclusive interepoch verifier handoff."""
import argparse
import json
import re
import subprocess
from pathlib import Path
import build_a23_live120_lstat as base
from a23_sequence32_model import encode,sha,require,history as history_values
w=base.w;core=base.core;c=base.c
PARENT=w.A/'A23-interepoch-guard-wiring-closeout-20261025'
PARENT_SUM='f8081e1a14c9e92a842ba68a4c123a99476e3de3d3b0b933ff06a7013617dda4'
LIVE=w.A/'A23-live120-lstat-review-20261025-r1/build'
ANCHOR=w.ROOT/'private/card-cycles/20261025-live120-lstat-first-read'
ANCHOR_SUM='929edc4ebd1ab6b16898990556b6f083692bf97b7e26edfb15455ef2ac955d7a'
FORMAL_ROOT=w.ROOT/'private/sequence-reservations48-417'
SCOPE_SCHEMA='A23-live126-interepoch-shared48-scope-1'
OLD_NEW=('host/a23_interepoch_guard.h','host/a23_interepoch_guard.m','tests/a23_interepoch_guard_fixture.m')
NEW=('tools/build_a23_live126_interepoch.py','tools/a23_live126_interepoch_workflow.py','tools/audit_a23_live126_interepoch.py','tests/test_a23_live126_interepoch.py')
DESCRIPTION=dict(base.DESCRIPTION,schema='A23-live126-interepoch-description-1',baseline_raw_files=126,
    first_sequence=417,last_sequence=464,full_guard_source_count=651,
    interepoch_full_check_queue='exclusive_worker',interepoch_deadline_ns=10000000000,
    worker_return_required_before_exit=True)
HEADER=base.HEADER

def guards():
    base.guards()
    require(w.plain(w.A/'A23-live120-lstat-once-20261025-r1.json')==w.plain(PARENT/'once369-record-unchanged.json'),'actual369 drift')
    require({p.relative_to(base.FORMAL_ROOT).as_posix():sha(w.plain(p)) for p in base.FORMAL_ROOT.rglob('*') if p.is_file()}==w.load(PARENT/'namespace369-hashes.json'),'369 namespace drift')

def sources():
    require(core.verify_seal(PARENT)==PARENT_SUM,'wiring closeout drift')
    old=base.sources()|{'research/usb-ds-iso/'+n:sha(w.plain(w.ROOT/n)) for n in OLD_NEW}
    require(len(old)==647 and old==w.load(PARENT/'source-hashes.json'),'old647 drift');guards()
    return dict(sorted((old|{'research/usb-ds-iso/'+n:sha(w.plain(w.ROOT/n)) for n in NEW}).items()))

def inputs():
    hashes=sources();base.verify(LIVE,current=False)
    files=w.card.verify_snapshot(ANCHOR);m=json.loads(files['snapshot.json']);e=json.loads(files['eject.json'])
    require(sha(w.plain(ANCHOR/'SHA256SUMS'))==ANCHOR_SUM and w.latest_snapshot()==ANCHOR,'latest recovered126 required')
    inventory={n[5:]:dict(bytes=len(v),sha256=sha(v)) for n,v in files.items() if n.startswith('card/')}
    require(len(inventory)==126 and inventory==m['raw_files'] and m['read_only_mount_verified'] is True and m['simulation'] is False and m['deployment_files_match'] is True and m['identity']['VolumeUUID']==w.card.UUID and m['identity']['WritableVolume'] is False and e['ejected'] is True and e['mount_absent'] is True,'126 receipt differs')
    require(all(inventory.get(n)==v for n,v in m['expected_deployment_files'].items()),'deployment drift')
    for k in ('hardware_verified','physical_run_authenticated','root_cause_confirmed','card_files_written','attempt_issued'):require(m[k] is False,'unsupported snapshot claim')
    require(type(m['remaining']) is int and m['remaining']==0 and m['usb_requests']==0,'snapshot counts differ')
    legacy={p.relative_to(LIVE/'history').as_posix():w.plain(p) for p in (LIVE/'history').rglob('*') if p.is_file()}
    spent=base.FORMAL_ROOT;record=w.A/'A23-live120-lstat-once-20261025-r1.json';v=w.load(record);burn=w.load(spent/'block-00369.json')
    require(burn['first']==369 and burn['last']==416 and burn['count']==48 and burn['simulation'] is False and v['remaining']==0 and v['stage']=='captured_logs_recovered' and v['creator_wait_verified'] is True and v['receiver_exit_code']==0 and v['device_log_recovered'] is True and v['device_log_pending'] is False and v['host_device_chain_consistent'] is True and v['device_lifecycle_normal_return'] is True and v['card_snapshot']==str(ANCHOR),'369 success not closed')
    for p in spent.rglob('*'):
        if p.is_file():legacy['spent369/'+p.relative_to(spent).as_posix()]=w.plain(p)
    legacy['records/'+record.name]=w.plain(record)
    history=w.load(spent/'history.json')+[dict(first=n,last=n+15,reservation_sha256=sha(w.plain(spent/'block-00369.json')),record_sha256=sha(w.plain(record))) for n in (369,385,401)]
    require(history_values(history)==set(range(49,417)),'complete49..416 required')
    index={p.parent.name+'/snapshot.json':w.plain(p) for p in (w.ROOT/'private/card-cycles').glob('*/snapshot.json')}
    d=dict(w.load(LIVE/'descriptor.json'));d.pop('generated_hashes')
    d.update(description=DESCRIPTION,source_hashes=hashes,workflow_source_sha256=sha(encode(hashes)),
        baseline_directory=ANCHOR.name,baseline_files={n:sha(v) for n,v in files.items()},baseline_manifest_sha256=ANCHOR_SUM,
        baseline_inventory_sha256=sha(encode(inventory)),history_files={n:sha(v) for n,v in legacy.items()},history_sha256=sha(encode(history)),
        recovery_index={n:sha(v) for n,v in index.items()},parent_manifest_sha256=PARENT_SUM)
    d['live_roots']=dict(d['live_roots'],spent369=str(spent))
    require(d['device_binding_sha256']==m['device_binding_sha256'] and d['recipe_sha256']==m['expected_recipe_sha256'],'device binding drift')
    return d,files,legacy,index,history

def rebase(raw):
    return raw.replace(str(base.FORMAL_ROOT),str(FORMAL_ROOT)).replace(base.SCOPE_SCHEMA,SCOPE_SCHEMA).replace('block-00369.json','block-00417.json').replace('@369','@417').replace('@416','@464').replace('firstSequence:369','firstSequence:417').replace('first!=369','first!=417')

def render_engine(raw):
    s=base.render_engine(raw).replace(str(base.FORMAL_ROOT),'__LIVE126_ROOT__').replace(base.SCOPE_SCHEMA,SCOPE_SCHEMA).replace('block-00369','block-00417')
    return re.sub(r'\b(369|416|417)\b',lambda m:{'369':'417','416':'464','417':'465'}[m[0]],s).replace('__LIVE126_ROOT__',str(FORMAL_ROOT))

QUEUE_DECL='''\n@interface A23VerifiedEntryCoordinator (A23InterepochWiring)
- (void)configureGuardQueue:(dispatch_queue_t)queue;
- (NSDictionary *)queueGuardResult;
@end
'''
QUEUE_METHOD=r'''
- (void)configureGuardQueue:(dispatch_queue_t)q {
    A23TwoEpochEntry *entry=_entry;A23ReadOnlyScopeVerifier *v=_verifier;
    A23SharedSequencePermit *permit=_permit;NSDictionary *scope=_scope;NSString *job=_job;
    _between=[[A23InterepochGuard alloc] initWithQueue:q job:job scopeDigest:digest(encode(scope)) fullCheck:^BOOL{
        [v setCheckPhase:@"between_epochs"];return [v verifyCore];
    } boundary:^NSDictionary *{
        NSDictionary *r=entry.result,*d=[r[@"driver"] isKindOfClass:NSDictionary.class]?r[@"driver"]:@{};
        return @{@"saved_epochs":d[@"saved_epochs"]?:@0,@"iso_attempts":d[@"iso_attempts"]?:@0,
            @"durable":@YES,@"pending":@([d[@"iso_attempts"] unsignedIntegerValue]>[d[@"saved_epochs"] unsignedIntegerValue]),
            @"stopped":@([r[@"stopped"] boolValue] || [d[@"stopped"] boolValue])};
    } recheck:^BOOL{return [v verifyLiveJob:scope job:job] && ![permit.result[@"stale"] boolValue];}
    poll:^{[entry tick];} stop:^{[entry requestExit];} finished:^{
#ifdef A23_EXPORT_MODEL_FIXTURE
        A23InterepochFixtureSettled();
#endif
    }];
}
- (NSDictionary *)queueGuardResult {return _between.result?:@{};}
'''
QUEUE_TICK=r'''
- (void)tick {
    if([_between.result[@"busy"] boolValue]){[_between observeDeadline];return;}
    if([_between.result[@"stopped"] boolValue]){[_entry requestExit];return;}
    NSDictionary *r=_entry.result,*d=[r[@"driver"] isKindOfClass:NSDictionary.class]?r[@"driver"]:@{};
    NSUInteger saved=[d[@"saved_epochs"] unsignedIntegerValue];
    if(_between && saved>0 && saved<3 && [d[@"iso_attempts"] unsignedIntegerValue]==saved &&
       ![r[@"stopped"] boolValue] && ![d[@"stopped"] boolValue]){
        struct timespec t;if(clock_gettime(CLOCK_MONOTONIC_RAW,&t)){[_entry requestExit];return;}
        uint64_t now=(uint64_t)t.tv_sec*1000000000ULL+t.tv_nsec;
        if(![_between requestEpoch:saved deadlineNS:now+10000000000ULL])[_entry requestExit];return;
    }
    if(![self inflight] && ![self guard:@"before_tick"])return;[_entry tick];
}
'''
EXIT_GATE='''#import <Foundation/Foundation.h>
static BOOL A23InterepochExitAllowed(NSDictionary *loop,NSDictionary *guard) {
    return [loop[@"finished"] boolValue] && ![guard[@"busy"] boolValue] &&
        [guard[@"verifier_on_serial_queue"] boolValue];
}
'''

def generated(source,d):
    root=Path(source)/'research/usb-ds-iso';old,_=base.generated(source,d)
    result={n:rebase(v.decode()) for n,v in old.items()}
    s=result['live_scope.m'].replace('@"spent273",@"spent321"]','@"spent273",@"spent321",@"spent369"]').replace('_roots.count==11','_roots.count==12')
    s=c.change(s,'([name hasPrefix:@"spent321/"]?_roots[@"spent321"]:_roots[@"records"])','([name hasPrefix:@"spent321/"]?_roots[@"spent321"]:([name hasPrefix:@"spent369/"]?_roots[@"spent369"]:_roots[@"records"]))')
    s=c.change(s,'@"spent321":at(records.stringByDeletingLastPathComponent,@"spent321")}','@"spent321":at(records.stringByDeletingLastPathComponent,@"spent321"),@"spent369":at(records.stringByDeletingLastPathComponent,@"spent369")}')
    s='#import "a23_interepoch_guard.h"\n#ifdef A23_EXPORT_MODEL_FIXTURE\nextern void A23InterepochFixtureSettled(void);\nextern void A23Live126WorkerStarted(void);\n#endif\n'+s
    s=c.change(s,'if(_failed)return NO;_checks++;BOOL ok=_roots.count==12', 'if(_failed)return NO;\n#ifdef A23_EXPORT_MODEL_FIXTURE\n    if([_checkPhase isEqual:@"between_epochs"])A23Live126WorkerStarted();\n#endif\n    _checks++;BOOL ok=_roots.count==12')
    s=c.change(s,'A23SharedSequencePermit *_permit;NSDictionary *_scope;NSString *_job;}','A23SharedSequencePermit *_permit;NSDictionary *_scope;NSString *_job;A23InterepochGuard *_between;}')
    marker='- (NSArray<NSDictionary *> *)liveFailureSnapshots'
    s=c.change(s,marker,QUEUE_METHOD+'\n'+marker)
    s=c.change(s,'- (void)tick {if(![self inflight] && ![self guard:@"before_tick"])return;[_entry tick];}',QUEUE_TICK)
    s=c.change(s,'- (BOOL)guard:(NSString *)phase {','- (BOOL)guard:(NSString *)phase {\n    if([_between.result[@"busy"] boolValue])return NO;')
    s=c.change(s,'- (NSDictionary *)exportEvidence {','- (NSDictionary *)exportEvidence {\n    if([_between.result[@"busy"] boolValue])return @{@"verification_pending":@YES,@"interepoch_guard":_between.result};')
    s=c.change(s,'@"future_disk_freshness_verified":@NO,@"physical_run_authenticated":@NO};','@"future_disk_freshness_verified":@NO,@"physical_run_authenticated":@NO,@"interepoch_guard":_between.result?:@{}};')
    result['live_scope.m']=s
    result['interepoch_exit.h']=EXIT_GATE
    main='#import "a23_scope_verifier.h"\n#include "interepoch_exit.h"\n'+QUEUE_DECL+result['live_main.m']
    main=c.change(main,'loop=[[A23CheckedTwoEpochRun alloc] initWithTarget:','[coordinator configureGuardQueue:queue];loop=[[A23CheckedTwoEpochRun alloc] initWithTarget:')
    main=c.change(main,'if([s[@"finished"] boolValue]){','if(A23InterepochExitAllowed(s,coordinator.queueGuardResult)){')
    result['live_main.m']=main
    result['fixed48.py']=render_engine((root/'tools/a23_shared_sequence32.py').read_text())
    result['sdk_analysis.py']=result['sdk_analysis.py'].replace('integer(first,369,369)','integer(first,417,417)')
    result['entry_analysis.py']=result['entry_analysis.py'].replace("integer(b.get('first_sequence'),369,369)","integer(b.get('first_sequence'),417,417)")
    result['workflow.py']=result['workflow.py'].replace('import build_a23_live120_lstat as builder','import build_a23_live126_interepoch as builder').replace('from a23_live120_lstat_workflow import','from a23_live126_interepoch_workflow import').replace('first_sequence=369,last_sequence=416','first_sequence=417,last_sequence=464')
    result['export_analysis.py']=result['export_analysis.py'].replace('A23-live120-lstat-candidate-1','A23-live126-interepoch-candidate-1')
    bound=dict(schema='A23-live126-interepoch-candidate-1',source_closure_sha256=d['workflow_source_sha256'],parent_manifest_sha256=PARENT_SUM,
        descriptor_inputs_sha256=sha(encode(d)),generated_scope_sha256=sha(s.encode()),controller_sha256=sha(result['live_export.m'].encode()),
        entry_main_sha256=sha(main.encode()),interepoch_controller_sha256=sha((root/'host/a23_interepoch_guard.m').read_bytes()),exit_gate_sha256=sha(EXIT_GATE.encode()),transaction_count=128,model_only=False)
    result['a23_checked_export_binding.h']=base.base.base.base.base.old.checked.binding_header(bound).decode()
    return {n:v.encode() for n,v in result.items()},bound

def command(build,fixture=None):
    cmd=base.command(build,fixture)
    cmd.insert(cmd.index('-o'),str(Path(build)/'source/research/usb-ds-iso/host/a23_interepoch_guard.m'))
    return cmd

def build(output):
    output=w.canonical(output);require(not output.exists(),'new126 build required')
    d,saved,hist,index,_=inputs();gen,_=generated(w.b.REPO,d);d['generated_hashes']={n:sha(v) for n,v in gen.items()};output.mkdir(mode=0o700)
    for n,v in [('descriptor.json',encode(d)),('a23_verified_binding.h',HEADER(d)),('a23_checked_export_binding.h',gen['a23_checked_export_binding.h'])]:w.card.put(output,n,v)
    for n in d['source_hashes']:w.card.put(output,'source/'+n,w.plain(w.b.REPO/n))
    for group,items in [('baseline',saved),('history',hist),('recovery-index',index),('generated',gen)]:
        for n,v in items.items():w.card.put(output,group+'/'+n,v)
    cmd=command(output);p=subprocess.run(cmd,capture_output=True,timeout=60);w.card.put(output,'compile.log',p.stdout+p.stderr);w.write(output/'build-command.json',dict(command=cmd,returncode=p.returncode,creator_wait_verified=True));require(p.returncode==0,'live126 compilation failed')
    w.write(output/'binary.json',dict(schema='A23-verified-entry-binary-1',receiver_sha256=sha(w.plain(output/'verified-entry',64*1024*1024)),descriptor_sha256=sha(encode(d))))
    require(inputs()[0]=={k:v for k,v in d.items() if k!='generated_hashes'},'inputs drift');w.b.seal(output);return verify(output)

def verify(build,*,current=True):
    build=w.canonical(build);files=w.card.seal_verify(build);d=w.load(build/'descriptor.json');require(d['description']==DESCRIPTION and len(d['source_hashes'])==651,'descriptor differs')
    if current:require(inputs()[0]=={k:v for k,v in d.items() if k!='generated_hashes'},'current126 differs')
    gen,_=generated(build/'source',{k:v for k,v in d.items() if k!='generated_hashes'});require(d['generated_hashes']=={n:sha(v) for n,v in gen.items()},'generated inputs differ')
    require(w.plain(build/'a23_verified_binding.h')==HEADER(d) and w.plain(build/'a23_checked_export_binding.h')==gen['a23_checked_export_binding.h'],'headers drift')
    expected={'descriptor.json','a23_verified_binding.h','a23_checked_export_binding.h','verified-entry','binary.json','compile.log','build-command.json'}
    for group,items in [('source',d['source_hashes']),('baseline',d['baseline_files']),('history',d['history_files']),('recovery-index',d['recovery_index']),('generated',d['generated_hashes'])]:
        for n,h in items.items():expected.add(group+'/'+n);require(sha(w.plain(build/group/n,64*1024*1024))==h,'group drift')
    require(set(files)==expected,'inventory differs')
    require(w.load(build/'binary.json')==dict(schema='A23-verified-entry-binary-1',receiver_sha256=sha(w.plain(build/'verified-entry',64*1024*1024)),descriptor_sha256=sha(w.plain(build/'descriptor.json'))),'binary drift')
    return dict(directory=str(build),manifest_sha256=sha(w.plain(build/'SHA256SUMS')),entries=len(files))

def runtime_scope(build):
    verify(build);d=w.load(Path(build)/'descriptor.json');v=w.load(Path(build)/'binary.json')
    return dict(schema=SCOPE_SCHEMA,**{k:d[k] for k in ('baseline_manifest_sha256','baseline_inventory_sha256','workflow_source_sha256','device_binding_sha256','recipe_sha256','history_sha256')},
        build_manifest_sha256=sha(w.plain(Path(build)/'SHA256SUMS')),receiver_sha256=v['receiver_sha256'],first_sequence=417,last_sequence=464,formal_issuance_available=True,acquisition_mode_implemented=True,hardware_entry_enabled=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True);g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);v=p.parse_args();print(json.dumps(build(v.output) if v.output else verify(v.check),indent=2))
