"""Build a file-only verified entry, retaining all dormant SDK components."""
import argparse,json,subprocess
from pathlib import Path
import a23_verified_scope as authority
import build_a23_two_epoch_entry as old
from a23_sequence32_model import encode,sha,require
w=authority.w
NATIVE=tuple(n for n in old.NATIVE if n!='a23_two_epoch_entry_build.m')+('a23_shared_sequence_permit.m','a23_scope_verifier.m')

def header(d):
    raw=encode(d);return ('static const unsigned char A23VerifiedDescriptor[]={'+','.join(str(n) for n in raw)+'};\n').encode()

def compile_command(build,binary,fixture=False):
    build=Path(build);r=build/'source/research/usb-ds-iso'
    return ['clang','-fobjc-arc','-fblocks','-Wall','-Wextra','-Werror',*(['-fsanitize=address,undefined','-fno-omit-frame-pointer','-g'] if fixture else ['-O2']),
        '-I'+str(build),'-framework','Foundation','-framework','IOUSBHost','-framework','IOKit',*(str(r/'host'/n) for n in NATIVE),
        str(r/('tests/generated_scope_verifier_test.m' if fixture else 'host/a23_verified_entry_main.m')),'-o',str(binary)]

def build(output):
    output=w.canonical(output);require(not output.exists(),'new verified build required');d,saved,history,index,h=authority.inputs();output.mkdir(mode=0o700)
    w.card.put(output,'descriptor.json',encode(d));w.card.put(output,'a23_verified_binding.h',header(d))
    for n,digest in d['source_hashes'].items():
        raw=w.plain(w.b.REPO/n,2*1024*1024);require(sha(raw)==digest,'source drift');w.card.put(output,'source/'+n,raw)
    for prefix,files in (('baseline',saved),('history',history),('recovery-index',index)):
        for n,raw in files.items():w.card.put(output,prefix+'/'+n,raw)
    command=compile_command(output,output/'verified-entry');r=subprocess.run(command,capture_output=True,text=True);w.card.put(output,'compile.log',(r.stdout+r.stderr).encode());require(r.returncode==0,'verified build compile failed')
    w.write(output/'binary.json',dict(schema='A23-verified-entry-binary-1',receiver_sha256=sha(w.plain(output/'verified-entry',64*1024*1024)),descriptor_sha256=sha(encode(d))))
    w.write(output/'build-command.json',dict(command=command));require(authority.inputs()[0]==d,'authority drift');w.b.seal(output);w.card.seal_verify(output)
    return w.reference(output)

def runtime_scope(build):
    build=Path(build);w.card.seal_verify(build);d=w.load(build/'descriptor.json');record=w.load(build/'binary.json')
    return dict(schema='A23-shared32-scope-1',baseline_manifest_sha256=d['baseline_manifest_sha256'],baseline_inventory_sha256=d['baseline_inventory_sha256'],workflow_source_sha256=d['workflow_source_sha256'],
        build_manifest_sha256=sha(w.plain(build/'SHA256SUMS')),receiver_sha256=record['receiver_sha256'],device_binding_sha256=d['device_binding_sha256'],recipe_sha256=d['recipe_sha256'],history_sha256=d['history_sha256'],
        first_sequence=81,last_sequence=112,formal_issuance_available=False,acquisition_mode_implemented=False,hardware_entry_enabled=False)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);print(json.dumps(build(p.parse_args().output),indent=2))
