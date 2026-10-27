#!/usr/bin/env python3
"""Audit the sealed V3 TLS/stack layout and logger with mocked FS only."""
import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess

import analyze_a23_session_stack as stack
import build_a23_waiting_receiver as storage
from workflows.artifacts import verify

ROOT=storage.ROOT;REPO=storage.REPO
PARENT=ROOT/'private/analysis/A23-waiting-collection-review-20261015'
DEVICE=storage.DEVICE
NEW=('tools/audit_a23_v3_runtime.py','tests/a23_v3_logger_fixture.c','tests/test_a23_v3_runtime.py')
CASES=('unmounted','empty','format-failure','open-failure','size-failure','write-failure',
       'binary','normal','length-1','length-510','length-511','length-512','length-2048',
       'offset','append','busy')
SDK_HEADERS=('/opt/devkitpro/libnx/include/switch/kernel/thread.h',
             '/opt/devkitpro/libnx/include/switch/arm/tls.h',
             '/opt/devkitpro/libnx/include/switch/sf/sessionmgr.h',
             '/opt/devkitpro/devkitA64/aarch64-none-elf/include/sys/reent.h')


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Elf:
    """Read ELF64 little endian section bytes; never map or execute the ELF."""
    def __init__(self,path):
        self.raw=Path(path).read_bytes()
        if self.raw[:6]!=b'\x7fELF\x02\x01':raise ValueError('ELF64 LE required')
        off=struct.unpack_from('<Q',self.raw,40)[0];size,count=struct.unpack_from('<HH',self.raw,58)
        if size!=64:raise ValueError('Unexpected section header')
        self.sections=[struct.unpack_from('<IIQQQQIIQQ',self.raw,off+i*size) for i in range(count)]

    def bytes(self,address,count):
        for s in self.sections:
            if s[1]!=8 and s[3]<=address and address+count<=s[3]+s[5]:
                start=s[4]+address-s[3];return self.raw[start:start+count]
        raise ValueError('Address not file backed: '+hex(address))

    def u64(self,address):return struct.unpack('<Q',self.bytes(address,8))[0]


def symbols(text):
    rows={}
    for line in text.splitlines():
        m=re.match(r'\s*\d+: ([0-9a-f]+)\s+(\d+)\s+\S+\s+\S+\s+\S+\s+\S+\s+(\S+)$',line)
        if m:rows[m[3]]=dict(address=int(m[1],16),bytes=int(m[2]))
    return rows


