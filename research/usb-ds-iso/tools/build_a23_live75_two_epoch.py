"""Bind the tested STATUS revision to saved75 and a fixed successor range."""
import argparse,json,re,subprocess,types
from pathlib import Path
import a23_status_capture_revision as revision
from a23_sequence32_model import encode,sha,parse,require,history as check_history
old=revision.old;w=old.w;previous=old.previous
PARENT=w.A/'A23-status-capture-revision-closeout-20261022'
PARENT_SUM='c7c10508251ba2a1cb961a3a09b272b67df8ace5f09e2e78850720bf0791372c'
ANCHOR=w.ROOT/'private/card-cycles/20261022-live-two-epoch-first-read'
ANCHOR_SUM='6d74823b74e4f81bce85d6410b148948d6fb84596c6efd96da732b651b049c56'
LIVE=w.A/'A23-live-two-epoch-first-live-closeout-20261022'
LIVE_SUM='4430c6330c20dc61df60093a3e3ca14c6003690c688446aef82b4aa689a89a15'
PREDECESSOR=old.FORMAL_ROOT
FORMAL_ROOT=w.ROOT/'private/sequence-reservations32-113'
SCOPE_SCHEMA='A23-live75-shared32-scope-1'
NEW=('tools/build_a23_live75_two_epoch.py','tools/a23_live75_two_epoch_workflow.py',
     'tools/audit_a23_live75_two_epoch.py','tests/a23_live75_two_epoch_fixture.inc','tests/test_a23_live75_two_epoch.py')
DESCRIPTION=dict(old.DESCRIPTION,schema='A23-live75-two-epoch-description-1',baseline_raw_files=75,
    first_sequence=113,last_sequence=144,status_capture_before_decision=True,report_count_zero_one=True,
    predecessor_range_preserved=True)


def sources():
    w.card.seal_verify(PARENT);require(sha(w.plain(PARENT/'SHA256SUMS'))==PARENT_SUM,'STATUS closeout changed')
    out=revision.sources();require(len(out)==592 and out==w.load(PARENT/'source-hashes.json'),'original592 drift')
    for name in NEW:out['research/usb-ds-iso/'+name]=sha(w.plain(w.ROOT/name))
    return dict(sorted(out.items()))


def predecessor():
    w.card.seal_verify(LIVE);require(sha(w.plain(LIVE/'SHA256SUMS'))==LIVE_SUM,'actual81 closeout changed')
    files={p.relative_to(PREDECESSOR).as_posix():w.plain(p) for p in sorted(PREDECESSOR.rglob('*')) if p.is_file()}
    require(all(not p.is_symlink() and (p.is_file() or p.is_dir()) for p in PREDECESSOR.rglob('*')),'predecessor unsafe node')
    require({n:sha(raw) for n,raw in files.items()}==w.load(LIVE/'shared32-ledger-hashes.json'),'spent81 namespace changed')
    raw=(w.ROOT/'tools/a23_shared_sequence32.py').read_text();module=types.ModuleType('A23_read_spent81')
    exec(compile(old.render_engine(raw),'<frozen-spent81-reader>','exec'),module.__dict__)
    burn=parse(files['block-00081.json']);job=burn['job_id'];module.check_consumed(PREDECESSOR,job)
    record=w.A/'A23-live-two-epoch-once-20261022-r1.json'
    require(w.plain(record)==w.plain(LIVE/'once-record.json'),'actual81 record changed')
    value=w.load(record)
    require(value['stage']=='failed_no_retry_logs_recovered' and value['remaining']==0 and value['creator_wait_verified'] is True and
        value['receiver_exit_code']==1 and value['device_log_pending'] is False and value['job_id']==job,'actual81 not closed')
    require(burn['first']==81 and burn['last']==112 and burn['count']==32 and burn['simulation'] is False,'spent32 range differs')
    old_history=parse(files['history.json']);require(sorted((r['first'],r['last']) for r in old_history)==[(49,64),(65,80)],'legacy history differs')
    result=old_history+[dict(first=n,last=n+15,reservation_sha256=sha(files['block-00081.json']),record_sha256=sha(w.plain(record))) for n in (81,97)]
    require(check_history(result)==set(range(49,113)),'spent history not complete')
    return files,result,record


