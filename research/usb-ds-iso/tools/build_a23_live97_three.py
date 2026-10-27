"""Fresh97, fixed48, checked-export build. Building never issues or opens USB."""
import argparse
import json
from pathlib import Path
import re
import subprocess

import audit_a23_three_epoch as core
import a23_three_epoch_candidate as c
import build_a23_live91_checked as old
from a23_sequence32_model import encode,sha,require,history as history_values

w=old.w;LIVE=core.LIVE
PARENT=w.A/'A23-three-epoch-offline-closeout-20261023'
PARENT_SUM='26cd48ae872e4d32eb81b5be0abc77a72ae8196f341e3f8dbb51582e3a67bec1'
ANCHOR=w.ROOT/'private/card-cycles/20261023-live91-first-read'
ANCHOR_SUM='2dc75e0848b4dfa4ce4c50764cc4a85f64cfb1376a85840182ae9affada15ee8'
FORMAL_ROOT=w.ROOT/'private/sequence-reservations48-177'
SCOPE_SCHEMA='A23-live97-three-shared48-scope-1'
NEW=('tools/build_a23_live97_three.py','tools/a23_live97_three_workflow.py','tools/audit_a23_live97_three.py','tests/test_a23_live97_three.py')
DESCRIPTION=dict(old.DESCRIPTION,schema='A23-live97-three-description-1',baseline_raw_files=97,first_sequence=177,last_sequence=224,max_epochs=3,full_guard_source_count=623)

def sources():
    require(core.verify_seal(PARENT)==PARENT_SUM,'three core closeout drift');out=core.sources()
    require(out==w.load(PARENT/'source-hashes.json') and len(out)==619,'old619 drift');core.guards()
    return dict(sorted((out|{'research/usb-ds-iso/'+n:sha(w.plain(w.ROOT/n)) for n in NEW}).items()))

def inputs():
    hashes=sources();core.verify_seal(LIVE);files=w.card.verify_snapshot(ANCHOR);m=json.loads(files['snapshot.json']);e=json.loads(files['eject.json'])
    require(sha(w.plain(ANCHOR/'SHA256SUMS'))==ANCHOR_SUM and w.latest_snapshot()==ANCHOR,'current97 required; no fallback')
    inventory={n[5:]:dict(bytes=len(b),sha256=sha(b)) for n,b in files.items() if n.startswith('card/')}
    require(len(inventory)==97 and inventory==m['raw_files'] and m['read_only_mount_verified'] is True and m['simulation'] is False and m['deployment_files_match'] is True and m['identity']['VolumeUUID']==w.card.UUID and m['identity']['WritableVolume'] is False and e['ejected'] is True and e['mount_absent'] is True,'97 receipt differs')
    require(all(inventory.get(n)==v for n,v in m['expected_deployment_files'].items()),'97 deployment differs')
    for key in ('hardware_verified','physical_run_authenticated','root_cause_confirmed','card_files_written','attempt_issued'):require(m[key] is False,'97 unsupported claim')
    require(m['remaining']==0 and m['usb_requests']==0,'97 count differs')
    legacy={p.relative_to(LIVE/'history').as_posix():w.plain(p) for p in (LIVE/'history').rglob('*') if p.is_file()}
    spent=w.ROOT/'private/sequence-reservations32-145';burn=w.load(spent/'block-00145.json');record=w.A/'A23-live91-checked-once-20261022-r1.json';actual=w.load(record)
    require(burn['first']==145 and burn['last']==176 and burn['count']==32 and burn['simulation'] is False and actual['remaining']==0 and actual['stage']=='captured_logs_recovered' and actual['creator_wait_verified'] is True and actual['receiver_exit_code']==0 and actual['device_log_recovered'] is True and actual['device_log_pending'] is False,'145 not closed')
    for p in spent.rglob('*'):
        if p.is_file():legacy['spent145/'+p.relative_to(spent).as_posix()]=w.plain(p)
    legacy['records/'+record.name]=w.plain(record)
    history=w.load(spent/'history.json')+[dict(first=n,last=n+15,reservation_sha256=sha(w.plain(spent/'block-00145.json')),record_sha256=sha(w.plain(record))) for n in (145,161)]
    require(history_values(history)==set(range(49,177)),'complete49..176 required')
    index={p.parent.name+'/snapshot.json':w.plain(p) for p in (w.ROOT/'private/card-cycles').glob('*/snapshot.json')}
    d=dict(w.load(LIVE/'descriptor.json'));d.pop('generated_hashes')
    d.update(description=DESCRIPTION,source_hashes=hashes,workflow_source_sha256=sha(encode(hashes)),baseline_directory=ANCHOR.name,baseline_files={n:sha(b) for n,b in files.items()},baseline_manifest_sha256=ANCHOR_SUM,baseline_inventory_sha256=sha(encode(inventory)),history_files={n:sha(b) for n,b in legacy.items()},history_sha256=sha(encode(history)),recovery_index={n:sha(b) for n,b in index.items()},parent_manifest_sha256=PARENT_SUM)
    d['live_roots']=dict(d['live_roots'],spent145=str(spent))
    require(d['device_binding_sha256']==m['device_binding_sha256'] and d['recipe_sha256']==m['expected_recipe_sha256'],'97 device binding drift')
    return d,files,legacy,index,history

