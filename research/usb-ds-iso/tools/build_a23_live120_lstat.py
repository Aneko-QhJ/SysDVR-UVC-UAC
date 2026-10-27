"""Fresh120, unchanged fixed128 transport with lstat node typing in full guards."""
import argparse,json,re,subprocess
from pathlib import Path
import build_a23_live112_short128 as base
from a23_sequence32_model import encode,sha,require,history as history_values
w=base.w;core=base.core;c=base.c
PARENT=w.A/'A23-live112-guard-metadata-closeout-20261025'
PARENT_SUM='685dfb5e660e915c40398f2d925b43639bbd7082343c914ac90e95f51a098c46'
ANCHOR=w.ROOT/'private/card-cycles/20261025-live112-short128-first-read'
ANCHOR_SUM='94feade6120cbc10cf1136268bce1801be7871d2c9138f229be89691a0731875'
FORMAL_ROOT=w.ROOT/'private/sequence-reservations48-369'
SCOPE_SCHEMA='A23-live120-lstat-shared48-scope-1'
LIVE=w.A/'A23-live112-short128-review-20261025-r2/build'
NEW=('tools/build_a23_live120_lstat.py','tools/a23_live120_lstat_workflow.py','tools/audit_a23_live120_lstat.py','tests/test_a23_live120_lstat.py')
DESCRIPTION=dict(base.DESCRIPTION,schema='A23-live120-lstat-description-1',baseline_raw_files=120,first_sequence=369,last_sequence=416,full_guard_source_count=644,file_node_type_query='lstat',maximum_epochs=3,maximum_iso_submissions=3,maximum_burst_triggers=3)
HEADER=base.HEADER
NODE_OLD='NSDictionary *a=[[NSFileManager defaultManager] attributesOfItemAtPath:p error:NULL];NSString *type=a[NSFileType];\n        if(!canonical(p))return nil;if([type isEqual:NSFileTypeDirectory]){out[[name stringByAppendingString:@"/"]]=@"directory";continue;}\n        if(![type isEqual:NSFileTypeRegular])return nil;'
NODE_NEW='struct stat kind;if(lstat(p.fileSystemRepresentation,&kind))return nil;\n        if(!canonical(p))return nil;if(S_ISDIR(kind.st_mode)){out[[name stringByAppendingString:@"/"]]=@"directory";continue;}\n        if(!S_ISREG(kind.st_mode))return nil;'

def guards():
    base.guards();require(w.plain(w.A/'A23-live112-short128-once-20261025-r2.json')==w.plain(PARENT/'once321-record-unchanged.json'),'actual321 drift')
    require({p.relative_to(base.FORMAL_ROOT).as_posix():sha(w.plain(p)) for p in base.FORMAL_ROOT.rglob('*') if p.is_file()}==w.load(PARENT/'namespace321-hashes.json'),'321 namespace drift')
def sources():
    require(core.verify_seal(PARENT)==PARENT_SUM,'prior metadata closeout drift');old=base.sources();guards();require(len(old)==640 and old==w.load(PARENT/'source-hashes.json'),'old640 drift')
    return dict(sorted((old|{'research/usb-ds-iso/'+n:sha(w.plain(w.ROOT/n)) for n in NEW}).items()))
