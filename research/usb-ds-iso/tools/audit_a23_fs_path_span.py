#!/usr/bin/env python3
"""Offline fixed-width path audit and guarded native prototype. No device access."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import lifecycle_card_workflow as w
from analyze_a23_session_stack import parse_disassembly, frame

b=w.b
BASE=w.once.ANALYSIS/'A23-lifecycle-companion-review-20261016'
DEVICE=w.once.ANALYSIS/'A23-lifecycle-device-review-20261016/candidate'
NEW=('device/ep0_fs_path_span.h','tests/a23_fs_path_span_fixture.c',
     'tools/audit_a23_fs_path_span.py','tests/test_a23_fs_path_span.py')
SPAN=0x301
OBJDUMP='/opt/devkitpro/devkitA64/bin/aarch64-none-elf-objdump'
GCC='/opt/devkitpro/devkitA64/bin/aarch64-none-elf-gcc'

def geometry(main_frame, caller_frame, offset, span=SPAN, slack=0):
    if any(type(x) is not int or x<0 for x in (main_frame,caller_frame,offset,span,slack)) or not span or offset>=caller_frame:
        raise ValueError('invalid modeled layout')
    start=-main_frame-caller_frame+offset
    return dict(start_from_main_entry_sp=start,end_exclusive_from_main_entry_sp=start+span,
        upper_mapping_slack_assumed=slack,crosses_assumed_upper_bound=start+span>slack,
        runtime_mapping_measured=False)

def linked_layout(text):
    functions=parse_disassembly(text);names={f['name']:f for f in functions.values()}
    sdk=names['fsFsCreateFile']['instructions']
    required=[('mov','x4, x1'),('mov','w0, #0x3010000'),('stp','w7, w4, [x3, #8]')]
    if any(pair not in [(op,arg) for _,op,arg in sdk] for pair in required):raise ValueError('fixed pointer descriptor changed')
    main=frame(names['main'],functions)['machine_observed_frame']
    if main!=128:raise ValueError('main layout changed')
    layouts={}
    for name,target,wanted_frame,wanted_offset in (
        ('Ep0CandidateSaveDiagnostic','diagnostic_create_open',656,304),
        ('Ep0ExecutionSaveJoined','session_file_create_open',496,144)):
        f=names[name];report=frame(f,functions)
        calls=[i for i,(_,op,arg) in enumerate(f['instructions']) if op=='bl' and '<'+target+'>' in arg]
        if len(calls)!=1:raise ValueError('ambiguous path call')
        i=calls[0];window=f['instructions'][max(0,i-12):i]
        offsets=[int(m[1],0) for _,op,arg in window if op=='add' for m in [re.fullmatch(r'x1, sp, #(0x[0-9a-f]+|[0-9]+)',arg)] if m]
        if not offsets or offsets[-1]!=wanted_offset or report['machine_observed_frame']!=wanted_frame:raise ValueError('path stack layout changed')
        pc=f['instructions'][i][0];edges=[e for e in report['edges'] if e['at']==pc]
        if len(edges)!=1 or edges[0]['held_bytes']!=wanted_frame:raise ValueError('call-site SP changed')
        layouts[name]=dict(frame_bytes=wanted_frame,path_offset=wanted_offset,path_object_bytes=96,
            path_object_shortfall=SPAN-96,call_address=hex(pc),geometry=geometry(main,wanted_frame,wanted_offset),
            excerpts=[dict(address=hex(p),op=op,args=arg) for p,op,arg in window]+[dict(address=hex(pc),op='bl',args=target)])
    return dict(span_bytes=SPAN,main_frame_bytes=main,paths=layouts,sdk_pointer_uses_caller_address=True,
        sdk_descriptor_evidence=[dict(address=hex(p),op=op,args=arg) for p,op,arg in sdk if (op,arg) in required],
        runtime_mapping_measured=False,kernel_error_reproduced=False,iso_root_cause_confirmed=False)

def run(output):
    output=w.pkg.output_path(output);w.seal_verify(BASE);parent=b.load(BASE/'audit.json');hashes=dict(parent['source_hashes'])
    b.require(len(hashes)==213,'parent source count');protected=b.load(BASE/'protected-inputs.json')
    records={n:b.plain(w.once.ANALYSIS/n) for n in ('A23-quiet-once-20261016-interface2.json','A23-lifecycle-once-20261016-interface2.json')}
    for n,h in hashes.items():b.require(b.sha(b.plain(b.REPO/n))==h,'source drift')
    for n in NEW:hashes['research/usb-ds-iso/'+n]=b.sha(b.plain(b.ROOT/n))
    old=b.load(w.once.ANALYSIS/'A23-execution-v3-candidate-review-20261015/audit.json')
    for n,h in old['external_sha256'].items():b.require(b.sha(b.plain(Path(n)))==h,'SDK/toolchain drift')
    b.require(b.sha(b.plain(DEVICE/'full.elf'))=='737ad5c1df026d7ea94ac898de0ff69ed4fef8c369f400d1dce72b377d58eb38','wrong actual candidate')
    disassembly=subprocess.check_output([OBJDUMP,'-d',str(DEVICE/'full.elf')],text=True)
    actual=linked_layout(disassembly);b.require(actual==linked_layout((DEVICE/'disassembly.txt').read_text()),'saved disassembly differs')
    output.mkdir(parents=True,mode=0o700)
    for n in NEW:w.pkg.put(output,'inputs/'+n,b.plain(b.ROOT/n))
    for n in ('fs.h','../result.h'):
        source=Path('/opt/devkitpro/libnx/include/switch/services')/n
        w.pkg.put(output,'sdk/'+source.name,source.read_bytes())
    w.pkg.put(output,'sdk/fs.o',subprocess.check_output(['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-ar','p','/opt/devkitpro/libnx/lib/libnx.a','fs.o']))
    w.pkg.put(output,'linked-disassembly.txt',disassembly.encode())
    binary=output/'native-model';command=['clang','-std=c11','-D_DARWIN_C_SOURCE','-O2','-Wall','-Wextra','-Werror','-I',str(b.ROOT/'device'),str(b.ROOT/'tests/a23_fs_path_span_fixture.c'),'-o',str(binary)]
    subprocess.run(command,check=True,capture_output=True);model=json.loads(subprocess.check_output([str(binary)]))
    source=output/'arm-prototype.c';w.pkg.put(output,source.name,b'#include <switch.h>\n#include "ep0_fs_path_span.h"\nstatic char staged[EP0_FS_PATH_SPAN];\nconst char *prototype(const char *p,size_t n) { return ep0_fs_path_prepare(staged,sizeof(staged),p,n)?staged:NULL; }\n')
    arm=[GCC,'-std=c11','-O2','-Wall','-Wextra','-Werror','-fstack-usage','-I/opt/devkitpro/libnx/include','-I'+str(b.ROOT/'device'),'-D__SWITCH__','-c',str(source),'-o',str(output/'arm-prototype.o')]
    subprocess.run(arm,check=True,capture_output=True)
    for n,h in hashes.items():b.require(b.sha(b.plain(b.REPO/n))==h,'source changed')
    for n,h in protected['production'].items():b.require(b.sha(b.plain(b.REPO/n))==h,'production changed')
    for group in ('tickets','offline_records_sha256'):
        for n,h in protected[group].items():b.require(b.sha(b.plain(w.once.ANALYSIS/n))==h,'old record changed')
    for n,raw in records.items():b.require(b.plain(w.once.ANALYSIS/n)==raw,'live record changed');w.pkg.put(output,'records/'+n,raw)
    result=dict(schema='A23-fs-path-span-review-1',source_hashes=hashes,prior_sources_unchanged=213,new_sources=4,
        layout=actual,native_model=model,compiler_commands=[command,arm],sdk_external_sha256=old['external_sha256'],
        prototype_integrated=False,device_elf_changed=False,firmware_packaged=False,deployed=False,sd_accesses=0,
        usb_requests=0,attempt_issued=False,remaining=0,kernel_error_reproduced=False,root_cause_confirmed=False)
    b.write(output/'audit.json',result);b.write(output/'protected-inputs.json',protected);b.seal(output);w.seal_verify(output);return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args();r=run(a.output)
    print(json.dumps(dict(sources=len(r['source_hashes']),layout=r['layout'],native_model=r['native_model'])))