def rebase(raw):
    return c.names(raw).replace('A23-two-epoch-entry-','A23-three-epoch-entry-').replace(str(old.FORMAL_ROOT),str(FORMAL_ROOT)).replace(old.SCOPE_SCHEMA,SCOPE_SCHEMA).replace('A23-shared32-','A23-shared48-').replace('block-00145.json','block-00177.json').replace('@145','@177').replace('@176','@224').replace('firstSequence:145','firstSequence:177')

def render_engine(raw):
    raw=old.render_engine(raw).replace(str(old.FORMAL_ROOT),'__FIXED48_ROOT__').replace(old.SCOPE_SCHEMA,SCOPE_SCHEMA).replace('shared32','shared48').replace('SharedSequence32','SharedSequence48').replace('block-00145','block-00177').replace('A23-two-epoch-entry-','A23-three-epoch-entry-')
    raw=re.sub(r'\b(145|176|177|32)\b',lambda m:{'145':'177','176':'224','177':'225','32':'48'}[m[0]],raw).replace('__FIXED48_ROOT__',str(FORMAL_ROOT))
    return c.change(raw,'f.history(historical)',"f.require(f.history(historical)==set(range(49,177)),'complete49..176 required')",2)

def generated(source,d):
    root=Path(source)/'research/usb-ds-iso';result={}
    for n in ('a23_two_epoch_entry.h','a23_shared_sequence_permit.h','a23_scope_verifier.h','a23_live_two_epoch.h','a23_checked_export.h','a23_guard_cadence_api.h'):
        result[n]=rebase((root/'host'/n).read_text())
    result['a23_three_epoch_sdk_driver.h']=c.names((root/'host/a23_two_epoch_sdk_driver.h').read_text())
    result['a23_triple_sdk_adapter.h']=c.names((root/'host/a23_paired_sdk_adapter.h').read_text())
    result['live_driver.m']=c.driver((LIVE/'generated/live_driver.m').read_text())
    result['live_adapter.m']=c.adapter((root/'host/a23_paired_sdk_adapter.m').read_text())
    for n in ('live_scope.m','live_permit.m','live_entry.m','live_main.m'):result[n]=rebase((LIVE/'generated'/n).read_text())
    s=result['live_scope.m'].replace('@"predecessor",@"spent113"]','@"predecessor",@"spent113",@"spent145"]').replace('_roots.count==6','_roots.count==7')
    s=c.change(s,'([name hasPrefix:@"spent113/"]?_roots[@"spent113"]:_roots[@"records"])','([name hasPrefix:@"spent113/"]?_roots[@"spent113"]:([name hasPrefix:@"spent145/"]?_roots[@"spent145"]:_roots[@"records"]))')
    s=c.change(s,'@"spent113":at(records.stringByDeletingLastPathComponent,@"spent113")}','@"spent113":at(records.stringByDeletingLastPathComponent,@"spent113"),@"spent145":at(records.stringByDeletingLastPathComponent,@"spent145")}')
    result['live_scope.m']=s
    result['live_permit.m']=c.change(result['live_permit.m'],'@"count":@32','@"count":@48')
    e=result['live_entry.m'];e=c.change(e,'first<81 || first>65504 || first%16!=1','first!=177');e=c.change(e,'!=first+31','!=first+47');result['live_entry.m']=e
    result['live_main.m']=result['live_main.m'].replace('A-two-epoch-','A-three-epoch-')
    result['live_export.m']=c.change(c.change((root/'host/a23_checked_export.m').read_text(),'_snapshotAttempted[2],_snapshotSaved[2]','_snapshotAttempted[3],_snapshotSaved[3]'),'epoch>=2','epoch>=3').replace('A23-live-two-epoch-export-1','A23-live-three-epoch-export-1')
    result['fixed48.py']=render_engine((root/'tools/a23_shared_sequence32.py').read_text())
    result['sdk_analysis.py']=c.analyzer((LIVE/'generated/a23_live75_sdk_analysis.py').read_text())
    e=rebase((LIVE/'generated/a23_live75_entry_analysis.py').read_text()).replace('from a23_live75_sdk_analysis import','from sdk_analysis import')
    e=c.change(e,"integer(b.get('first_sequence'),81,65504)","integer(b.get('first_sequence'),177,177)");e=e.replace("b['first_sequence']+31","b['first_sequence']+47");result['entry_analysis.py']=e
    result['export_analysis.py']=(LIVE/'generated/a23_live91_export_analysis.py').read_text().replace('A23-live91-checked-candidate-1','A23-live97-three-candidate-1')
    flow=(LIVE/'generated/a23_live91_workflow.py').read_text().replace('import build_a23_live91_checked as builder','import build_a23_live97_three as builder').replace('from a23_live91_checked_workflow import analyze_entry as entry_analyze','from a23_live97_three_workflow import analyze_entry as entry_analyze')
    flow=flow.replace('SharedSequence32','SharedSequence48').replace('A23-shared32-','A23-shared48-').replace('A23-two-epoch-entry-','A23-three-epoch-entry-').replace('A23-live-two-epoch-','A23-live-three-epoch-').replace('A-two-epoch-','A-three-epoch-').replace('first_sequence=145,last_sequence=176','first_sequence=177,last_sequence=224').replace('two-epoch','three-epoch').replace('two_epoch','three_epoch')
    result['workflow.py']=flow
    bound=dict(schema='A23-live97-three-candidate-1',source_closure_sha256=d['workflow_source_sha256'],parent_manifest_sha256=PARENT_SUM,descriptor_inputs_sha256=sha(encode(d)),generated_scope_sha256=sha(result['live_scope.m'].encode()),controller_sha256=sha(result['live_export.m'].encode()),entry_main_sha256=sha(result['live_main.m'].encode()),model_only=False)
    result['a23_checked_export_binding.h']=old.checked.binding_header(bound).decode()
    return {n:b.encode() for n,b in result.items()},bound