def certificate(folder):
    text=(folder/'disassembly.txt').read_text();fs=stack.parse_disassembly(text)
    named={f['name']:f for f in fs.values()};sym=symbols((folder/'symbols.txt').read_text());elf=Elf(folder/'full.elf')
    selected=('threadCreate','_EntryWrap','threadExit','threadClose','newlibSetup','__libnx_init',
              '__getreent','__syscall_getreent','__aarch64_read_tp','LogFunctionImpl',
              'fsFsOpenFile','_fsFsOpenCommon','fsFileGetSize','fsFileWrite','_fsObjectClose',
              'sessionmgrAttachClient','sessionmgrDetachClient','main','VideoStreamThread','AudioStreamThread')
    functions={n:named[n]['instructions'] for n in selected}
    instructions={pc:(op,arg) for rows in functions.values() for pc,op,arg in rows}
    # These are exact instructions in the window-30s final ELF. Formula below
    # applies to the non-NULL caller supplied stack path, not SDK allocation.
    checks={
        0xbb60:('sub','x19, x19, x0'),0xbb64:('add','x19, x19, #0xf'),
        0xbb68:('and','x19, x19, #0xfffffffffffffff0'),
        0xbb84:('ldr','x3, [x0]'),0xbb88:('mov','x0, #0x10'),
        0xbb8c:('cmp','x3, #0x10'),0xbb90:('csel','x3, x3, x0, cs'),
        0xbb94:('add','x0, x3, #0x23f'),0xbb98:('add','x0, x0, x19'),
        0xbb9c:('neg','x3, x3'),0xbba0:('and','x0, x0, x3'),
        0xbba4:('add','x1, x0, #0x30'),0xbba8:('cmp','x1, x4'),
        0xbbb0:('sub','x20, x4, x0'),0xbc78:('add','x0, x23, x20'),
        0xbc7c:('sub','x20, x20, #0x30'),0xbc84:('sub','x3, x0, #0x30'),
        0xbc88:('add','x1, x0, x19'),0xbca0:('stp','x20, xzr, [x7, #24]'),
        0xbca8:('stur','x7, [x0, #-48]'),0xbcb0:('stp','x8, x9, [x3, #8]'),
        0xbcb4:('stp','x1, x0, [x3, #24]'),
        0xbd34:('mov','x2, #0x240'),0xbd50:('bl','12bc0 <memset>'),
        0xbdd4:('ldr','x1, [x0, #496]'),0xbde0:('str','x2, [x0, #8]'),
        0xbde8:('str','x2, [x0, #16]'),0xbdf0:('str','x1, [x0, #24]'),
        0xbf10:('stp','x29, x30, [sp, #-48]!'),0xbf2c:('mrs','x20, tpidrro_el0'),
        0xbf30:('add','x20, x20, #0x180'),0xbf3c:('str','w1, [x20, #96]'),
        0xbf48:('str','x1, [x20, #112]'),0xbf70:('str','x1, [x20, #120]'),
        0xbfb4:('blr','x1'),0xbfb8:('bl','be60 <threadExit>'),
        0x1249c:('str','w1, [x0, #480]'),0x124b8:('stp','xzr, x0, [x19, #8]'),
        0x12404:('ldr','w1, [x0, #480]'),0x1241c:('ldr','x0, [x2, #16]'),
        0x11ac8:('ldr','x0, [x0, #504]'),
        0x200:('mov','w4, #0x5000'),0x220:('mov','w4, #0x3000'),
    }
    for pc,expected in checks.items():
        if instructions.get(pc)!=expected:raise ValueError('Instruction drift at '+hex(pc))
    got={hex(a):elf.u64(a) for a in (0x274c0,0x274e0,0x27538,0x275b8,0x27590,0x27528,0x27530,0x275d0)}
    assert got['0x274c0']==sym['__tls_align']['address'] and elf.u64(got['0x274c0'])==4
    assert got['0x274e0']==sym['__syscall_getreent']['address']
    assert got['0x27538']==sym['__tls_start']['address'] and got['0x275b8']==sym['__tls_end']['address']
    assert got['0x27590']==sym['__tdata_lma_end']['address'] and got['0x27530']==sym['__tdata_lma']['address']
    assert got['0x275d0']==sym['_impure_ptr']['address'] and elf.u64(got['0x275d0'])==sym['_impure_data']['address']
    assert sym['_impure_data']['bytes']==0x240
    tls_bytes=sym['__tls_end']['address']-sym['__tls_start']['address'];assert tls_bytes==8
    aligned_tls=(tls_bytes+15)&~15;alignment=max(16,elf.u64(sym['__tls_align']['address']))
    reserve=(alignment+0x23f+aligned_tls)&-alignment;assert reserve==592
    layouts={}
    for label,name in (('video','g_videoThreadStack'),('audio','g_audioThreadStack')):
        total=sym[name]['bytes'];assert total in (20480,12288) and sym[name]['address']%4096==0
        sp=total-reserve-48;assert sp>0
        layouts[label]=dict(backing_array_bytes=total,aligned_tls_bytes=aligned_tls,reent_bytes=576,
            tls_reent_padding_bytes=reserve-aligned_tls-576,start_argument_bytes=48,initial_sp_offset=sp,
            thread_stack_sz_field=sp,entry_wrapper_held_bytes=48,user_entry_remaining_bytes=sp-48,
            reent_offset=total-reserve+aligned_tls,tls_offset=total-reserve,
            offsets_relative_to_mapped_stack_base=True,actual_mapping_success_assumed=True)
    assert layouts['video']['initial_sp_offset']==19840 and layouts['audio']['initial_sp_offset']==11648
    calls=lambda n:[arg for _,op,arg in functions[n] if op in ('bl','b','blr','br')]
    init_calls=calls('__libnx_init');assert init_calls.index('12480 <newlibSetup>')<init_calls.index('16b0 <__appInit>')
    sdk={}
    for name in ('_fsFsOpenCommon','fsFileGetSize','fsFileWrite'):
        c=calls(name);assert any('sessionmgrAttachClient>' in s for s in c) and any('sessionmgrDetachClient>' in s for s in c)
        sdk[name]=dict(calls=c,one_command_session_attach_detach_present=True,log_group_lock_present=False)
    log_calls=calls('LogFunctionImpl')
    assert not any('mutex' in s.lower() or 'sessionmgr' in s for s in log_calls)
    assert all(not any('_reclaim_reent' in s for s in calls(n)) for n in ('threadExit','threadClose'))
    return dict(schema='A23-V3-runtime-static-certificate-1',elf_sha256=sha(folder/'full.elf'),
        recipe_sha256=json.loads((folder/'recipe.json').read_text())['input_digest'],
        function_sha256={n:storage.sha(json.dumps(v,separators=(',',':')).encode()) for n,v in functions.items()},
        checked_instruction_count=len(checks),functions=functions,got_words=got,workers=layouts,
        linked_tls_align_value=4,tls_bytes=tls_bytes,worker_static_reservation_bytes=640,
        main_reent_symbol=sym['_impure_data'],main_stack_budget_verified=False,
        main_newlib_setup_before_app_init=True,worker_reent_install_before_user_entry=True,
        child_standard_stream_pointers_inherited=True,thread_exit_tls_destructor_indirect=True,
        direct_reclaim_reent_call_present=False,all_reent_allocations_reclaimed_verified=False,
        sdk_command_boundaries=sdk,logger_direct_calls=log_calls,
        tls_lifecycle_static_paths_reviewed=True,tls_runtime_integrity_verified=False,
        fs_service_open_sharing_semantics_verified=False,fs_service_append_semantics_verified=False,
        log_group_atomicity_verified=False,whole_thread_stack_verified=False,
        kernel_and_loader_success_assumed=True,elf_load_bias_and_relocation_contract_assumed=True,
        full_machine_proof=False,arm_executed=False,hardware_verified=False,root_cause_confirmed=False)


