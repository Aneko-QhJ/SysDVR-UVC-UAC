"""Q1 SDK-capable candidate; preparation never issues or launches a capture."""
import argparse
import json
import subprocess
from pathlib import Path
import build_a23_live132_completion as base
import audit_a23_postcompletion_semantics as prior
import a23_checked_export as checked

w=base.w;sha=base.sha;encode=base.encode;require=base.require
PARENT=w.A/'A23-evidence-conclusions-20261026'
PARENT_SUM='7ad581facd3fda5c8cb372b6cf146ec62f985509d1a7ee74c20946e7af2669a6'
NEW=('tools/build_a23_live132_q1.py','tools/a23_live132_q1_workflow.py','tools/a23_live132_q1_consumer.py','tools/audit_a23_live132_q1.py')
FORMAL_ROOT=w.ROOT/'private/sequence-reservations48-465'
SCHEMA='A23-live132-q1-shared48-scope-1'
DESCRIPTION=dict(base.DESCRIPTION,schema='A23-live132-q1-description-1',full_guard_source_count=672,
    hardware_entry_enabled=True,formal_issuance_available=True,acquisition_mode_implemented=True,
    capability_is_not_authorization=True)
LIVE=w.A/'A23-live126-interepoch-review-20261025-r1/build'

def sources():
    require(base.base.base.core.verify_seal(PARENT)==PARENT_SUM,'conclusions drift')
    old=prior.sources();require(len(old)==668 and old==w.load(PARENT/'source-hashes.json'),'old668 drift')
    return dict(sorted((old|{'research/usb-ds-iso/'+n:sha(w.plain(w.ROOT/n)) for n in NEW}).items()))

def inputs():
    d,saved,hist,index,history=base.inputs();hashes=sources()
    d.update(description=DESCRIPTION,source_hashes=hashes,workflow_source_sha256=sha(encode(hashes)),parent_manifest_sha256=PARENT_SUM)
    return d,saved,hist,index,history

def one(raw,old,new):
    require(raw.count(old)==1,'Q1 generation anchor '+old[:65]);return raw.replace(old,new)

COLLECT_EXTRA=r'''
    require(state['execution_mode']=='require_escalated' and state['run']==str(run),'collector mode/run differs')
    require(state['receiver_launched'] is True and state['scope']==builder.scope(state['build'],current=False),'collector launch/scope differs')
    require(job.parent==builder.FORMAL_ROOT/'jobs','collector formal job differs')
    native_context=w.load(job/'native-context.json')
    require(type(state.get('receiver_pid')) is int and native_context['pid']==state['receiver_pid'],'direct child/context PID differs')
    require(w.load(job/'consumed.json')['simulation'] is False and w.load(job/'native-process-claim.json')['simulation'] is False and
        w.load(job/'native-sdk-claim.json')['simulation'] is False,'model native claims in real collection')
'''

def runtime_source():
    # Immutable prior real workflow retains burn-before-launch and direct wait.
    base.base.base.verify(LIVE,current=False)
    raw=w.plain(LIVE/'generated/workflow.py').decode()
    raw=raw.replace('import build_a23_live126_interepoch as builder','import build_a23_live132_q1 as builder')
    raw=raw.replace('from a23_live126_interepoch_workflow import analyze_entry as entry_analyze',
        'from a23_live132_q1_consumer import analyze_entry as entry_analyze\nfrom a23_live132_q1_consumer import collect_failure')
    begin=raw.index('def engine_module(build):');end=raw.index('\ndef fresh_scope',begin)
    raw=raw[:begin]+'''def engine_module(build):
    builder.verify(build)
    from a23_live132_q1_consumer import module
    return module(build,'fixed48')
\n'''+raw[end:]
    raw=raw.replace('builder.runtime_scope(build)','builder.scope(build)')
    raw=raw.replace('first_sequence=417,last_sequence=464','first_sequence=465,last_sequence=512')
    raw=raw.replace("'A-three-epoch-'","'A-q1-three-epoch-'")
    raw=one(raw,'result=entry_analyze(stage,Path(state["build"]))',
        'result=entry_analyze(stage,Path(state["build"]),job=state["job"],simulation=False)')
    raw=one(raw,'scope=state[\'scope\'];binding=w.load(stage/\'entry-current.json\')[\'binding\'];job=Path(state[\'job\'])',
        'scope=state[\'scope\'];binding=w.load(stage/\'entry-current.json\')[\'binding\'];job=Path(state[\'job\'])\n'+COLLECT_EXTRA)
    raw=one(raw,"    w.b.seal(run);return state\n\n\nif __name__",'''    else:
        try:w.write(run/'failure-analysis.json',collect_failure(run))
        except (ValueError,OSError,KeyError,TypeError) as exc:w.write(run/'failure-analysis-error.json',dict(error=str(exc)))
    w.b.seal(run);return state


if __name__''')
    return raw