def command(build,fixture=None):
    cmd=[x.replace(str(LIVE),str(build)) for x in w.load(LIVE/'build-command.json')['command']]
    root=Path(build)/'source/research/usb-ds-iso/host';gen=Path(build)/'generated'
    cmd=[str(gen/'live_adapter.m') if x==str(root/'a23_paired_sdk_adapter.m') else str(gen/'live_export.m') if x==str(root/'a23_checked_export.m') else x for x in cmd]
    cmd.insert(1,'-I'+str(gen))
    if fixture:
        cmd=[str(fixture) if x==str(gen/'live_main.m') else x for x in cmd];cmd[-1]=str(Path(build)/'live-fixture');cmd[cmd.index('-O2')]='-g';cmd[1:1]=['-DA23_EXPORT_MODEL_FIXTURE=1','-fsanitize=address,undefined','-fno-omit-frame-pointer']
    return cmd

def build(output):
    output=w.canonical(output);require(not output.exists(),'new three build required');d,saved,history,index,_=inputs();gen,_=generated(w.b.REPO,d);d['generated_hashes']={n:sha(b) for n,b in gen.items()};output.mkdir(mode=0o700)
    for n,b in [('descriptor.json',encode(d)),('a23_verified_binding.h',old.previous.header(d)),('a23_checked_export_binding.h',gen['a23_checked_export_binding.h'])]:w.card.put(output,n,b)
    for n,h in d['source_hashes'].items():w.card.put(output,'source/'+n,w.plain(w.b.REPO/n))
    for group,files in [('baseline',saved),('history',history),('recovery-index',index),('generated',gen)]:
        for n,b in files.items():w.card.put(output,group+'/'+n,b)
    cmd=command(output);p=subprocess.run(cmd,capture_output=True,timeout=60);w.card.put(output,'compile.log',p.stdout+p.stderr);w.write(output/'build-command.json',dict(command=cmd,returncode=p.returncode));require(p.returncode==0,'three compilation failed')
    w.write(output/'binary.json',dict(schema='A23-verified-entry-binary-1',receiver_sha256=sha(w.plain(output/'verified-entry',64*1024*1024)),descriptor_sha256=sha(encode(d))))
    require(inputs()[0]=={k:v for k,v in d.items() if k!='generated_hashes'},'three inputs drift');w.b.seal(output);return verify(output)

