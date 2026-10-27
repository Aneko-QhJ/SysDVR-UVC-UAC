"""Offline cached entry-to-session linkage and reproducible semantic failures."""
from pathlib import Path
import argparse
import json
import shutil
import sys
import a23_cached_session_links as model
import audit_a23_cached_build_relations as previous

view, ar, a, f = model.view, model.ar, model.a, model.f
PARENT='A23-build-relations-closeout-20261020'
PARENT_SUM='a138b1895008a890401e3f6e5d2e0071d9c6176be143646796a873e8c922e3a0'
NEW=('tools/a23_cached_session_links.py','tools/audit_a23_cached_session_links.py',
     'tests/test_a23_cached_session_links.py')
CASES={**{k:[] for k in ('normal','owner-clock-shift','callback-order')},
       **{k:['driver_receipt'] for k in ('driver-copy','receipt-stale','entry-final-stale',
          'snapshot-hash','embedded-snapshot','driver-session','driver-count-bool','lease-callback-bool','entry-complete-int')},
       **{k:['session_journals'] for k in ('journal-index-bool','journal-tick-bool','journal-duplicate',
          'journal-partial','event-session','receipt-binding','claim-binding','identity-bool',
          'context-hash','entry-event')},
       **{k:['epoch_links'] for k in ('epoch-session','sample-link','budget-link','saved-hash',
          'owner-count','control-bytes','quiet-record')},'build-reference':['build_subset']}


def sources():
    import audit_a23_pinned_view as old
    w=old.w;root=w.A/PARENT;w.card.seal_verify(root)
    f.require(f.sha(w.plain(root/'SHA256SUMS'))==PARENT_SUM,'parent pin differs')
    parent=w.load(root/'closeout.json');out=previous.sources()
    f.require(out==parent['source_hashes'] and len(out)==422,'prior422 drift')
    for name in NEW:
        key='research/usb-ds-iso/'+name;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/name))
    return dict(sorted(out.items()))


def variant(base,case):
    raw=dict(base);H=model.HOST
    def obj(name):return f.parse(raw[H+name])
    def put(name,value):raw[H+name]=f.encode(value)
    def change(name,action):
        value=obj(name);action(value);put(name,value)
    def entry(action):
        for name in ('entry-current.json','entry-final/entry.json'):change(name,action)
    def driver(action):
        value=obj('result.json');action(value)
        for name in ('result.json','entry-final/driver.json','sdk-receipt/snapshot.json'):put(name,value)
        entry(lambda row:row.update(driver=value))
        change('sdk-receipt/receipt.json',lambda row:row.update(snapshot=value,snapshot_sha256=f.sha(raw[H+'sdk-receipt/snapshot.json'])))
    sdk=[f.parse(v) for v in raw[H+'session.jsonl'].splitlines()]
    erows=[f.parse(v) for v in raw[H+'entry.jsonl'].splitlines()]
    if case=='driver-copy':entry(lambda row:row['driver'].update(saved_epochs=1))
    if case=='receipt-stale':
        for name in ('receipt-status.json','entry-final/receipt-status.json'):change(name,lambda row:row.update(stale=True))
        entry(lambda row:row['driver_receipt'].update(stale=True))
    if case=='entry-final-stale':change('entry-final-status.json',lambda row:row.update(stale=True))
    if case=='snapshot-hash':change('sdk-receipt/receipt.json',lambda row:row.update(snapshot_sha256='0'*64))
    if case=='embedded-snapshot':change('sdk-receipt/receipt.json',lambda row:row['snapshot'].update(saved_epochs=1))
    if case=='driver-session':driver(lambda row:row.update(session_id='00000000-0000-0000-0000-000000000001'))
    if case=='driver-count-bool':driver(lambda row:row.update(iso_attempts=True))
    if case=='lease-callback-bool':driver(lambda row:row['lease'].update(iso_callbacks=[True,1]))
    if case=='entry-complete-int':entry(lambda row:row.update(complete=1))
    if case=='journal-index-bool':sdk[0]['index']=True
    if case=='journal-tick-bool':sdk[0]['ticks']=True
    if case=='journal-duplicate':sdk[2]['event']=sdk[1]['event']
    if case=='event-session':sdk[7]['session_id']='00000000-0000-0000-0000-000000000001'
    if case=='receipt-binding':change('sdk-receipt/receipt.json',lambda row:row['binding']['descriptor_sha256'].update(active_interface='0'*64))
    if case in ('claim-binding','identity-bool'):
        claim=obj('sdk-claim.json')
        if case=='claim-binding':claim['binding']['authorization_receipt_sha256']='0'*64
        else:claim['device_id']=True
        put('sdk-claim.json',claim);erows[7]['details']=claim
    if case=='context-hash':entry(lambda row:row.update(context_sha256='0'*64))
    if case=='entry-event':erows[9]['event']='start'
    if case=='epoch-session':
        for n in (0,1):change('epoch-%d/metadata.json'%n,lambda row:row['binding'].update(session_id='00000000-0000-0000-0000-000000000001'))
    if case=='sample-link':change('epoch-0/metadata.json',lambda row:row['sample'].update(current_frame=101))
    if case=='budget-link':change('epoch-0/metadata.json',lambda row:row['budget'].update(age_ns=501))
    if case=='saved-hash':sdk[11]['details']['metadata_sha256']='0'*64
    if case=='owner-count':sdk[8]['details']['owner']['count']=2
    if case=='control-bytes':sdk[7]['details']['bytes']=1
    if case=='quiet-record':driver(lambda row:row.update(quiet_end_ticks=row['quiet_end_ticks']+1))
    if case=='owner-clock-shift':
        for row in sdk:
            if row['event']=='iso_callback':row['details']['owner']['arrival_ticks']+=1000000
    if case=='callback-order':
        ticks=[v['ticks'] for v in sdk];sdk[7],sdk[8]=sdk[8],sdk[7]
        for i,row in enumerate(sdk):row.update(index=i+1,ticks=ticks[i])
    if case=='build-reference':
        name=model.prior.INPUTS+'config.json';row=f.parse(raw[name]);row['binding']['build_manifest_sha256']='0'*64;raw[name]=f.encode(row)
    if case!='normal':
        for n in (0,1):
            name=H+'epoch-%d/metadata.json'%n
            if raw[name]!=base[name]:
                for row in sdk:
                    if row['event']=='saved' and row['details'].get('epoch')==n:
                        row['details']['metadata_sha256']=f.sha(raw[name])
        raw[H+'session.jsonl']=b''.join(f.encode(row) for row in sdk)
        raw[H+'entry.jsonl']=b''.join(f.encode(row) for row in erows)
        if case=='journal-partial':raw[H+'session.jsonl']=raw[H+'session.jsonl'][:-1]
        previous.epochs.rebuild_seals(raw)
    return raw


