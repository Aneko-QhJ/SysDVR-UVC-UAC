"""Two sealed roles for one fake-SDK child binary. No production entry mode."""
import argparse,copy,json,shutil,subprocess
from pathlib import Path
import build_a23_supervisor_model as prior
import build_a23_verified_entry as receiver
import a23_supervisor_archive as supervision
w=prior.w;f=supervision.f
PARENT=w.A/'A23-supervisor-closeout-20261019';PARENT_SUM='68455a7a03ece170cd4be4bace1bf3a9588117856098da6a5ca308b09583b276'
NEW=('tools/a23_broker_supervision.py','tests/a23_broker_model_fixture.m','tools/build_a23_broker_model.py','tools/a23_broker_model.py','tools/a23_broker_archive.py','tools/audit_a23_broker_model.py','tests/test_a23_broker_model.py')
def sources():
    w.card.seal_verify(PARENT);f.require(f.sha(w.plain(PARENT/'SHA256SUMS'))==PARENT_SUM,'parent closeout differs');c=w.load(PARENT/'closeout.json');out=prior.sources();f.require(out==c['source_hashes'] and len(out)==378,'prior378 drift')
    for n,h in c['protected_sha256'].items():f.require(f.sha(w.plain(Path(n)))==h,'protected drift')
    f.require(c['actual_ledger_sha256']=={p.name:f.sha(w.plain(p)) for p in w.LEDGER.iterdir() if p.is_file()},'real ledger drift')
    for n in NEW:key='research/usb-ds-iso/'+n;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/n))
    return dict(sorted(out.items()))
def generate(source):
    r=Path(source)/'research/usb-ds-iso/tests';parts=[]
    for name in ('a23_two_epoch_receiver_test.m','a23_paired_sdk_fixture.inc','a23_two_epoch_sdk_fixture.inc','a23_two_epoch_entry_fixture.inc'):
        text=(r/name).read_text();f.require(text.count('\nint main(')==1,'fixture prefix differs');parts.append(text.split('\nint main(',1)[0])
    parts.append((r/'a23_broker_model_fixture.m').read_text());return '\n'.join(parts).encode()
def command(build,generated,binary):
    r=Path(build)/'source/research/usb-ds-iso/host'
    return ['clang','-fobjc-arc','-fblocks','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer','-g','-I'+str(build),'-I'+str(r.parent/'tests'),'-framework','Foundation','-framework','IOUSBHost','-framework','IOKit',*(str(r/n) for n in receiver.NATIVE),str(generated),'-o',str(binary)]
def build(root):
    root=w.canonical(root);f.require(not root.exists(),'new broker build root required');source=sources();d,saved,history,index,h=receiver.authority.inputs();d=copy.deepcopy(d);d.update(source_hashes=source,workflow_source_sha256=f.sha(f.encode(source)),parent_manifest_sha256=PARENT_SUM);d['description']=dict(schema='A23-broker-model-description-1',modes=['--model'],model_only=True,acquisition_mode_implemented=False,formal_issuance_available=False,hardware_entry_enabled=False)
    root.mkdir(mode=0o700);target=root/'receiver-build';target.mkdir();w.card.put(target,'descriptor.json',f.encode(d));w.card.put(target,'a23_verified_binding.h',receiver.header(d))
    for n,digest in source.items():raw=w.plain(w.b.REPO/n,2*1024*1024);f.require(f.sha(raw)==digest,'source drift');w.card.put(target,'source/'+n,raw)
    for prefix,files in (('baseline',saved),('history',history),('recovery-index',index)):
        for n,raw in files.items():w.card.put(target,prefix+'/'+n,raw)
    # Generated file lives next to the frozen test prefixes so relative includes
    # resolve; the compile work copy is not a sealed or reusable build.
    work=root/'compile-work';shutil.copytree(target/'source',work/'source');generated=work/'source/research/usb-ds-iso/tests/generated-broker.m';generated.write_bytes(generate(target/'source'));w.card.put(root,'generated-broker.m',generated.read_bytes());cmd=command(target,generated,target/'verified-entry');r=subprocess.run(cmd,capture_output=True,text=True);w.card.put(target,'compile.log',(r.stdout+r.stderr).encode());f.require(r.returncode==0,'broker fake SDK compile failed');shutil.rmtree(work)
    symbols=target/'verified-entry.dSYM'
    if symbols.exists():shutil.move(str(symbols),str(root/'receiver-symbols.dSYM'))
    sha=f.sha(supervision.a.read(target/'verified-entry'));w.write(target/'binary.json',dict(schema='A23-verified-entry-binary-1',receiver_sha256=sha,descriptor_sha256=f.sha(f.encode(d))));w.write(target/'build-command.json',dict(command=cmd));w.b.seal(target)
    model=root/'supervisor-build';model.mkdir();shutil.copytree(target/'source',model/'source');shutil.copyfile(target/'verified-entry',model/'model-child');(model/'model-child').chmod(0o700);w.card.put(model,'compile.log',b'Identical binary copied from sibling receiver-build; descriptor contains frozen fake operations.\n');w.write(model/'build.json',dict(schema='A23-supervisor-model-build-1',source_hashes=source,binary_sha256=sha,model_only=True));w.b.seal(model)
    w.write(root/'history.json',h);f.require(sources()==source,'sources changed during broker build');w.b.seal(root);return w.reference(root)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);print(json.dumps(build(p.parse_args().output),indent=2))
