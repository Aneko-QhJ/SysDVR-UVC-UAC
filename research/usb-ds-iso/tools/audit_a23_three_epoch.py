"""Compile and exercise only injected fixed-three SDK resources and driver."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import struct
import tempfile
import types
import uuid

import a23_three_epoch_candidate as candidate

ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parents[1];A=ROOT/'private/analysis'
PARENT=A/'A23-three-epoch-scope-review-20261023'
LIVE=A/'A23-live91-checked-review-20261022-r2/build'
NEW=('tools/a23_three_epoch_candidate.py','tools/audit_a23_three_epoch.py','tests/a23_three_epoch_fixture.inc','tests/test_a23_three_epoch.py')
CASES=('normal','fail-0','fail-1','fail-2','third-before-first','reuse-first','reuse-second',
       'alias-third-data','alias-third-rows','third-storage-change','late-first','late-second',
       'third-save-collision','third-status-collision','third-timeout','detach-before-third',
       'fourth-status','fourth-submit','old-after-third')
NATIVE=('io_usb_host_transaction_owner.m','io_usb_host_runtime_guard.m','io_usb_host_evidence.m',
        'io_usb_host_session.m','io_usb_host_sdk_adapter.m','a23_two_epoch_receiver.m',
        'a23_triple_sdk_adapter.m','a23_three_epoch_sdk_driver.m')

def sha(b):return hashlib.sha256(b).hexdigest()
def load(p):return json.loads(p.read_bytes())
def write(p,v):p.write_text(json.dumps(v,sort_keys=True,indent=2)+'\n')
def verify_seal(p):
    raw=(p/'SHA256SUMS').read_bytes();assert (p/'COMMITTED').read_text().strip()==sha(raw)
    for line in raw.decode().splitlines():
        h,n=line.split('  ',1);assert not Path(n).is_absolute() and '..' not in Path(n).parts
        assert sha((p/n).read_bytes())==h,(p,n)
    return sha(raw)
def seal(p):
    # Nested manifests are themselves evidence; only omit this directory's seal.
    rows=[f for f in sorted(p.rglob('*')) if f.is_file() and f not in (p/'SHA256SUMS',p/'COMMITTED')]
    raw=''.join(sha(f.read_bytes())+'  '+f.relative_to(p).as_posix()+'\n' for f in rows).encode()
    (p/'SHA256SUMS').write_bytes(raw);(p/'COMMITTED').write_text(sha(raw)+'\n');return sha(raw)
def sources():
    verify_seal(PARENT);old=load(PARENT/'source-hashes.json');assert len(old)==615
    for n,h in old.items():assert sha((REPO/n).read_bytes())==h,n
    return dict(sorted((old|{'research/usb-ds-iso/'+n:sha((ROOT/n).read_bytes()) for n in NEW}).items()))
def guards():
    prior=A/'A23-archive-read-view-closeout-20261023'
    for n,h in load(prior/'protected-hashes.json').items():assert sha(Path(n).read_bytes())==h,n
    for tag,root in [('81','sequence-reservations32'),('113','sequence-reservations32-113'),('145','sequence-reservations32-145')]:
        p=ROOT/'private'/root
        assert {f.relative_to(p).as_posix():sha(f.read_bytes()) for f in p.rglob('*') if f.is_file()}==load(prior/('namespace'+tag+'-hashes.json'))
    assert (A/'A23-live91-checked-once-20261022-r1.json').read_bytes()==(prior/'once145-record-unchanged.json').read_bytes()
    p=load(A/'A23-context65-pending.json');assert p['remaining']==p['live91_remaining']==0 and not p['acquisition_enabled']

def fixture(root):
    parts=[]
    for name in ('a23_two_epoch_receiver_test.m','a23_paired_sdk_fixture.inc','a23_two_epoch_sdk_fixture.inc'):
        raw=(root/'tests'/name).read_text().split('\nint main(')[0]
        if name=='a23_two_epoch_receiver_test.m':
            raw=raw.replace('_submissions<2','_submissions<3').replace('_triggers<2','_triggers<3')
            raw=raw.replace('81+_triggers*16','177+_triggers*16').replace('81+n*16','177+n*16')
            raw=candidate.change(raw,'_isoCallbacks=[NSMutableArray new];',
                '_dataStores=[_dataStores arrayByAddingObject:[NSMutableData dataWithLength:184320]];\n        _transactionStores=[_transactionStores arrayByAddingObject:[NSMutableData dataWithLength:26880]];\n        _isoCallbacks=[NSMutableArray new];')
        if name=='a23_paired_sdk_fixture.inc':raw=raw.replace('n<4 && length','n<6 && length').replace('firstSequence:81','firstSequence:177')
        parts.append(candidate.names(raw))
    return '\n'.join(parts)+'\n'+(root/'tests/a23_three_epoch_fixture.inc').read_text()

def engine_model(text, folder):
    # Derived model has no formal branch; historical consumption is read-only input.
    m=types.ModuleType('fixed48_model');m.__file__=str(folder/'fixed48.py');exec(compile(text,m.__file__,'exec'),m.__dict__)
    f=m.f;old=A/'A23-archive-read-view-closeout-20261023';prior=load(ROOT/'private/sequence-reservations32-145/history.json')
    record=A/'A23-live91-checked-once-20261022-r1.json';burn=ROOT/'private/sequence-reservations32-145/block-00145.json'
    h=prior+[dict(first=n,last=n+15,reservation_sha256=sha(burn.read_bytes()),record_sha256=sha(record.read_bytes())) for n in (145,161)]
    assert f.history(h)==set(range(49,177))
    scope={k:'1'*64 for k in m.SCOPE_HASHES};scope.update({k:False for k in m.SCOPE_FLAGS});scope.update(schema='A23-shared48-scope-1',first_sequence=177,last_sequence=224,history_sha256=f.sha(f.encode(h)))
    s=m.SharedSequence48(folder/'namespace',simulation=True,fresh_scope=lambda:scope);s.initialize(h)
    job=str(uuid.uuid4());ns=s.validate();auth=dict(schema='A23-shared48-authorization-1',job_id=job,scope_sha256=ns['scope_sha256'],maximum_invocations=1,simulation=True,hardware_test_authorized=False)
    s.prepare(job,auth);s.issue(job);s.consume(job);v=m.check_burn(s.root,job);assert v['count']==48 and (v['first'],v['last'])==(177,224)
    before={p.relative_to(s.root).as_posix():sha(p.read_bytes()) for p in s.root.rglob('*') if p.is_file()}
    rejected=[]
    for name,call in [('reconsume',lambda:s.consume(job)),('reissue',lambda:s.issue(job)),('formal',lambda:m.SharedSequence48(folder/'formal',simulation=False,fresh_scope=lambda:scope)),('old-scope',lambda:m.scope(dict(scope,schema='A23-shared32-scope-1')))]:
        try:call()
        except (ValueError,OSError):rejected.append(name)
        else:raise AssertionError('model accepted '+name)
    assert before=={p.relative_to(s.root).as_posix():sha(p.read_bytes()) for p in s.root.rglob('*') if p.is_file()}
    return dict(history_first=49,history_last=176,first=177,last=224,count=48,rejected=rejected,simulation=True)

def run(out):
    out=out.resolve();assert not out.exists();hashes=sources();guards();verify_seal(LIVE)
    out.mkdir(mode=0o700);completed=[]
    try:
        write(out/'source-hashes.json',hashes)
        for n,h in hashes.items():
            p=out/'source'/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((REPO/n).read_bytes());assert sha(p.read_bytes())==h
        native=out/'native';shutil.copytree(out/'source',native);r=native/'research/usb-ds-iso'
        generated={
            'host/a23_three_epoch_sdk_driver.h':candidate.names((r/'host/a23_two_epoch_sdk_driver.h').read_text()),
            'host/a23_triple_sdk_adapter.h':candidate.names((r/'host/a23_paired_sdk_adapter.h').read_text()),
            'host/a23_three_epoch_sdk_driver.m':candidate.driver((LIVE/'generated/live_driver.m').read_text()),
            'host/a23_triple_sdk_adapter.m':candidate.adapter((r/'host/a23_paired_sdk_adapter.m').read_text()),
            'tools/analyze_fixed_three.py':candidate.analyzer((LIVE/'generated/a23_live75_sdk_analysis.py').read_text()),
            'tools/fixed48_model.py':candidate.engine((r/'tools/a23_shared_sequence32.py').read_text()),
        }
        for n,text in generated.items():(r/n).write_text(text)
        (r/'tests/generated_three.m').write_text(fixture(r))
        cmd=['clang','-fobjc-arc','-fblocks','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer','-g',
             '-framework','Foundation','-framework','IOUSBHost','-framework','IOKit',*[str(r/'host'/n) for n in NATIVE],str(r/'tests/generated_three.m'),'-o',str(out/'three-fixture')]
        p=subprocess.run(cmd,capture_output=True,timeout=60);(out/'compile.stdout').write_bytes(p.stdout);(out/'compile.stderr').write_bytes(p.stderr);write(out/'compile.json',dict(command=cmd,returncode=p.returncode));assert p.returncode==0,'compile failed'
        spec=importlib.util.spec_from_file_location('fixed_three_analysis',r/'tools/analyze_fixed_three.py');sdk=importlib.util.module_from_spec(spec);spec.loader.exec_module(sdk)
        matrix={};accepted={};models=out/'models';models.mkdir()
        for case in CASES:
            folder=models/case;folder.mkdir();p=subprocess.run([str(out/'three-fixture'),case,str(folder)],capture_output=True,timeout=30)
            (folder/'native.stdout').write_bytes(p.stdout);(folder/'native.stderr').write_bytes(p.stderr);write(folder/'process.json',dict(returncode=p.returncode,creator_wait_completed=True))
            assert p.returncode==0 and not p.stderr,'native failed '+case
            row=json.loads(p.stdout);matrix[case]=row
            if case=='normal':
                accepted[case]=sdk.analyze(folder);assert accepted[case]['total_bytes']==9216
            else:
                assert row['init_rejected'] or row['result']['stopped']
                if case.startswith('fail-'):assert row['iso_submissions']==int(case[-1])+1
                if case in ('third-before-first','late-first','late-second','third-storage-change','detach-before-third'):assert row['iso_submissions']==2
                try:sdk.analyze(folder)
                except (ValueError,OSError):pass
                else:raise AssertionError('failed run accepted '+case)
            completed.append(case)
        negative={}
        for kind in ('two-epochs','four-epochs','third-raw','third-urb-first','third-urb-second'):
            folder=out/('negative-'+kind);shutil.copytree(models/'normal',folder)
            if kind=='two-epochs':shutil.rmtree(folder/'epoch-2')
            elif kind=='four-epochs':shutil.copytree(folder/'epoch-2',folder/'epoch-3')
            elif kind=='third-raw':
                p=folder/'epoch-2/raw.bin';b=bytearray(p.read_bytes());b[240*192]^=1;p.write_bytes(b);seal(folder/'epoch-2')
            else:
                p=folder/'epoch-2/after.bin';b=bytearray(p.read_bytes());urb=501 if kind=='third-urb-first' else 502
                struct.pack_into('<II',b,20,urb,urb);p.write_bytes(b);seal(folder/'epoch-2')
                capture=folder/'status-after-epoch-2';(capture/'raw.bin').write_bytes(b)
                v=load(capture/'verdict.json');v['raw_sha256']=sha(b);write(capture/'verdict.json',v);seal(capture)
            try:sdk.analyze(folder)
            except (ValueError,OSError) as e:negative[kind]=str(e)
            else:raise AssertionError('invalid archive accepted '+kind)
        with tempfile.TemporaryDirectory(prefix='a23-fixed48-',dir='/private/tmp') as tmp:
            permit=engine_model(generated['tools/fixed48_model.py'],Path(tmp));shutil.copytree(tmp,out/'permit-model')
        assert sources()==hashes;guards()
        write(out/'report.json',dict(schema='A23-three-epoch-offline-1',passed=True,source_count=len(hashes),old615_unchanged=True,completed=completed,matrix=matrix,accepted=accepted,negative_archives=negative,permit_model=permit,
            compiler_jobs=1,creator_waited_native_processes=len(completed),usb_requests=0,sd_accesses=0,real_sdk_objects=0,formal_reservations=0,new_authorizations=0,remaining=0,hardware_ready=False,current97_live_scope_implemented=False,checked_export_controller_integrated=False))
    except BaseException as e:
        write(out/'failure.json',dict(error=str(e),type=type(e).__name__,completed=completed));seal(out);raise
    seal(out);return dict(directory=str(out),manifest_sha256=verify_seal(out),native_cases=len(completed),source_count=len(hashes),passed=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);print(json.dumps(run(p.parse_args().output),indent=2))