def inputs():
    hashes=sources();base.verify(LIVE,current=False);files=w.card.verify_snapshot(ANCHOR);m=json.loads(files['snapshot.json']);e=json.loads(files['eject.json'])
    require(sha(w.plain(ANCHOR/'SHA256SUMS'))==ANCHOR_SUM and w.latest_snapshot()==ANCHOR,'last recovered120 required; no fallback')
    inventory={n[5:]:dict(bytes=len(v),sha256=sha(v)) for n,v in files.items() if n.startswith('card/')}
    require(len(inventory)==120 and inventory==m['raw_files'] and m['read_only_mount_verified'] is True and m['simulation'] is False and m['deployment_files_match'] is True and m['identity']['VolumeUUID']==w.card.UUID and m['identity']['WritableVolume'] is False and e['ejected'] is True and e['mount_absent'] is True,'120 receipt differs')
    require(all(inventory.get(n)==v for n,v in m['expected_deployment_files'].items()),'deployment drift')
    for k in ('hardware_verified','physical_run_authenticated','root_cause_confirmed','card_files_written','attempt_issued'):require(m[k] is False,'unsupported snapshot claim')
    require(type(m['remaining']) is int and m['remaining']==0 and m['usb_requests']==0,'snapshot counts differ')
    legacy={p.relative_to(LIVE/'history').as_posix():w.plain(p) for p in (LIVE/'history').rglob('*') if p.is_file()}
    spent=base.FORMAL_ROOT;burn=w.load(spent/'block-00321.json');record=w.A/'A23-live112-short128-once-20261025-r2.json';v=w.load(record)
    require(burn['first']==321 and burn['last']==368 and burn['count']==48 and burn['simulation'] is False and v['remaining']==0 and v['stage']=='captured_logs_recovered' and v['creator_wait_verified'] is True and v['receiver_exit_code']==0 and v['device_log_recovered'] is True and v['device_log_pending'] is False and v['host_device_chain_consistent'] is True and v['device_lifecycle_normal_return'] is True and v['card_snapshot']==str(ANCHOR),'321 success not closed')
    for p in spent.rglob('*'):
        if p.is_file():legacy['spent321/'+p.relative_to(spent).as_posix()]=w.plain(p)
    legacy['records/'+record.name]=w.plain(record)
    history=w.load(spent/'history.json')+[dict(first=n,last=n+15,reservation_sha256=sha(w.plain(spent/'block-00321.json')),record_sha256=sha(w.plain(record))) for n in (321,337,353)]
    require(history_values(history)==set(range(49,369)),'complete49..368 required')
    index={p.parent.name+'/snapshot.json':w.plain(p) for p in (w.ROOT/'private/card-cycles').glob('*/snapshot.json')}
    d=dict(w.load(LIVE/'descriptor.json'));d.pop('generated_hashes');d.update(description=DESCRIPTION,source_hashes=hashes,workflow_source_sha256=sha(encode(hashes)),baseline_directory=ANCHOR.name,baseline_files={n:sha(v) for n,v in files.items()},baseline_manifest_sha256=ANCHOR_SUM,baseline_inventory_sha256=sha(encode(inventory)),history_files={n:sha(v) for n,v in legacy.items()},history_sha256=sha(encode(history)),recovery_index={n:sha(v) for n,v in index.items()},parent_manifest_sha256=PARENT_SUM)
    d['live_roots']=dict(d['live_roots'],spent321=str(spent));require(d['device_binding_sha256']==m['device_binding_sha256'] and d['recipe_sha256']==m['expected_recipe_sha256'],'device binding drift')
    return d,files,legacy,index,history

def rebase(raw):
    return raw.replace(str(base.FORMAL_ROOT),str(FORMAL_ROOT)).replace(base.SCOPE_SCHEMA,SCOPE_SCHEMA).replace('block-00321.json','block-00369.json').replace('@321','@369').replace('@368','@416').replace('firstSequence:321','firstSequence:369').replace('first!=321','first!=369')
def render_engine(raw):
    engine=base.render_engine(raw).replace(str(base.FORMAL_ROOT),'__LIVE120_ROOT__').replace(base.SCOPE_SCHEMA,SCOPE_SCHEMA).replace('block-00321','block-00369')
    return re.sub(r'\b(321|368|369)\b',lambda m:{'321':'369','368':'416','369':'417'}[m[0]],engine).replace('__LIVE120_ROOT__',str(FORMAL_ROOT))
def generated(source,d):
    root=Path(source)/'research/usb-ds-iso';old,_=base.generated(source,d);result={n:rebase(v.decode()) for n,v in old.items()}
    s=result['live_scope.m'].replace('@"spent225",@"spent273"]','@"spent225",@"spent273",@"spent321"]').replace('_roots.count==10','_roots.count==11')
    s=c.change(s,'([name hasPrefix:@"spent273/"]?_roots[@"spent273"]:_roots[@"records"])','([name hasPrefix:@"spent273/"]?_roots[@"spent273"]:([name hasPrefix:@"spent321/"]?_roots[@"spent321"]:_roots[@"records"]))')
    s=c.change(s,'@"spent273":at(records.stringByDeletingLastPathComponent,@"spent273")}','@"spent273":at(records.stringByDeletingLastPathComponent,@"spent273"),@"spent321":at(records.stringByDeletingLastPathComponent,@"spent321")}')
    s=c.change(s,NODE_OLD,NODE_NEW);result['live_scope.m']=s
    result['fixed48.py']=render_engine((root/'tools/a23_shared_sequence32.py').read_text())
    result['sdk_analysis.py']=result['sdk_analysis.py'].replace('integer(first,321,321)','integer(first,369,369)')
    result['entry_analysis.py']=result['entry_analysis.py'].replace("integer(b.get('first_sequence'),321,321)","integer(b.get('first_sequence'),369,369)")
    result['workflow.py']=result['workflow.py'].replace('import build_a23_live112_short128 as builder','import build_a23_live120_lstat as builder').replace('from a23_live112_short128_workflow import','from a23_live120_lstat_workflow import').replace('first_sequence=321,last_sequence=368','first_sequence=369,last_sequence=416')
    result['export_analysis.py']=result['export_analysis.py'].replace('A23-live112-short128-candidate-1','A23-live120-lstat-candidate-1')
    bound=dict(schema='A23-live120-lstat-candidate-1',source_closure_sha256=d['workflow_source_sha256'],parent_manifest_sha256=PARENT_SUM,descriptor_inputs_sha256=sha(encode(d)),generated_scope_sha256=sha(s.encode()),controller_sha256=sha(result['live_export.m'].encode()),entry_main_sha256=sha(result['live_main.m'].encode()),transaction_count=128,model_only=False)
    result['a23_checked_export_binding.h']=base.base.base.base.old.checked.binding_header(bound).decode();return {n:v.encode() for n,v in result.items()},bound

