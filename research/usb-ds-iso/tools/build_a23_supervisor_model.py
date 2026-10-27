"""Freeze sources and compile a context-only model helper, never a receiver."""
import argparse,json,subprocess
from pathlib import Path
import audit_a23_two_epoch_final as prior
import a23_supervisor_archive as v
w=prior.w;f=v.f
PARENT=w.A/'A23-final-closeout-20261019';PARENT_SUM='b9851a6f28e618255a1f4a035f1c3f212624d0965bfd520f8c3d3c15e66a0c39'
NEW=('host/a23_supervisor_model_main.m','tools/a23_model_supervisor.py','tools/a23_supervisor_archive.py','tools/build_a23_supervisor_model.py','tools/audit_a23_model_supervisor.py','tests/test_a23_model_supervisor.py')
def sources():
    w.card.seal_verify(PARENT);f.require(f.sha(w.plain(PARENT/'SHA256SUMS'))==PARENT_SUM,'parent closeout differs');c=w.load(PARENT/'closeout.json');out=prior.sources();f.require(out==c['source_hashes'] and len(out)==372,'prior372 drift')
    for n,h in c['protected_sha256'].items():f.require(f.sha(w.plain(Path(n)))==h,'protected drift')
    f.require(c['actual_ledger_sha256']=={p.name:f.sha(w.plain(p)) for p in w.LEDGER.iterdir() if p.is_file()},'actual ledger drift')
    for n in NEW:key='research/usb-ds-iso/'+n;f.require(key not in out,'new source overlap');out[key]=f.sha(w.plain(w.ROOT/n))
    return dict(sorted(out.items()))
def command(source,binary):
    host=Path(source)/'research/usb-ds-iso/host'
    return ['clang','-fobjc-arc','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer','-g','-framework','Foundation','-framework','IOUSBHost','-framework','IOKit',str(host/'a23_execution_context.m'),str(host/'a23_supervisor_model_main.m'),'-o',str(binary)]
def build(root):
    root=w.canonical(root);f.require(not root.exists(),'new model build required');source=sources();root.mkdir(mode=0o700)
    for n,h in source.items():raw=w.plain(w.b.REPO/n,2*1024*1024);f.require(f.sha(raw)==h,'source drift');w.card.put(root,'source/'+n,raw)
    cmd=command(root/'source',root/'model-child');r=subprocess.run(cmd,capture_output=True,text=True);w.card.put(root,'compile.log',(r.stdout+r.stderr).encode());f.require(r.returncode==0,'context model compile failed')
    # Debug symbols are diagnostics outside this strictly inventoried build.
    import shutil
    symbols=root/'model-child.dSYM'
    if symbols.exists():shutil.move(str(symbols),str(root.parent/(root.name+'-symbols.dSYM')))
    w.write(root/'build.json',dict(schema='A23-supervisor-model-build-1',source_hashes=source,binary_sha256=f.sha(v.a.read(root/'model-child')),model_only=True));f.require(sources()==source,'source changed during model build');w.b.seal(root);v.build_info(root);return w.reference(root)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);print(json.dumps(build(p.parse_args().output),indent=2))
