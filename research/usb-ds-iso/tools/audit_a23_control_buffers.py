#!/usr/bin/env python3
"""Offline actual-source review of control buffer reuse and cleanup paths.
No production edits, ARM execution/build, USB/SD operations or ticket renewal.
DMA/thread state is explicitly injected, not inferred from wait/cancel/close.
"""
import argparse
import json
from pathlib import Path
import build_a23_trace_candidate as base
from workflows.artifacts import verify
ROOT=base.ep0.ROOT
SINK=base.ep0.PRIVATE/'analysis/A23-EP0-candidate-sink-review-20261013-final'
BUFFER_CASES=('drained','in-timeout','in-report-error','in-wrong-id','in-status-1','in-status-2',
              'in-status-unknown','in-terminal-4','in-terminal-5','out-status-timeout','out-data-timeout',
              'out-data-report-error','burst-ack-timeout','burst-ack-terminal-4','cross-vs','cross-vc',
              'late-report-after-copy','cancel-control-pending','disconnect-reconnect')
EXIT_CASES=('callback-live','callback-stopped-pending','callback-drained','original-pending',
            'original-video-join-error','original-drained','candidate-pending','candidate-video-join-error',
            'candidate-audio-join-error','candidate-sink-error','candidate-drained')
INPUTS=('tests/a23_control_buffer_model.c','tests/a23_control_buffer_session.c','tests/a23_exit_paths_fixture.c',
        'tools/audit_a23_control_buffers.py','tools/build_a23_trace_candidate.py','tools/probe_a23_ep0_trace.py',
        'tools/audit_a23_ep0.py','tools/audit_a23_trace_owner.py','tools/workflows/artifacts.py',
        'tests/a23_ep0_dispatch_fixture.c','tests/a23_hos_setup_fixture.c',
        'tests/a23_ep0_candidate_services.c','tests/a23_ep0_candidate_bridge.c',
        *('device/'+x for x in base.DEVICE))


def extract(s,start,end):
    if s.count(start)!=1:raise ValueError('Unique extraction anchor drift: '+start)
    a=s.index(start);b=s.index(end,a);return s[a:b]


def buffer_fixture(candidate):
    source=base.poll_source()+'\n'+base.ep0.actual_source()
    if candidate:source=base.integrate(source)
    source=base.trace.replace(source,'    memcpy(buf, data, len);',
                             '    model_before_copy(buf,len);\n    memcpy(buf, data, len);\n    model_after_copy(buf,len);')
    text=base.native_fixture('shared',source,'03'*32)
    pos=text.index('static void record_log(');text=text[:pos]+(ROOT/'tests/a23_control_buffer_model.c').read_text()+'\n'+text[pos:]
    text=base.trace.replace(text,'    i->CtrlInCompletionEvent.signaled=true;return 0;',
                           '    model_post(i->interface_index,0,b,n,*id);\n    i->CtrlInCompletionEvent.signaled=true;return 0;')
    text=base.trace.replace(text,'    i->CtrlOutCompletionEvent.signaled=true;return 0;',
                           '    model_post(i->interface_index,1,b,n,*id);\n    i->CtrlOutCompletionEvent.signaled=true;return 0;')
    a=text.index('static Result candidate_ctrl_report(');b=text.index('static Result usbDsInterface_GetCtrlInReportData(',a)
    chunk=text[a:b]
    chunk=base.trace.replace(chunk,'    ctrl_report_calls++;','    ctrl_report_calls++;\n    if(direction && model_out_report_rc)return model_out_report_rc;')
    chunk=base.trace.replace(chunk,'        late_ctrl_id=0;return 0;',
                            '        late_ctrl_id=0;model_report(i->interface_index,direction,r);return 0;')
    chunk=base.trace.replace(chunk,'    return 0;\n}', '    model_report(i->interface_index,direction,r);return 0;\n}')
    text=text[:a]+chunk+text[b:]
    for old in ('    if (e->kind==1 && ack_wait_rc) { now_ns+=timeout; return ack_wait_rc; }',
                '    if(e->kind==1 && ack_wait_rc) { now_ns+=timeout;return ack_wait_rc; }'):
        text=base.trace.replace(text,old,'    if(e->kind==2 && model_out_wait_rc) { now_ns+=timeout;return model_out_wait_rc; }\n'+old)
    return text[:text.index('int main(')]+(ROOT/'tests/a23_control_buffer_session.c').read_text()