def exercise(bundle):
    builds,journal,roots=previous.load_bundle(bundle)
    base={n:journal[0].read(n) for n in journal[0].files};rows={}
    gate=dict(active=False,opens=[])
    def hook(event,args):
        if gate['active'] and event=='open':gate['opens'].append(str(args[0]));raise ValueError('consumer opened file')
    sys.addaudithook(hook)
    for case,expected in CASES.items():
        raw=variant(base,case)
        js=journal if case=='normal' else previous.journal_spec(raw,journal[4],journal[2])
        links=previous.link_bytes(builds['receiver'],builds['supervisor'],js,roots)
        gate['active']=True
        try:result=model.consume(builds['receiver'],builds['supervisor'],js,links,f.sha(links))
        finally:gate['active']=False
        f.require(result['errors']==expected,'unexpected '+case+': '+str(result))
        rows[case]=dict(result=result,constructed_model=case!='normal',journal_manifest_sha256=js[3],link_sha256=f.sha(links))
    f.require(not gate['opens'],'consumer opened paths')
    return dict(passed=True,cases=rows,consumer_filesystem_opens=0, **model.FALSE)


def replay(root,pin):
    root=a.canonical(root);_,_,digest=a.sealed(root)
    f.require(f.hex64(pin) and digest==pin,'external review pin differs')
    result=exercise(root/'bundle');f.require(f.encode(result)==a.read(root/'results.json'),'saved result differs')
    return result


def run(output):
    import audit_a23_pinned_view as old
    w=old.w;output=a.canonical(output);f.require(not output.exists(),'new session-link review required')
    frozen=sources();parent=f.load(w.A/PARENT/'closeout.json');ref=parent['references']['review']
    source=Path(ref['directory']);_,_,digest=a.sealed(source);f.require(digest==ref['manifest_sha256'],'parent review differs')
    output.mkdir(mode=0o700)
    for name,digest in frozen.items():
        value=w.plain(w.b.REPO/name);f.require(f.sha(value)==digest,'source drift');a.put(output,'source/'+name,value)
    shutil.copytree(source/'bundle',output/'bundle')
    result=exercise(output/'bundle');a.put(output,'results.json',f.encode(result))
    f.require(sources()==frozen,'source drift after review')
    a.put(output,'audit.json',f.encode(dict(passed=True,source_count=425,prior_sources_unchanged=422,
          source_hashes=frozen,model_cases=len(CASES),semantic_rejections=sum(bool(v) for v in CASES.values()),
          consistent_subset_cases=sum(not v for v in CASES.values()),consumer_filesystem_opens=0,
          usb_requests=0,sd_accesses=0,real_sdk_objects=0,native_executions=0,formal_records=0,formal_reservations=0, **model.FALSE)))
    a.seal(output);return dict(passed=True,review_sha256=f.sha(a.read(output/'SHA256SUMS')),model_cases=len(CASES))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--output',type=Path);group.add_argument('--check',type=Path);parser.add_argument('--expected-sha256');args=parser.parse_args()
    if args.check and not args.expected_sha256:parser.error('--check requires --expected-sha256')
    try:result=run(args.output) if args.output else replay(args.check,args.expected_sha256)
    except (ValueError,OSError,KeyError,TypeError) as exc:print(json.dumps(dict(passed=False,error=str(exc))));raise SystemExit(2)
    print(json.dumps(result,indent=2))
