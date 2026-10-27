"""Current91 checked-export receiver; build and checks never open USB."""
import argparse,json,re,subprocess,types
from pathlib import Path
import a23_checked_export as checked
from a23_sequence32_model import encode,sha,parse,require,history as check_history

base=checked.b;w=base.w;previous=base.previous
PARENT=w.A/'A23-checked-export-closeout-20261022'
PARENT_SUM='f6ad7dde330ede915be0e3010c2e2c1c7e696b68602aef6e4382b608db6c102d'
ANCHOR=w.ROOT/'private/card-cycles/20261022-live75-first-read'
ANCHOR_SUM='2865ffdd86c2c6a246e1e8381371a2d1c07abbdb58e4ff72b29c327b005fbd75'
FORMAL_ROOT=w.ROOT/'private/sequence-reservations32-145'
SCOPE_SCHEMA='A23-live91-checked-shared32-scope-1'
NEW=('tools/build_a23_live91_checked.py','tools/a23_live91_checked_workflow.py',
     'tools/audit_a23_live91_checked.py','tests/test_a23_live91_checked.py')
DESCRIPTION=dict(base.DESCRIPTION,schema='A23-live91-checked-description-1',baseline_raw_files=91,
    first_sequence=145,last_sequence=176,checked_export_required=True,full_guard_source_count=611)


def one(raw,before,after):return checked.prior.once(raw,before,after)


def sources():
    w.card.seal_verify(PARENT);require(sha(w.plain(PARENT/'SHA256SUMS'))==PARENT_SUM,'checked closeout drift')
    out=checked.sources();require(len(out)==607 and out==w.load(PARENT/'source-hashes.json'),'original607 drift')
    for name in NEW:out['research/usb-ds-iso/'+name]=sha(w.plain(w.ROOT/name))
    return dict(sorted(out.items()))


def spent113():
    checked.prior.guards();root=base.FORMAL_ROOT
    files={p.relative_to(root).as_posix():w.plain(p) for p in sorted(root.rglob('*')) if p.is_file()}
    require({n:sha(raw) for n,raw in files.items()}==w.load(PARENT/'successor-namespace-hashes.json'),'spent113 tree drift')
    module=types.ModuleType('read_spent113');exec(compile(base.render_engine((w.ROOT/'tools/a23_shared_sequence32.py').read_text()),'<spent113>','exec'),module.__dict__)
    burn=parse(files['block-00113.json']);module.check_consumed(root,burn['job_id'])
    record=w.A/'A23-live75-two-epoch-once-20261022-r1.json';frozen=checked.prior.PARENT/'once-record.json'
    require(w.plain(record)==w.plain(frozen),'actual113 record drift');v=w.load(record)
    require(v['remaining']==0 and v['stage']=='captured_logs_recovered' and v['creator_wait_verified'] is True and v['receiver_exit_code']==0 and
        v['device_log_pending'] is False and v['device_log_recovered'] is True and v['result_closeout_complete'] is True,'113 not closed')
    require(burn['first']==113 and burn['last']==144 and burn['count']==32 and burn['simulation'] is False,'113 burn differs')
    pred,prior,prior_record=base.predecessor();require(parse(files['history.json'])==prior,'113 history drift')
    history=prior+[dict(first=n,last=n+15,reservation_sha256=sha(files['block-00113.json']),record_sha256=sha(w.plain(record))) for n in (113,129)]
    require(check_history(history)==set(range(49,145)),'spent coverage incomplete')
    return files,history,record,pred,prior_record


