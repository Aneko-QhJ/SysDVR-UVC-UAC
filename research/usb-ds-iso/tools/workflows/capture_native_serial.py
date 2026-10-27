from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import os
import hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[2]; P=ROOT/'private'; A=P/'packages-A23-interval1/A'
plan=json.loads((P/'analysis/A23-next-test.json').read_text())
if plan.get('stage')!='native_guard_serial_prepared' or plan.get('next_test_repeats')!=16:
    raise SystemExit('Serial capture is not prepared. Inspect experiment status and review the recorded failure first; no USB accessed.')
now=lambda:datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
write=lambda p,v:p.write_text(json.dumps(v,indent=2)+'\n')
h=json.loads((A/'host-manifest.json').read_text()); e=json.loads((A/'experiment.json').read_text())
assert sha(A/'iso-probe-native-diag')==h['receiver_sha256']==e['receiver_sha256']
assert e['device_revision']=='A23' and e['diagnostics_layout']=='ISO7'
assert e['followup_sia'] and e['scheduling_policy']=='TD0 explicit FrameID lead32; TD1..15 SIA1 and FrameID0'
assert (e['host_frame_lead'],e['requested_bytes'],e['trigger_delay_ms'],e['packets'],e['repeats'])==(64,192,40,960,1)
assert e['interval']==h['expected_interval']==1 and e['nominal_capture_window_ms']==120
for line in (A/'SHA256SUMS').read_text().splitlines():
    checksum,name=line.split('  ',1);assert sha(A/name)==checksum
