#!/usr/bin/env python3
"""Verify/seal the prepared package and compile a dormant single-use entry."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from build_a23_short24_candidate import verify_tree
from package_a23_short24 import PATHS, CONTENT, PATCH, pfs_files, verify_nso, verify_npdm

ROOT=Path(__file__).resolve().parents[1]
A=ROOT/'private/analysis'
PACKAGE=A/'A23-short24-package-20261027-r1'
SDK=A/'A23-short24-sdk-20261027-r5'
CANDIDATE=A/'A23-short24-candidate-20261027-r2'


def require(v,m):
    if not v:raise ValueError(m)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def seal(root):
    files=sorted(p for p in root.rglob('*') if p.is_file())
    raw=''.join(sha(p.read_bytes())+'  '+p.relative_to(root).as_posix()+'\n' for p in files).encode()
    for name,data in [('SHA256SUMS',raw),('COMMITTED',(sha(raw)+'\n').encode())]:
        with (root/name).open('xb') as f:f.write(data)
    return sha(raw)


def build(output):
    output=output.resolve();require(not output.exists(),'fresh entry build required')
    parent_seals={str(p):verify_tree(p) for p in (SDK,CANDIDATE)}
    sdk=json.loads((SDK/'report.json').read_text())
    for n,h in sdk['source_hashes'].items():require(sha((ROOT/n).read_bytes())==h,'SDK source drift: '+n)
    report=json.loads((PACKAGE/'package-report.json').read_text())
    elf=(PACKAGE/'device/full.elf').read_bytes();nso=(PACKAGE/'exefs/main').read_bytes();npdm=(PACKAGE/'exefs/main.npdm').read_bytes()
    nsp=(PACKAGE/'exefs.nsp').read_bytes()
    require(elf==(CANDIDATE/'device/full.elf').read_bytes(),'packaged ELF differs')
    require(verify_nso(elf,nso)==report['conversion'] and verify_npdm(npdm)==report['npdm'] and
            pfs_files(nsp)=={'main':nso,'main.npdm':npdm} and sha(nsp)==report['exefs_nsp_sha256'],'package roundtrip differs')
    snapshot=Path(report['last_recovered_snapshot']);require(verify_tree(snapshot)==report['snapshot_manifest_sha256'],'recovered baseline differs')
    for n in PATHS:
        before=(PACKAGE/'rollback-review'/n).read_bytes();after=(PACKAGE/'sd-review'/n).read_bytes()
        require(before==(snapshot/'card'/n).read_bytes(),'rollback differs: '+n)
        expected=nsp if n==CONTENT+'exefs.nsp' else (CANDIDATE/'controller/A'/PATCH).read_bytes() if n==PATCH else before
        require(after==expected and sha(after)==report['deployment_files'][n]['after_sha256'],'deployment pair differs: '+n)
    package_seal=verify_tree(PACKAGE) if (PACKAGE/'COMMITTED').exists() else seal(PACKAGE)
    output.mkdir(parents=True)
    values=dict(A23LaunchRecipe=report['recipe'],A23LaunchPackageManifest=package_seal,A23LaunchNSP=report['exefs_nsp_sha256'],
        A23LaunchIPS=report['controller_ips_sha256'],A23LaunchBaseline=report['snapshot_manifest_sha256'],A23LaunchPrivate=str(ROOT/'private'))
    header='/* Generated from file-verified short24 pair, no authorization. */\n'+''.join(
        'static NSString *const '+n+'=@'+json.dumps(v)+';\n' for n,v in values.items())
    (output/'a23_short24_launch_config.h').write_text(header)
    command=['clang','-std=gnu11','-fobjc-arc','-fblocks','-Wall','-Wextra','-Werror','-Wno-deprecated-declarations',
        '-mmacosx-version-min=26.4','-I'+str(output),str(ROOT/'host/a23_short24_capture.m'),
        str(ROOT/'host/a23_short24_runtime.m'),str(ROOT/'host/a23_short24_entry_main.m'),
        '-framework','Foundation','-framework','IOKit','-framework','IOUSBHost','-o',str(output/'short24-receiver')]
    result=subprocess.run(command,capture_output=True);(output/'compile.log').write_bytes(result.stdout+result.stderr)
    require(result.returncode==0,'entry compilation failed; see compile.log')
    description=subprocess.run([str(output/'short24-receiver'),'--describe'],check=True,capture_output=True,text=True)
    (output/'description.json').write_text(description.stdout)
    names=['host/a23_short24_runtime.h','host/a23_short24_runtime.m','host/a23_short24_entry_main.m',
           'tools/package_a23_short24.py','tools/build_a23_short24_entry.py']
    metadata=dict(schema='A23-short24-entry-build-1',package_manifest_sha256=package_seal,
        parent_seals=parent_seals,source_hashes={**sdk['source_hashes'],**{n:sha((ROOT/n).read_bytes()) for n in names}},
        receiver_sha256=sha((output/'short24-receiver').read_bytes()),compiler_command=command,
        description=json.loads(description.stdout),authorization_issued=False,range_reserved=False,
        sdk_objects_created=0,usb_operations=0,sd_accesses=0,deployed=False)
    (output/'build.json').write_text(json.dumps(metadata,indent=2,sort_keys=True)+'\n')
    return metadata


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    result=build(parser.parse_args().output)
    print(json.dumps({k:result[k] for k in ('authorization_issued','range_reserved','sdk_objects_created')}))
