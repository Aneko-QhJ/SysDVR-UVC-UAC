"""File-only native scope verification and complete injected entry chains."""
import argparse,copy,json,os,shutil,subprocess,tempfile
from pathlib import Path
import build_a23_verified_entry as builder
import audit_a23_shared_sequence32 as shared
from analyze_a23_shared_sequence32 import analyze as shared_analyze
from analyze_a23_two_epoch_entry import analyze as entry_analyze
w=builder.w;f=shared.f
CASES=('normal','queued-delay','bad-payload','live-source-afterprepare','restored-after-observed','new-recovery','baseline-drift','legacy-drift','foreign-job','own-native-context','new-empty-job','unknown-shared-file','during-pending-source','stopped-pending-source','between-epochs-source','before-final-source','after-final-source')
ARCHIVE_CASES=('frozen-source','binary','descriptor','header','extra-file','extra-empty-dir','bad-seal','frozen-history','frozen-index','resealed-source','resealed-header')

def generate(build,work):
    shutil.copytree(build,work);r=work/'source/research/usb-ds-iso';parts=[]
    for n in ('a23_two_epoch_receiver_test.m','a23_paired_sdk_fixture.inc','a23_two_epoch_sdk_fixture.inc','a23_two_epoch_entry_fixture.inc'):
        raw=(r/'tests'/n).read_text();f.require(raw.count('\nint main(')==1,'fixture prefix differs');parts.append(raw.split('\nint main(',1)[0])
    parts.append((r/'tests/a23_scope_verifier_fixture.m').read_text());(r/'tests/generated_scope_verifier_test.m').write_text('\n'.join(parts))

def template(build,root):
    d=f.load(build/'descriptor.json');shutil.copytree(build/'source',root/'repository');shutil.copytree(build/'history/ledger',root/'ledger');shutil.copytree(build/'history/records',root/'records');shutil.copytree(build/'recovery-index',root/'cards');anchor=root/'cards'/d['baseline_directory']
    for p in (build/'baseline').rglob('*'):
        if p.is_file():dest=anchor/p.relative_to(build/'baseline');dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(p.read_bytes())
    sums=''.join(h+'  '+n+'\n' for n,h in sorted(d['baseline_files'].items())).encode();f.require(f.sha(sums)==d['baseline_manifest_sha256'],'baseline reconstruction differs');(anchor/'SHA256SUMS').write_bytes(sums);(anchor/'COMMITTED').write_bytes((f.sha(sums)+'\n').encode())

def analyze_combined(case,scope,row):
    f.require(row.get('schema')=='A23-verified-scope-fixture-1' and row['verifier']['failed'] is False,'fresh verifier failed');f.require(row['real_sdk_objects']==row['usb_requests']==row['sd_accesses']==0,'fixture authority differs')
    a=shared_analyze(case/'namespace',f.load(case/'case-info.json')['job_id'],scope,row['native']);b=entry_analyze(case/'host')
    folder=case/'namespace/jobs'/f.load(case/'case-info.json')['job_id'];context=f.load(folder/'native-context.json');host_context=f.load(case/'host/context.json');selection=f.load(folder/'native-sdk-claim.json');host_selection=f.load(case/'host/sdk-claim.json')
    f.require(f.encode(context)==f.encode(host_context),'native/entry context differs')
    f.require(selection['pid']==host_selection['pid'] and selection['identity']['device_id']==host_selection['device_id'] and selection['identity']['interface_id']==host_selection['interface_id'],'native/entry selected identity differs')
    expected=dict(schema='A23-two-epoch-entry-binding-1',build_manifest_sha256=scope['build_manifest_sha256'],receiver_sha256=scope['receiver_sha256'],authorization_receipt_sha256=f.sha(f.read(folder/'consumed.json')),first_sequence=81,last_sequence=112)
    for binding in (row['entry']['binding'],f.load(case/'config.json')['binding'],f.load(case/'host/entry-current.json')['binding']):f.require(f.encode(binding)==f.encode(expected),'entry/consumption binding differs')
    return dict(shared=a,entry=b,physical_run_authenticated=False,hardware_verified=False)

