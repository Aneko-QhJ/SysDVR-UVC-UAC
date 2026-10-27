"""Rehashed cached permit/context models, including coherent PID/context splices."""
from pathlib import Path
import argparse
import json
import shutil
import sys
import a23_cached_permit_context as model
import audit_a23_cached_session_links as previous

factory=previous.previous
view,ar,a,f=model.view,model.ar,model.a,model.f
PARENT='A23-session-links-closeout-20261020'
PARENT_SUM='863e7410b1780d386a002bf44b3a2b7f401d4df8b1a7ccf65194e87e0417f1a4'
NEW=('tools/a23_cached_permit_context.py','tools/audit_a23_cached_permit_context.py','tests/test_a23_cached_permit_context.py')
CASES={**{k:[] for k in ('normal','owner-clock-shift','hello-observation-shift')},
       **{k:['shared_records'] for k in ('authorization-count-bool','authorization-hardware','reservation-count',
          'reservation-job-hash','issue-marker','consumed-bool','consume-marker')},
       **{k:['native_claims'] for k in ('context-pid-bool','context-sandbox','native-receipt','native-speed-bool',
          'native-marker','native-stale','native-hardware-count','native-identity','entry-receipt','entry-pid')},
       **{k:['supervision_context'] for k in ('control-nonce','supervised-pid','injection-declaration','actual-context-copy',
          'saved-policy','coherent-pid-splice','extra-context-substitution','supervision-owner','hello-budget',
          'late-hello','control-job','envelope-pid')},'session-receipt':['session_subset']}


def sources():
    import audit_a23_pinned_view as old
    w=old.w;root=w.A/PARENT;w.card.seal_verify(root)
    f.require(f.sha(w.plain(root/'SHA256SUMS'))==PARENT_SUM,'parent pin differs')
    parent=w.load(root/'closeout.json');out=previous.sources()
    f.require(out==parent['source_hashes'] and len(out)==425,'prior425 drift')
    for name in NEW:
        key='research/usb-ds-iso/'+name;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/name))
    return dict(sorted(out.items()))