def recipe_identities():
    device=json.loads((DEVICE/'audit.json').read_text());folder=DEVICE/'window-30s'
    runtime=json.loads((folder/'recipe.json').read_text());header=folder/'source/uvc/ep0_candidate_recipe.h'
    raw=bytes(int(v) for v in re.search(r'=\{([0-9,]+)\}',header.read_text())[1].split(','));assert len(raw)==32
    symbols_text=(folder/'symbols.txt').read_text();elf=Elf(folder/'full.elf')
    addresses=[int(m[1],16) for m in re.finditer(r'^\s*\d+: ([0-9a-f]+)\s+32\s+OBJECT\s+LOCAL\s+DEFAULT\s+\d+\s+ep0CandidateRecipe$',symbols_text,re.M)]
    assert len(addresses)==2 and all(elf.bytes(a,32)==raw for a in addresses)
    assert raw.hex()==runtime['input_digest']==device['builds']['window-30s']['runtime_recipe_digest']
    assert runtime['parent_input_digest']==device['recipe_digest']
    record=ROOT/'private/analysis/A23-waiting-receiver-review-20261015/offline-record.json'
    receipt=json.loads(record.read_text());receiver_recipe=receipt['recipe_sha256']
    assert receiver_recipe==device['recipe_digest'] and receiver_recipe!=raw.hex()
    assert receipt['remaining']==0 and receipt['acquisition_enabled'] is False
    return dict(schema='A23-V3-recipe-identities-1',parent_input_digest=device['recipe_digest'],
        runtime_input_digest=raw.hex(),receiver_record_recipe_sha256=receiver_recipe,
        receiver_record_sha256=sha(record),candidate_header_sha256=sha(header),
        linked_recipe_addresses=addresses,linked_recipe_bytes_verified=True,
        receiver_record_uses_parent_digest=True,receiver_record_matches_runtime_recipe=False,
        use_receiver_record_as_expected_execution_recipe_valid=False,
        receiver_capture_failure_proven=False,new_receiver_binding_implemented=False,
        old_receiver_record_modified=False,attempt_issued=False)