d=Path((P/'deployments/latest-A23.txt').read_text().strip()); deployment=json.loads((d/'deployment.json').read_text())
assert deployment['revision']=='A23' and deployment['status']=='deployed_and_readback_verified' and deployment['ejected']
assert deployment['followup_sia']
for f in deployment['files']:assert sha(A/f['path'])==f['sha256']
assert sha(A/'receiver-source.c')==h['receiver_source_sha256']
assert sha(A/'iso_probe_protocol.h')==h['protocol_header_sha256']
assert sha(A/'atmosphere/contents/00FF0000A53BB666/exefs.nsp')==e['sysmodule_sha256']
lib=P/'darwin-diag-host64/libusb-1.0.30/libusb/.libs/libusb-1.0.a'
assert sha(lib)==h['static_library_sha256']
H=P/'host-A23-native-guard-serial'
h=json.loads((H/'manifest.json').read_text())
assert h['host_revision']=='native-guard-serial-1' and h['backend_inverse_patch_matches_frozen']
assert sha(H/'iso-probe-native-diag')==h['receiver_sha256']
assert sha(H/'receiver-source.c')==h['receiver_source_sha256']
assert sha(H/'native_file_guard.h')==h['native_guard_header_sha256']
assert h['receiver_inverse_patch_matches_reference'] and h['native_evidence_mandatory']
e=dict(e,repeats=16)
assert sha(H/'iso_probe_protocol.h')==sha(A/'iso_probe_protocol.h')==h['protocol_header_sha256']
lib=Path(h['library'])
assert sha(lib)==h['static_library_sha256']
assert sha(lib.parent.parent/'os/darwin_usb.c')==h['backend_after_sha256']
assert json.loads((H/'validation.json').read_text())['native_failure_stops_before_third_submission']
run=P/'runs'/('A-A23-HS-native-serial-'+datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d-%H%M%S'));run.mkdir()
(P/'runs/latest-A23-preflight.txt').write_text(str(run)+'\n')
old=Path((P/'runs/latest-A19-run.txt').read_text().strip())
preflight=(old/'preflight.c').read_text()
anchor=' logfile=stdout; IsoProbeStatus s;'
assert preflight.count(anchor)==1
preflight=preflight.replace(anchor,""" struct libusb_config_descriptor *cfg=NULL;
 int descriptor_count=0;
 int cfg_rc=libusb_get_active_config_descriptor(libusb_get_device(dev),&cfg);
 if(cfg_rc==0) {
  for(unsigned i=0;i<cfg->bNumInterfaces;++i)
   for(int j=0;j<cfg->interface[i].num_altsetting;++j) {
    const struct libusb_interface_descriptor *d=&cfg->interface[i].altsetting[j];
    if(d->bInterfaceNumber!=2 || d->bAlternateSetting!=0 || d->bInterfaceClass!=0xff || d->bInterfaceSubClass!=0x49 || d->bInterfaceProtocol!=1 || d->bNumEndpoints!=1) continue;
    const struct libusb_endpoint_descriptor *ep=&d->endpoint[0];
    fprintf(stderr,\"Preflight descriptor: endpoint=%02x mps=%u interval=%u attributes=%u\\n\",ep->bEndpointAddress,ep->wMaxPacketSize,ep->bInterval,ep->bmAttributes);
    descriptor_count+=ep->bEndpointAddress==0x83 && (ep->bmAttributes&3)==LIBUSB_TRANSFER_TYPE_ISOCHRONOUS && ep->wMaxPacketSize==256 && ep->bInterval==1;
   }
  libusb_free_config_descriptor(cfg);
 }
 logfile=stdout; IsoProbeStatus s;""")
preflight=preflight.replace('int pass=rc==0 &&','int pass=cfg_rc==0 && descriptor_count==1 && rc==0 &&')
(run/'preflight.c').write_text(preflight)
cmd=['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-I'+str(lib.parent.parent),'-I'+str(A),str(run/'preflight.c'),str(lib),'-framework','IOKit','-framework','CoreFoundation','-framework','Security','-lobjc','-o',str(run/'preflight')]
with (run/'preflight-build.log').open('x') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
a=dict(revision='A23',host_revision='native-guard-serial-1',host_build=str(H),created_at=now(),deployment=str(d),package=str(A),receiver_sha256=h['receiver_sha256'],static_library_sha256=sha(lib),receiver_invocations=0,device_trigger_count=0,phase='preflight',video_closed_requested=True,video_closed_independently_verified=False,runtime_revision_identity_verified=False,revision_identity_pending='collect full Switch A23 startup/runtime installation log; require ISO7 after trigger',preflight_compile_command=cmd,**{k:e[k] for k in ['repeats','host_frame_lead','requested_bytes','trigger_delay_ms','packets']})
write(run/'acquisition.json',a)
with (run/'preflight.jsonl').open('x') as out,(run/'preflight-stderr.txt').open('x') as err:
    result=subprocess.run([str(run/'preflight')],stdout=out,stderr=err,timeout=20)
a['preflight_exit_code']=result.returncode;(run/'preflight-exit-code.txt').write_text(str(result.returncode)+'\n');write(run/'acquisition.json',a)
print('Run:',run,flush=True);print('Preflight:',(run/'preflight.jsonl').read_text(),(run/'preflight-stderr.txt').read_text(),flush=True)
assert result.returncode==0,'Preflight failed: no transfer submitted'
cmd=[str(H/'iso-probe-native-diag'),'--burst','--repeat','16','--packets','960','--trigger-delay-ms','40','--log',str(run/'host.jsonl')]
write(run/'command.json',cmd);write(run/'single-test-started.json',dict(started_at=now(),command=cmd))
(P/'runs/latest-A23-run.txt').write_text(str(run)+'\n')
a.update(command=cmd,phase='running',receiver_invocations=1);write(run/'acquisition.json',a)
with (run/'stdout.txt').open('x') as out,(run/'native-stderr.txt').open('x') as err:
    process=subprocess.Popen(cmd,stdout=out,stderr=err,env=dict(os.environ,ISO_NATIVE_LOG_PATH=str(run/'native-stderr.txt')))
    try:rc=process.wait(timeout=45);a['timed_out']=False
    except subprocess.TimeoutExpired:
        process.terminate()
        try:rc=process.wait(timeout=10)
        except subprocess.TimeoutExpired:process.kill();rc=process.wait()
        a['timed_out']=True
(run/'exit-code.txt').write_text(str(rc)+'\n')
rows=[json.loads(x) for x in (run/'host.jsonl').read_text().splitlines() if x.startswith('{')]
a.update(exit_code=rc,finished_at=now(),phase='captured',device_trigger_count=sum(x['kind']=='host_trigger_timing' for x in rows),switch_log_pending=True,device_timing_pending=True)
write(run/'acquisition.json',a)
subprocess.run(['python3',str(A/'summarize_run.py'),str(run/'host.jsonl'),'--out',str(run/'summary.json')],check=True)
print('Bounded serial capture complete; receiver exit:',rc,flush=True)
print((run/'stdout.txt').read_text(),flush=True)

subprocess.run(['python3',str(ROOT/'tools/analyze_native_serial_run.py'),str(run)],check=True)