def variant(base,case):
    raw=previous.variant(base,'owner-clock-shift') if case=='owner-clock-shift' else dict(base)
    H,I,E=model.HOST,model.INPUTS,model.ENV
    job=f.parse(raw[I+'case-info.json'])['job_id'];J=I+'namespace/jobs/'+job+'/'
    def obj(name):return f.parse(raw[name])
    def put(name,value):raw[name]=f.encode(value)
    def change(name,action):
        value=obj(name);action(value);put(name,value)
    def report(action):
        value=obj(I+'report.json');action(value)
        put(I+'report.json',value);put(E+'final/report.json',value)
    def entry(action):
        for name in (H+'entry-current.json',H+'entry-final/entry.json'):change(name,action)
        report(lambda row:row.update(entry=obj(H+'entry-current.json')))
    def entry_events(action):
        rows=[f.parse(v) for v in raw[H+'entry.jsonl'].splitlines()];action(rows);raw[H+'entry.jsonl']=b''.join(f.encode(v) for v in rows)
    def repair_context(context):
        put(J+'native-context.json',context);put(H+'context.json',context)
        native_sha=f.sha(raw[J+'native-context.json']);host_sha=f.sha(raw[H+'context.json'])
        change(J+'native-process-claim.json',lambda row:row.update(context_sha256=native_sha,pid=context['pid']))
        change(J+'native-sdk-claim.json',lambda row:row.update(context_sha256=native_sha,pid=context['pid'],process_sha256=f.sha(raw[J+'native-process-claim.json'])))
        for name in ('process-claim.json','sdk-claim.json'):change(H+name,lambda row:row.update(context_sha256=host_sha,pid=context['pid']))
        entry(lambda row:row.update(context_sha256=host_sha))
        report(lambda row:row.update(execution_context=context))
        def fix(rows):
            for row in rows:
                if row['event']=='context':row['details']['sha256']=host_sha
                if row['event'] in ('process_claim','sdk_claim'):row['details']=obj(H+row['event'].replace('_','-')+'.json')
        entry_events(fix)
    if case=='authorization-count-bool':change(J+'authorization.json',lambda row:row.update(maximum_invocations=True))
    if case=='authorization-hardware':change(J+'authorization.json',lambda row:row.update(hardware_test_authorized=True))
    if case=='reservation-count':change(I+'namespace/block-00081.json',lambda row:row.update(count=31))
    if case=='reservation-job-hash':change(I+'namespace/block-00081.json',lambda row:row.update(job_sha256='0'*64))
    if case=='issue-marker':raw[J+'issue-commit']=b''
    if case=='consumed-bool':change(J+'consumed.json',lambda row:row.update(remaining=False))
    if case=='consume-marker':raw[J+'consume-commit']=b'not committed\n'
    if case=='context-pid-bool':change(J+'native-context.json',lambda row:row.update(pid=True))
    if case=='context-sandbox':change(J+'native-context.json',lambda row:row.update(sandbox_query_result=1))
    if case=='native-receipt':change(J+'native-process-claim.json',lambda row:row.update(consumed_sha256='0'*64))
    if case=='native-speed-bool':change(J+'native-sdk-claim.json',lambda row:row['identity'].update(speed=True))
    if case=='native-marker':raw[J+'native-process-attempt']=b''
    if case=='native-stale':report(lambda row:row['native']['permit'].update(stale=True))
    if case=='native-hardware-count':report(lambda row:row['native'].update(usb_requests=False))
    if case=='native-identity':change(J+'native-sdk-claim.json',lambda row:row['identity'].update(device_id=103))
    if case=='entry-receipt':
        def replace(value):
            if type(value) is dict:
                if value.get('schema')=='A23-two-epoch-entry-binding-1':value['authorization_receipt_sha256']='0'*64
                for child in value.values():replace(child)
            elif type(value) is list:
                for child in value:replace(child)
        for name in (I+'config.json',H+'entry-current.json',H+'entry-final/entry.json',H+'process-claim.json',H+'sdk-claim.json'):
            change(name,replace)
        entry_events(lambda rows:replace(rows))
        report(lambda row:row.update(entry=obj(H+'entry-current.json')))
    if case=='entry-pid':
        change(H+'process-claim.json',lambda row:row.update(pid=row['pid']+1))
        entry_events(lambda rows:rows[1].update(details=obj(H+'process-claim.json')))
    if case=='control-nonce':change(E+'control.json',lambda row:row.update(nonce='0'*64))
    if case=='supervised-pid':change(E+'supervision/result.json',lambda row:row.update(child_pid=row['child_pid']+1))
    if case=='injection-declaration':
        change(E+'plan.json',lambda row:row.update(inject_policy=False));report(lambda row:row.update(execution_context_injected=False))
    if case=='actual-context-copy':report(lambda row:row['actual_context'].update(euid=502))
    if case=='saved-policy':change(E+'supervision/result.json',lambda row:row.update(child_execution_policy_pass=True))
    if case in ('coherent-pid-splice','extra-context-substitution'):
        context=obj(H+'context.json')
        if case=='coherent-pid-splice':context['pid']+=1
        else:context['euid']+=1
        repair_context(context)
    if case=='supervision-owner':
        for name in ('OWNER','OWNER-original'):raw[E+'supervision/'+name]=b'0'*64+b'\n'
    if case=='hello-budget':
        for name in ('handoff.json','handoff-original.json'):change(E+'supervision/'+name,lambda row:row.update(hello_budget_ns=1000000000))
        change(E+'supervision/stdout.bin',lambda row:row.update(handoff_sha256=f.sha(raw[E+'supervision/handoff-original.json'])))
    if case=='late-hello':change(E+'supervision/result.json',lambda row:row.update(hello_observed_ns=row['hello_deadline_ns']))
    if case=='control-job':change(E+'control.json',lambda row:row.update(job_path='/private/tmp/wrong-job'))
    if case=='envelope-pid':change(E+'envelope.json',lambda row:row.update(child_pid=row['child_pid']+1))
    if case=='session-receipt':change(H+'sdk-receipt/receipt.json',lambda row:row.update(snapshot_sha256='0'*64))
    if case=='hello-observation-shift':change(E+'supervision/result.json',lambda row:row.update(hello_observed_ns=row['hello_observed_ns']+1))
    if case!='normal':factory.epochs.rebuild_seals(raw)
    return raw