def inventory(folder):
    fs=stack.parse_disassembly((folder/'disassembly.txt').read_text());named={v['name']:a for a,v in fs.items()}
    rows=json.loads((folder/'stack-usage.json').read_text());reported={r['function']:r['bytes'] for r in rows if r['kind']=='static'}
    frames={a:stack.frame(f,fs,reported.get(f['name'])) for a,f in fs.items()};result={}
    for root in ('main','VideoStreamThread','AudioStreamThread','_EntryWrap'):
        todo=deque([(named[root],[root])]);seen=set();issues=[];logger_paths=[]
        while todo:
            a,path=todo.popleft()
            if a in seen:continue
            seen.add(a);f=frames[a];name=fs[a]['name']
            issues.extend(dict(function=name,issue=s,path=path) for s in f['unresolved'])
            if name=='LogFunctionImpl':logger_paths.append(path)
            for e in f['edges']:todo.append((e['target'],[*path,fs[e['target']]['name']]))
        result[root]=dict(own_frame_bytes=frames[named[root]]['machine_observed_frame'],
            direct_reachable_count=len(seen),reachable_functions=sorted(fs[a]['name'] for a in seen),
            logger_direct_path=logger_paths,unresolved=issues,unresolved_count=len(issues),
            stack_bound_bytes=None,indirect_targets_expanded=False,recursive_cycles_bounded=False)
    assert all(result[r]['logger_direct_path'] for r in ('main','VideoStreamThread','AudioStreamThread'))
    assert all(result[r]['unresolved_count']>0 for r in result)
    return dict(schema='A23-V3-conservative-reachability-1',roots=result,
        stack_bound_verified=False,own_frames_are_not_callchain_bounds=True,
        old_formatter_certificate_reused=False,runtime_peak_measured=False)


def logger_source(core,template):
    branch=core.split('#elif FILE_LOGGING\n',1)[1].split('\n#endif',1)[0]
    body=branch[branch.index('void LogFunctionImpl('):]
    assert body.count('void LogFunctionImpl(')==1 and template.count('/* INSERT_LOGGER */')==1
    return template.replace('/* INSERT_LOGGER */',body),body