def command(build,fixture=None):return base.command(build,fixture)

def build(output):
    output=w.canonical(output);require(not output.exists(),'new120 lstat build required');d,saved,hist,index,_=inputs();gen,_=generated(w.b.REPO,d);d['generated_hashes']={n:sha(v) for n,v in gen.items()};output.mkdir(mode=0o700)
    for n,v in [('descriptor.json',encode(d)),('a23_verified_binding.h',HEADER(d)),('a23_checked_export_binding.h',gen['a23_checked_export_binding.h'])]:w.card.put(output,n,v)
    for n in d['source_hashes']:w.card.put(output,'source/'+n,w.plain(w.b.REPO/n))
    for group,items in [('baseline',saved),('history',hist),('recovery-index',index),('generated',gen)]:
        for n,v in items.items():w.card.put(output,group+'/'+n,v)
    cmd=command(output);p=subprocess.run(cmd,capture_output=True,timeout=60);w.card.put(output,'compile.log',p.stdout+p.stderr);w.write(output/'build-command.json',dict(command=cmd,returncode=p.returncode));require(p.returncode==0,'live120 lstat compilation failed')
    w.write(output/'binary.json',dict(schema='A23-verified-entry-binary-1',receiver_sha256=sha(w.plain(output/'verified-entry',64*1024*1024)),descriptor_sha256=sha(encode(d))));require(inputs()[0]=={k:v for k,v in d.items() if k!='generated_hashes'},'inputs drift');w.b.seal(output);return verify(output)
def verify(build,*,current=True):
    build=w.canonical(build);files=w.card.seal_verify(build);d=w.load(build/'descriptor.json');require(d['description']==DESCRIPTION and len(d['source_hashes'])==644,'descriptor differs')
    if current:require(inputs()[0]=={k:v for k,v in d.items() if k!='generated_hashes'},'current120 differs')
    gen,_=generated(build/'source',{k:v for k,v in d.items() if k!='generated_hashes'});require(d['generated_hashes']=={n:sha(v) for n,v in gen.items()},'generated inputs differ');require(w.plain(build/'a23_verified_binding.h')==HEADER(d) and w.plain(build/'a23_checked_export_binding.h')==gen['a23_checked_export_binding.h'],'headers drift')
    expected={'descriptor.json','a23_verified_binding.h','a23_checked_export_binding.h','verified-entry','binary.json','compile.log','build-command.json'}
    for group,items in [('source',d['source_hashes']),('baseline',d['baseline_files']),('history',d['history_files']),('recovery-index',d['recovery_index']),('generated',d['generated_hashes'])]:
        for n,h in items.items():expected.add(group+'/'+n);require(sha(w.plain(build/group/n,64*1024*1024))==h,'group drift')
    require(set(files)==expected,'inventory differs');require(w.load(build/'binary.json')==dict(schema='A23-verified-entry-binary-1',receiver_sha256=sha(w.plain(build/'verified-entry',64*1024*1024)),descriptor_sha256=sha(w.plain(build/'descriptor.json'))),'binary drift');return dict(directory=str(build),manifest_sha256=sha(w.plain(build/'SHA256SUMS')),entries=len(files))
def runtime_scope(build):
    verify(build);d=w.load(Path(build)/'descriptor.json');v=w.load(Path(build)/'binary.json');return dict(schema=SCOPE_SCHEMA,**{k:d[k] for k in ('baseline_manifest_sha256','baseline_inventory_sha256','workflow_source_sha256','device_binding_sha256','recipe_sha256','history_sha256')},build_manifest_sha256=sha(w.plain(Path(build)/'SHA256SUMS')),receiver_sha256=v['receiver_sha256'],first_sequence=369,last_sequence=416,formal_issuance_available=True,acquisition_mode_implemented=True,hardware_entry_enabled=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True);g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);v=p.parse_args();print(json.dumps(build(v.output) if v.output else verify(v.check),indent=2))
