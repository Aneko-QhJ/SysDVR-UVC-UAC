"""Build the dedicated live two-epoch CLI. Build/file checks never acquire USB."""
from pathlib import Path
import argparse,json,subprocess
import build_a23_verified_entry as previous
import audit_a23_child_signal as prior
from a23_sequence32_model import encode,sha,require
w=previous.w
NEW=('host/a23_live_two_epoch.h','host/a23_live_two_epoch.m','host/a23_live_two_epoch_main.m',
     'tools/build_a23_live_two_epoch.py','tools/a23_live_two_epoch_workflow.py',
     'tools/audit_a23_live_two_epoch.py','tests/a23_live_two_epoch_fixture.inc','tests/test_a23_live_two_epoch.py')
DESCRIPTION=dict(schema='A23-live-two-epoch-description-1',acquisition_mode_implemented=True,
    formal_issuance_available=True,hardware_entry_enabled=True,maximum_epochs=2,
    maximum_iso_submissions=2,maximum_burst_triggers=2,automatic_retry=False,
    failure_resources_policy='retain_and_keep_process_alive',raw_inflight_buffers_copied=False,
    callback_drain_verified=False,hardware_verified=False,
    modes=['--describe','--check-build','--check-archive','--inspect-context','--acquire-once'])
SCOPE_SCHEMA='A23-live-shared32-scope-1'
FORMAL_ROOT=w.ROOT/'private/sequence-reservations32'


def sources():
    out=prior.sources();require(len(out)==579,'prior579 drift')
    parent=w.load(w.A/'A23-child-signal-closeout-20261022/closeout.json')
    require(out==parent['source_hashes'],'prior579 source binding differs')
    for n in NEW:
        key='research/usb-ds-iso/'+n;require(key not in out,'live source overlap');out[key]=sha(w.plain(w.ROOT/n))
    return dict(sorted(out.items()))


def replace_once(raw,old,new):
    require(raw.count(old)==1,'live derivation anchor differs: '+old[:70]);return raw.replace(old,new)


def render_scope(raw):
    raw='#import "a23_live_two_epoch.h"\n'+raw
    raw=replace_once(raw,'- (BOOL)inflight {','- (NSArray<NSDictionary *> *)liveFailureSnapshots {return [_entry liveFailureSnapshots];}\n- (BOOL)inflight {')
    raw=replace_once(raw,'@"A23-shared32-scope-1"','@"'+SCOPE_SCHEMA+'"')
    raw=replace_once(raw,'@"formal_issuance_available":@NO,@"acquisition_mode_implemented":@NO,@"hardware_entry_enabled":@NO};return YES;',
        '@"formal_issuance_available":@YES,@"acquisition_mode_implemented":@YES,@"hardware_entry_enabled":@YES};return YES;')
    raw=replace_once(raw,'@"compile.log",@"build-command.json"','@"compile.log",@"build-command.json",@"generated/live_scope.m",@"generated/live_permit.m",@"generated/live_driver.m",@"generated/live_entry.m"')
    return raw


def render_permit(raw):
    raw=replace_once(raw,'@"A23-shared32-scope-1"','@"'+SCOPE_SCHEMA+'"')
    raw=replace_once(raw,'flag(_scope[@"hardware_entry_enabled"],NO)','flag(_scope[@"hardware_entry_enabled"],YES)')
    return replace_once(raw,'flag(_scope[key],_simulation ? NO : YES)','flag(_scope[key],YES)')



def render_driver(raw):
    raw='#import "a23_live_two_epoch.h"\n'+raw
    method='- (NSArray<NSDictionary *> *)liveFailureSnapshots {\n    dispatch_assert_queue(_queue);NSMutableArray *out=[NSMutableArray new];\n    for(NSUInteger n=0;n<_owners.count;n++){NSDictionary *e=_owners[n].evidence;if(e)[out addObject:@{@"epoch":@(n),@"evidence":e}];}\n    return out;\n}\n'
    return replace_once(raw,'- (NSDictionary *)result {',method+'- (NSDictionary *)result {')


def render_entry(raw):
    raw='#import "a23_live_two_epoch.h"\n'+raw
    return replace_once(raw,'- (NSDictionary *)finalStatus {','- (NSArray<NSDictionary *> *)liveFailureSnapshots {return _driver ? [_driver liveFailureSnapshots] : @[];}\n- (NSDictionary *)finalStatus {')

def render_engine(raw):
    raw=replace_once(raw,"FORMAL_ROOT=Path(__file__).resolve().parents[1]/'private/sequence-reservations32'",'FORMAL_ROOT=Path('+repr(str(FORMAL_ROOT))+')')
    raw=replace_once(raw,"v['schema']=='A23-shared32-scope-1'","v['schema']=='"+SCOPE_SCHEMA+"'")
    return replace_once(raw,"v['hardware_entry_enabled'] is False","v['hardware_entry_enabled'] is True")


