"""Current103 candidate: preserve all-interest stop, capture raw message/ticks."""
import argparse,json,re,subprocess
from pathlib import Path
import build_a23_live97_three as base
import audit_a23_interest_trace as trace
from a23_sequence32_model import encode,sha,require,history as history_values
w=base.w
PARENT=w.A/'A23-interest-trace-closeout-20261024'
PARENT_SUM='faf621faa913d19097847f99876a120749b879525ccedc8e9adf8dba3ade2b7e'
ANCHOR=w.ROOT/'private/card-cycles/20261024-live97-three-first-read'
ANCHOR_SUM='17ebdeff19b22522e68a35f7097a9cd72f26d7472be599a3b9fdaf287ca9697a'
FORMAL_ROOT=w.ROOT/'private/sequence-reservations48-225'
SCOPE_SCHEMA='A23-live103-interest-shared48-scope-1'
LIVE=w.A/'A23-live97-three-review-20261023-r2/build'
NEW=('tools/build_a23_live103_interest.py','tools/a23_live103_interest_workflow.py','tools/audit_a23_live103_interest.py','tests/test_a23_live103_interest.py')
DESCRIPTION=dict(base.DESCRIPTION,schema='A23-live103-interest-description-1',baseline_raw_files=103,first_sequence=225,last_sequence=272,full_guard_source_count=632,interest_trace_required=True,all_interest_still_fatal=True)

def sources():
    require(base.core.verify_seal(PARENT)==PARENT_SUM,'interest closeout drift');old=trace.sources();trace.guards()
    require(len(old)==628 and old==w.load(PARENT/'source-hashes.json'),'old628 drift')
    return dict(sorted((old|{'research/usb-ds-iso/'+n:sha(w.plain(w.ROOT/n)) for n in NEW}).items()))

def inputs():
    hashes=sources();base.verify(LIVE,current=False);files=w.card.verify_snapshot(ANCHOR);m=json.loads(files['snapshot.json']);e=json.loads(files['eject.json'])
    require(sha(w.plain(ANCHOR/'SHA256SUMS'))==ANCHOR_SUM and w.latest_snapshot()==ANCHOR,'current103 required; no fallback')
    inventory={n[5:]:dict(bytes=len(b),sha256=sha(b)) for n,b in files.items() if n.startswith('card/')}
    require(len(inventory)==103 and inventory==m['raw_files'] and m['read_only_mount_verified'] is True and m['simulation'] is False and m['deployment_files_match'] is True and m['identity']['VolumeUUID']==w.card.UUID and m['identity']['WritableVolume'] is False and e['ejected'] is True and e['mount_absent'] is True,'103 receipt differs')
    require(all(inventory.get(n)==v for n,v in m['expected_deployment_files'].items()),'deployment drift')
    for k in ('hardware_verified','physical_run_authenticated','root_cause_confirmed','card_files_written','attempt_issued'):require(m[k] is False,'unsupported snapshot claim')
    require(type(m['remaining']) is int and m['remaining']==0 and m['usb_requests']==0,'snapshot counts differ')
    legacy={p.relative_to(LIVE/'history').as_posix():w.plain(p) for p in (LIVE/'history').rglob('*') if p.is_file()}
    spent=base.FORMAL_ROOT;burn=w.load(spent/'block-00177.json');record=w.A/'A23-live97-three-once-20261023-r1.json';v=w.load(record)
    require(burn['first']==177 and burn['last']==224 and burn['count']==48 and burn['simulation'] is False and v['remaining']==0 and v['stage']=='failed_no_retry_logs_recovered' and v['creator_wait_verified'] is True and v['receiver_exit_code']==1 and v['device_log_recovered'] is True and v['device_log_pending'] is False,'177 failure not closed')
    for p in spent.rglob('*'):
        if p.is_file():legacy['spent177/'+p.relative_to(spent).as_posix()]=w.plain(p)
    legacy['records/'+record.name]=w.plain(record)
    history=w.load(spent/'history.json')+[dict(first=n,last=n+15,reservation_sha256=sha(w.plain(spent/'block-00177.json')),record_sha256=sha(w.plain(record))) for n in (177,193,209)]
    require(history_values(history)==set(range(49,225)),'complete49..224 including unused third required')
    index={p.parent.name+'/snapshot.json':w.plain(p) for p in (w.ROOT/'private/card-cycles').glob('*/snapshot.json')}
    d=dict(w.load(LIVE/'descriptor.json'));d.pop('generated_hashes');d.update(description=DESCRIPTION,source_hashes=hashes,workflow_source_sha256=sha(encode(hashes)),baseline_directory=ANCHOR.name,baseline_files={n:sha(v) for n,v in files.items()},baseline_manifest_sha256=ANCHOR_SUM,baseline_inventory_sha256=sha(encode(inventory)),history_files={n:sha(v) for n,v in legacy.items()},history_sha256=sha(encode(history)),recovery_index={n:sha(v) for n,v in index.items()},parent_manifest_sha256=PARENT_SUM)
    d['live_roots']=dict(d['live_roots'],spent177=str(spent));require(d['device_binding_sha256']==m['device_binding_sha256'] and d['recipe_sha256']==m['expected_recipe_sha256'],'device binding drift')
    return d,files,legacy,index,history

