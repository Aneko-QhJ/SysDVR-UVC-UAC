#!/usr/bin/env python3
"""Isolated full-width filesystem path candidate; never package, deploy or run ARM."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
from unittest.mock import patch
import build_a23_lifecycle_candidate as life
import lifecycle_card_workflow as w
from analyze_a23_elf_boundaries import elf_metadata
from analyze_a23_session_stack import parse_disassembly, frame

b=w.b;BASE=w.once.ANALYSIS/'A23-fs-path-span-review-20261016'
DEVICE=w.once.ANALYSIS/'A23-lifecycle-device-review-20261016/candidate'
NEW=('tools/build_a23_path_span_candidate.py','tests/test_a23_path_span_candidate.py')
FILES=('ep0_candidate_file.c','ep0_diagnostic_file.c','ep0_session_file.c','ep0_lifecycle_file.c')

def prepare(folder,recipe):
    shutil.copytree(DEVICE/'source',folder/'source');src=folder/'source/uvc'
    shutil.copyfile(b.ROOT/'device/ep0_fs_path_span.h',src/'ep0_fs_path_span.h')
    changes={
        'ep0_candidate_file.c': [('char path[96];','static char path[EP0_FS_PATH_SPAN];memset(path,0,sizeof(path));')],
        'ep0_diagnostic_file.c': [('char path[96],nonce[65];','static char path[EP0_FS_PATH_SPAN];memset(path,0,sizeof(path));char nonce[65];')],
        'ep0_session_file.c': [('char path[EP0_SESSION_PATH_BYTES];','static char path[EP0_FS_PATH_SPAN];memset(path,0,sizeof(path));'),
                              ('char path[96];','static char path[EP0_FS_PATH_SPAN];memset(path,0,sizeof(path));')],
        'ep0_lifecycle_file.c': [('static char life_path[64];','static char life_path[EP0_FS_PATH_SPAN];'),
                               ('    memcpy(life_path,"/ep0-life-",10);','    memset(life_path,0,sizeof(life_path));\n    memcpy(life_path,"/ep0-life-",10);')]}
    for name,items in changes.items():
        p=src/name;text=p.read_text()
        for old,new in items:text=life.replace(text,old,new)
        # FS_MAX_PATH is available in ARM via the ordinary SDK headers. The
        # unchanged prototype asserts its width, and models use the same value.
        text='#include "ep0_fs_path_span.h"\n'+text
        if name=='ep0_lifecycle_file.c':
            text=life.replace(text,'#include <switch.h>','#include <switch.h>\n_Static_assert(EP0_FS_PATH_SPAN==FS_MAX_PATH,"SDK path span changed");')
        else:
            text=life.replace(text,'#include "ep0_lifecycle_file.h"','#include "ep0_lifecycle_file.h"\n#ifdef FS_MAX_PATH\n_Static_assert(EP0_FS_PATH_SPAN==FS_MAX_PATH,"SDK path span changed");\n#endif')
        p.write_text(text)
    (src/'ep0_candidate_recipe.h').write_text('static const uint8_t ep0CandidateRecipe[32]={'+','.join(map(str,bytes.fromhex(recipe)))+'};\n')
    for n in ('main.npdm','sysmodule.json'):shutil.copyfile(DEVICE/n,folder/n)
    changed=sorted(p.relative_to(folder/'source').as_posix() for p in (folder/'source').rglob('*') if p.is_file() and
        (not (DEVICE/'source'/p.relative_to(folder/'source')).exists() or p.read_bytes()!=(DEVICE/'source'/p.relative_to(folder/'source')).read_bytes()))
    b.require(len(changed)==6,'unexpected source delta');return changed

def checked_compile(source,binary,folder):
    text=source.read_text()
    marker='static Result fsFsCreateFile('
    if marker in text:
        check='''static void check_sdk_path(const char *path) {
 size_t length=strlen(path);assert(length<0x301);
 for(size_t i=0;i<0x301;i++) { volatile unsigned char value=(unsigned char)path[i];if(i>length)assert(!value); }
}
'''
        text=text.replace(marker,check+marker,1)
        text,count=re.subn(r'(static Result fsFs(?:Create|Open)File\([^\{]+\)\s*\{)',r'\1 check_sdk_path(path);',text)
        b.require(count==2,'modeled SDK adapters changed')
        source.write_text(text)
    return ORIGINAL_COMPILE(source,binary,folder)

ORIGINAL_COMPILE=life.compile_model

def machine_review(folder):
    text=(folder/'disassembly.txt').read_text();functions=parse_disassembly(text);names={f['name']:f for f in functions.values()}
    meta=elf_metadata(b.plain(folder/'full.elf'))
    paths=[s for s in meta['symbols'] if s['type']==1 and (s['name']=='life_path' or re.fullmatch(r'path\.[0-9]+',s['name']))]
    b.require(len(paths)==5 and all(s['size']==769 for s in paths),'five full-width linked objects required')
    writable=[s for s in meta['sections'] if s['name']=='.bss' and s['flags']&1]
    b.require(len(writable)==1,'expected BSS');area=writable[0]
    b.require(all(area['address']<=s['address'] and s['address']+769<=area['address']+area['size'] for s in paths),'path outside full BSS storage')
    # REL2's save function is not linked in this EXE3 build. Its source and static
    # object still receive the same capacity fix; do not invent a machine body.
    roots=('main','Ep0LifePrepare','life_transfer','Ep0CandidateSaveCapture','Ep0CandidateSaveDiagnostic','Ep0ExecutionSaveJoined','fsFsCreateFile')
    def resolve(table,name):
        matches=[f for n,f in table.items() if n==name or n.startswith(name+'.')]
        b.require(len(matches)==1,'ambiguous machine function: '+name);return matches[0]
    frames={n:dict(resolved_name=resolve(names,n)['name'],**frame(resolve(names,n),functions)) for n in roots}
    old_functions=parse_disassembly((DEVICE/'disassembly.txt').read_text());old_names={f['name']:f for f in old_functions.values()}
    b.require('Ep0SessionSaveJoined' not in names and 'Ep0SessionSaveJoined' not in old_names,'REL2 linkage changed')
    delta={n:dict(before=frame(resolve(old_names,n),old_functions)['machine_observed_frame'],after=frames[n]['machine_observed_frame']) for n in roots}
    return dict(linked_path_objects=paths,total_path_storage_bytes=5*769,path_objects_in_bss=True,
        function_frames=frames,frame_comparison=delta,not_linked_functions=['Ep0SessionSaveJoined'],whole_call_graph_stack_verified=False,
        runtime_peak_measured=False,actual_kernel_thread_budget_verified=False)

def run(output):
    output=w.pkg.output_path(output);w.seal_verify(BASE);prior=b.load(BASE/'audit.json');hashes=dict(prior['source_hashes']);b.require(len(hashes)==217,'parent count')
    protected=b.load(BASE/'protected-inputs.json');records={p.name:b.plain(p) for p in (BASE/'records').glob('*.json')}
    for n,h in hashes.items():b.require(b.sha(b.plain(b.REPO/n))==h,'source drift')
    for n in NEW:hashes['research/usb-ds-iso/'+n]=b.sha(b.plain(b.ROOT/n))
    for n,h in prior['sdk_external_sha256'].items():b.require(b.sha(b.plain(Path(n)))==h,'toolchain drift')
    for n,raw in records.items():b.require(b.plain(w.once.ANALYSIS/n)==raw,'live record drift')
    recipe=b.sha(b.canonical(dict(schema='A23-path-span-device-recipe-1',source_hashes=hashes,parent_elf=b.sha(b.plain(DEVICE/'full.elf')),parent_review=b.sha(b.plain(BASE/'SHA256SUMS')))))
    output.mkdir(parents=True,mode=0o700);folder=output/'candidate';changed=prepare(folder,recipe);commands=[];models={}
    with patch.object(life,'compile_model',checked_compile):
        for name,method in (('adapter',life.adapter_models),('startup',life.startup_models),('lifecycle',life.lifecycle_models)):
            models[name],command=method(output,folder);commands.append(command)
    build=life.quiet.v3.compile_arm(folder,commands);strict=[]
    for cmd in list(commands):
        if '-c' not in cmd:continue
        check=[cmd[0],*[x for x in cmd[1:cmd.index('-c')] if x!='-fstack-usage'],'-Wformat=2','-fsyntax-only',cmd[cmd.index('-c')+1]]
        subprocess.run(check,check=True,capture_output=True,text=True);strict.append(check);commands.append(check)
    b.require(len(strict)==14,'expected 14 ARM units');build['strict_format_units']=len(strict);build['linked_checks']=life.quiet.linked_checks(folder,recipe)
    build['machine_review']=machine_review(folder)
    b.write(folder/'recipe.json',dict(schema='A23-path-span-device-recipe-1',runtime_recipe_sha256=recipe,parent_runtime_recipe_sha256=b.load(DEVICE/'device-binding.json')['runtime_recipe_sha256'],window_ms=30000,source_hashes=hashes))
    files=('full.elf','recipe.json','symbols.txt','source/uvc/ep0_candidate_recipe.h','main.npdm','sysmodule.json')
    binding=dict(schema='A23-lifecycle-device-material-1',runtime_recipe_sha256=recipe,device_elf_sha256=b.sha(b.plain(folder/'full.elf')),
        artifact_hashes={n:b.sha(b.plain(folder/n)) for n in files},main_thread_stack_request_bytes=8192,actual_kernel_thread_budget_verified=False,host_receiver_rebound=False)
    b.write(folder/'device-binding.json',binding)
    for n,h in hashes.items():b.require(b.sha(b.plain(b.REPO/n))==h,'source changed')
    for n,h in prior['sdk_external_sha256'].items():b.require(b.sha(b.plain(Path(n)))==h,'toolchain changed')
    for n,h in protected['production'].items():b.require(b.sha(b.plain(b.REPO/n))==h,'production changed')
    for group in ('tickets','offline_records_sha256'):
        for n,h in protected[group].items():b.require(b.sha(b.plain(w.once.ANALYSIS/n))==h,'record changed')
    for n,raw in records.items():b.require(b.plain(w.once.ANALYSIS/n)==raw,'live record changed');w.pkg.put(output,'records/'+n,raw)
    for n in NEW:w.pkg.put(output,'inputs/'+n,b.plain(b.ROOT/n))
    b.write(output/'protected-inputs.json',protected)
    result=dict(schema='A23-path-span-device-candidate-1',source_hashes=hashes,prior_sources_unchanged=217,changed_files=changed,
        runtime_recipe_sha256=recipe,device_binding=binding,build=build,models=models,model_count=sum(len(x) for x in models.values()),
        compiler_commands=commands,modeled_sdk_reads_full_span=True,real_sdk_service_verified=False,arm_executed=False,
        firmware_packaged=False,deployed=False,host_receiver_rebound=False,sd_accesses=0,usb_requests=0,attempt_issued=False,remaining=0,root_cause_confirmed=False)
    b.write(output/'audit.json',result);b.seal(output);w.seal_verify(output);return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args();r=run(a.output)
    print(json.dumps(dict(sources=len(r['source_hashes']),recipe=r['runtime_recipe_sha256'],elf=r['device_binding']['device_elf_sha256'],models=r['model_count'],machine_review=r['build']['machine_review'])))
