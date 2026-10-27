#!/usr/bin/env python3
"""Instrument frozen A23 client source COPIES and export bounded simulated traces.

No production source edits, USB/SD, deployment or acquisition ticket changes.
Every source replacement requires exactly one anchor in its explicit scope.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import uuid

import audit_a23_ep0 as ep0
import audit_a23_hos_setup as hos
from analyze_ep0_trace import decode
from workflows.artifacts import verify


def replace(text,old,new):
    if text.count(old)!=1:raise ValueError('Instrumentation anchor mismatch: '+old[:100])
    return text.replace(old,new)


def scoped(text,begin,end,transform):
    a=text.index(begin);b=text.index(end,a)
    return text[:a]+transform(text[a:b])+text[b:]


def ctrl_helper(text,direction):
    event='iface->Ctrl'+direction+'CompletionEvent';flag='EP0_TRACE_IN' if direction=='In' else '0'
    text=replace(text,'{\n    eventClear','{\n    u64 traceBegin; Result traceRc;\n    eventClear')
    # There are two eventClear calls in each scoped helper; replace each by line order.
    lines=text.splitlines();n=0;changed=[]
    for line in lines:
        if line.strip().startswith('eventClear(&'+event+');'):
            stage='EP0_T_CTRL_CLEAR_PRE' if n==0 else 'EP0_T_CTRL_CLEAR_DONE';n+=1
            changed.extend(['    traceBegin = svcGetSystemTick();',
                            '    traceRc = eventClear(&'+event+');',
                            f'    trace_emit({stage},iface,traceRc,0,0,{flag},NULL,traceBegin,svcGetSystemTick());'])
        else:changed.append(line)
    if n!=2:raise ValueError('Control event clear anchor count')
    text='\n'.join(changed)+'\n'
    post=f'Result rc = usbDsInterface_Ctrl{direction}PostBufferAsync(iface, buf, len, &urbId);'
    text=replace(text,post,'traceBegin = svcGetSystemTick();\n    '+post+
                 f'\n    trace_emit(EP0_T_CTRL_POST,iface,rc,(u32)len,rc ? 0 : urbId,'
                 f'{flag}|EP0_TRACE_ARG0_VALID|(rc ? 0 : EP0_TRACE_ARG1_VALID),NULL,traceBegin,svcGetSystemTick());')
    wait=f'rc = eventWait(&{event}, EP0_XFER_TIMEOUT);'
    text=replace(text,wait,'traceBegin = svcGetSystemTick();\n    '+wait+
                 f'\n    trace_emit(EP0_T_CTRL_WAIT,iface,rc,urbId,0,{flag}|EP0_TRACE_ARG0_VALID,NULL,traceBegin,svcGetSystemTick());')
    report=f'rc = usbDsInterface_GetCtrl{direction}ReportData(iface, &rpt);'
    text=replace(text,report,'traceBegin = svcGetSystemTick();\n    '+report+
                 f'\n    trace_emit(EP0_T_CTRL_REPORT,iface,rc,0,0,{flag},NULL,traceBegin,svcGetSystemTick());')
    parse='rc = usbDsParseReportData(&rpt, urbId, NULL, &t);'
    text=replace(text,parse,'traceBegin = svcGetSystemTick();\n    '+parse+
                 f'\n    trace_emit(EP0_T_CTRL_PARSE,iface,rc,rc ? 0 : t,urbId,{flag}|EP0_TRACE_ARG1_VALID|'
                 '(rc ? 0 : EP0_TRACE_ARG0_VALID),NULL,traceBegin,svcGetSystemTick());')
    return text


def instrument(text):
    text=scoped(text,'static Result _ctrlInXfer(','static Result _ctrlOutXfer(',lambda s:ctrl_helper(s,'In'))
    text=scoped(text,'static Result _ctrlOutXfer(','// GET-type request:',lambda s:ctrl_helper(s,'Out'))
    ack='''static void _ctrlAck(UsbDsInterface* iface)
{
    if (R_FAILED(_ctrlInXfer(iface, _ctrlBufferFor(iface), 0, NULL)))
        usbDsInterface_StallCtrl(iface);
}'''
    text=replace(text,ack,'''static void _ctrlAck(UsbDsInterface* iface)
{
    u64 traceBegin = svcGetSystemTick();
    Result traceRc = _ctrlInXfer(iface, _ctrlBufferFor(iface), 0, NULL);
    trace_emit(EP0_T_ACK,iface,traceRc,0,0,EP0_TRACE_IN,NULL,traceBegin,svcGetSystemTick());
    if (R_FAILED(traceRc)) usbDsInterface_StallCtrl(iface);
}''')
    text=replace(text,'''static void _handleIsoSetup(UsbDsInterface* iface, const UsbSetupPacket* setup)
{''','''static void _handleIsoSetup(UsbDsInterface* iface, const UsbSetupPacket* setup)
{
    u64 traceEntry = svcGetSystemTick();
    trace_emit(EP0_T_ISO_ENTER,iface,0,g_isoStatus.state,g_isoStatus.sequence,
        EP0_TRACE_ARG0_VALID|EP0_TRACE_ARG1_VALID,setup,traceEntry,traceEntry);''')
    text=replace(text,'if (setup->wIndex != iface->interface_index) {',
                 '''if (setup->wIndex != iface->interface_index) {
        trace_emit(EP0_T_GUARD,iface,0,EP0_G_WRONG_INTERFACE,g_isoStatus.state,
            EP0_TRACE_ARG0_VALID|EP0_TRACE_ARG1_VALID,setup,traceEntry,svcGetSystemTick());''')
    text=replace(text,'''        _ctrlWrite(iface, &g_isoStatus, sizeof(g_isoStatus));''',
                 '''        u64 traceStatus = svcGetSystemTick();
        trace_emit(EP0_T_STATUS,iface,0,g_isoStatus.state,g_isoStatus.sequence,
            EP0_TRACE_ARG0_VALID|EP0_TRACE_ARG1_VALID,NULL,traceStatus,traceStatus);
        _ctrlWrite(iface, &g_isoStatus, sizeof(g_isoStatus));''')
    def burst(s):
        s=replace(s,'''if (g_isoStatus.state == ISO_PROBE_PENDING || g_isoStatus.state == ISO_PROBE_RETAINED) {
            usbDsInterface_StallCtrl''',
                  '''if (g_isoStatus.state == ISO_PROBE_PENDING || g_isoStatus.state == ISO_PROBE_RETAINED) {
            trace_emit(EP0_T_GUARD,iface,0,EP0_G_BUSY,g_isoStatus.state,
                EP0_TRACE_ARG0_VALID|EP0_TRACE_ARG1_VALID,setup,traceEntry,svcGetSystemTick());
            usbDsInterface_StallCtrl''')
        s=replace(s,'Result rc = usbDsGetSpeed(&speed);',
                  '''u64 traceSpeed = svcGetSystemTick();
        Result rc = usbDsGetSpeed(&speed);
        trace_emit(EP0_T_SPEED,iface,rc,rc ? 0 : speed,0,rc ? 0 : EP0_TRACE_ARG0_VALID,
            NULL,traceSpeed,svcGetSystemTick());''')
        s=replace(s,'''if (R_FAILED(rc) || (speed != UsbDeviceSpeed_High && speed != UsbDeviceSpeed_Super)) {
            usbDsInterface_StallCtrl''',
                  '''if (R_FAILED(rc) || (speed != UsbDeviceSpeed_High && speed != UsbDeviceSpeed_Super)) {
            trace_emit(EP0_T_GUARD,iface,rc,EP0_G_SPEED,g_isoStatus.state,
                EP0_TRACE_ARG0_VALID|EP0_TRACE_ARG1_VALID,setup,traceEntry,svcGetSystemTick());
            usbDsInterface_StallCtrl''')
        s=replace(s,'''if (speed != UsbDeviceSpeed_High) {
            usbDsInterface_StallCtrl''',
                  '''if (speed != UsbDeviceSpeed_High) {
            trace_emit(EP0_T_GUARD,iface,0,EP0_G_NOT_HS,g_isoStatus.state,
                EP0_TRACE_ARG0_VALID|EP0_TRACE_ARG1_VALID,setup,traceEntry,svcGetSystemTick());
            usbDsInterface_StallCtrl''')
        s=replace(s,'g_isoStatus.sequence = setup->wValue;',
                  '''g_isoStatus.sequence = setup->wValue;
        u64 traceSequence = svcGetSystemTick();
        trace_emit(EP0_T_SEQUENCE,iface,0,g_isoStatus.sequence,g_isoStatus.state,
            EP0_TRACE_ARG0_VALID|EP0_TRACE_ARG1_VALID,NULL,traceSequence,traceSequence);''')
        s=replace(s,'u64 postAfterTicks = svcGetSystemTick();',
                  '''u64 postAfterTicks = svcGetSystemTick();
        trace_emit(EP0_T_ISO_POST,iface,rc,length,rc ? 0 : urbId,
            EP0_TRACE_ARG0_VALID|(rc ? 0 : EP0_TRACE_ARG1_VALID),NULL,postBeforeTicks,postAfterTicks);''')
        return s
    text=scoped(text,'        u64 triggerTicks = svcGetSystemTick();','        LOG("ISO submit',burst)
    text=replace(text,'Result rc = usbDsInterface_GetSetupPacket(iface, &setup, sizeof(setup));',
                 '''u64 traceBegin = svcGetSystemTick();
    Result rc = usbDsInterface_GetSetupPacket(iface, &setup, sizeof(setup));
    trace_emit(EP0_T_SETUP,iface,rc,0,0,0,rc ? NULL : &setup,traceBegin,svcGetSystemTick());''')
    service='''    if (R_FAILED(eventWait(&iface->SetupEvent, 0)))
        return false;
    eventClear(&iface->SetupEvent);
    _handleSetupPacket(iface);'''
    text=replace(text,service,'''    u64 traceBegin = svcGetSystemTick();
    Result traceRc = eventWait(&iface->SetupEvent, 0);
    trace_poll(iface,traceRc);
    if (R_FAILED(traceRc)) return false; /* Quiet non-ready polls. */
    trace_request(iface);
    trace_emit(EP0_T_EVENT,iface,traceRc,0,0,0,NULL,traceBegin,svcGetSystemTick());
    traceBegin = svcGetSystemTick();
    traceRc = eventClear(&iface->SetupEvent);
    trace_emit(EP0_T_CLEAR,iface,traceRc,0,0,0,NULL,traceBegin,svcGetSystemTick());
    _handleSetupPacket(iface);''')
    text=replace(text,'            LOG("USB host disconnected\\n");',
                 '''            u64 traceDisconnect = svcGetSystemTick();
            trace_emit(EP0_T_DEVICE_STATE,NULL,0,state,g_isoStatus.sequence,
                EP0_TRACE_ARG0_VALID|EP0_TRACE_ARG1_VALID,NULL,traceDisconnect,traceDisconnect);
            LOG("USB host disconnected\\n");''')
    return text


def fixture_copy(family,source):
    bridge=(ep0.ROOT/'tests/a23_ep0_trace_bridge.c').read_text()
    if family=='dispatch':
        text=(ep0.ROOT/'tests/a23_ep0_dispatch_fixture.c').read_text()
        text=replace(text,'/* INSERT_ACTUAL_SOURCE */',bridge+'\n'+source)
    else:
        template=(ep0.ROOT/'tests/a23_ep0_dispatch_fixture.c').read_text()
        services=template.split('/* INSERT_ACTUAL_SOURCE */')[0]
        names={'record_log':'legacy_record_log','eventWait':'legacy_eventWait','waitMulti':'legacy_waitMulti',
               'usbDsInterface_GetSetupPacket':'legacy_GetSetupPacket',
               'usbDsInterface_CtrlInPostBufferAsync':'legacy_CtrlInPost'}
        defines='\n'.join('#define '+k+' '+v for k,v in names.items())+'\n'
        undef='\n'.join('#undef '+k for k in names)+'\n'
        hos_fixture=(ep0.ROOT/'tests/a23_hos_setup_fixture.c').read_text()
        text=defines+services+undef+replace(hos_fixture,'/* INSERT_ACTUAL_SOURCE */',bridge+'\n'+source)
    text=replace(text,'assert(argc==2);const char *name=argv[1];',
                 'assert(argc==5);const char *name=argv[1];\n    trace_probe_begin(argv[3],argv[4]);')
    # File export is after the original assertions and every modeled service call.
    text=replace(text,'    printf("{\\"scenario\\":',
                 '    trace_probe_export(argv[2]);\n    printf("{\\"scenario\\":')
    return text


def compile_native(source,out,extra=()):
    command=['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function',
             '-fsanitize=address,undefined','-fno-omit-frame-pointer','-g','-I'+str(ep0.REPO),
             *extra,str(source),'-o',str(out)]
    subprocess.run(command,check=True,capture_output=True,text=True);return command


def run_probe(output):
    validation=json.loads((ep0.PACKAGE/'validation.json').read_text())
    for name in ('source/uvc/uvc_device.c','source/sysmodule/main.c','source/uvc/iso_probe_protocol.h'):
        if ep0.sha(ep0.REPO/name)!=validation['sources_sha256'][name]:raise ValueError('Source differs from frozen A23')
    source=instrument(ep0.actual_source());(output/'instrumented-client.c').write_text(source)
    extra=['-DISO_PROBE','-DISO_PROBE_BURST_MODE','-DISO_PROBE_EVENT_AUDIT',
           '-DISO_PROBE_CONTEXT_AUDIT','-DISO_PROBE_FOLLOWUP_SIA']
    timing=hos.host_timing();rows=[];commands=[]
    baselines={family:{r['scenario']:r for r in json.loads((ep0.PRIVATE/'analysis'/path/'audit.json').read_text())['source_probe']['scenarios']}
               for family,path in [('dispatch','A23-EP0-dispatch-review-20261013'),
                                   ('shared','A23-HOS-shared-setup-review-20261013-final')]}
    for family,scenarios in [('dispatch',ep0.SCENARIOS),('shared',hos.SCENARIOS)]:
        text=fixture_copy(family,source);file=output/(family+'-probe.c');file.write_text(text)
        defines=list(extra)
        if family=='shared':
            defines+=['-DSTATUS_BEGIN_NS='+str(math.ceil(timing['after_status_begin_ms']*1e6)),
                      '-DSTATUS_END_NS='+str(math.ceil(timing['after_status_end_ms']*1e6))]
        commands.append(compile_native(file,output/(family+'-probe'),defines))
        for scenario in scenarios:
            path=output/(family+'-'+scenario+'.bin')
            result=subprocess.run([str(output/(family+'-probe')),scenario,str(path),uuid.uuid4().hex,uuid.uuid4().hex],
                                  check=True,capture_output=True,text=True)
            if result.stderr:raise ValueError('Unexpected sanitizer output: '+result.stderr)
            observed=json.loads(result.stdout)
            if observed!=baselines[family][scenario]:raise ValueError('Instrumentation changed fixture service results')
            analysis=decode(path.read_bytes())
            if not analysis['trace_window_complete']:raise ValueError('Fixture trace incomplete')
            (output/(family+'-'+scenario+'.json')).write_text(json.dumps(analysis,indent=2)+'\n')
            rows.append(dict(family=family,scenario=scenario,original_observation=observed,
                             baseline_identical=True,trace=path.name,record_count=analysis['record_count'],
                             mixed_first_setup=analysis['mixed_first_interface_setup'],
                             iso_paths=[r['path'] for r in analysis['requests'] if r['interface']==2]))
    # Full three-request windows, compared to freshly compiled ORIGINAL client
    # code under the same services; only the traced copy emits stage records.
    session_defines=list(extra)+['-DSTATUS_BEGIN_NS='+str(math.ceil(timing['after_status_begin_ms']*1e6)),
                                '-DSTATUS_END_NS='+str(math.ceil(timing['after_status_end_ms']*1e6))]
    for label,client in [('session',source),('session-baseline',ep0.actual_source())]:
        text=fixture_copy('shared',client)
        text=text[:text.index('int main(')]+(ep0.ROOT/'tests/a23_ep0_trace_session.c').read_text()
        file=output/(label+'-probe.c');file.write_text(text)
        commands.append(compile_native(file,output/(label+'-probe'),session_defines))
    for scenario in ('session-kept','session-replaced'):
        observations=[];identities=[uuid.uuid4().hex,uuid.uuid4().hex]
        for label in ('session','session-baseline'):
            path=output/(label+'-'+scenario+'.bin')
            done=subprocess.run([str(output/(label+'-probe')),scenario,str(path),*identities],
                                check=True,capture_output=True,text=True)
            if done.stderr:raise ValueError('Unexpected session sanitizer output: '+done.stderr)
            observations.append(json.loads(done.stdout))
        if observations[0]!=observations[1]:raise ValueError('Full session service results changed')
        path=output/('session-'+scenario+'.bin');analysis=decode(path.read_bytes())
        if not analysis['trace_window_complete']:raise ValueError('Full session trace incomplete')
        (output/('session-'+scenario+'.json')).write_text(json.dumps(analysis,indent=2)+'\n')
        rows.append(dict(family='session',scenario=scenario,original_observation=observations[0],
                         baseline_identical=True,trace=path.name,record_count=analysis['record_count'],
                         mixed_first_setup=analysis['mixed_first_interface_setup'],
                         iso_paths=[r['path'] for r in analysis['requests'] if r['interface']==2]))
    commands.append(compile_native(ep0.ROOT/'tests/ep0_trace_test.c',output/'core-test'))
    result=subprocess.run([str(output/'core-test'),str(output/'overflow.bin')],check=True,capture_output=True,text=True)
    if result.stderr:raise ValueError('Unexpected core sanitizer output: '+result.stderr)
    core=json.loads(result.stdout);overflow=decode((output/'overflow.bin').read_bytes())
    if overflow['trace_window_complete']:raise ValueError('Overflow must remain incomplete')
    (output/'overflow.json').write_text(json.dumps(overflow,indent=2)+'\n')
    # Compile the portable core for the device architecture without making firmware.
    smoke=output/'aarch64-smoke.c'
    smoke.write_text('#include "research/usb-ds-iso/device/ep0_trace.h"\n'
                     'size_t smoke(Ep0Trace *t,uint8_t *p,const Ep0TraceRecord *r) {\n'
                     ' ep0_trace_append(t,r);ep0_trace_freeze(t,t->last_end,EP0_TRACE_FINISHED);\n'
                     ' return ep0_trace_export(t,p,EP0_TRACE_EXPORT_MAX);}\n')
    cross=['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-gcc','-std=c11','-Wall','-Wextra','-Werror',
           '-ffreestanding','-O2','-I'+str(ep0.REPO),'-c',str(smoke),'-o',str(output/'aarch64-smoke.o')]
    subprocess.run(cross,check=True,capture_output=True,text=True);commands.append(cross)
    result=dict(schema='A23-EP0-memory-trace-probe-1',usb_accessed=False,sd_accessed=False,
                firmware_modified=False,acquisition_state_modified=False,hardware_verified=False,
                root_cause_confirmed=False,production_trace_integrated=False,
                simulation_services=True,hos_machine_code_emulated=False,compiler_commands=commands,
                source_sha256=hashlib.sha256(ep0.actual_source().encode()).hexdigest(),
                core_sha256=ep0.sha(ep0.ROOT/'device/ep0_trace.h'),instrumented_cases=rows,
                instrumented_case_count=len(rows),core_test=core,aarch64_core_compile_pass=True,
                measured_real_instrumentation_cost=False,baseline_compared_frozen_fixture_observations=True,
                full_session_compared_uninstrumented_actual_source=True)
    (output/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (output/'SHA256SUMS').write_text(''.join(ep0.sha(p)+'  '+p.name+'\n' for p in sorted(output.iterdir()) if p.is_file()))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    for folder in (ep0.RUN,ep0.CARD,ep0.COLLECTION,ep0.PACKAGE,
                   ep0.PRIVATE/'analysis/A23-EP0-dispatch-review-20261013',
                   ep0.PRIVATE/'analysis/A23-HOS-shared-setup-review-20261013-final'):verify(folder)
    result=run_probe(args.output)
    print(json.dumps(dict(output=str(args.output),instrumented_cases=result['instrumented_case_count'],
                         core_test=result['core_test'],baseline_identical=True,aarch64_compile=True),indent=2))


if __name__=='__main__':main()