def rebase(raw):
    return raw.replace(str(base.FORMAL_ROOT),str(FORMAL_ROOT)).replace(base.SCOPE_SCHEMA,SCOPE_SCHEMA).replace('block-00177.json','block-00225.json').replace('@177','@225').replace('@224','@272').replace('firstSequence:177','firstSequence:225').replace('first!=177','first!=225')
def render_engine(raw):
    raw=base.render_engine(raw).replace(str(base.FORMAL_ROOT),'__FORMAL103__').replace(base.SCOPE_SCHEMA,SCOPE_SCHEMA).replace('block-00177','block-00225')
    return re.sub(r'\b(177|224|225)\b',lambda m:{'177':'225','224':'272','225':'273'}[m[0]],raw).replace('__FORMAL103__',str(FORMAL_ROOT))

def generated(source,d):
    root=Path(source)/'research/usb-ds-iso';old,_=base.generated(source,d);result={n:rebase(v.decode()) for n,v in old.items()}
    result['live_adapter.m']=trace.trace.render(result['live_adapter.m'])
    result['live_entry.m']=base.c.change(result['live_entry.m'],'@"driver":driver ?: NSNull.null,@"driver_receipt":receipt ?: NSNull.null,','@"driver":driver ?: NSNull.null,@"driver_receipt":receipt ?: NSNull.null,@"provider_failure":_provider.retainedFailure.result ?: NSNull.null,')
    s=result['live_scope.m'].replace('@"spent113",@"spent145"]','@"spent113",@"spent145",@"spent177"]').replace('_roots.count==7','_roots.count==8')
    s=base.c.change(s,'([name hasPrefix:@"spent145/"]?_roots[@"spent145"]:_roots[@"records"])','([name hasPrefix:@"spent145/"]?_roots[@"spent145"]:([name hasPrefix:@"spent177/"]?_roots[@"spent177"]:_roots[@"records"]))')
    s=base.c.change(s,'@"spent145":at(records.stringByDeletingLastPathComponent,@"spent145")}','@"spent145":at(records.stringByDeletingLastPathComponent,@"spent145"),@"spent177":at(records.stringByDeletingLastPathComponent,@"spent177")}');result['live_scope.m']=s
    result['fixed48.py']=render_engine((root/'tools/a23_shared_sequence32.py').read_text())
    result['sdk_analysis.py']=result['sdk_analysis.py'].replace('integer(first,177,177)','integer(first,225,225)')
    result['entry_analysis.py']=result['entry_analysis.py'].replace("integer(b.get('first_sequence'),177,177)","integer(b.get('first_sequence'),225,225)")
    result['workflow.py']=result['workflow.py'].replace('import build_a23_live97_three as builder','import build_a23_live103_interest as builder').replace('from a23_live97_three_workflow import','from a23_live103_interest_workflow import').replace('first_sequence=177,last_sequence=224','first_sequence=225,last_sequence=272')
    result['export_analysis.py']=result['export_analysis.py'].replace('A23-live97-three-candidate-1','A23-live103-interest-candidate-1')
    controller=result['live_export.m'];controller=base.c.change(controller,'_operatorOffAcknowledged;NSUInteger','_operatorOffAcknowledged,_interestAfterOffAttempted,_interestAfterOffSaved;NSUInteger')
    controller=base.c.change(controller,'    return YES;\n}\n- (NSDictionary *)files:',r'''    _interestAfterOffAttempted=YES;
    NSDictionary *latest=_target.result;
    _interestAfterOffSaved=exportFiles(_directory,@"interest-after-power-off",@{@"entry-current.json":latest,@"result.json":[latest[@"driver"] isKindOfClass:NSDictionary.class]?latest[@"driver"]:@{},
        @"boundary.json":@{@"schema":@"A23-interest-after-off-boundary-1",@"operator_power_off_confirmed":@YES,@"device_power_observed_by_software":@NO,@"raw_sdk_buffers_copied":@NO,@"callback_drain_verified":@NO,@"future_events_excluded":@NO}});
    return YES;
}
- (NSDictionary *)files:''')
    controller=base.c.change(controller,'@"operator_power_off_acknowledged":@(_operatorOffAcknowledged),','@"operator_power_off_acknowledged":@(_operatorOffAcknowledged),@"interest_after_off_attempted":@(_interestAfterOffAttempted),@"interest_after_off_saved":@(_interestAfterOffSaved),');result['live_export.m']=controller
    bound=dict(schema='A23-live103-interest-candidate-1',source_closure_sha256=d['workflow_source_sha256'],parent_manifest_sha256=PARENT_SUM,descriptor_inputs_sha256=sha(encode(d)),generated_scope_sha256=sha(result['live_scope.m'].encode()),controller_sha256=sha(controller.encode()),entry_main_sha256=sha(result['live_main.m'].encode()),model_only=False)
    result['a23_checked_export_binding.h']=base.old.checked.binding_header(bound).decode();return {n:v.encode() for n,v in result.items()},bound

