#!/usr/bin/env python3
"""Publication/interruption tests and final-ELF stack audit; existing runtime unchanged."""
import argparse,json,re,shutil
from pathlib import Path
import build_a23_session_candidate as candidate
from analyze_ep0_session import decode_session
from analyze_a23_session_stack import analyze
from workflows.artifacts import verify
base=candidate.base;ROOT=candidate.ROOT
SEALED=base.ep0.PRIVATE/'analysis/A23-session-candidate-review-20261014'
INPUTS=('tests/ep0_session_concurrent_publish_test.c','tests/ep0_session_runtime_concurrency_test.c','tools/analyze_a23_session_stack.py','tools/audit_a23_session_concurrency.py')
CASES=('capture-busy','capture-interrupted','context-publishing','receipt-publishing','capture-rejected','failed-join','nonreturned-receipt','startup-during-bind','full-race','pre-bind-snapshot','failed-bind')
r=base.trace.replace

def local_includes(s):return re.sub(r'#include "(ep0_[^"]+)"',r'#include "research/usb-ds-iso/device/\1"',s)

def runtime_source():
    s=(ROOT/'tests/ep0_session_runtime_concurrency_test.c').read_text()
    old=(SEALED/'dormant/source/uvc/ep0_startup_runtime.c').read_text();assert old.endswith(candidate.BRIDGE)
    s=r(s,'/* INSERT_STARTUP_RUNTIME */',local_includes(old[:-len(candidate.BRIDGE)]))
    s=r(s,'/* INSERT_BRIDGE */',candidate.BRIDGE)
    return r(s,'/* INSERT_SESSION_RUNTIME */',local_includes((SEALED/'dormant/source/uvc/ep0_session_runtime.c').read_text()))

def run(output):
    output=Path(output).resolve();verify(SEALED);old=json.loads((SEALED/'audit.json').read_text())
    source_audit=base.owner.source_audit();assert source_audit==old['source_audit']
    tickets={n:base.ep0.sha(base.ep0.PRIVATE/'analysis'/n) for n in base.owner.TICKETS};assert tickets==old['tickets_sha256']
    inputs={n:base.ep0.sha(ROOT/n) for n in dict.fromkeys([*old['source_hashes'],*INPUTS])}
    for n,h in old['source_hashes'].items():assert inputs[n]==h,n
    production={n:base.ep0.sha(candidate.startup.startup.REPO/n) for n in candidate.startup.startup.PRODUCTION};assert production==old['production_sources_sha256']
    # No runtime edit: hooks exist only in this newly generated core test header.
    header=(ROOT/'device/ep0_session_capture.h').read_text();header=local_includes(header)
    header=r(header,'    atomic_store_explicit(&r->phase,2,memory_order_release);return true;',
                    '    publication_boundary(&r->phase);\n    atomic_store_explicit(&r->phase,2,memory_order_release);return true;')
    header=r(header,'    atomic_store_explicit(&c->phase,2,memory_order_release);return true;',
                    '    publication_boundary(&c->phase);\n    atomic_store_explicit(&c->phase,2,memory_order_release);return true;')
    (output/'ep0_session_capture.h').write_text(header)
    pure=output/'publish-native.c';shutil.copyfile(ROOT/'tests/ep0_session_concurrent_publish_test.c',pure)
    runtime=output/'runtime-native.c';runtime.write_text(runtime_source());commands=[];policies={};rows=[]
    for sanitizer in ('address-undefined','thread'):
        flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if sanitizer=='address-undefined' else ['-fsanitize=thread']
        folder=output/sanitizer;folder.mkdir()
        for file,name in ((pure,'publisher'),(runtime,'runtime')):
            binary=folder/name;cmd=['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function',*flags,'-g','-pthread','-I'+str(base.ep0.REPO),str(file),'-o',str(binary)]
            base.owner.command(cmd);commands.append(cmd)
            if name=='publisher':policies[sanitizer]=json.loads(base.owner.command([str(binary),str(folder/'publish')]))
            else:
                for case in CASES:
                    path=folder/(case+'.bin');row=json.loads(base.owner.command([str(binary),case,str(path)]));row['sanitizer']=sanitizer
                    if path.exists():row['session']=decode_session(path.read_bytes())
                    rows.append(row)
        for path in sorted(folder.glob('*.bin')):
            path.with_suffix('.json').write_text(json.dumps(decode_session(path.read_bytes()),indent=2)+'\n')
    stacks={}
    for label in ('dormant','window-30s'):
        folder=output/label;folder.mkdir();cmd=['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-objdump','-d',str(SEALED/label/'full.elf')]
        disassembly=base.owner.command(cmd);commands.append(cmd);(folder/'disassembly.txt').write_text(disassembly)
        stack_rows=json.loads((SEALED/label/'stack-usage.json').read_text());(folder/'compiler-stack-usage.json').write_text(json.dumps(stack_rows,indent=2)+'\n')
        data=analyze(disassembly,stack_rows);data['elf_sha256']=base.ep0.sha(SEALED/label/'full.elf')
        (folder/'stack-analysis.json').write_text(json.dumps(data,indent=2)+'\n');stacks[label]=data
        assert data['roots']['session_capture']['stack_bound_bytes']==352
        assert data['roots']['Ep0SessionSaveJoined']['stack_bound_bytes'] is None
    assert inputs=={n:base.ep0.sha(ROOT/n) for n in inputs};assert production=={n:base.ep0.sha(candidate.startup.startup.REPO/n) for n in production}
    assert source_audit==base.owner.source_audit();assert tickets=={n:base.ep0.sha(base.ep0.PRIVATE/'analysis'/n) for n in tickets};verify(SEALED)
    result=dict(schema='A23-session-concurrency-1',source_audit=source_audit,source_hashes=inputs,production_sources_sha256=production,tickets_sha256=tickets,
        compiler_commands=commands,policy=policies,runtime_cases=rows,runtime_case_count=len(CASES),native_cases_per_sanitizer=10+len(CASES),
        native_sanitizer_runs=2*(10+len(CASES)),stack_analysis=stacks,core_test_hooks_only=True,runtime_status_test_hook_only=True,
        core_context_objects_per_sanitizer=32,core_receipt_objects_per_sanitizer=32,
        actual_host_pthreads=True,actual_switch_threads_executed=False,cooperative_host_interruption_only=True,
        runtime_modified=False,production_modified=False,prior_evidence_modified=False,old_wire_modified=False,
        new_full_arm_elf_built=False,arm_executed=False,firmware_packaged=False,usb_accessed=False,sd_accessed=False,
        hardware_verified=False,root_cause_confirmed=False,source_authenticated=False,cleanup_authorized=False,
        whole_thread_stack_verified=False,runtime_peak_measured=False)
    (output/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (output/'SHA256SUMS').write_text(''.join(base.ep0.sha(p)+'  '+str(p.relative_to(output))+'\n' for p in sorted(output.rglob('*')) if p.is_file()))
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    s=run(a.output);print(json.dumps(dict(policy=s['policy'],runtime_cases=s['runtime_case_count'],sanitizer_runs=s['native_sanitizer_runs']),indent=2))
if __name__=='__main__':main()