def exit_fixture():
    uv=(base.ep0.REPO/'source/uvc/uvc_device.c').read_text()
    main=(base.ep0.REPO/'source/sysmodule/main.c').read_text()
    core=(base.ep0.REPO/'source/core.c').read_text()
    candidate=(SINK/'window-30s/source/sysmodule/main.c').read_text()
    original_callback=extract(main,'void __appExit(void)','// ============================================================================\n// Main Entry Point')
    if original_callback!=extract(candidate,'void __appExit(void)','// ============================================================================\n// Main Entry Point'):
        raise ValueError('Sealed callback unexpectedly changed')
    normal=extract(main[main.index('int main('):],'    g_running = false;','    LOG("SysDVR-UVC exiting')
    transforms={
        '/* INSERT_DEVICE_EXIT */':extract(uv,'void UvcDeviceExit(void)','bool UvcDeviceIsConnected(void)'),
        '/* INSERT_ORIGINAL_JOIN */':extract(core,'void JoinThread(Thread* t)','const char* CoreGetSerialNumber'),
        '/* INSERT_APP_EXIT */':original_callback,
        '/* INSERT_ORIGINAL_NORMAL */':normal,
        '/* INSERT_CANDIDATE_NORMAL */':extract(candidate,'    Result video_join=threadWaitForExit','    LOG("SysDVR-UVC exiting')}
    text=(ROOT/'tests/a23_exit_paths_fixture.c').read_text()
    for marker,value in transforms.items():text=base.trace.replace(text,marker,value)
    return text


def run(output):
    output=Path(output);sealed=verify(SINK);source_audit=base.owner.source_audit()
    for name in base.DEVICE:
        if base.ep0.sha(ROOT/'device'/name)!=base.ep0.sha(SINK/'dormant/source/uvc'/name):
            raise ValueError('Native runtime differs from sealed ARM input: '+name)
    tickets={n:base.ep0.sha(base.ep0.PRIVATE/'analysis'/n) for n in base.owner.TICKETS}
    inputs={n:base.ep0.sha(ROOT/n) for n in INPUTS};commands=[];rows=[]
    flags=['-DISO_PROBE','-DISO_PROBE_BURST_MODE','-DISO_PROBE_EVENT_AUDIT','-DISO_PROBE_CONTEXT_AUDIT','-DISO_PROBE_FOLLOWUP_SIA']
    for label,enabled in (('original',False),('candidate',True)):
        file=output/(label+'-buffers.c');file.write_text(buffer_fixture(enabled))
        commands.append(base.trace.compile_native(file,output/(label+'-buffers'),flags))
    for case in BUFFER_CASES:
        pair={}
        for label in ('original','candidate'):
            row=json.loads(base.owner.command([str(output/(label+'-buffers')),case]));pair[label]=row
        def observed(r):return {k:v for k,v in r.items() if not k.startswith('ledger_')}
        if observed(pair['original'])!=observed(pair['candidate']):raise ValueError('Source behavior changed: '+case)
        rows.append(dict(case=case,original=pair['original'],candidate=pair['candidate'],source_behavior_identical=True))
    file=output/'exit-paths.c';file.write_text(exit_fixture())
    commands.append(base.trace.compile_native(file,output/'exit-paths',['-DISO_PROBE']))
    exits=[json.loads(base.owner.command([str(output/'exit-paths'),case])) for case in EXIT_CASES]
    if base.owner.source_audit()!=source_audit or tickets!={n:base.ep0.sha(base.ep0.PRIVATE/'analysis'/n) for n in base.owner.TICKETS}:
        raise ValueError('Production/ticket changed')
    if inputs!={n:base.ep0.sha(ROOT/n) for n in INPUTS}:raise ValueError('Input changed')
    verify(SINK)
    result=dict(schema='A23-control-buffer-cleanup-audit-1',source_audit=source_audit,tickets_sha256=tickets,
                source_hashes=inputs,sealed_input=sealed,compiler_commands=commands,buffer_cases=rows,
                buffer_case_count=len(rows),source_replay_count=len(rows)*2,exit_cases=exits,exit_case_count=len(exits),
                cpu_overlap_hooks_native_only=True,matching_terminal_status_assumption=[3,4,5],dma_executed=False,
                threads_executed=False,callback_during_live_thread_reachability_verified=False,
                hardware_verified=False,root_cause_confirmed=False,production_modified=False,firmware_packaged=False,
                usb_accessed=False,sd_accessed=False,ledger_drain_proves_no_prior_reuse=False,
                zero_length_pointer_reuse_proves_nonzero_dma_corruption=False)
    (output/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (output/'SHA256SUMS').write_text(''.join(base.ep0.sha(p)+'  '+str(p.relative_to(output))+'\n' for p in sorted(output.rglob('*')) if p.is_file()))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False);r=run(args.output)
    print(json.dumps(dict(output=str(args.output),source_replays=r['source_replay_count'],exit_cases=r['exit_case_count'])))

if __name__=='__main__':main()
