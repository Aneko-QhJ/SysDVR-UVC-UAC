#!/usr/bin/env python3
"""Build and validate the bounded matched-backend serial receiver without USB."""
import hashlib,json,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];PRIVATE=ROOT/'private'
OUT=PRIVATE/'host-A23-matched-serial-2'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    reference=PRIVATE/'host-A23-native-guard-serial';baseline=PRIVATE/'host-A23-no-td-window'
    meta=json.loads((reference/'manifest.json').read_text());base=json.loads((baseline/'manifest.json').read_text())
    lib=Path(base['library'])
    assert sha(lib)==base['static_library_sha256'] and sha(lib.parent.parent/'os/darwin_usb.c')==base['backend_sha256']
    assert sha(reference/'receiver-source.c')==meta['receiver_source_sha256']
    OUT.mkdir(exist_ok=False)
    source=(reference/'receiver-source.c').read_text()
    source=source.replace('#include "native_file_guard.h"','#include "native_file_guard.h"\n#include "serial_ring_guard.h"\nstatic SerialRingState ring_state;')
    anchor='    if (!outpath) {';assert source.count(anchor)==1
    source=source.replace(anchor,'''    if (!burst_mode || receive_only || empty_window || cancel_only || frame_only ||
        packets != 960 || trigger_delay_ms != 40) {
        fprintf(stderr, "Matched serial requires --burst --packets 960 --trigger-delay-ms 40\\n");
        return 2;
    }
    if (!outpath) {''')
    anchor='                   burst_diag.completed_bitmap==0xffff && burst_diag.actual_sum==3072;'
    assert source.count(anchor)==1
    source=source.replace(anchor,anchor+'''
        bool ring_ok = complete && payload_ok && serial_ring_guard(&ring_state,&burst_diag,sequence);
        fprintf(logfile,"{\\"kind\\":\\"serial_ring_gate\\",\\"sequence\\":%u,\\"passed\\":%s,\\"slot\\":%u,\\"cycle\\":%u,\\"wraps\\":%u}\\n",
                sequence,ring_ok ? "true" : "false",(unsigned)(burst_diag.first_virtual_trb&4095)/16,
                burst_diag.first_control&1,ring_state.wraps);
        complete = complete && ring_ok;''')
    (OUT/'receiver-source.c').write_text(source)
    for name in ['native_file_guard.h','iso_probe_protocol.h']:shutil.copyfile(reference/name,OUT/name)
    shutil.copyfile(ROOT/'host/serial_ring_guard.h',OUT/'serial_ring_guard.h')
    shutil.copyfile(baseline/'preflight.c',OUT/'preflight.c')
    commands=[]
    def compile(source,target,defines=(),link=True):
        cmd=['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-I'+str(lib.parent.parent),'-I'+str(OUT),*defines,str(source)]
        if link:cmd += [str(lib),'-framework','IOKit','-framework','CoreFoundation','-framework','Security','-lobjc']
        cmd += ['-o',str(OUT/target)];commands.append(cmd)
        result=subprocess.run(cmd,capture_output=True,text=True)
        (OUT/(target+'-build.log')).write_text(result.stdout+result.stderr)
        assert result.returncode==0,result.stderr
    compile(OUT/'receiver-source.c','iso-probe-matched-serial',['-DISO_NATIVE_DIAGNOSTICS'])
    compile(OUT/'preflight.c','preflight',['-DISO_NATIVE_DIAGNOSTICS'])
    for name in ['serial_ring_guard_test.c','native_serial_gate_test.c']:
        shutil.copyfile(ROOT/'tests'/name,OUT/name)
        compile(OUT/name,name[:-2],['-DISO_RECEIVER_SOURCE="'+str(OUT/'receiver-source.c')+'"'],name!='serial_ring_guard_test.c')
    fixture=(ROOT/'tests/native_serial_loop_test.c').read_text().replace('"--trigger-delay-ms","1"','"--trigger-delay-ms","40"')
    fixture=fixture.replace('bitmap_fail_at;','bitmap_fail_at,ring_fail_at;').replace('assert(argc==5);','assert(argc==6);ring_fail_at=(unsigned)atoi(argv[5]);')
    fixture=fixture.replace('(bitmap_fail_at?bitmap_fail_at:3)','(bitmap_fail_at?bitmap_fail_at:(ring_fail_at?ring_fail_at:3))').replace('(fail_at || bitmap_fail_at)?1:0','(fail_at || bitmap_fail_at || ring_fail_at)?1:0')
    anchor=' memcpy(&device_state.diagnostics,&diag,sizeof(diag));return 0;';assert fixture.count(anchor)==1
    fixture=fixture.replace(anchor,''' unsigned total=(triggered-1)*32,slot=total%247,cycle=1^((total/247)&1);
 diag.first_virtual_trb=0x100000+slot*16;diag.first_control=(1u<<20)|(5u<<10)|cycle;
 diag.frame_select_mfi=16136;diag.context_valid=1;
 diag.context[0]=0x00010001;diag.context[1]=0x0100002e;diag.context[4]=0x01000c00;
 for(unsigned i=0;i<2;++i){diag.td[i].event[0]=0x100000+((slot+1+2*i)%247)*16;
 diag.td[i].event[2]=0x010000c0;diag.td[i].event[3]=0x00078005;}
 if(triggered==ring_fail_at)diag.td[0].event[0]+=16;
 memcpy(&device_state.diagnostics,&diag,sizeof(diag));return 0;''')
    (OUT/'matched-serial-loop-test.c').write_text(fixture)
    compile(OUT/'matched-serial-loop-test.c','matched-serial-loop-test',['-DISO_RECEIVER_SOURCE="'+str(OUT/'receiver-source.c')+'"'])
    cases=[]
    def run_case(cmd):
        r=subprocess.run(cmd,capture_output=True,text=True,timeout=15);assert r.returncode==0,r.stderr
        cases.append(dict(command=cmd,stdout=r.stdout,stderr=r.stderr,passed=True))
    run_case([str(OUT/'serial_ring_guard_test')])
    callback=OUT/'validation/callback';callback.mkdir(parents=True)
    run_case([str(OUT/'native_serial_gate_test'),str(callback/'host.jsonl'),str(callback/'native.txt')])
    for fail,bitmap,ring in [(0,0,0),(2,0,0),(0,2,0),(0,0,2)]:
        folder=OUT/'validation'/f'loop-{fail}-{bitmap}-{ring}';folder.mkdir()
        run_case([str(OUT/'matched-serial-loop-test'),str(folder/'host.jsonl'),str(folder/'native.txt'),str(fail),str(bitmap),str(ring)])
    fixture16=fixture.replace('"--repeat","3"','"--repeat","16"').replace('ring_fail_at:3','ring_fail_at:16')
    (OUT/'matched-serial-16-test.c').write_text(fixture16)
    compile(OUT/'matched-serial-16-test.c','matched-serial-16-test',['-DISO_RECEIVER_SOURCE="'+str(OUT/'receiver-source.c')+'"'])
    folder=OUT/'validation/loop-16';folder.mkdir()
    run_case([str(OUT/'matched-serial-16-test'),str(folder/'host.jsonl'),str(folder/'native.txt'),'0','0','0'])
    sys.path.insert(0,str(ROOT/'tools'))
    from analyze_matched_serial_run import analyze
    for folder in (OUT/'validation').glob('loop-*'):
        shutil.copyfile(folder/'native.txt',folder/'native-stderr.txt')
        (folder/'exit-code.txt').write_text('0\n' if folder.name in ['loop-0-0-0','loop-16'] else '1\n')
        count=16 if folder.name=='loop-16' else (3 if folder.name=='loop-0-0-0' else 2)
        # Synthetic timing records exercise the classifier, never hardware timing evidence.
        with (folder/'native-stderr.txt').open('a') as out:
            for i in range(count):
                out.write(json.dumps(dict(kind='darwin_iso_queue_timing',queue_result=0,clock='CLOCK_MONOTONIC',frame_before_ns=1,frame_after_ns=2,queue_before_ns=3,queue_after_ns=4,callback_entry_ns=5))+'\n')
                out.write(json.dumps(dict(kind='darwin_iso_schedule',configured_lead_frames=64,packets=960,interval=1,speed=3))+'\n')
        e=analyze(folder)
        assert e['callbacks']==count and e['no_submission_after_failure']
        assert e['host_serial_passed']==(folder.name=='loop-16')
        if folder.name=='loop-16':assert e['observed_ring_wraps']==1 and e['runtime_ring_gate_verified']
        (folder/'analysis.json').write_text(json.dumps(e,indent=2)+'\n')
    rejected=[]
    for args in [[],['--receive-only'],['--burst','--repeat','17'],['--burst','--packets','959'],['--burst','--packets','960','--trigger-delay-ms','39']]:
        target=OUT/'must-not-exist.jsonl';r=subprocess.run([str(OUT/'iso-probe-matched-serial'),*args,'--log',str(target)],capture_output=True,text=True,timeout=8)
        assert r.returncode==2 and not target.exists();rejected.append(args)
    (OUT/'validation.json').write_text(json.dumps(dict(passed=True,usb_accessed=False,cases=cases,analyzer_cases=5,analyzer_passed=True,synthetic_timing_in_analyzer_fixtures=True,cli_rejections=rejected),indent=2)+'\n')
    manifest=dict(device_revision='A23',host_revision='native-guard-serial-2',max_repeats=16,packets=960,wait_ms=40,device_code_changed=False,backend_identical_to_no_td=True,library=str(lib),static_library_sha256=sha(lib),backend_sha256=base['backend_sha256'],validation_passed=True,hardware_verified=False,build_commands=commands)
    for name,key in [('iso-probe-matched-serial','receiver_sha256'),('receiver-source.c','receiver_source_sha256'),('preflight','preflight_sha256'),('native_file_guard.h','native_guard_header_sha256'),('serial_ring_guard.h','ring_guard_header_sha256'),('iso_probe_protocol.h','protocol_header_sha256')]:manifest[key]=sha(OUT/name)
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(OUT)

if __name__=='__main__':main()