def command(build,fixture=None):
    build=Path(build);r=build/'source/research/usb-ds-iso'
    native=[r/'host'/n for n in previous.NATIVE if n not in ('a23_scope_verifier.m','a23_shared_sequence_permit.m','a23_two_epoch_sdk_driver.m','a23_two_epoch_entry.m')]
    return ['clang','-fobjc-arc','-fblocks','-Wall','-Wextra','-Werror',
        *(['-fsanitize=address,undefined','-fno-omit-frame-pointer','-g'] if fixture else ['-O2']),
        '-I'+str(build),'-I'+str(r/'host'),'-framework','Foundation','-framework','IOUSBHost','-framework','IOKit',
        *map(str,native),str(build/'generated/live_scope.m'),str(build/'generated/live_permit.m'),str(build/'generated/live_driver.m'),str(build/'generated/live_entry.m'),
        str(r/'host/a23_live_two_epoch.m'),str(fixture or r/'host/a23_live_two_epoch_main.m'),'-o',str(build/('live-fixture' if fixture else 'verified-entry'))]


def build(output):
    output=w.canonical(output);require(not output.exists(),'new live build required')
    d,saved,history,index,_=previous.authority.inputs();hashes=sources()
    d.update(description=DESCRIPTION,source_hashes=hashes,workflow_source_sha256=sha(encode(hashes)))
    output.mkdir(mode=0o700);w.card.put(output,'descriptor.json',encode(d));w.card.put(output,'a23_verified_binding.h',previous.header(d))
    for n,h in hashes.items():
        raw=w.plain(w.b.REPO/n,2*1024*1024);require(sha(raw)==h,'live source drift');w.card.put(output,'source/'+n,raw)
    for prefix,files in (('baseline',saved),('history',history),('recovery-index',index)):
        for n,raw in files.items():w.card.put(output,prefix+'/'+n,raw)
    r=output/'source/research/usb-ds-iso'
    for name,source,render in (('live_scope.m','a23_scope_verifier.m',render_scope),('live_permit.m','a23_shared_sequence_permit.m',render_permit),('live_driver.m','a23_two_epoch_sdk_driver.m',render_driver),('live_entry.m','a23_two_epoch_entry.m',render_entry)):
        w.card.put(output,'generated/'+name,render((r/'host'/source).read_text()).encode())
    cmd=command(output);p=subprocess.run(cmd,capture_output=True);w.card.put(output,'compile.log',p.stdout+p.stderr);require(p.returncode==0,'live CLI compilation failed')
    w.write(output/'binary.json',dict(schema='A23-verified-entry-binary-1',receiver_sha256=sha(w.plain(output/'verified-entry',64*1024*1024)),descriptor_sha256=sha(encode(d))))
    w.write(output/'build-command.json',dict(command=cmd));require(sources()==hashes,'live source drift after build');w.b.seal(output);verify(output)
    return w.reference(output)


def verify(build,*,current=True):
    build=w.canonical(build);files=w.card.seal_verify(build);d=w.load(build/'descriptor.json')
    require(d['description']==DESCRIPTION and len(d['source_hashes'])==587,'live descriptor differs')
    if current:require(d['source_hashes']==sources(),'live current sources differ')
    require((build/'a23_verified_binding.h').read_bytes()==previous.header(d),'live binding differs')
    for n,h in d['source_hashes'].items():require(sha(w.plain(build/'source'/n,2*1024*1024))==h,'live frozen source differs')
    for n,render,source in (('live_scope.m',render_scope,'a23_scope_verifier.m'),('live_permit.m',render_permit,'a23_shared_sequence_permit.m'),('live_driver.m',render_driver,'a23_two_epoch_sdk_driver.m'),('live_entry.m',render_entry,'a23_two_epoch_entry.m')):
        require((build/'generated'/n).read_text()==render((build/'source/research/usb-ds-iso/host'/source).read_text()),'live generated source differs')
    record=w.load(build/'binary.json');require(record==dict(schema='A23-verified-entry-binary-1',receiver_sha256=sha(w.plain(build/'verified-entry',64*1024*1024)),descriptor_sha256=sha(encode(d))),'live binary binding differs')
    expected={'descriptor.json','a23_verified_binding.h','verified-entry','binary.json','compile.log','build-command.json','generated/live_scope.m','generated/live_permit.m','generated/live_driver.m','generated/live_entry.m'}
    for group,hashes in (('source',d['source_hashes']),('baseline',d['baseline_files']),('history',d['history_files']),('recovery-index',d['recovery_index'])):
        for n,h in hashes.items():
            expected.add(group+'/'+n);require(sha(w.plain(build/group/n,64*1024*1024))==h,'live grouped input differs')
    require(set(files)==expected,'live build inventory differs');return w.reference(build)


def runtime_scope(build):
    verify(build);d=w.load(Path(build)/'descriptor.json');r=w.load(Path(build)/'binary.json')
    return dict(schema=SCOPE_SCHEMA,baseline_manifest_sha256=d['baseline_manifest_sha256'],baseline_inventory_sha256=d['baseline_inventory_sha256'],
        workflow_source_sha256=d['workflow_source_sha256'],build_manifest_sha256=sha(w.plain(Path(build)/'SHA256SUMS')),
        receiver_sha256=r['receiver_sha256'],device_binding_sha256=d['device_binding_sha256'],recipe_sha256=d['recipe_sha256'],history_sha256=d['history_sha256'],
        first_sequence=81,last_sequence=112,formal_issuance_available=True,acquisition_mode_implemented=True,hardware_entry_enabled=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True);g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);args=p.parse_args()
    print(json.dumps(build(args.output) if args.output else verify(args.check),indent=2))
