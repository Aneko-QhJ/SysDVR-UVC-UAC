#!/usr/bin/env python3
"""Isolated joint BURST preflight and per-ready-request trace budget candidate.
Native execution and full ARM ELF link only; no package, USB, SD or ticket writes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import audit_a23_guard_session as session
from analyze_ep0_candidate_capture import decode_capture
from analyze_ep0_diagnostic import decode_diagnostic
from workflows.artifacts import verify
guard=session.guard;base=session.base;ROOT=session.ROOT;SEALED=session.SEALED
SESSION=session.base.ep0.PRIVATE/'analysis/A23-guard-session-review-20261014-final'
DEVICE=('ep0_request_admission.h','ep0_request_admission.c')
INPUTS=(*('device/'+x for x in DEVICE),'tools/build_a23_bounded_candidate.py','tests/ep0_request_admission_test.c')
POLICIES=tuple('limit-'+str(n) for n in range(129))+('slot-one-left','iso-borrowed','proposed-alias','bound-violation','stop-before-followup',
    'ack-out-borrowed','ack-zero-borrowed','proposed-adjacent','followup-flood')

def handler(s):
    r=base.trace.replace
    s=r(s,'        if(!Ep0CandidateGuardAllow(g_isoBuffer,length,2))return;',
        '        if(!Ep0CandidateAdmissionBurst(g_isoBuffer,length,_ctrlBufferFor(iface)))return;')
    s=r(s,'static bool _serviceSetup(UsbDsInterface* iface)\n{',
        'static bool _serviceSetup(UsbDsInterface* iface)\n{\n    if(Ep0CandidateStopRequested())return false;')
    s=r(s,'    trace_request(iface);','    if(!Ep0CandidateAdmissionReady())return false;\n    trace_request(iface);')
    s=r(s,'    _handleSetupPacket(iface);\n    return true;',
        '    _handleSetupPacket(iface);\n    Ep0CandidateAdmissionEnd();\n    return true;')
    s=r(s,'    while (serviced &&','    while (serviced && !Ep0CandidateStopRequested() &&')
    return r(s,'''    bool entered=Ep0CandidateEnter();
    if(entered)Ep0CandidateObserveIsoOwnership(g_isoStatus.state,g_isoStatus.urb_id);
    _candidateProcessRequests();
    if(entered)Ep0CandidateLeave();''', '''    if(!Ep0CandidateEnter()) { Ep0CandidateRequestStop();return; }
    Ep0CandidateObserveIsoOwnership(g_isoStatus.state,g_isoStatus.urb_id);
    if(Ep0CandidateAdmissionBegin())_candidateProcessRequests();
    Ep0CandidateLeave();''')

def strict_export(s):
    return base.trace.replace(s,'    if(!ep0_owner_handoff(&storage,exporter,actual_join_result))return false;',
        '    if(!ep0_owner_handoff(&storage,exporter,actual_join_result))return false;\n'
        '    if(storage.trace.dropped || storage.trace.invalid)storage.fault=1;')

def native_transform(s):
    s=handler(strict_export(s));r=base.trace.replace
    s=r(s,'#include "research/usb-ds-iso/device/ep0_candidate_guard.h"',
        '#include "research/usb-ds-iso/device/ep0_candidate_guard.h"\n#include "research/usb-ds-iso/device/ep0_request_admission.h"')
    adapter=(ROOT/'device/ep0_request_admission.c').read_text().replace('#include "ep0_request_admission.h"','')
    return r(s,'static void trace_id(',
        'void Ep0CandidateGuardReject(unsigned reason) { (void)reject(reason); }\n'+adapter+'\nstatic void trace_id(')

def native_session(label,digest):
    s=native_transform(session.native_source(label));r=base.trace.replace
    s=r(s,(SEALED/label/'source/uvc/ep0_candidate_recipe.h').read_text(),recipe_header(digest))
    s=r(s,'    Ep0TraceOwner before=*o;','    const Ep0AdmissionObservation *admission=Ep0CandidateAdmissionObservation();\n    Ep0TraceOwner before=*o;')
    s=r(s,'\\"records\\":%u,',
        '\\"admitted_requests\\":%u,\\"trace_refusals\\":%u,\\"bound_violations\\":%u,\\"largest_request\\":%u,\\"stop_skips\\":%u,\\"records\\":%u,')
    return r(s,'           o->trace.count,o->trace.dropped,',
        '           admission->admitted,admission->trace_refusals,admission->bound_violations,admission->largest_request,admission->stop_skips,o->trace.count,o->trace.dropped,')

def recipe_header(digest):return 'static const uint8_t ep0CandidateRecipe[32]={'+','.join(str(x) for x in bytes.fromhex(digest))+'};\n'

def run(output):
    output=Path(output);sealed=verify(SEALED);verify(SESSION)
    old=json.loads((SESSION/'audit.json').read_text());source_audit=base.owner.source_audit()
    assert source_audit==old['source_audit']
    tickets={n:base.ep0.sha(base.ep0.PRIVATE/'analysis'/n) for n in base.owner.TICKETS};assert tickets==old['tickets_sha256']
    names=[*old['source_hashes'],*INPUTS];inputs={n:base.ep0.sha(ROOT/n) for n in names}
    for n,h in old['source_hashes'].items():
        if inputs[n]!=h:raise ValueError('Input drift: '+n)
    info=dict(source_sha256=inputs,guard_manifest_sha256=base.ep0.sha(SEALED/'SHA256SUMS'),
        session_manifest_sha256=base.ep0.sha(SESSION/'SHA256SUMS'),libnx_a_sha256=base.ep0.sha(Path('/opt/devkitpro/libnx/lib/libnx.a')),
        compiler_version=base.owner.command(['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-gcc','--version']))
    recipe=hashlib.sha256(json.dumps(info,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    (output/'recipe.json').write_text(json.dumps(dict(input_digest=recipe,inputs=info),indent=2)+'\n')
    commands=[];digests={};builds={}
    flags=['-DISO_PROBE','-DISO_PROBE_BURST_MODE','-DISO_PROBE_EVENT_AUDIT','-DISO_PROBE_CONTEXT_AUDIT','-DISO_PROBE_FOLLOWUP_SIA']
    for label in ('dormant','window-30s'):
        folder=output/label;folder.mkdir();shutil.copytree(SEALED/label/'source',folder/'source')
        for name in DEVICE:shutil.copyfile(ROOT/'device'/name,folder/'source/uvc'/name)
        p=folder/'source/uvc/ep0_candidate_guard.c';p.write_text(p.read_text()+'\nvoid Ep0CandidateGuardReject(unsigned reason) { (void)reject(reason); }\n')
        p=folder/'source/uvc/ep0_candidate.c';p.write_text(strict_export(p.read_text()))
        p=folder/'source/uvc/uvc_device.c';p.write_text('#include "ep0_request_admission.h"\n'+handler(p.read_text()))
        config=dict(input_digest=recipe,window_ms=0 if label=='dormant' else 30000,request_record_reserve=17,offline_compile_only=True)
        digest=hashlib.sha256(json.dumps(config,sort_keys=True,separators=(',',':')).encode()).hexdigest();digests[label]=digest
        (folder/'recipe.json').write_text(json.dumps(dict(input_digest=digest,configuration=config),indent=2)+'\n')
        (folder/'source/uvc/ep0_candidate_recipe.h').write_text(recipe_header(digest))
        builds[label]=base.compile_elf(folder,commands);builds[label].update(runtime_recipe_digest=digest,window_ms=config['window_ms'])
        symbols=(folder/'symbols.txt').read_text()
        for symbol in ('Ep0CandidateAdmissionBegin','Ep0CandidateAdmissionReady','Ep0CandidateAdmissionEnd','Ep0CandidateAdmissionBurst','Ep0CandidateGuardReject'):
            if symbol not in symbols:raise ValueError('Admission hook missing: '+symbol)
        file=output/(label+'-session.c');file.write_text(native_session(label,digest))
        commands.append(base.trace.compile_native(file,output/(label+'-session'),flags))
    rows=[]
    for case in session.CASES:
        label='window-30s' if case=='window-wait' else 'dormant';digest=digests[label]
        path=output/(case+'.diagnostic.bin');normal=output/(case+'.ownership.bin')
        row=json.loads(base.owner.command([str(output/(label+'-session')),case,str(path),str(normal)]))
        row['candidate_recipe_digest']=digest
        if path.exists():
            row['diagnostic']=decode_diagnostic(path.read_bytes(),digest)
            (output/(case+'.diagnostic.json')).write_text(json.dumps(row['diagnostic'],indent=2)+'\n')
        if normal.exists():
            row['ownership']=decode_capture(normal.read_bytes(),digest)
            (output/(case+'.ownership.json')).write_text(json.dumps(row['ownership'],indent=2)+'\n')
        if row['copy_overlaps'] or row['reposts'] or row['invalid']:raise ValueError('Unsafe replay: '+case)
        if case!='trace-overflow' and row['dropped']:raise ValueError('Budget overflow: '+case)
        rows.append(row)
    prefix=(SEALED/'guard-buffers.c').read_text();prefix=prefix[:prefix.index('int main(')]
    prefix=native_transform(prefix)
    prefix=base.trace.replace(prefix,'static UsbSetupPacket shared_setup;', 'static unsigned native_followups;\nstatic UsbSetupPacket shared_setup;')
    prefix=base.trace.replace(prefix,'    Event *events[]={a,b,c};',
        '    Event *events[]={a,b,c};\n'
        '    if(native_followups && !a->signaled && !b->signaled && !c->signaled) {\n'
        '        native_followups--;shared_setup=status;now_ns++;a->signaled=b->signaled=c->signaled=true;\n'
        '    }')
    file=output/'admission-policy.c';file.write_text(prefix+(ROOT/'tests/ep0_request_admission_test.c').read_text())
    commands.append(base.trace.compile_native(file,output/'admission-policy',flags))
    policies=[json.loads(base.owner.command([str(output/'admission-policy'),c])) for c in POLICIES]
    file=output/'bounded-buffers.c';file.write_text(native_transform((SEALED/'guard-buffers.c').read_text()))
    commands.append(base.trace.compile_native(file,output/'bounded-buffers',flags))
    buffers=[json.loads(base.owner.command([str(output/'bounded-buffers'),c])) for c in guard.audit.BUFFER_CASES]
    if any(r['cpu_write_overlaps'] or r['same_address_reposts'] for r in buffers):raise ValueError('Buffer regression')
    if source_audit!=base.owner.source_audit() or inputs!={n:base.ep0.sha(ROOT/n) for n in names}:raise ValueError('Source drift')
    if tickets!={n:base.ep0.sha(base.ep0.PRIVATE/'analysis'/n) for n in base.owner.TICKETS}:raise ValueError('Ticket drift')
    verify(SEALED);verify(SESSION)
    result=dict(schema='A23-bounded-candidate-1',source_audit=source_audit,tickets_sha256=tickets,source_hashes=inputs,
        recipe_digest=recipe,compiler_commands=commands,sealed_input=sealed,cases=rows,case_count=len(rows),
        policy_cases=policies,policy_case_count=len(policies),buffer_cases=buffers,buffer_case_count=len(buffers),builds=builds,request_record_reserve=17,
        diagnostic_count=sum('diagnostic' in r for r in rows),normal_capture_count=sum('ownership' in r for r in rows),
        whole_burst_ack_preflight_implemented=True,per_ready_request_budget_implemented=True,
        normal_export_requires_lossless_trace=True,stop_ends_followup_loop=True,diagnostic_sink_in_candidate=False,
        production_modified=False,prior_runtime_modified=False,usb_accessed=False,sd_accessed=False,
        firmware_packaged=False,arm_executed=False,hardware_verified=False,root_cause_confirmed=False,
        actual_threads_executed=False)
    (output/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (output/'SHA256SUMS').write_text(''.join(base.ep0.sha(p)+'  '+str(p.relative_to(output))+'\n' for p in sorted(output.rglob('*')) if p.is_file()))
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);r=run(a.output)
    print(json.dumps(dict(output=str(a.output),sessions=r['case_count'],policies=r['policy_case_count'],builds=r['builds']),indent=2))
if __name__=='__main__':main()