def exercise(bundle):
    builds,journal,roots=factory.load_bundle(bundle);base={n:journal[0].read(n) for n in journal[0].files}
    rows={};gate=dict(active=False,opens=[])
    def hook(event,args):
        if gate['active'] and event=='open':gate['opens'].append(str(args[0]));raise ValueError('consumer opened file')
    sys.addaudithook(hook)
    for case,expected in CASES.items():
        raw=variant(base,case);js=journal if case=='normal' else factory.journal_spec(raw,journal[4],journal[2])
        links=factory.link_bytes(builds['receiver'],builds['supervisor'],js,roots)
        gate['active']=True
        try:result=model.consume(builds['receiver'],builds['supervisor'],js,links,f.sha(links))
        finally:gate['active']=False
        f.require(result['errors']==expected,'unexpected '+case+': '+str(result))
        rows[case]=dict(result=result,constructed_model=case!='normal',journal_manifest_sha256=js[3],link_sha256=f.sha(links))
    f.require(not gate['opens'],'consumer opened paths')
    return dict(passed=True,cases=rows,consumer_filesystem_opens=0, **model.FALSE)


def replay(root,pin):
    root=a.canonical(root);_,_,digest=a.sealed(root);f.require(f.hex64(pin) and digest==pin,'external review pin differs')
    result=exercise(root/'bundle');f.require(f.encode(result)==a.read(root/'results.json'),'saved results differ');return result


def run(output):
    import audit_a23_pinned_view as old
    w=old.w;output=a.canonical(output);f.require(not output.exists(),'new permit/context review required')
    frozen=sources();parent=f.load(w.A/PARENT/'closeout.json');ref=parent['references']['review']
    source=Path(ref['directory']);_,_,digest=a.sealed(source);f.require(digest==ref['manifest_sha256'],'parent review differs')
    output.mkdir(mode=0o700)
    for name,digest in frozen.items():
        value=w.plain(w.b.REPO/name);f.require(f.sha(value)==digest,'source drift');a.put(output,'source/'+name,value)
    shutil.copytree(source/'bundle',output/'bundle')
    result=exercise(output/'bundle');a.put(output,'results.json',f.encode(result));f.require(sources()==frozen,'source drift after review')
    a.put(output,'audit.json',f.encode(dict(passed=True,source_count=428,prior_sources_unchanged=425,source_hashes=frozen,
          model_cases=len(CASES),semantic_rejections=sum(bool(v) for v in CASES.values()),consistent_subset_cases=sum(not v for v in CASES.values()),
          consumer_filesystem_opens=0,usb_requests=0,sd_accesses=0,real_sdk_objects=0,native_executions=0,formal_records=0,formal_reservations=0, **model.FALSE)))
    a.seal(output);return dict(passed=True,review_sha256=f.sha(a.read(output/'SHA256SUMS')),model_cases=len(CASES))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--output',type=Path);group.add_argument('--check',type=Path);parser.add_argument('--expected-sha256');args=parser.parse_args()
    if args.check and not args.expected_sha256:parser.error('--check requires --expected-sha256')
    try:result=run(args.output) if args.output else replay(args.check,args.expected_sha256)
    except (ValueError,OSError,KeyError,TypeError) as exc:print(json.dumps(dict(passed=False,error=str(exc))));raise SystemExit(2)
    print(json.dumps(result,indent=2))