def main_source():
    base.base.base.verify(LIVE,current=False)
    raw=w.plain(LIVE/'generated/live_main.m').decode()
    raw=raw.replace(str(w.ROOT/'private/sequence-reservations48-417'),str(FORMAL_ROOT))
    raw=raw.replace('@417','@465').replace('@464','@512').replace('firstSequence:417','firstSequence:465')
    raw=raw.replace('@"A-three-epoch-"','@"A-q1-three-epoch-"')
    raw=one(raw,'if(!loop){','if(!loop || ![loop configureCompletionQueue:queue]){')
    raw=one(raw,'if(A23InterepochExitAllowed(s,coordinator.queueGuardResult)){',
        'if(A23CompletionExitAllowed(s,coordinator.queueGuardResult,coordinator.terminalGuardResult)){')
    raw=one(raw,'@"loop":s,@"run":run});exit([s[@"exit_code"] intValue]);',
        '@"loop":s,@"interepoch_guard":coordinator.queueGuardResult,@"terminal_guard":coordinator.terminalGuardResult,'
        '@"success_scope":@"historical_completion_sample",@"current_device_state":@"unverified",@"run":run});exit([s[@"exit_code"] intValue]);')
    return raw

def generated(source,d):
    gen,_=base.generated(source,d);result={n:v.decode() for n,v in gen.items()}
    for name in result:result[name]=result[name].replace(base.SCHEMA,SCHEMA)
    s=result['live_scope.m']
    s=one(s,'@"formal_issuance_available":@NO,@"acquisition_mode_implemented":@NO,@"hardware_entry_enabled":@NO',
        '@"formal_issuance_available":@YES,@"acquisition_mode_implemented":@YES,@"hardware_entry_enabled":@YES')
    s=one(s,'@"schema":@"A23-live132-terminal-binding-1",@"model_only":@YES,',
        '@"schema":@"A23-live132-q1-terminal-binding-1",@"model_only":@([_verifier.result[@"model_roots"] boolValue]),')
    s=one(s,'BOOL _terminalStarted;}','BOOL _terminalStarted,_q1ModelScope;}')
    s=one(s,'    _guardQueue=q;','    _guardQueue=q;_q1ModelScope=[_verifier.result[@"model_roots"] boolValue];')
    s=one(s,'@"verification_pending":@YES,@"interepoch_guard":', '@"q1_mode_model":@(_q1ModelScope),@"verification_pending":@YES,@"interepoch_guard":')
    s=one(s,'@"schema":@"A23-export-boundary-evidence-1",@"entry_binding":', '@"q1_mode_model":@(_q1ModelScope),@"schema":@"A23-export-boundary-evidence-1",@"entry_binding":')
    result['live_scope.m']=s
    driver=result['live_driver.m']
    driver=one(driver,'static BOOL sdkHealthy',r'''
static id frozenTerminalJSON(id value) {
    if(![value isKindOfClass:NSDictionary.class] || ![NSJSONSerialization isValidJSONObject:value])return nil;
    NSArray *samples=value[@"samples_ns"],*events=value[@"events"];
    if(![samples isKindOfClass:NSArray.class] || ![events isKindOfClass:NSArray.class] ||
       samples.count<2 || samples.count>512 || events.count!=samples.count+8 ||
       ![value[@"sample_count"] isEqual:@(samples.count)])return nil;
    NSData *raw=[NSJSONSerialization dataWithJSONObject:value options:NSJSONWritingSortedKeys error:NULL];
    return raw.length<=262144?[NSJSONSerialization JSONObjectWithData:raw options:0 error:NULL]:nil;
}
#ifdef A23_EXPORT_MODEL_FIXTURE
NSDictionary *A23Q1EncodingFixture(NSDictionary *value) {
    NSMutableDictionary *bad=[value mutableCopy];bad[@"sample_count"]=@513;
    return @{@"legacy_accepts":@((BOOL)(frozenJSON(value)!=nil)),@"terminal_accepts":@((BOOL)(frozenTerminalJSON(value)!=nil)),
        @"bad_count_rejected":@((BOOL)(frozenTerminalJSON(bad)==nil))};
}
#endif
static BOOL sdkHealthy''')
    driver=one(driver,'_terminalProof=frozenJSON(e);uint64_t now=_clock.nowTicks;',
        '_terminalProof=frozenTerminalJSON(e);if(!_terminalProof){[self stop:@"terminal_evidence_encoding"];return NO;}uint64_t now=_clock.nowTicks;')
    result['live_driver.m']=driver
    p=result['live_permit.m']
    p=one(p,'else return nil;', 'else if(![_root isEqual:@"'+str(FORMAL_ROOT)+'"])return nil;')
    p=p.replace('flag(_scope[@"hardware_entry_enabled"],NO)','flag(_scope[@"hardware_entry_enabled"],YES)').replace('flag(_scope[key],NO)','flag(_scope[key],YES)')
    result['live_permit.m']=p
    result['fixed48.py']=result['fixed48.py'].replace("v['hardware_entry_enabled'] is False","v['hardware_entry_enabled'] is True")
    result['live_main.m']=main_source();result['workflow.py']=runtime_source()
    # A maximum-size, bounded 512-point service record can exceed the old 16K
    # driver snapshot reader. Keep explicit limits while retaining all schemas.
    result['entry_analysis.py']=result['entry_analysis.py'].replace("read(root/'result.json',16384)","read(root/'result.json',262144)").replace('read(root/n,65536)','read(root/n,262144)').replace("read(root/'entry-current.json',65536)","read(root/'entry-current.json',262144)")
    bound=dict(schema='A23-live132-q1-candidate-1',source_closure_sha256=d['workflow_source_sha256'],
        descriptor_inputs_sha256=sha(encode(d)),parent_manifest_sha256=PARENT_SUM,generated_scope_sha256=sha(s.encode()),
        controller_sha256=sha(result['live_export.m'].encode()),entry_main_sha256=sha(result['live_main.m'].encode()),
        transaction_count=128,model_only=False,completion_fact_required=True,completion_owner_queue_handoffs=1)
    result['a23_checked_export_binding.h']=checked.binding_header(bound).decode()
    result['export_analysis.py']=result['export_analysis.py'].replace('A23-live132-completion-offline-candidate-1',bound['schema']).replace("bound['model_only'] is True","bound['model_only'] is False")
    return {n:v.encode() for n,v in result.items()},bound