def tamper(build,name):
    paths={'frozen-source':'source/research/usb-ds-iso/host/a23_scope_verifier.m','binary':'verified-entry','descriptor':'descriptor.json','header':'a23_verified_binding.h','bad-seal':'COMMITTED','frozen-history':'history/ledger/block-00049.json'}
    if name.startswith('resealed-'):
        tamper(build,'frozen-source' if name=='resealed-source' else 'header');sums=''.join(f.sha(p.read_bytes())+'  '+p.relative_to(build).as_posix()+'\n' for p in sorted(build.rglob('*')) if p.is_file() and p.relative_to(build).as_posix() not in ('SHA256SUMS','COMMITTED')).encode();(build/'SHA256SUMS').write_bytes(sums);(build/'COMMITTED').write_bytes((f.sha(sums)+'\n').encode());return
    if name in paths:(build/paths[name]).write_bytes(b'changed\n')
    elif name=='extra-file':(build/'unexpected').write_bytes(b'x')
    elif name=='extra-empty-dir':(build/'unexpected').mkdir()
    elif name=='frozen-index':next((build/'recovery-index').rglob('snapshot.json')).write_bytes(b'{}')

def exercise(build,binary,inputs,scope,history,output,scratch):
    output.mkdir();matrix={};accepted={};rejected={}
    # Only scratch copies change. Reset these unsealed copies between processes.
    for name in CASES+ARCHIVE_CASES:
        case=output/name;case.mkdir();host=case/'host';host.mkdir();store=shared.namespace(case/'namespace',scope,history);ident=shared.job(store);foreign=shared.job(store);store.issue(ident);store.consume(ident)
        current=scratch/'current';current_build=scratch/'current-build';shutil.copytree(inputs,current);shutil.copytree(build,current_build)
        config=dict(case=name,build=str(current_build),repository=str(current/'repository'),cards=str(current/'cards'),ledger=str(current/'ledger'),records=str(current/'records'),job=str(store.root/'jobs'/ident),foreign_job=str(store.root/'jobs'/foreign/'job.json'),host=str(host),binding=store.binding(ident))
        f.exclusive(case/'config.json',f.encode(config));f.exclusive(case/'case-info.json',f.encode(dict(job_id=ident,foreign_job_id=foreign)))
        if name in ARCHIVE_CASES:tamper(current_build,name)
        r=subprocess.run([str(binary),str(case/'config.json')],capture_output=True,text=True,timeout=60);f.exclusive(case/'native.stdout',r.stdout.encode());f.exclusive(case/'native.stderr',r.stderr.encode());f.require(r.returncode==0 and not r.stderr,'native scope case failed '+name+': '+r.stderr)
        row=json.loads(r.stdout);f.exclusive(case/'summary.json',f.encode(row));matrix[name]=row
        f.require(row['calls']['iso_submissions']<=2 and row['calls']['burst_triggers']<=2 and row['calls']['aborts']<=1,'native limits exceeded')
        if name in ARCHIVE_CASES:f.require(row['initial_core'] is False and row['calls']['wait_creates']==row['calls']['opens']==0,'bad archive reached wait/SDK')
        try:accepted[name]=analyze_combined(case,scope,row)
        except (ValueError,OSError,KeyError,TypeError) as e:rejected[name]=str(e)
        shutil.rmtree(current);shutil.rmtree(current_build)
    f.require(set(accepted)=={'normal','queued-delay'} and len(rejected)==26,'combined classification differs')
    for name in ('during-pending-source','stopped-pending-source'):f.require(matrix[name]['full_checks_skipped_while_pending'] is True,'hashed while operation pending')
    for name in ('live-source-afterprepare','restored-after-observed','new-recovery','baseline-drift','legacy-drift','foreign-job','own-native-context','new-empty-job','unknown-shared-file'):
        f.require(matrix[name]['calls']['iso_submissions']==0,'stale inputs reached ISO '+name)
    for name in ('during-pending-source','stopped-pending-source','between-epochs-source'):f.require(matrix[name]['calls']['iso_submissions']==1,'stale inputs reached second ISO '+name)
    f.require(matrix['after-final-source']['final']['stale'] is True and matrix['after-final-source']['final']['saved'] is False,'post-final drift kept checkpoint current')
    return dict(matrix=matrix,accepted=accepted,rejected=rejected)

