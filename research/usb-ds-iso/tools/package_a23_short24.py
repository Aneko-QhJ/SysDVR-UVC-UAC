#!/usr/bin/env python3
"""Package the frozen short24 ELF/IPS against the last recovered card, file-only."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from build_a23_short24_candidate import verify_tree
from build_a23_lifecycle_deployment import pfs_files, verify_nso, verify_npdm
from build_patch import BUILD_ID, validate_module, read_mapped, ips32

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "private/analysis/A23-short24-candidate-20261027-r2"
ACTUAL = ROOT / "private/analysis/A23-live132-q1-once-20261026-r1.json"
TITLE = "00FF0000A53BB666"
CONTENT = "atmosphere/contents/" + TITLE + "/"
PATCH = "atmosphere/exefs_patches/SysDVR-ISO/" + BUILD_ID + ".ips"
PATHS = (CONTENT + "exefs.nsp", PATCH, CONTENT + "flags/boot2.flag", CONTENT + "toolbox.json")


def sha(raw):return hashlib.sha256(raw).hexdigest()
def require(value, message):
    if not value:raise ValueError(message)
def put(root, name, raw):
    path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("xb") as handle:handle.write(raw)


def build(output):
    output=output.resolve();require(not output.exists(),"fresh package output required")
    build_seal=verify_tree(BUILD)
    actual=json.loads(ACTUAL.read_text());snapshot=Path(actual['card_snapshot']);snapshot_seal=verify_tree(snapshot)
    manifest=json.loads((BUILD/'controller/A/manifest.json').read_text())
    nso=validate_module((ROOT/'private/module/exefs/main').read_bytes())
    edits=manifest['edits'];patch=ips32([(int(e['address'],16),bytes.fromhex(e['after'])) for e in edits])
    require(sha(patch)==manifest['patch_sha256'] and patch==(BUILD/'controller/A'/PATCH).read_bytes(),"short24 IPS differs")
    require(all(read_mapped(nso,int(e['address'],16),len(bytes.fromhex(e['before'])))==bytes.fromhex(e['before']) for e in edits),
            "controller original bytes differ")
    baseline={n:(snapshot/'card'/n).read_bytes() for n in PATHS}
    output.mkdir(parents=True)
    for name in ('full.elf','main.npdm','sysmodule.json','recipe.json'):
        put(output,'device/'+name,(BUILD/'device'/name).read_bytes())
    (output/'exefs').mkdir();put(output,'exefs/main.npdm',(BUILD/'device/main.npdm').read_bytes())
    commands=[['/opt/devkitpro/tools/bin/elf2nso',str(output/'device/full.elf'),str(output/'exefs/main')],
              ['/opt/devkitpro/tools/bin/build_pfs0',str(output/'exefs'),str(output/'exefs.nsp')]]
    for i,command in enumerate(commands):
        result=subprocess.run(command,capture_output=True)
        put(output,f'command-{i}.log',result.stdout+result.stderr)
        require(result.returncode==0,'packaging command failed')
    raw_nso=(output/'exefs/main').read_bytes();npdm=(output/'exefs/main.npdm').read_bytes();package=(output/'exefs.nsp').read_bytes()
    conversion=verify_nso((output/'device/full.elf').read_bytes(),raw_nso)
    npdm_checked=verify_npdm(npdm)
    require(pfs_files(package)=={'main':raw_nso,'main.npdm':npdm},'PFS members differ')
    for name,raw in baseline.items():
        put(output,'rollback-review/'+name,raw)
        after=package if name==CONTENT+'exefs.nsp' else patch if name==PATCH else raw
        put(output,'sd-review/'+name,after)
    # Native installer fixture inputs are fresh synthetic images, not HOS dumps.
    original=bytearray(0x69000)
    for e in edits:
        address=int(e['address'],16);raw=bytes.fromhex(e['before']);original[address:address+len(raw)]=raw
    old=json.loads((ROOT/'private/packages-A23-interval1/A/manifest.json').read_text())
    old_image=bytearray(original);new_image=bytearray(original)
    for m,image in ((old,old_image),(manifest,new_image)):
        for e in m['edits']:
            address=int(e['address'],16);raw=bytes.fromhex(e['after']);image[address:address+len(raw)]=raw
    require(sha(baseline[PATCH])==old['patch_sha256'],'last recovered IPS is not the expected old A23')
    for name,image in [('MODEL-original.bin',original),('MODEL-old-IPS.bin',old_image),('MODEL-new-IPS.bin',new_image)]:
        put(output,name,image)
    recipe=json.loads((BUILD/'device/recipe.json').read_text())['runtime_recipe_sha256']
    report=dict(schema='A23-short24-package-1',candidate_manifest_sha256=build_seal,
        last_recovered_snapshot=str(snapshot),snapshot_manifest_sha256=snapshot_seal,recipe=recipe,
        conversion=conversion,npdm=npdm_checked,commands=commands,
        exefs_nsp_sha256=sha(package),controller_ips_sha256=sha(patch),
        deployment_files={n:dict(before_sha256=sha(baseline[n]),after_sha256=sha((output/'sd-review'/n).read_bytes()),
            changed=baseline[n]!=(output/'sd-review'/n).read_bytes()) for n in PATHS},
        deployment_requires_matching_nsp_and_ips=True,firmware_packaged=True,deployed=False,
        sd_accesses=0,usb_operations=0,remaining=0,acquisition_enabled=False,hardware_verified=False)
    put(output,'package-report.json',(json.dumps(report,indent=2,sort_keys=True)+'\n').encode())
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    result=build(parser.parse_args().output)
    print(json.dumps({k:result[k] for k in ('firmware_packaged','deployed','deployment_requires_matching_nsp_and_ips')}))