command=base.command
def build(output):
    output=w.canonical(output);require(not output.exists(),'fresh Q1 build required')
    d,saved,hist,index,_=inputs();gen,_=generated(w.b.REPO,d);d['generated_hashes']={n:sha(v) for n,v in gen.items()};output.mkdir(mode=0o700)
    for n,v in [('descriptor.json',encode(d)),('a23_verified_binding.h',base.base.base.HEADER(d)),('a23_checked_export_binding.h',gen['a23_checked_export_binding.h'])]:w.card.put(output,n,v)
    for n in d['source_hashes']:w.card.put(output,'source/'+n,w.plain(w.b.REPO/n))
    for group,items in [('baseline',saved),('history',hist),('recovery-index',index),('generated',gen)]:
        for n,v in items.items():w.card.put(output,group+'/'+n,v)
    cmd=command(output);p=subprocess.run(cmd,capture_output=True,timeout=60)
    w.card.put(output,'compile.log',p.stdout+p.stderr);w.write(output/'build-command.json',dict(command=cmd,returncode=p.returncode,creator_wait_verified=True));require(p.returncode==0,'Q1 compilation failed')
    w.write(output/'binary.json',dict(schema='A23-verified-entry-binary-1',receiver_sha256=sha(w.plain(output/'verified-entry',64*1024*1024)),descriptor_sha256=sha(encode(d))))
    require(inputs()[0]=={k:v for k,v in d.items() if k!='generated_hashes'},'Q1 inputs drift');w.b.seal(output);return verify(output)

def verify(build,current=True):
    build=Path(build);files=w.card.seal_verify(build);d=w.load(build/'descriptor.json')
    require(d['description']==DESCRIPTION and len(d['source_hashes'])==672,'Q1 descriptor differs')
    if current:require(inputs()[0]=={k:v for k,v in d.items() if k!='generated_hashes'},'current Q1 inputs differ')
    gen,_=generated(build/'source',{k:v for k,v in d.items() if k!='generated_hashes'})
    require(d['generated_hashes']=={n:sha(v) for n,v in gen.items()},'Q1 generated drift')
    require(w.plain(build/'a23_verified_binding.h')==base.base.base.HEADER(d) and w.plain(build/'a23_checked_export_binding.h')==gen['a23_checked_export_binding.h'],'Q1 headers differ')
    expected={'descriptor.json','a23_verified_binding.h','a23_checked_export_binding.h','verified-entry','binary.json','compile.log','build-command.json'}
    for group,items in [('source',d['source_hashes']),('baseline',d['baseline_files']),('history',d['history_files']),('recovery-index',d['recovery_index']),('generated',d['generated_hashes'])]:
        for n,h in items.items():expected.add(group+'/'+n);require(sha(w.plain(build/group/n,64*1024*1024))==h,'Q1 input drift')
    require(set(files)==expected,'Q1 inventory differs')
    require(w.load(build/'binary.json')==dict(schema='A23-verified-entry-binary-1',receiver_sha256=sha(w.plain(build/'verified-entry',64*1024*1024)),descriptor_sha256=sha(w.plain(build/'descriptor.json'))),'Q1 binary drift')
    return dict(directory=str(build),manifest_sha256=sha(w.plain(build/'SHA256SUMS')),entries=len(files))

def scope(build,current=True):
    verify(build,current=current);d=w.load(Path(build)/'descriptor.json');r=w.load(Path(build)/'binary.json')
    return dict(schema=SCHEMA,**{k:d[k] for k in ('baseline_manifest_sha256','baseline_inventory_sha256','workflow_source_sha256','device_binding_sha256','recipe_sha256','history_sha256')},
        build_manifest_sha256=sha(w.plain(Path(build)/'SHA256SUMS')),receiver_sha256=r['receiver_sha256'],first_sequence=465,last_sequence=512,
        formal_issuance_available=True,acquisition_mode_implemented=True,hardware_entry_enabled=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);print(json.dumps(build(p.parse_args().output)))
