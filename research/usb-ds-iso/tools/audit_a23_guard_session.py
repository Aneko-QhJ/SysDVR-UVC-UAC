#!/usr/bin/env python3
"""Replay sealed guarded VideoStreamThread and serialize offline diagnostics only.
No old runtime edits, new firmware, device calls, SD or ARM execution.
"""
import argparse
import json
from pathlib import Path
import build_a23_guard_candidate as guard
from analyze_ep0_diagnostic import decode_diagnostic
from analyze_ep0_candidate_capture import decode_capture
from workflows.artifacts import verify
base=guard.base;ROOT=guard.ROOT
SEALED=base.ep0.PRIVATE/'analysis/A23-guarded-candidate-review-20261014'
CASES=('complete','iso-pending','ack-timeout','late-ack-report','ack-report-error','ctrl-duplicate',
       'iso-duplicate','iso-report-error','failed-iso-post','failed-ack-post','stop-inside-wait',
       'prestatus-timeout','reused-control-id','statuses-5','statuses-6','statuses-8','statuses-9',
       'session-extra-2','session-extra-3','session-extra-5','session-extra-6','trace-overflow',
       'video-join-error','audio-join-error','identity-error','zero-nonce','ready-stop','window-wait')
INPUTS=('device/ep0_diagnostic_capture.h','tools/analyze_ep0_diagnostic.py','tools/audit_a23_guard_session.py',
        'tools/analyze_ep0_trace.py','tools/analyze_ep0_candidate_capture.py',
        'tests/a23_guard_session.c','tests/ep0_diagnostic_policy_test.c')

def native_source(label):
    s=(SEALED/'guard-buffers.c').read_text();s=s[:s.index('int main(')]
    source=(SEALED/label/'source/sysmodule/main.c').read_text()
    video=guard.audit.extract(source,'static void VideoStreamThread(void* arg)','// ============================================================================\n// Audio Streaming Thread')
    video=base.trace.replace(video,'        UvcDeviceProcessRequests();','        session_dispatch();')
    recipe=(SEALED/label/'source/uvc/ep0_candidate_recipe.h').read_text()
    session=(ROOT/'tests/a23_guard_session.c').read_text()
    session=base.trace.replace(session,'/* INSERT_VIDEO_THREAD */',video)
    return s+'\n#include "research/usb-ds-iso/device/ep0_diagnostic_capture.h"\n#include "research/usb-ds-iso/device/ep0_candidate_window.h"\n'+recipe+session

def run(output):
    output=Path(output);sealed=verify(SEALED);source_audit=base.owner.source_audit()
    old=json.loads((SEALED/'audit.json').read_text())
    assert source_audit==old['source_audit']
    tickets={n:base.ep0.sha(base.ep0.PRIVATE/'analysis'/n) for n in base.owner.TICKETS}
    assert tickets==old['tickets_sha256']
    names=[*old['source_hashes'],*INPUTS];inputs={n:base.ep0.sha(ROOT/n) for n in names}
    for n,h in old['source_hashes'].items():
        if inputs[n]!=h:raise ValueError('Sealed input drift: '+n)
    commands=[];flags=['-DISO_PROBE','-DISO_PROBE_BURST_MODE','-DISO_PROBE_EVENT_AUDIT','-DISO_PROBE_CONTEXT_AUDIT','-DISO_PROBE_FOLLOWUP_SIA']
    for label in ('dormant','window-30s'):
        file=output/(label+'.c');file.write_text(native_source(label))
        commands.append(base.trace.compile_native(file,output/label,flags))
    rows=[]
    for case in CASES:
        label='window-30s' if case=='window-wait' else 'dormant'
        recipe=old['builds'][label]['runtime_recipe_digest'];path=output/(case+'.diagnostic.bin')
        normal=output/(case+'.ownership.bin')
        row=json.loads(base.owner.command([str(output/label),case,str(path),str(normal)]));row['candidate_recipe_digest']=recipe
        if normal.exists():
            row['ownership']=decode_capture(normal.read_bytes(),recipe)
            (output/(case+'.ownership.json')).write_text(json.dumps(row['ownership'],indent=2)+'\n')
        if path.exists():
            row['diagnostic']=decode_diagnostic(path.read_bytes(),recipe)
            (output/(case+'.diagnostic.json')).write_text(json.dumps(row['diagnostic'],indent=2)+'\n')
        if row['copy_overlaps'] or row['reposts']:raise ValueError('Unsafe control reuse: '+case)
        rows.append(row)
    policy=output/'diagnostic-policy'
    commands.append(base.trace.compile_native(ROOT/'tests/ep0_diagnostic_policy_test.c',policy,[]))
    policies=json.loads(base.owner.command([str(policy)]))
    # Compile pure serialization against the actual Switch headers; no link or
    # integration into the old candidate ELF and no execution of this object.
    file=output/'diagnostic-arm.c';file.write_text('#include "ep0_diagnostic_capture.h"\nsize_t test_diagnostic(const Ep0TraceOwner *s,const Ep0GuardObservation *g,uint64_t e,uint32_t v,uint32_t a,const uint8_t r[32],uint8_t *o,size_t n) { return ep0_diagnostic_capture(s,g,e,v,a,r,o,n); }\n')
    cmd=['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-gcc','-std=gnu11','-Wall','-Wextra','-Werror','-O3','-D__SWITCH__','-I'+str(ROOT/'device'),'-I/opt/devkitpro/libnx/include','-c',str(file),'-o',str(output/'diagnostic-arm.o')]
    base.owner.command(cmd);commands.append(cmd)
    if source_audit!=base.owner.source_audit() or inputs!={n:base.ep0.sha(ROOT/n) for n in names}:raise ValueError('Source drift')
    if tickets!={n:base.ep0.sha(base.ep0.PRIVATE/'analysis'/n) for n in base.owner.TICKETS}:raise ValueError('Ticket drift')
    verify(SEALED)
    result=dict(schema='A23-guard-session-audit-1',source_audit=source_audit,tickets_sha256=tickets,source_hashes=inputs,
        sealed_input=sealed,compiler_commands=commands,cases=rows,case_count=len(rows),diagnostic_count=sum('diagnostic' in r for r in rows),
        diagnostic_policy=policies,diagnostic_arm_object_sha256=base.ep0.sha(output/'diagnostic-arm.o'),
        real_video_function_replayed=True,usb_accessed=False,sd_accessed=False,production_modified=False,prior_runtime_modified=False,
        firmware_packaged=False,new_full_arm_elf_built=False,arm_executed=False,hardware_verified=False,root_cause_confirmed=False,
        actual_threads_executed=False,diagnostic_sink_in_candidate=False,diagnostic_authorizes_cleanup=False,
        candidate_recipe_authenticates_native_diagnostics=False,matching_terminal_assumption=[3,4,5])
    (output/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (output/'SHA256SUMS').write_text(''.join(base.ep0.sha(p)+'  '+str(p.relative_to(output))+'\n' for p in sorted(output.rglob('*')) if p.is_file()))
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);r=run(a.output)
    print(json.dumps(dict(output=str(a.output),cases=r['case_count'],diagnostics=r['diagnostic_count']),indent=2))
if __name__=='__main__':main()