def inputs():
    hashes=sources();files=w.card.verify_snapshot(ANCHOR);m=parse(files['snapshot.json']);e=parse(files['eject.json'])
    require(sha(w.plain(ANCHOR/'SHA256SUMS'))==ANCHOR_SUM and w.latest_snapshot()==ANCHOR,'latest75 recovery differs; no fallback')
    inventory={n[5:]:dict(bytes=len(raw),sha256=sha(raw)) for n,raw in files.items() if n.startswith('card/')}
    package=previous.authority.baseline.PACKAGE
    require(len(inventory)==75 and encode(m['raw_files'])==encode(inventory) and m['schema']=='A23-path-span-card-snapshot-1' and
        m['mode']=='recovery' and m['simulation'] is False and m['read_only_mount_verified'] is True and
        m['deployment_files_match'] is True and m['identity']['VolumeUUID']==w.card.UUID and m['identity']['WritableVolume'] is False and
        e['ejected'] is True and e['mount_absent'] is True and e['simulation'] is False,'saved75 receipt differs')
    require(encode(m['expected_deployment_files'])==encode(package) and all(encode(inventory.get(n))==encode(row) for n,row in package.items()),'75 deployed package differs')
    for key in ('hardware_verified','physical_run_authenticated','root_cause_confirmed','card_files_written','attempt_issued'):require(m[key] is False,'saved75 unsupported claim')
    require(m['remaining']==0 and type(m['remaining']) is int and m['usb_requests']==0,'saved75 count differs')
    pred,history,record=predecessor();legacy={}
    for p in w.LEDGER.iterdir():legacy['ledger/'+p.name]=w.plain(p)
    for row in previous.authority.baseline.legacy.entries(w.LEDGER).values():
        p=Path(row['value']['record']);legacy['records/'+p.name]=w.plain(p)
    require(parse(w.plain(PREDECESSOR/'history.json'))==history[:2],'predecessor history changed')
    require(sorted((r['value']['first'],r['value']['last']) for r in previous.authority.baseline.legacy.entries(w.LEDGER).values())==[(49,64),(65,80)],'legacy intervals changed')
    legacy['records/'+record.name]=w.plain(record)
    for n,raw in pred.items():legacy['predecessor/'+n]=raw
    index={p.parent.name+'/snapshot.json':w.plain(p) for p in (w.ROOT/'private/card-cycles').glob('*/snapshot.json')}
    d=dict(schema='A23-verified-entry-descriptor-1',description=DESCRIPTION,source_hashes=hashes,workflow_source_sha256=sha(encode(hashes)),
        baseline_directory=ANCHOR.name,baseline_files={n:sha(raw) for n,raw in files.items()},baseline_manifest_sha256=ANCHOR_SUM,
        baseline_inventory_sha256=sha(encode(inventory)),history_files={n:sha(raw) for n,raw in legacy.items()},history_sha256=sha(encode(history)),
        recovery_index={n:sha(raw) for n,raw in index.items()},device_binding_sha256=m['device_binding_sha256'],recipe_sha256=m['expected_recipe_sha256'],
        live_roots=dict(repository=str(w.b.REPO),cards=str(w.ROOT/'private/card-cycles'),ledger=str(w.LEDGER),records=str(w.A),predecessor=str(PREDECESSOR)),parent_manifest_sha256=PARENT_SUM)
    require(d['device_binding_sha256']=='a10e3750ed104576c05b205145e8a8efefe8811d20dec0d1e1debc8c368c61cf' and d['recipe_sha256']=='37269528ee3baa2941e1cb9268ccd4702d9db5b0fec87e913d3111c99b6e894f','75 recipe/binding differs')
    return d,files,legacy,index,history


def one(raw,before,after):return revision.replace(raw,before,after)