def inputs():
    hashes=sources();files=w.card.verify_snapshot(ANCHOR);m=parse(files['snapshot.json']);e=parse(files['eject.json'])
    require(sha(w.plain(ANCHOR/'SHA256SUMS'))==ANCHOR_SUM and w.latest_snapshot()==ANCHOR,'current91 required; no fallback')
    inventory={n[5:]:dict(bytes=len(raw),sha256=sha(raw)) for n,raw in files.items() if n.startswith('card/')}
    require(len(inventory)==91 and encode(m['raw_files'])==encode(inventory) and m['read_only_mount_verified'] is True and m['simulation'] is False and
        m['deployment_files_match'] is True and m['identity']['VolumeUUID']==w.card.UUID and m['identity']['WritableVolume'] is False and
        e['ejected'] is True and e['mount_absent'] is True and e['simulation'] is False,'91 receipt invalid')
    package=previous.authority.baseline.PACKAGE
    require(encode(m['expected_deployment_files'])==encode(package) and all(encode(inventory.get(n))==encode(row) for n,row in package.items()),'91 deployment differs')
    for k in ('hardware_verified','physical_run_authenticated','root_cause_confirmed','card_files_written','attempt_issued'):require(m[k] is False,'91 unsupported claim')
    require(m['remaining']==0 and type(m['remaining']) is int and m['usb_requests']==0,'91 count differs')
    spent,history,record,pred,prior_record=spent113();legacy={}
    for p in w.LEDGER.iterdir():legacy['ledger/'+p.name]=w.plain(p)
    for row in previous.authority.baseline.legacy.entries(w.LEDGER).values():
        p=Path(row['value']['record']);legacy['records/'+p.name]=w.plain(p)
    for p in (record,prior_record):legacy['records/'+p.name]=w.plain(p)
    for group,items in [('predecessor',pred),('spent113',spent)]:
        for n,raw in items.items():legacy[group+'/'+n]=raw
    index={p.parent.name+'/snapshot.json':w.plain(p) for p in (w.ROOT/'private/card-cycles').glob('*/snapshot.json')}
    d=dict(schema='A23-verified-entry-descriptor-1',description=DESCRIPTION,source_hashes=hashes,workflow_source_sha256=sha(encode(hashes)),
        baseline_directory=ANCHOR.name,baseline_files={n:sha(raw) for n,raw in files.items()},baseline_manifest_sha256=ANCHOR_SUM,
        baseline_inventory_sha256=sha(encode(inventory)),history_files={n:sha(raw) for n,raw in legacy.items()},history_sha256=sha(encode(history)),
        recovery_index={n:sha(raw) for n,raw in index.items()},device_binding_sha256=m['device_binding_sha256'],recipe_sha256=m['expected_recipe_sha256'],
        live_roots=dict(repository=str(w.b.REPO),cards=str(w.ROOT/'private/card-cycles'),ledger=str(w.LEDGER),records=str(w.A),
            predecessor=str(base.PREDECESSOR),spent113=str(base.FORMAL_ROOT)),parent_manifest_sha256=PARENT_SUM)
    require(d['device_binding_sha256']=='a10e3750ed104576c05b205145e8a8efefe8811d20dec0d1e1debc8c368c61cf' and d['recipe_sha256']=='37269528ee3baa2941e1cb9268ccd4702d9db5b0fec87e913d3111c99b6e894f','91 device binding differs')
    return d,files,legacy,index,history


def rebase(raw):
    return raw.replace(str(base.FORMAL_ROOT),str(FORMAL_ROOT)).replace(base.SCOPE_SCHEMA,SCOPE_SCHEMA).replace('@113','@145').replace('@144','@176').replace('firstSequence:113','firstSequence:145').replace('block-00113.json','block-00145.json')


def render_scope(raw):
    raw=rebase(checked.render_scope(base.render_scope(raw)))
    raw=one(raw,'@"compile.log",@"build-command.json"','@"compile.log",@"build-command.json",@"a23_checked_export_binding.h"')
    raw=one(raw,'@"records",@"predecessor"]','@"records",@"predecessor",@"spent113"]')
    raw=one(raw,'_roots.count==5','_roots.count==6')
    raw=one(raw,'@"sdk_clock_is_synthetic":@YES','@"sdk_clock_is_synthetic":@(_model)')
    raw=one(raw,'([name hasPrefix:@"predecessor/"]?_roots[@"predecessor"]:_roots[@"records"])',
        '([name hasPrefix:@"predecessor/"]?_roots[@"predecessor"]:([name hasPrefix:@"spent113/"]?_roots[@"spent113"]:_roots[@"records"]))')
    begin=raw.index('        NSDictionary *actual=files(_roots[@"predecessor"]);')
    end=raw.index('    if(!ok)_failed=YES;return ok;',begin)
    raw=raw[:begin]+'''        for(NSString *kind in @[@"predecessor",@"spent113"]){
            NSDictionary *actual=files(_roots[kind]);NSMutableDictionary *wanted=[NSMutableDictionary new];NSString *prefix=[kind stringByAppendingString:@"/"];
            for(NSString *n in d[@"history_files"])if([n hasPrefix:prefix])wanted[[n substringFromIndex:prefix.length]]=d[@"history_files"][n];
            if(!actual)ok=NO;
            for(NSString *n in actual){if([n hasSuffix:@"/"]){BOOL valid=NO;for(NSString *p in wanted)if([p hasPrefix:n])valid=YES;if(!valid)ok=NO;}
                else if(![actual[n] isEqual:wanted[n]])ok=NO;}
        }
    }
'''+raw[end:]
    raw=one(raw,'@"predecessor":at(records.stringByDeletingLastPathComponent,@"predecessor")}',
        '@"predecessor":at(records.stringByDeletingLastPathComponent,@"predecessor"),@"spent113":at(records.stringByDeletingLastPathComponent,@"spent113")}')
    return raw


