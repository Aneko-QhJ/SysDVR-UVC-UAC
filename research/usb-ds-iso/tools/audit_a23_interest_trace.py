"""Eight bounded ingress tests, same poison policy, injected operations only."""
import argparse,json,subprocess,shutil
from pathlib import Path
import build_a23_live97_three as b
import a23_interest_trace_candidate as trace
w=b.w;PARENT=w.A/'A23-live97-three-first-live-closeout-20261024'
NEW=('host/a23_interest_trace.h','tools/a23_interest_trace_candidate.py','tools/audit_a23_interest_trace.py','tests/a23_interest_trace_fixture.inc','tests/test_a23_interest_trace.py')
CASES=('normal','terminated','request-close','configuration','unknown','zero','overflow','contracts')

def sources():
    b.core.verify_seal(PARENT);old=b.sources();w.require(len(old)==623 and old==w.load(PARENT/'source-hashes.json'),'old623 drift')
    return dict(sorted((old|{'research/usb-ds-iso/'+n:b.sha(w.plain(w.ROOT/n)) for n in NEW}).items()))
def guards():
    b.core.guards();w.require(w.plain(w.A/'A23-live97-three-once-20261023-r1.json')==w.plain(PARENT/'once-record.json'),'actual177 drift')
    w.require({p.relative_to(b.FORMAL_ROOT).as_posix():b.sha(w.plain(p)) for p in b.FORMAL_ROOT.rglob('*') if p.is_file()}==w.load(PARENT/'namespace177-hashes.json'),'177 namespace drift')

def run(out):
    out=w.canonical(out);w.require(not out.exists(),'new interest audit required');hashes=sources();guards();out.mkdir(mode=0o700);done=[]
    try:
        for n,h in hashes.items():w.card.put(out,'source/'+n,w.plain(w.b.REPO/n))
        w.write(out/'source-hashes.json',hashes)
        native=out/'native';shutil.copytree(out/'source',native);r=native/'research/usb-ds-iso';live=w.A/'A23-live97-three-review-20261023-r2/build';b.verify(live,current=False)
        for name in ('a23_triple_sdk_adapter.h','a23_three_epoch_sdk_driver.h'):
            w.card.put(r,'host/'+name,w.plain(live/'generated'/name))
        original=w.plain(live/'generated/live_adapter.m').decode();candidate=trace.render(original);w.card.put(r,'host/a23_triple_sdk_adapter.m',candidate.encode());w.card.put(r,'host/a23_three_epoch_sdk_driver.m',w.plain(live/'generated/live_driver.m'))
        # Shared declarations only; exclude the prior fixture main.
        prefix=b.core.fixture(r).split('\nint main(')[0]
        w.card.put(r,'tests/generated_sdk_driver.m',(prefix+'\n'+w.plain(r/'tests/a23_interest_trace_fixture.inc').decode()).encode())
        cmd=['clang','-fobjc-arc','-fblocks','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer','-g','-I'+str(r/'host'),'-framework','Foundation','-framework','IOUSBHost','-framework','IOKit',*[str(r/'host'/n) for n in b.core.NATIVE],str(r/'tests/generated_sdk_driver.m'),'-o',str(out/'interest-fixture')]
        p=subprocess.run(cmd,capture_output=True,timeout=60);w.card.put(out,'compile.log',p.stdout+p.stderr);w.write(out/'compile.json',dict(command=cmd,returncode=p.returncode));w.require(p.returncode==0,'interest fixture compilation failed')
        models=out/'models';models.mkdir();rows={}
        for name in CASES:
            folder=models/name;folder.mkdir();p=subprocess.run([str(out/'interest-fixture'),name,str(folder)],capture_output=True,timeout=30);w.card.put(folder,'native.stdout',p.stdout);w.card.put(folder,'native.stderr',p.stderr);w.write(folder/'process.json',dict(returncode=p.returncode,creator_wait_completed=True));w.require(p.returncode==0 and not p.stderr,'native failed '+name);rows[name]=json.loads(p.stdout);done.append(name)
        sdk=Path('/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/System/Library/Frameworks')
        headers={n:p.resolve() for n,p in {'IOUSBHostObject.h':sdk/'IOUSBHost.framework/Headers/IOUSBHostObject.h','IOUSBHostDefinitions.h':sdk/'IOUSBHost.framework/Headers/IOUSBHostDefinitions.h','IOUSBHostFamilyDefinitions.h':sdk/'IOKit.framework/Headers/usb/IOUSBHostFamilyDefinitions.h','IOMessage.h':sdk/'IOKit.framework/Headers/IOMessage.h'}.items()}
        for n,p in headers.items():w.card.put(out,'sdk-headers/'+n,w.plain(p))
        expected={'terminated':0xe0000010,'request-close':0xe0005003,'configuration':0xe0005000,'unknown':0xffffffff,'zero':0}
        for name,value in expected.items():
            d=rows[name]['result'];t=d['lease']['interest_trace'];w.require(d['stopped'] is True and d['lease']['poisoned'] is True and rows[name]['iso_submissions']==2 and t['rows'][0]['message_u32']==value and t['rows'][0]['provider_ingress_ticks']>0 and t['complete'] is True,'raw message/policy differs')
        w.require(rows['normal']['result']['complete'] is True and rows['overflow']['result']['lease']['interest_trace']['overflow'] is True,'normal/overflow differs')
        w.require(sources()==hashes,'source drift');guards()
        w.write(out/'report.json',dict(schema='A23-interest-trace-offline-1',passed=True,source_count=628,old623_unchanged=True,completed=done,matrix=rows,message_values=expected,sdk_headers={n:b.sha(w.plain(p)) for n,p in headers.items()},callback_recording_boundary='provider_interest_after_poison_before_async_pin',sdk_argument_captured=False,new_live103_scope_implemented=False,hardware_ready=False,native_processes=8,native_creator_waits=8,native_threads_joined=9,usb_requests=0,sd_accesses=0,real_sdk_objects=0,new_authorizations=0,formal_reservations=0,remaining=0))
    except BaseException as e:
        w.write(out/'failure.json',dict(error=str(e),completed=done));w.b.seal(out);raise
    w.b.seal(out);return dict(directory=str(out),manifest_sha256=b.core.verify_seal(out),native_cases=len(done),passed=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);print(json.dumps(run(p.parse_args().output),indent=2))