def render_scope(raw):
    raw=old.render_scope(raw)
    raw=one(raw,'@"A23-live-shared32-scope-1"','@"'+SCOPE_SCHEMA+'"')
    raw=raw.replace('@"first_sequence":@81,@"last_sequence":@112','@"first_sequence":@113,@"last_sequence":@144')
    raw=raw.replace(str(PREDECESSOR),str(FORMAL_ROOT))
    raw=one(raw,'@"repository",@"cards",@"ledger",@"records"]','@"repository",@"cards",@"ledger",@"records",@"predecessor"]')
    raw=one(raw,'_roots.count==4','_roots.count==5')
    raw=one(raw,'@"recovery-index":d[@"recovery_index"]','@"recovery-index":d[@"recovery_index"],@"generated":d[@"generated_hashes"]')
    raw=one(raw,'NSString *root=[name hasPrefix:@"ledger/"]?_roots[@"ledger"]:_roots[@"records"]',
        'NSString *root=[name hasPrefix:@"ledger/"]?_roots[@"ledger"]:([name hasPrefix:@"predecessor/"]?_roots[@"predecessor"]:_roots[@"records"])')
    raw=one(raw,'    if(!ok)_failed=YES;return ok;',r'''    if(ok){
        NSDictionary *actual=files(_roots[@"predecessor"]);NSMutableDictionary *wanted=[NSMutableDictionary new];
        for(NSString *n in d[@"history_files"])if([n hasPrefix:@"predecessor/"])wanted[[n substringFromIndex:12]]=d[@"history_files"][n];
        if(!actual)ok=NO;
        for(NSString *n in actual){if([n hasSuffix:@"/"]){BOOL prefix=NO;for(NSString *p in wanted)if([p hasPrefix:n])prefix=YES;if(!prefix)ok=NO;}
            else if(![actual[n] isEqual:wanted[n]])ok=NO;}
    }
    if(!ok)_failed=YES;return ok;''')
    raw=one(raw,'@"ledger":ledger,@"records":records}', '@"ledger":ledger,@"records":records,@"predecessor":at(records.stringByDeletingLastPathComponent,@"predecessor")}')
    return raw


def render_permit(raw):
    raw=old.render_permit(raw).replace('A23-live-shared32-scope-1',SCOPE_SCHEMA)
    raw=raw.replace(str(PREDECESSOR),str(FORMAL_ROOT)).replace('block-00081.json','block-00113.json')
    raw=raw.replace('@81','@113').replace('@112','@144')
    return raw


def render_main(raw):
    return raw.replace(str(PREDECESSOR),str(FORMAL_ROOT)).replace('@81','@113').replace('@112','@144').replace('firstSequence:81','firstSequence:113')


def render_engine(raw):
    raw=old.render_engine(raw).replace(str(PREDECESSOR),str(FORMAL_ROOT)).replace('A23-live-shared32-scope-1',SCOPE_SCHEMA).replace('block-00081.json','block-00113.json')
    return re.sub(r'\b(?:81|112|113)\b',lambda m:{'81':'113','112':'144','113':'145'}[m[0]],raw.replace(str(FORMAL_ROOT),'__A23_SUCCESSOR_ROOT__')).replace('__A23_SUCCESSOR_ROOT__',str(FORMAL_ROOT))


def render_workflow(raw):
    raw=one(raw,'import build_a23_live_two_epoch as builder','import build_a23_live75_two_epoch as builder')
    raw=one(raw,'from analyze_a23_two_epoch_entry import analyze as entry_analyze','from a23_live75_two_epoch_workflow import analyze_entry as entry_analyze')
    raw=one(raw,'builder.previous.authority.inputs()[4]','builder.inputs()[4]')
    raw=one(raw,'result=entry_analyze(stage)','result=entry_analyze(stage,Path(state["build"]))')
    return one(raw,'first_sequence=81,last_sequence=112','first_sequence=113,last_sequence=144')


def generated(source):
    r=Path(source)/'research/usb-ds-iso'
    result={}
    for n,name,render in [('live_scope.m','a23_scope_verifier.m',render_scope),('live_permit.m','a23_shared_sequence_permit.m',render_permit),
            ('live_driver.m','a23_two_epoch_sdk_driver.m',revision.render_driver),('live_entry.m','a23_two_epoch_entry.m',old.render_entry),('live_main.m','a23_live_two_epoch_main.m',render_main)]:
        result[n]=render((r/'host'/name).read_text()).encode()
    result['a23_live75_sdk_analysis.py']=revision.render_analyzer((r/'tools/analyze_a23_two_epoch_sdk.py').read_text()).encode()
    result['a23_live75_entry_analysis.py']=(r/'tools/analyze_a23_two_epoch_entry.py').read_bytes().replace(b'from analyze_a23_two_epoch_sdk import',b'from a23_live75_sdk_analysis import')
    return result