def render_main(raw):
    raw=rebase(base.render_main(raw)).replace('A23LiveTwoEpochRun','A23CheckedTwoEpochRun').replace('id<A23LiveEntryTarget>','id<A23CheckedEntryTarget>')
    raw='#import "a23_checked_export.h"\n'+raw
    return one(raw,'return [verifier verifyScope:s job:job];','return [verifier verifyLiveJob:s job:job];')


def render_engine(raw):
    raw=base.render_engine(raw).replace(str(base.FORMAL_ROOT),'__FORMAL91__').replace(base.SCOPE_SCHEMA,SCOPE_SCHEMA).replace('block-00113.json','block-00145.json')
    return re.sub(r'\b(?:113|144|145)\b',lambda m:{'113':'145','144':'176','145':'177'}[m[0]],raw).replace('__FORMAL91__',str(FORMAL_ROOT))


def consumer(raw):
    raw=one(raw,"bound['schema']=='A23-checked-export-candidate-1' and bound['model_only'] is True", "bound['schema']=='A23-live91-checked-candidate-1' and bound['model_only'] is False")
    raw=one(raw,'def _evidence(value,entry_binding):','def _evidence(value,entry_binding,simulation):')
    raw=one(raw,"metrics['sdk_clock_is_synthetic'] is True","metrics['sdk_clock_is_synthetic'] is simulation")
    raw=one(raw,'def accept(root,*,expected_binding):','def accept(root,*,expected_binding,simulation=False):')
    raw=one(raw,'root=w.canonical(root)\n    final=',"require(type(simulation) is bool,'explicit clock domain required')\n    root=w.canonical(root)\n    final=")
    return raw.replace("_evidence(before,entry['binding'])","_evidence(before,entry['binding'],simulation)").replace("_evidence(after,entry['binding'])","_evidence(after,entry['binding'],simulation)")


def generated(source,d):
    root=Path(source)/'research/usb-ds-iso';gen=base.generated(source)
    gen['live_scope.m']=render_scope((root/'host/a23_scope_verifier.m').read_text()).encode()
    gen['live_permit.m']=rebase(base.render_permit((root/'host/a23_shared_sequence_permit.m').read_text())).encode()
    gen['live_main.m']=render_main((root/'host/a23_live_two_epoch_main.m').read_text()).encode()
    gen['a23_live91_export_analysis.py']=consumer((root/'tools/a23_checked_export.py').read_text()).encode()
    raw=(root/'tools/a23_live_two_epoch_workflow.py').read_text()
    raw=one(raw,'import build_a23_live_two_epoch as builder','import build_a23_live91_checked as builder')
    raw=one(raw,'from analyze_a23_two_epoch_entry import analyze as entry_analyze','from a23_live91_checked_workflow import analyze_entry as entry_analyze')
    raw=one(raw,'builder.previous.authority.inputs()[4]','builder.inputs()[4]')
    raw=one(raw,'result=entry_analyze(stage)','result=entry_analyze(stage,Path(state["build"]))')
    raw=one(raw,'first_sequence=81,last_sequence=112','first_sequence=145,last_sequence=176')
    gen['a23_live91_workflow.py']=raw.encode()
    bound=dict(schema='A23-live91-checked-candidate-1',source_closure_sha256=d['workflow_source_sha256'],parent_manifest_sha256=PARENT_SUM,
        descriptor_inputs_sha256=sha(encode({k:v for k,v in d.items() if k!='generated_hashes'})),generated_scope_sha256=sha(gen['live_scope.m']),
        controller_sha256=sha(w.plain(root/'host/a23_checked_export.m')),entry_main_sha256=sha(gen['live_main.m']),model_only=False)
    gen['a23_checked_export_binding.h']=checked.binding_header(bound)
    return gen,bound