def combined_negatives(normal,scope,row,output):
    output.mkdir();rejected={}
    for name in ('context-mix','identity-mix','binding-mix'):
        case=output/name;shutil.copytree(normal,case);folder=case/'namespace/jobs'/f.load(case/'case-info.json')['job_id'];selection=f.load(folder/'native-sdk-claim.json')
        if name=='context-mix':
            context=f.load(folder/'native-context.json');context['pid']=124;(folder/'native-context.json').write_bytes(f.encode(context));digest=f.sha(f.read(folder/'native-context.json'));process=f.load(folder/'native-process-claim.json');process.update(pid=124,context_sha256=digest);(folder/'native-process-claim.json').write_bytes(f.encode(process));selection.update(pid=124,context_sha256=digest,process_sha256=f.sha(f.read(folder/'native-process-claim.json')))
        elif name=='identity-mix':selection['identity'].update(device_id=201,interface_id=202)
        else:
            for p in (case/'host').rglob('*'):
                if p.is_file() and p.suffix in ('.json','.jsonl'):p.write_bytes(p.read_bytes().replace(scope['build_manifest_sha256'].encode(),b'e'*64))
            checkpoint=case/'host/entry-final';sums=''.join(f.sha((checkpoint/n).read_bytes())+'  '+n+'\n' for n in ('driver.json','entry.json','receipt-status.json')).encode();(checkpoint/'SHA256SUMS').write_bytes(sums);(checkpoint/'COMMITTED').write_bytes((f.sha(sums)+'\n').encode())
        (folder/'native-sdk-claim.json').write_bytes(f.encode(selection))
        # Each separate analyzer still accepts. Only the joined claims reject.
        shared_analyze(case/'namespace',f.load(case/'case-info.json')['job_id'],scope,row['native']);entry_analyze(case/'host')
        try:analyze_combined(case,scope,row)
        except ValueError as e:rejected[name]=str(e)
        else:raise ValueError('mixed native/entry chain accepted')
    f.require(rejected=={'context-mix':'native/entry context differs','identity-mix':'native/entry selected identity differs','binding-mix':'entry/consumption binding differs'},'mixed-chain rejection differs');return rejected

def file_modes(build,output,live=True):
    output.mkdir();rows={}
    for name,args,code in (('describe',['--describe'],0),('archive',['--check-archive',str(build)],0),*((('current',['--check-build',str(build)],0),) if live else ()),('context',['--inspect-context'],0),('acquire',['--acquire'],2)):
        r=subprocess.run([str(build/'verified-entry'),*args],capture_output=True,text=True,timeout=30);f.exclusive(output/(name+'.stdout'),r.stdout.encode());f.exclusive(output/(name+'.stderr'),r.stderr.encode());f.require(r.returncode==code,'file mode failed '+name);rows[name]=dict(returncode=r.returncode,result=json.loads(r.stdout) if r.stdout else None)
    return rows

def run(output):
    output=w.canonical(output);f.require(not output.exists(),'new review required');output.mkdir();builder.build(output/'build');scope=builder.runtime_scope(output/'build');d=f.load(output/'build/descriptor.json')
    # Obtain the exact frozen legacy history list, without inventing range rows.
    history=builder.authority.inputs()[4];f.exclusive(output/'history.json',f.encode(history));f.exclusive(output/'scope.json',f.encode(scope));template(output/'build',output/'inputs');generate(output/'build',output/'native-work')
    cmd=builder.compile_command(output/'native-work',output/'native-test',True);r=subprocess.run(cmd,capture_output=True,text=True);f.exclusive(output/'native-compile.log',(r.stdout+r.stderr).encode());f.require(r.returncode==0,'native scope compile failed')
    modes=file_modes(output/'build',output/'file-modes')
    with tempfile.TemporaryDirectory(prefix='a23-verifier-',dir='/private/tmp') as tmp:
        tmp=Path(tmp);rows=exercise(output/'build',output/'native-test',output/'inputs',scope,history,tmp/'cases',tmp);bad=combined_negatives(tmp/'cases/normal',scope,rows['matrix']['normal'],tmp/'negative');shutil.copytree(tmp/'cases',output/'cases');shutil.copytree(tmp/'negative',output/'negative')
    f.require(builder.authority.sources()==d['source_hashes'],'source changed during audit')
    report=dict(schema='A23-scope-verifier-audit-1',passed=True,source_count=len(d['source_hashes']),source_hashes=d['source_hashes'],prior_sources_unchanged=359,native_cases=len(CASES)+len(ARCHIVE_CASES),archive_cases=len(ARCHIVE_CASES),file_modes=modes,compiler_command=cmd,native_inputs=list(builder.NATIVE),sanitizers=['address','undefined'],combined_negative_archives=bad,**rows,usb_requests=0,sd_accesses=0,real_sdk_objects=0,formal_records=0,formal_reservations=0,hardware_verified=False,firmware_built=False,acquisition_mode_implemented=False,formal_issuance_available=False)
    f.exclusive(output/'audit.json',f.encode(report));w.b.seal(output);return dict(reference=w.reference(output),sources=len(d['source_hashes']),native_cases=report['native_cases'],accepted=list(rows['accepted']),passed=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);print(json.dumps(run(p.parse_args().output),indent=2))