def verify(build,*,current=True):
    build=w.canonical(build);files=w.card.seal_verify(build);d=w.load(build/'descriptor.json');require(d['description']==DESCRIPTION and len(d['source_hashes'])==623,'three descriptor differs')
    if current:require(inputs()[0]=={k:v for k,v in d.items() if k!='generated_hashes'},'current97 inputs differ')
    gen,_=generated(build/'source',{k:v for k,v in d.items() if k!='generated_hashes'});require(d['generated_hashes']=={n:sha(b) for n,b in gen.items()},'three generation differs')
    require(w.plain(build/'a23_verified_binding.h')==old.previous.header(d) and w.plain(build/'a23_checked_export_binding.h')==gen['a23_checked_export_binding.h'],'binding header differs')
    expected={'descriptor.json','a23_verified_binding.h','a23_checked_export_binding.h','verified-entry','binary.json','compile.log','build-command.json'}
    for group,items in [('source',d['source_hashes']),('baseline',d['baseline_files']),('history',d['history_files']),('recovery-index',d['recovery_index']),('generated',d['generated_hashes'])]:
        for n,h in items.items():expected.add(group+'/'+n);require(sha(w.plain(build/group/n,64*1024*1024))==h,'three grouped drift')
    require(set(files)==expected,'three inventory differs');require(w.load(build/'binary.json')==dict(schema='A23-verified-entry-binary-1',receiver_sha256=sha(w.plain(build/'verified-entry',64*1024*1024)),descriptor_sha256=sha(w.plain(build/'descriptor.json'))),'three binary differs')
    return dict(directory=str(build),manifest_sha256=sha(w.plain(build/'SHA256SUMS')),entries=len(files))

def runtime_scope(build):
    verify(build);d=w.load(Path(build)/'descriptor.json');v=w.load(Path(build)/'binary.json')
    return dict(schema=SCOPE_SCHEMA,**{k:d[k] for k in ('baseline_manifest_sha256','baseline_inventory_sha256','workflow_source_sha256','device_binding_sha256','recipe_sha256','history_sha256')},build_manifest_sha256=sha(w.plain(Path(build)/'SHA256SUMS')),receiver_sha256=v['receiver_sha256'],first_sequence=177,last_sequence=224,formal_issuance_available=True,acquisition_mode_implemented=True,hardware_entry_enabled=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True);g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);args=p.parse_args();print(json.dumps(build(args.output) if args.output else verify(args.check),indent=2))
