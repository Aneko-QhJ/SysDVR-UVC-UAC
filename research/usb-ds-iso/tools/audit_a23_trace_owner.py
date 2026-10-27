#!/usr/bin/env python3
"""Offline lifecycle/ownership policy audit and libnx adapter ELF link.

No production insertion, firmware packaging, hardware or ticket operations.
The generated ELF is a link fixture, NOT a complete instrumented A23 firmware.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess

import audit_a23_ep0 as ep0
from analyze_ep0_trace import decode
from workflows.artifacts import verify

CASES=('happy','prejoin','failed-join','immutable','wrong-writer','inside-call','trace-overflow',
       'terminal-4','terminal-5','wait-timeout','cancel-only','disconnect','wrong-id','wrong-channel',
       'state-1','state-2','unknown-status','failed-report','count-9','duplicate-report',
       'failed-post','missing-id','reuse','capacity','same-id-other-channel','zero-id',
       'late-terminal','reentrant')
INPUTS=('device/ep0_trace.h','device/ep0_trace_owner.h','device/ep0_trace_libnx.h',
        'tests/ep0_trace_owner_test.c','tests/ep0_trace_owner_link.c')
TICKETS=('A23-IOUSBHost-burst-next-test.json','A23-IOUSBHost-next-test.json','A23-next-test.json')


def command(args,env=None):
    p=subprocess.run(args,env=env,check=True,capture_output=True,text=True)
    if p.stderr:raise ValueError('Unexpected compiler/sanitizer stderr: '+p.stderr)
    return p.stdout


def source_audit():
    frozen=json.loads((ep0.PACKAGE/'validation.json').read_text())
    names=('source/uvc/uvc_device.c','source/sysmodule/main.c','source/uvc/iso_probe_protocol.h')
    sources={name:ep0.sha(ep0.REPO/name) for name in names}
    if any(sources[name]!=frozen['sources_sha256'][name] for name in names):
        raise ValueError('Production sources differ from frozen A23')
    main=(ep0.REPO/'source/sysmodule/main.c').read_text()
    device=(ep0.REPO/'source/uvc/uvc_device.c').read_text()
    # Fail on anchor drift even though hashes already bind these observations.
    video=main[main.index('static void VideoStreamThread'):main.index('static void AudioStreamThread')]
    if video.count('UvcDeviceProcessRequests();')!=1:raise ValueError('Owner call anchor mismatch')
    tail=main[main.index('int main('):]
    order=['while (g_running)', 'g_running = false;', 'JoinThread(&g_videoThread);',
           'JoinThread(&g_audioThread);','UvcDeviceExit();']
    cursor=0
    for text in order:cursor=tail.index(text,cursor)+len(text)
    writes=[i for i,line in enumerate(main.splitlines(),1) if 'g_running = false;' in line]
    if len(writes)!=2:raise ValueError('Stop writer anchor mismatch')
    ctrl=device[device.index('static Result _ctrlInXfer('):device.index('// GET-type request:')]
    if ctrl.count('if (R_FAILED(rc)) return rc;')!=6:raise ValueError('Control failure path mismatch')
    core=(ep0.REPO/'source/core.c').read_text()
    join='void JoinThread(Thread* t)\n{\n    threadWaitForExit(t);\n    threadClose(t);\n}'
    if core.count(join)!=1:raise ValueError('JoinThread result handling anchor drift')
    return dict(production_sources_sha256=sources,single_ep0_owner='VideoStreamThread',
                core_source_sha256=ep0.sha(ep0.REPO/'source/core.c'),join_helper_discards_wait_result=True,
                normal_exit_order=order,g_running_false_lines=writes,
                regular_stop_trigger_present=False,exit_export_automatically_reachable=False,
                ctrl_wait_failure_proves_release=False,cancel_or_disconnect_proves_release=False,
                interface_close_result_proves_release=False,
                iso_terminal_assumption=[3,4,5],iso_terminal_assumption_hardware_verified=False,
                existing_ctrl_helpers_do_not_preserve_raw_report_ownership_ledger=True)


def run(output):
    output=Path(output)
    before={name:ep0.sha(ep0.PRIVATE/'analysis'/name) for name in TICKETS}
    audit=source_audit();snap=output/'inputs';snap.mkdir()
    for name in INPUTS:
        p=snap/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ep0.ROOT/name,p)
    input_hashes={name:ep0.sha(ep0.ROOT/name) for name in INPUTS}
    for name in (*audit['production_sources_sha256'],'source/core.c'):
        p=snap/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ep0.REPO/name,p)
    commands=[]
    native=['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
            '-fno-omit-frame-pointer','-g','-I'+str(ep0.REPO),
            str(ep0.ROOT/'tests/ep0_trace_owner_test.c'),'-o',str(output/'owner-test')]
    command(native);commands.append(native);rows=[]
    for case in CASES:
        binary=output/(case+'.bin')
        row=json.loads(command([str(output/'owner-test'),case,str(binary)]))
        if binary.exists():
            analysis=decode(binary.read_bytes())
            if analysis['trace_window_complete']:raise ValueError('Policy fixture cannot claim a complete capture')
            (output/(case+'-trace.json')).write_text(json.dumps(analysis,indent=2)+'\n')
        rows.append(row)
    # Link against the installed libnx ABI and startup. No make target, NSO,
    # NSP, service access, console execution or production objects are involved.
    compiler='/opt/devkitpro/devkitA64/bin/aarch64-none-elf-gcc'
    cross=[compiler,'-std=c11','-Wall','-Wextra','-Werror','-O2','-g',
           '-march=armv8-a+crc+crypto','-mtune=cortex-a57','-mtp=soft','-fPIE',
           '-ffunction-sections','-D__SWITCH__','-I'+str(ep0.REPO),'-I/opt/devkitpro/libnx/include',
           '-c',str(ep0.ROOT/'tests/ep0_trace_owner_link.c'),'-o',str(output/'owner-libnx.o')]
    command(cross);commands.append(cross)
    link=[compiler,'-specs=/opt/devkitpro/libnx/switch.specs','-march=armv8-a+crc+crypto',
          '-mtune=cortex-a57','-mtp=soft','-fPIE',str(output/'owner-libnx.o'),
          '-L/opt/devkitpro/libnx/lib','-lnx','-Wl,-Map,'+str(output/'owner-libnx.map'),
          '-o',str(output/'owner-libnx.elf')]
    env=dict(os.environ,DEVKITPRO='/opt/devkitpro');command(link,env);commands.append(link)
    readelf='/opt/devkitpro/devkitA64/bin/aarch64-none-elf-readelf'
    header=command([readelf,'-h',str(output/'owner-libnx.elf')])
    symbols=command([readelf,'-Ws',str(output/'owner-libnx.elf')])
    if 'AArch64' not in header or 'DYN' not in header or 'checked_adapter' not in symbols:
        raise ValueError('ELF ABI/adapter binding failed')
    for name in ('usbDsInitialize','usbDsEndpoint_PostBufferAsync','fsOpenSdCardFileSystem'):
        if name in symbols:raise ValueError('Unexpected service entry in link fixture: '+name)
    (output/'elf-header.txt').write_text(header);(output/'elf-symbols.txt').write_text(symbols)
    # Bind the installed helper's actual code, not just header declarations.
    prefix='/opt/devkitpro/devkitA64/bin/aarch64-none-elf-'
    member=subprocess.check_output([prefix+'ar','p','/opt/devkitpro/libnx/lib/libnx.a','usbds.o'])
    (output/'usbds.o').write_bytes(member)
    parse=output/'usbds-parse.bin'
    command([prefix+'objcopy','--dump-section','.text.usbDsParseReportData='+str(parse),
             str(output/'usbds.o')])
    code=parse.read_bytes()
    anchors={0x50:0xb9400cc1,0x54:0x52905180,0x58:0x7100103f,0x60:0x528e9180,
             0x64:0x7100143f,0x6c:0x52821180,0x70:0x71000c3f,0x90:0x52800000}
    if len(code)!=0xa0 or any(struct.unpack_from('<I',code,a)[0]!=v for a,v in anchors.items()):
        raise ValueError('Installed libnx parse helper anchor drift')
    assembly=command([prefix+'objdump','-d','-j','.text.usbDsParseReportData',str(output/'usbds.o')])
    (output/'usbds-parse-disassembly.txt').write_text(assembly)
    libnx={str(p):ep0.sha(p) for p in map(Path,('/opt/devkitpro/libnx/include/switch/services/usbds.h',
                                            '/opt/devkitpro/libnx/lib/libnx.a','/opt/devkitpro/libnx/switch.specs'))}
    if audit!=source_audit():raise ValueError('Production source changed during audit')
    if any(ep0.sha(ep0.ROOT/name)!=input_hashes[name] or ep0.sha(snap/name)!=input_hashes[name] for name in INPUTS):
        raise ValueError('Owner input changed during build')
    after={name:ep0.sha(ep0.PRIVATE/'analysis'/name) for name in TICKETS}
    if before!=after:raise ValueError('Ticket changed during audit')
    result=dict(schema='A23-EP0-trace-owner-audit-1',source_audit=audit,policy_cases=rows,
                policy_case_count=len(rows),compiler_commands=commands,compiler_version=command([compiler,'--version']),
                libnx_inputs_sha256=libnx,elf_sha256=ep0.sha(output/'owner-libnx.elf'),
                libnx_parse_sha256=hashlib.sha256(code).hexdigest(),libnx_parse_instruction_anchors=anchors,
                libnx_parse_matched_status_results={'3':0,'4':0x828c,'5':0x748c,'other':0x108c},
                input_sources_sha256=input_hashes,
                tickets_sha256=after,libnx_adapter_full_elf_link=True,
                complete_instrumented_a23_firmware_link=False,actual_handler_owner_hooks_inserted=False,
                filesystem_sink_implemented=False,automatic_session_stop_implemented=False,
                measured_real_instrumentation_cost=False,hardware_verified=False,root_cause_confirmed=False,
                usb_accessed=False,sd_accessed=False,firmware_packaged=False,production_modified=False,
                ownership_inputs_injected=True,thread_identity_and_join_inputs_authenticated=False)
    (output/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    files=sorted(p for p in output.rglob('*') if p.is_file())
    (output/'SHA256SUMS').write_text(''.join(ep0.sha(p)+'  '+str(p.relative_to(output))+'\n' for p in files))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    # Validate prior sealed trace inputs before opening a NEW audit directory.
    for name in ('A23-EP0-memory-trace-review-20261013','A23-EP0-memory-trace-validation-20261013'):
        verify(ep0.PRIVATE/'analysis'/name)
    args.output.mkdir(parents=True,exist_ok=False)
    result=run(args.output)
    print(json.dumps(dict(output=str(args.output),policy_cases=result['policy_case_count'],
                          libnx_adapter_elf_link=True,production_integrated=False),indent=2))


if __name__=='__main__':main()