def command(build,fixture=None):
    build=Path(build);cmd=old.command(build,fixture or build/'generated/live_main.m')
    if fixture is None:
        cmd=[x for x in cmd if x not in ('-fsanitize=address,undefined','-fno-omit-frame-pointer','-g')]
        cmd.insert(1,'-O2');cmd[-1]=str(build/'verified-entry')
    return cmd


def build(output):
    output=w.canonical(output);require(not output.exists(),'new live75 build required')
    d,saved,history,index,_=inputs();gen=generated(w.b.REPO);d['generated_hashes']={n:sha(raw) for n,raw in gen.items()}
    output.mkdir(mode=0o700);w.card.put(output,'descriptor.json',encode(d));w.card.put(output,'a23_verified_binding.h',previous.header(d))
    for name,h in d['source_hashes'].items():
        raw=w.plain(w.b.REPO/name,2*1024*1024);require(sha(raw)==h,'live75 source drift');w.card.put(output,'source/'+name,raw)
    for group,files in [('baseline',saved),('history',history),('recovery-index',index),('generated',gen)]:
        for name,raw in files.items():w.card.put(output,group+'/'+name,raw)
    cmd=command(output);p=subprocess.run(cmd,capture_output=True,timeout=60)
    w.card.put(output,'compile.log',p.stdout+p.stderr);w.write(output/'build-command.json',dict(command=cmd,returncode=p.returncode))
    require(p.returncode==0,'live75 native compilation failed')
    w.write(output/'binary.json',dict(schema='A23-verified-entry-binary-1',receiver_sha256=sha(w.plain(output/'verified-entry',64*1024*1024)),descriptor_sha256=sha(encode(d))))
    require(inputs()[0]=={k:v for k,v in d.items() if k!='generated_hashes'},'live75 inputs changed during build')
    w.b.seal(output);return verify(output)


def verify(build,*,current=True):
    build=w.canonical(build);files=w.card.seal_verify(build);d=w.load(build/'descriptor.json')
    require(d['description']==DESCRIPTION and len(d['source_hashes'])==597,'live75 descriptor differs')
    if current:require(inputs()[0]=={k:v for k,v in d.items() if k!='generated_hashes'},'live75 current inputs differ')
    require(w.plain(build/'a23_verified_binding.h')==previous.header(d),'live75 descriptor header differs')
    gen=generated(build/'source');require(d['generated_hashes']=={n:sha(raw) for n,raw in gen.items()},'live75 generation changed')
    expected={'descriptor.json','a23_verified_binding.h','verified-entry','binary.json','compile.log','build-command.json'}
    for group,hashes in [('source',d['source_hashes']),('baseline',d['baseline_files']),('history',d['history_files']),('recovery-index',d['recovery_index']),('generated',d['generated_hashes'])]:
        for name,h in hashes.items():expected.add(group+'/'+name);require(sha(w.plain(build/group/name,64*1024*1024))==h,'live75 grouped input differs')
    for n,raw in gen.items():require(w.plain(build/'generated'/n)==raw,'live75 generated bytes differ')
    require(set(files)==expected,'live75 build inventory differs')
    require(w.load(build/'binary.json')==dict(schema='A23-verified-entry-binary-1',receiver_sha256=sha(w.plain(build/'verified-entry',64*1024*1024)),descriptor_sha256=sha(w.plain(build/'descriptor.json'))),'live75 binary binding differs')
    return old.prior.reference(build)


def runtime_scope(build):
    verify(build);d=w.load(Path(build)/'descriptor.json');binary=w.load(Path(build)/'binary.json')
    return dict(schema=SCOPE_SCHEMA,baseline_manifest_sha256=d['baseline_manifest_sha256'],baseline_inventory_sha256=d['baseline_inventory_sha256'],
        workflow_source_sha256=d['workflow_source_sha256'],build_manifest_sha256=sha(w.plain(Path(build)/'SHA256SUMS')),receiver_sha256=binary['receiver_sha256'],
        device_binding_sha256=d['device_binding_sha256'],recipe_sha256=d['recipe_sha256'],history_sha256=d['history_sha256'],first_sequence=113,last_sequence=144,
        formal_issuance_available=True,acquisition_mode_implemented=True,hardware_entry_enabled=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True);g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);args=p.parse_args()
    print(json.dumps(build(args.output) if args.output else verify(args.check),indent=2))