def command(build,fixture=None):
    build=Path(build);source=build/'source/research/usb-ds-iso';cmd=base.command(build,fixture)
    return [str(source/'host/a23_checked_export.m') if x==str(source/'host/a23_live_two_epoch.m') else x for x in cmd]


def build(output):
    output=w.canonical(output);require(not output.exists(),'new live91 build required');d,saved,history,index,_=inputs();gen,bound=generated(w.b.REPO,d)
    d['generated_hashes']={n:sha(raw) for n,raw in gen.items()};output.mkdir(mode=0o700)
    for name,raw in [('descriptor.json',encode(d)),('a23_verified_binding.h',previous.header(d))]:w.card.put(output,name,raw)
    for name,h in d['source_hashes'].items():
        raw=w.plain(w.b.REPO/name);require(sha(raw)==h,'live91 source drift');w.card.put(output,'source/'+name,raw)
    for group,files in [('baseline',saved),('history',history),('recovery-index',index),('generated',gen)]:
        for name,raw in files.items():w.card.put(output,group+'/'+name,raw)
    # The publisher's include resolves alongside the descriptor binding header.
    w.card.put(output,'a23_checked_export_binding.h',gen['a23_checked_export_binding.h'])
    cmd=command(output);p=subprocess.run(cmd,capture_output=True,timeout=60);w.card.put(output,'compile.log',p.stdout+p.stderr)
    w.write(output/'build-command.json',dict(command=cmd,returncode=p.returncode));require(p.returncode==0,'live91 compilation failed')
    w.write(output/'binary.json',dict(schema='A23-verified-entry-binary-1',receiver_sha256=sha(w.plain(output/'verified-entry',64*1024*1024)),descriptor_sha256=sha(encode(d))))
    require(inputs()[0]=={k:v for k,v in d.items() if k!='generated_hashes'},'live91 inputs changed during compilation')
    w.b.seal(output);return verify(output)


def verify(build,*,current=True):
    build=w.canonical(build);files=w.card.seal_verify(build);d=w.load(build/'descriptor.json')
    require(d['description']==DESCRIPTION and len(d['source_hashes'])==611,'live91 descriptor differs')
    if current:require(inputs()[0]=={k:v for k,v in d.items() if k!='generated_hashes'},'live91 current inputs differ')
    require(w.plain(build/'a23_verified_binding.h')==previous.header(d),'live91 descriptor header differs')
    gen,bound=generated(build/'source',d);require(d['generated_hashes']=={n:sha(raw) for n,raw in gen.items()},'live91 generation differs')
    require(w.plain(build/'a23_checked_export_binding.h')==gen['a23_checked_export_binding.h'],'publisher binding differs')
    expected={'descriptor.json','a23_verified_binding.h','a23_checked_export_binding.h','verified-entry','binary.json','compile.log','build-command.json'}
    for group,items in [('source',d['source_hashes']),('baseline',d['baseline_files']),('history',d['history_files']),('recovery-index',d['recovery_index']),('generated',d['generated_hashes'])]:
        for n,h in items.items():expected.add(group+'/'+n);require(sha(w.plain(build/group/n,64*1024*1024))==h,'live91 grouped input differs')
    require(set(files)==expected,'live91 inventory differs')
    require(w.load(build/'binary.json')==dict(schema='A23-verified-entry-binary-1',receiver_sha256=sha(w.plain(build/'verified-entry',64*1024*1024)),descriptor_sha256=sha(w.plain(build/'descriptor.json'))),'live91 binary differs')
    return base.old.prior.reference(build)


def runtime_scope(build):
    verify(build);d=w.load(Path(build)/'descriptor.json');binary=w.load(Path(build)/'binary.json')
    return dict(schema=SCOPE_SCHEMA,baseline_manifest_sha256=d['baseline_manifest_sha256'],baseline_inventory_sha256=d['baseline_inventory_sha256'],
        workflow_source_sha256=d['workflow_source_sha256'],build_manifest_sha256=sha(w.plain(Path(build)/'SHA256SUMS')),receiver_sha256=binary['receiver_sha256'],
        device_binding_sha256=d['device_binding_sha256'],recipe_sha256=d['recipe_sha256'],history_sha256=d['history_sha256'],
        first_sequence=145,last_sequence=176,formal_issuance_available=True,acquisition_mode_implemented=True,hardware_entry_enabled=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True);g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);args=p.parse_args()
    print(json.dumps(build(args.output) if args.output else verify(args.check),indent=2))