def command(build,fixture=None):return base.command(build,fixture)
def build(output):
    output=w.canonical(output);require(not output.exists(),'new103 build required');d,saved,hist,index,_=inputs();gen,_=generated(w.b.REPO,d);d['generated_hashes']={n:sha(v) for n,v in gen.items()};output.mkdir(mode=0o700)
    for n,v in [('descriptor.json',encode(d)),('a23_verified_binding.h',base.old.previous.header(d)),('a23_checked_export_binding.h',gen['a23_checked_export_binding.h'])]:w.card.put(output,n,v)
    for n in d['source_hashes']:w.card.put(output,'source/'+n,w.plain(w.b.REPO/n))
    for group,items in [('baseline',saved),('history',hist),('recovery-index',index),('generated',gen)]:
        for n,v in items.items():w.card.put(output,group+'/'+n,v)
    cmd=command(output);p=subprocess.run(cmd,capture_output=True,timeout=60);w.card.put(output,'compile.log',p.stdout+p.stderr);w.write(output/'build-command.json',dict(command=cmd,returncode=p.returncode));require(p.returncode==0,'live103 compilation failed')
    w.write(output/'binary.json',dict(schema='A23-verified-entry-binary-1',receiver_sha256=sha(w.plain(output/'verified-entry',64*1024*1024)),descriptor_sha256=sha(encode(d))));require(inputs()[0]=={k:v for k,v in d.items() if k!='generated_hashes'},'inputs drift');w.b.seal(output);return verify(output)
def verify(build,*,current=True):
    build=w.canonical(build);files=w.card.seal_verify(build);d=w.load(build/'descriptor.json');require(d['description']==DESCRIPTION and len(d['source_hashes'])==632,'descriptor differs')
    if current:require(inputs()[0]=={k:v for k,v in d.items() if k!='generated_hashes'},'current103 differs')
    gen,_=generated(build/'source',{k:v for k,v in d.items() if k!='generated_hashes'});require(d['generated_hashes']=={n:sha(v) for n,v in gen.items()},'generated inputs differ');require(w.plain(build/'a23_verified_binding.h')==base.old.previous.header(d) and w.plain(build/'a23_checked_export_binding.h')==gen['a23_checked_export_binding.h'],'headers drift')
    expected={'descriptor.json','a23_verified_binding.h','a23_checked_export_binding.h','verified-entry','binary.json','compile.log','build-command.json'}
    for group,items in [('source',d['source_hashes']),('baseline',d['baseline_files']),('history',d['history_files']),('recovery-index',d['recovery_index']),('generated',d['generated_hashes'])]:
        for n,h in items.items():expected.add(group+'/'+n);require(sha(w.plain(build/group/n,64*1024*1024))==h,'group drift')
    require(set(files)==expected,'inventory differs');require(w.load(build/'binary.json')==dict(schema='A23-verified-entry-binary-1',receiver_sha256=sha(w.plain(build/'verified-entry',64*1024*1024)),descriptor_sha256=sha(w.plain(build/'descriptor.json'))),'binary drift');return dict(directory=str(build),manifest_sha256=sha(w.plain(build/'SHA256SUMS')),entries=len(files))
def runtime_scope(build):
    verify(build);d=w.load(Path(build)/'descriptor.json');v=w.load(Path(build)/'binary.json');return dict(schema=SCOPE_SCHEMA,**{k:d[k] for k in ('baseline_manifest_sha256','baseline_inventory_sha256','workflow_source_sha256','device_binding_sha256','recipe_sha256','history_sha256')},build_manifest_sha256=sha(w.plain(Path(build)/'SHA256SUMS')),receiver_sha256=v['receiver_sha256'],first_sequence=225,last_sequence=272,formal_issuance_available=True,acquisition_mode_implemented=True,hardware_entry_enabled=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True);g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);v=p.parse_args();print(json.dumps(build(v.output) if v.output else verify(v.check),indent=2))
