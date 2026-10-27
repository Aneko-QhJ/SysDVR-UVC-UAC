#!/usr/bin/env python3
"""Prepare one A23 burst using the frozen no-TD diagnostic backend; no USB."""
import hashlib,json,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];PRIVATE=ROOT/'private'
OUT=PRIVATE/'host-A23-burst-window-1'
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    reference=PRIVATE/'host-A23-native-guard-serial';baseline=PRIVATE/'host-A23-no-td-window'
    meta=json.loads((reference/'manifest.json').read_text());base=json.loads((baseline/'manifest.json').read_text())
    lib=Path(base['library']);assert sha(lib)==base['static_library_sha256']
    assert sha(reference/'receiver-source.c')==meta['receiver_source_sha256']
    assert sha(lib.parent.parent/'os/darwin_usb.c')==base['backend_sha256']
    OUT.mkdir(exist_ok=False)
    text=(reference/'receiver-source.c').read_text();anchor='    if (!outpath) {';assert text.count(anchor)==1
    text=text.replace(anchor,'''    if (!burst_mode || receive_only || empty_window || cancel_only || frame_only ||
        repeats != 1 || packets != 960 || trigger_delay_ms != 40) {
        fprintf(stderr, "Matched burst requires --burst --repeat 1 --packets 960 --trigger-delay-ms 40\\n");
        return 2;
    }
    if (!outpath) {''')
    (OUT/'receiver-source.c').write_text(text)
    for name in ['native_file_guard.h','iso_probe_protocol.h']:shutil.copyfile(reference/name,OUT/name)
    shutil.copyfile(baseline/'preflight.c',OUT/'preflight.c')
    commands=[]
    for source,target in [('receiver-source.c','iso-probe-burst-window'),('preflight.c','preflight')]:
        cmd=['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-DISO_NATIVE_DIAGNOSTICS','-I'+str(lib.parent.parent),'-I'+str(OUT),str(OUT/source),str(lib),'-framework','IOKit','-framework','CoreFoundation','-framework','Security','-lobjc','-o',str(OUT/target)]
        commands.append(cmd)
        with (OUT/(target+'-build.log')).open('x') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
    fixture=(ROOT/'tests/native_serial_loop_test.c').read_text()
    assert fixture.count('"--repeat","3"')==1 and fixture.count('bitmap_fail_at:3')==1
    fixture=fixture.replace('"--repeat","3"','"--repeat","1"').replace('bitmap_fail_at:3','bitmap_fail_at:1').replace('"--trigger-delay-ms","1"','"--trigger-delay-ms","40"')
    anchor=' memcpy(&device_state.diagnostics,&diag,sizeof(diag));return 0;'
    assert fixture.count(anchor)==1
    fixture=fixture.replace(anchor,''' diag.first_virtual_trb=0x100000;
 diag.frame_select_mfi=16136;diag.context_valid=1;
 uint32_t context[8]={0x00010001,0x0100002e,0x80023001,0,0x01000c00,0,0x000c0000,0};
 memcpy(diag.context,context,sizeof(context));
 uint32_t control=(1u<<20)|(5u<<10)|1u;memcpy((unsigned char *)&diag+8,&control,4);
 uint32_t event0[5]={0x100010,0,0x010000c0,0x00078005,8};
 uint32_t event1[5]={0x100030,0,0x010000c0,0x00078005,9};
 memcpy((unsigned char *)&diag+32,event0,20);memcpy((unsigned char *)&diag+52,event1,20);
 memcpy(&device_state.diagnostics,&diag,sizeof(diag));return 0;''')
    (OUT/'single-burst-test.c').write_text(fixture)
    cmd=['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-I'+str(lib.parent.parent),'-I'+str(OUT),'-DISO_RECEIVER_SOURCE="'+str(OUT/'receiver-source.c')+'"',str(OUT/'single-burst-test.c'),str(lib),'-framework','IOKit','-framework','CoreFoundation','-framework','Security','-lobjc','-o',str(OUT/'single-burst-test')]
    with (OUT/'validation-build.log').open('x') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
    cases=[]
    for fail,bitmap in [(0,0),(1,0),(0,1)]:
        folder=OUT/'validation'/f'{fail}-{bitmap}';folder.mkdir(parents=True)
        result=subprocess.run([str(OUT/'single-burst-test'),str(folder/'host.jsonl'),str(folder/'native.txt'),str(fail),str(bitmap)],capture_output=True,text=True,timeout=8)
        assert result.returncode==0,result.stderr
        cases.append(dict(native_fail_at=fail,bitmap_fail_at=bitmap,stdout=result.stdout,stderr=result.stderr,passed=True))
    rejected=[]
    for args in [[],['--receive-only'],['--burst','--repeat','2'],['--burst','--packets','959'],['--burst','--packets','960','--trigger-delay-ms','39']]:
        target=OUT/'must-not-exist.jsonl';r=subprocess.run([str(OUT/'iso-probe-burst-window'),*args,'--log',str(target)],capture_output=True,text=True,timeout=8)
        assert r.returncode==2 and not target.exists();rejected.append(args)
    (OUT/'validation.json').write_text(json.dumps(dict(passed=True,usb_accessed=False,real_receiver_mock_cases=cases,cli_rejections=rejected),indent=2)+'\n')
    manifest=dict(device_revision='A23',host_revision='burst-window-1',repeats=1,packets=960,wait_ms=40,requested_bytes=192,host_frame_lead=64,interval=1,mps=256,device_code_changed=False,backend_identical_to_no_td=True,library=str(lib),static_library_sha256=sha(lib),backend_sha256=base['backend_sha256'],receiver_sha256=sha(OUT/'iso-probe-burst-window'),receiver_source_sha256=sha(OUT/'receiver-source.c'),preflight_sha256=sha(OUT/'preflight'),native_guard_header_sha256=sha(OUT/'native_file_guard.h'),protocol_header_sha256=sha(OUT/'iso_probe_protocol.h'),validation_passed=True,hardware_verified=False,build_commands=commands,test_build_command=cmd)
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(OUT)

if __name__=='__main__':main()
