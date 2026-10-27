"""Build a file-only inspector and dormant two-epoch entry; acquisition unavailable."""
import argparse,json,shutil,subprocess
from pathlib import Path
import audit_a23_two_epoch_sdk as prior
w=prior.w
PARENT=w.A/'A23-sdk-driver-closeout-20261018'
PARENT_SUM='d7d292045895d954a1bf91e0b21d9c141f254f109c3e8f5f0cb19a8dbd9ab84b'
NEW=('host/a23_two_epoch_entry.h','host/a23_two_epoch_entry.m','host/a23_two_epoch_entry_build.m','host/a23_two_epoch_entry_main.m',
     'tools/build_a23_two_epoch_entry.py','tools/analyze_a23_two_epoch_entry.py','tools/audit_a23_two_epoch_entry.py',
     'tests/a23_two_epoch_entry_fixture.inc','tests/test_a23_two_epoch_entry.py')
NATIVE=prior.NATIVE+('a23_two_epoch_entry.m','a23_two_epoch_entry_build.m','a23_execution_context.m','a23_passive_wait_adapter.c','a23_passive_wait_iokit.c')
DESCRIPTION=dict(schema='A23-two-epoch-entry-description-1',sdk_driver='A23TwoEpochSDKDriver',max_epochs=2,iso_limit=2,trigger_limit=2,
    observation_minimum_ns=250000000,wait_budget_ns=120000000000,prepare_and_start_separate_turns=True,
    active_resources_policy='retain_for_process_lifetime',executable_modes=['--describe','--check-build','--inspect-context'],
    acquisition_mode_implemented=False,production_permit_implemented=False,formal_issuance_available=False,hardware_entry_enabled=False,
    callback_drain_verified=False,hardware_verified=False)

def sources():
    w.card.seal_verify(PARENT);w.require(w.sha(w.plain(PARENT/'SHA256SUMS'))==PARENT_SUM,'parent closeout differs')
    current=prior.sources();w.require(len(current)==336 and current==w.load(PARENT/'closeout.json')['source_hashes'],'prior336 drift')
    for n in NEW:
        key='research/usb-ds-iso/'+n;w.require(key not in current,'new overlap');current[key]=w.sha(w.plain(w.ROOT/n))
    return dict(sorted(current.items()))

def metadata(hashes):return dict(schema='A23-two-epoch-entry-build-1',description=DESCRIPTION,source_hashes=hashes,native_inputs=list(NATIVE),
    parent_manifest_sha256=PARENT_SUM,execution_context_policy='A23-execution-context-policy-1',
    acquisition_enabled=False,formal_records=0,formal_reservations=0)

def binding_header(meta):
    raw=json.dumps(meta,sort_keys=True,separators=(',',':')).encode()
    return ('static const unsigned char A23EntryMetadata[]={'+','.join(str(n) for n in raw)+'};\n').encode()

def compile_command(build,binary,fixture=False):
    build=Path(build);root=build/'source/research/usb-ds-iso'
    return ['clang','-fobjc-arc','-fblocks','-Wall','-Wextra','-Werror',*(['-fsanitize=address,undefined','-fno-omit-frame-pointer','-g'] if fixture else ['-O2']),
        '-I'+str(build),'-framework','Foundation','-framework','IOUSBHost','-framework','IOKit',
        *(str(root/'host'/n) for n in NATIVE),str(root/('tests/generated_entry_test.m' if fixture else 'host/a23_two_epoch_entry_main.m')),'-o',str(binary)]

def build(output):
    output=w.canonical(output);w.require(not output.exists(),'new build required');hashes=sources();output.mkdir(mode=0o700)
    for n,h in hashes.items():
        raw=w.plain(w.b.REPO/n,2*1024*1024);w.require(w.sha(raw)==h,'source changed');w.card.put(output,'source/'+n,raw)
    meta=metadata(hashes);w.card.put(output,'manifest.json',json.dumps(meta,sort_keys=True,separators=(',',':')).encode())
    w.card.put(output,'a23_two_epoch_entry_binding.h',binding_header(meta));cmd=compile_command(output,output/'entry-inspector')
    r=subprocess.run(cmd,capture_output=True,text=True);w.card.put(output,'compile.log',(r.stdout+r.stderr).encode());w.require(r.returncode==0,'entry compile failed')
    record=dict(schema='A23-two-epoch-entry-binary-1',receiver_sha256=w.sha(w.plain(output/'entry-inspector',64*1024*1024)),metadata_sha256=w.sha(w.plain(output/'manifest.json')))
    w.write(output/'binary.json',record)
    described=subprocess.run([str(output/'entry-inspector'),'--describe'],capture_output=True,text=True);w.require(described.returncode==0 and json.loads(described.stdout)==DESCRIPTION,'description differs')
    checked=subprocess.run([str(output/'entry-inspector'),'--check-build',str(output)],capture_output=True,text=True);w.require(checked.returncode==0,'native build check failed')
    w.card.put(output,'describe.json',described.stdout.encode());w.card.put(output,'check-build.json',checked.stdout.encode());w.write(output/'compile-command.json',dict(command=cmd))
    w.require(sources()==hashes,'source drift');w.b.seal(output);w.card.seal_verify(output);return w.reference(output)

def verify_build(output):
    output=w.canonical(output);files=w.card.seal_verify(output);meta=w.load(output/'manifest.json');w.require(meta==metadata(sources()),'metadata mismatch')
    w.require(w.plain(output/'a23_two_epoch_entry_binding.h',1024*1024)==binding_header(meta),'binding header differs')
    for n,h in meta['source_hashes'].items():w.require(w.sha(w.plain(output/'source'/n,2*1024*1024))==h,'frozen source differs')
    expected={'manifest.json','a23_two_epoch_entry_binding.h','entry-inspector','binary.json','compile.log','describe.json','check-build.json','compile-command.json'}|{'source/'+n for n in meta['source_hashes']}
    w.require(set(files)==expected,'build inventory differs')
    row=w.load(output/'binary.json');w.require(row==dict(schema='A23-two-epoch-entry-binary-1',receiver_sha256=w.sha(w.plain(output/'entry-inspector',64*1024*1024)),metadata_sha256=w.sha(w.plain(output/'manifest.json'))),'binary record differs')
    return w.reference(output)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);print(json.dumps(build(p.parse_args().output),indent=2))