def run(output):
    output=Path(output)
    if not output.is_absolute() or output!=output.resolve() or output.exists():raise ValueError('new canonical output required')
    parent=json.loads(storage.plain(PARENT/'audit.json'));device=json.loads(storage.plain(DEVICE/'audit.json'))
    sealed=(PARENT,PARENT.parent/'A23-waiting-collection-validation-20261015',DEVICE,
            PARENT.parent/'A23-waiting-receiver-review-20261015')
    seals=[verify(p) for p in sealed]
    for n,h in parent['source_hashes'].items():
        if sha(REPO/n)!=h:raise ValueError('Parent source drift: '+n)
    sources=dict(parent['source_hashes']);sources.update({'research/usb-ds-iso/'+n:sha(ROOT/n) for n in NEW})
    sources['research/usb-ds-iso/tools/analyze_a23_session_stack.py']=sha(ROOT/'tools/analyze_a23_session_stack.py')
    def check():
        for n,h in sources.items():
            if sha(REPO/n)!=h:raise ValueError('Source drift: '+n)
        for n,h in parent['production_sources_sha256'].items():
            if sha(REPO/n)!=h:raise ValueError('Production drift: '+n)
        for n,h in parent['tickets_sha256'].items():
            if sha(PARENT.parent/n)!=h:raise ValueError('Ticket drift: '+n)
    check();output.mkdir(parents=True)
    for n,h in sources.items():
        target=output/'source'/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(REPO/n,target);assert sha(target)==h
    external={n:sha(n) for n in SDK_HEADERS};external.update({n:sha(n) for n in device['external_sha256']})
    for n,h in device['external_sha256'].items():assert external[n]==h,n
    for n in SDK_HEADERS:
        target=output/'sdk-headers'/Path(n).name;target.parent.mkdir(exist_ok=True);shutil.copyfile(n,target);assert sha(target)==external[n]
    cert=certificate(DEVICE/'window-30s');identities=recipe_identities()
    assert cert['elf_sha256']==device['builds']['window-30s']['elf_sha256']
    graph=inventory(DEVICE/'window-30s');storage.write(output/'certificate.json',cert);storage.write(output/'reachability.json',graph)
    storage.write(output/'recipe-identities.json',identities)
    frozen=DEVICE/'window-30s/source/core.c';native,body=logger_source(frozen.read_text(),(output/'source/research/usb-ds-iso/tests/a23_v3_logger_fixture.c').read_text())
    src=output/'logger-model.c';src.write_text(native);compiler=subprocess.check_output(['xcrun','-f','clang'],text=True).strip()
    external[compiler]=sha(compiler);binary=output/'logger-model'
    command=[compiler,'-std=c11','-Wall','-Wextra','-Werror','-pthread','-fsanitize=address,undefined','-g',str(src),'-o',str(binary)]
    storage.write(output/'native-command.json',command)
    with (output/'native-build.log').open('x') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
    models={}
    for name in CASES:
        p=subprocess.run([str(binary),name],capture_output=True,text=True,check=True,timeout=15)
        assert not p.stderr,p.stderr;models[name]=json.loads(p.stdout)
    storage.write(output/'logger-models.json',models)
    abi=output/'reent-abi.c';abi.write_text('#include <sys/reent.h>\n#include <stddef.h>\n'
        '_Static_assert(sizeof(struct _reent)==576,"reent size");\n'
        '_Static_assert(offsetof(struct _reent,_stdin)==8,"stdin");\n'
        '_Static_assert(offsetof(struct _reent,_stdout)==16,"stdout");\n'
        '_Static_assert(offsetof(struct _reent,_stderr)==24,"stderr");\n')
    arm='/opt/devkitpro/devkitA64/bin/aarch64-none-elf-gcc'
    abi_cmd=[arm,'-std=c11','-Wall','-Wextra','-Werror','-D__SWITCH__','-mtp=soft','-c',str(abi),'-o',str(output/'reent-abi.o')]
    storage.write(output/'abi-command.json',abi_cmd)
    with (output/'abi-build.log').open('x') as log:subprocess.run(abi_cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
    check();assert recipe_identities()==identities
    for n,h in external.items():assert sha(n)==h,n
    for p in sealed:verify(p)
    result=dict(schema='A23-V3-runtime-review-1',source_hashes=sources,sealed_inputs=seals,
        device_elf_sha256=cert['elf_sha256'],device_recipe_sha256=cert['recipe_sha256'],recipe_identities=identities,
        production_sources_sha256=parent['production_sources_sha256'],tickets_sha256=parent['tickets_sha256'],
        external_sha256=external,logger_source_sha256=sha(frozen),logger_body_sha256=storage.sha(body.encode()),
        workers=cert['workers'],native_cases=len(models),native_sanitizers='address,undefined',
        logger_body_extracted_verbatim=True,mock_fs_only=True,formatter_backend='host_libc_vsnprintf',
        abi_static_assertions_compiled=True,hermetic_full_toolchain_verified=False,
        command_serialization_does_not_prove_group_atomicity=True,
        real_concurrency_verified=False,logger_reentrancy_verified=False,tls_runtime_integrity_verified=False,
        whole_thread_stack_verified=False,synchronous_log_latency_bound_verified=False,
        full_formatter_replayed_on_new_elf=False,device_candidate_modified=False,
        new_device_elf_built=False,arm_executed=False,native_sdk_calls=0,usb_requests=0,sd_accesses=0,
        attempt_issued=False,hardware_verified=False,root_cause_confirmed=False)
    storage.write(output/'audit.json',result);storage.seal(output);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    r=run(args.output);print(json.dumps({k:r[k] for k in ('schema','native_cases','workers','whole_thread_stack_verified')},indent=2))
