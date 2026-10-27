#!/usr/bin/env python3
"""Build one burst with deferred Mach clock/USB frame timestamp recording; no USB."""
from pathlib import Path
import hashlib,json,shutil,subprocess
ROOT=Path(__file__).resolve().parents[1];P=ROOT/'private';OUT=P/'host-A23-clock-audit-1'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def once(s,a,b):
 assert s.count(a)==1,(a,s.count(a));return s.replace(a,b)
def main():
 base=P/'host-A23-no-td-window';single=P/'host-A23-burst-window-1';meta=json.loads((base/'manifest.json').read_text());lib=Path(meta['library']);assert sha(lib)==meta['static_library_sha256'];assert sha(lib.parent.parent/'os/darwin_usb.c')==meta['backend_sha256']
 OUT.mkdir(exist_ok=False);tree=OUT/'libusb-1.0.30';shutil.copytree(lib.parents[2],tree,symlinks=True)
 backend=tree/'libusb/os/darwin_usb.c';header=tree/'libusb/os/darwin_usb.h';s=backend.read_text()
 s=once(s,'  tpriv->diag_frame_before = iso_diag_ns();','  tpriv->clock_frame_before=mach_absolute_time();\n  tpriv->diag_frame_before = iso_diag_ns();')
 s=once(s,'  tpriv->diag_frame_after = iso_diag_ns();','  tpriv->diag_frame_after = iso_diag_ns();\n  tpriv->clock_frame_after=mach_absolute_time();\n  tpriv->clock_at_time=((UInt64)atTime.hi<<32)|atTime.lo;\n  tpriv->clock_frame_result=kresult;')
 s=once(s,'  /* submit the request */\n  tpriv->diag_queue_before = iso_diag_ns();','  /* submit the request */\n  tpriv->clock_queried_frame=queried_frame;\n  tpriv->clock_start_frame=frame;\n  tpriv->clock_queue_before=mach_absolute_time();\n  tpriv->diag_queue_before = iso_diag_ns();')
 s=once(s,'  tpriv->diag_queue_after = iso_diag_ns();','  tpriv->diag_queue_after = iso_diag_ns();\n  tpriv->clock_queue_after=mach_absolute_time();')
 s=once(s,'  uint64_t callback_entry_ns = iso_diag_ns();','  uint64_t clock_callback=mach_absolute_time();\n  uint64_t callback_entry_ns = iso_diag_ns();')
 s=once(s,'  tpriv->diag_callback_entry = callback_entry_ns;','  tpriv->clock_callback=clock_callback;\n  tpriv->diag_callback_entry = callback_entry_ns;')
 s=s.replace('  if (is_isoc && tpriv->isoc_framelist) {','''  if (is_isoc && tpriv->isoc_framelist) {
    mach_timebase_info_data_t clock_base;mach_timebase_info(&clock_base);
    fprintf(stderr,"{\\"kind\\":\\"darwin_iso_clock_audit\\",\\"clock\\":\\"mach_absolute_time\\",\\"frame_result\\":%u,\\"queried_frame\\":%llu,\\"start_frame\\":%llu,\\"at_time_ticks\\":%llu,\\"frame_before_ticks\\":%llu,\\"frame_after_ticks\\":%llu,\\"queue_before_ticks\\":%llu,\\"queue_after_ticks\\":%llu,\\"callback_ticks\\":%llu,\\"numer\\":%u,\\"denom\\":%u}\\n",
            (unsigned)tpriv->clock_frame_result,(unsigned long long)tpriv->clock_queried_frame,(unsigned long long)tpriv->clock_start_frame,
            (unsigned long long)tpriv->clock_at_time,(unsigned long long)tpriv->clock_frame_before,(unsigned long long)tpriv->clock_frame_after,
            (unsigned long long)tpriv->clock_queue_before,(unsigned long long)tpriv->clock_queue_after,(unsigned long long)tpriv->clock_callback,clock_base.numer,clock_base.denom);''',1)
 backend.write_text(s)
 header.write_text(once(header.read_text(),'  /* Isoc */','  uint64_t clock_frame_before,clock_frame_after,clock_at_time,clock_queried_frame,clock_start_frame,clock_queue_before,clock_queue_after,clock_callback;\n  IOReturn clock_frame_result;\n  /* Isoc */'))
 assert s.count('GetBusFrameNumber(IOINTERFACE')==1 and s.count('ReadIsochPipeAsync(IOINTERFACE')==1 and 'frame += 64;' in s
 with (OUT/'backend-build.log').open('x') as log:subprocess.run(['make','-C',str(tree/'libusb'),'-j4'],stdout=log,stderr=subprocess.STDOUT,check=True)
 newlib=tree/'libusb/.libs/libusb-1.0.a';commands=[]
 for name in ['receiver-source.c','native_file_guard.h','iso_probe_protocol.h','preflight.c','single-burst-test.c']:shutil.copyfile(single/name,OUT/name)
 def compile(src,target,extra=()):
  cmd=['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-DISO_NATIVE_DIAGNOSTICS','-I'+str(tree/'libusb'),'-I'+str(OUT),*extra,str(OUT/src),str(newlib),'-framework','IOKit','-framework','CoreFoundation','-framework','Security','-lobjc','-o',str(OUT/target)];commands.append(cmd)
  with (OUT/(target+'-build.log')).open('x') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
 compile('receiver-source.c','iso-probe-clock-audit');compile('preflight.c','preflight');compile('single-burst-test.c','single-burst-test',['-DISO_RECEIVER_SOURCE="'+str(OUT/'receiver-source.c')+'"'])
 cases=[]
 for fail,bitmap in [(0,0),(1,0),(0,1)]:
  folder=OUT/'validation'/f'{fail}-{bitmap}';folder.mkdir(parents=True);r=subprocess.run([str(OUT/'single-burst-test'),str(folder/'host.jsonl'),str(folder/'native.txt'),str(fail),str(bitmap)],capture_output=True,text=True,timeout=8);assert r.returncode==0,r.stderr;cases.append(dict(native_fail=fail,bitmap_fail=bitmap,stdout=r.stdout,passed=True))
 rejects=0
 for args in [[],['--burst','--repeat','2'],['--burst','--packets','959'],['--burst','--packets','960','--trigger-delay-ms','39']]:
  log=OUT/'must-not-exist.jsonl';r=subprocess.run([str(OUT/'iso-probe-clock-audit'),*args,'--log',str(log)],capture_output=True,timeout=8);assert r.returncode==2 and not log.exists();rejects+=1
 (OUT/'validation.json').write_text(json.dumps(dict(passed=True,USB_accessed=False,real_receiver_mock_cases=cases,cli_rejections=rejects,backend_static_API_count_checked=True),indent=2)+'\n')
 result=dict(device_revision='A23',host_revision='clock-audit-1',repeats=1,packets=960,wait_ms=40,device_code_changed=False,backend_identical_to_no_td=False,backend_only_clock_observation_added=True,additional_USB_queries=0,scheduling_unchanged=True,native_errors_preserved=True,library=str(newlib),static_library_sha256=sha(newlib),backend_sha256=sha(backend),reference_backend_sha256=meta['backend_sha256'],receiver_sha256=sha(OUT/'iso-probe-clock-audit'),receiver_source_sha256=sha(OUT/'receiver-source.c'),validation_passed=True,hardware_verified=False,build_commands=commands)
 (OUT/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');shutil.copyfile(Path(__file__),OUT/Path(__file__).name);print(OUT)
if __name__=='__main__':main()
