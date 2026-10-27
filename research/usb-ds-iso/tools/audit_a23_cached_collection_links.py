"""Offline cached admission/verifier/static-collection semantic counterexamples."""
from pathlib import Path
import argparse,json,shutil,sys
import a23_cached_collection_links as model
import audit_a23_cached_clock_domains as previous

factory=previous.factory
view,ar,a,f=model.view,model.ar,model.a,model.f
PARENT='A23-clock-domains-closeout-20261020'
PARENT_SUM='7169ac8aa1f33f4ff288b405b24f73546894520d0c2472ad4b3d81e5f4fdd657'
NEW=('tools/a23_cached_collection_links.py','tools/audit_a23_cached_collection_links.py',
     'tests/test_a23_cached_collection_links.py')
CASES={**{k:[] for k in ('normal','declared-checks-change','coherent-quiet-minimum','coherent-queued-delay')},
       **{k:['admission'] for k in ('admission-source','admission-observed','admission-count-bool','admission-current-count',
          'admission-match','admission-point','admission-authority','expected-scope','admission-attempt')},
       **{k:['verifier'] for k in ('verifier-failed','verifier-roots','verifier-checks-bool','verifier-checks-zero',
          'verifier-origin','verifier-extra','report-final','report-calls','report-case')},
       **{k:['collection'] for k in ('inventory-hash','inventory-size-bool','inventory-omission','directories-duplicate',
          'directories-omission','directories-traversal','collection-report-pin','collection-attempt','stream-copy',
          'origin-promotion','collection-authority','collection-extra')},
       **{k:['saved_summary'] for k in ('summary-packet','summary-total','summary-quiet','summary-authority')},
       **{k:['envelope'] for k in ('envelope-exit-bool','envelope-full-claim','envelope-report-state','envelope-delivery',
          'envelope-attempt','envelope-extra')},'prior-receipt':['prior_subset']}


def sources():
    import audit_a23_pinned_view as old
    w=old.w;root=w.A/PARENT;w.card.seal_verify(root)
    f.require(f.sha(w.plain(root/'SHA256SUMS'))==PARENT_SUM,'parent pin differs')
    parent=w.load(root/'closeout.json');out=previous.sources()
    f.require(out==parent['source_hashes'] and len(out)==431,'prior431 drift')
    for name in NEW:
        key='research/usb-ds-iso/'+name;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/name))
    return dict(sorted(out.items()))


def refresh_collection(raw):
    inputs={n[len(model.INPUTS):]:v for n,v in raw.items() if n.startswith(model.INPUTS)}
    meta=f.parse(raw[model.FINAL+'collection.json'])
    meta.update(raw_files=a.inventory(inputs),report_sha256=f.sha(raw[model.FINAL+'report.json']))
    raw[model.FINAL+'collection.json']=f.encode(meta)


def variant(base,case):
    if case=='normal':return dict(base)
    if case=='prior-receipt':return previous.previous.variant(base,'session-receipt')
    raw=dict(base);E,F,I=model.ENV,model.FINAL,model.INPUTS
    if case.startswith('coherent-'):
        raw=previous.schedule(base,**(dict(quiet=250000000) if case=='coherent-quiet-minimum' else dict(queue_lag=25000000)))
        previous.refresh(raw)
        saved=f.parse(raw[F+'analysis.json']);driver=f.parse(raw[model.HOST+'result.json'])
        saved['entry']['sdk']['observation_window_ns']=driver['quiet_end_ticks']-driver['quiet_start_ticks']
        raw[F+'analysis.json']=f.encode(saved)
    report=f.parse(raw[I+'report.json']);v=report['verifier']
    if case=='declared-checks-change':v['checks']+=1
    if case=='verifier-failed':v['failed']=True
    if case=='verifier-roots':v['model_roots']=False
    if case=='verifier-checks-bool':v['checks']=True
    if case=='verifier-checks-zero':v['checks']=0
    if case=='verifier-origin':v['binary_origin_authenticated']=True
    if case=='verifier-extra':v['runtime_authenticated']=True
    if case=='report-final':report['final']['saved']=False
    if case=='report-calls':report['calls']['iso_submissions']+=1
    if case=='report-case':report['case']='different-model'
    if case=='declared-checks-change' or case.startswith(('verifier-','report-')):
        for name in (I+'report.json',F+'report.json'):raw[name]=f.encode(report)
    refresh_collection(raw)
    admission=f.parse(raw[E+'admission.json'])
    if case=='admission-source':admission['source_sha256']='0'*64
    if case=='admission-observed':admission['observed_sha256']='0'*64
    if case=='admission-count-bool':admission['source_count']=True
    if case=='admission-current-count':admission['source_count']=434
    if case=='admission-match':admission['source_match']=False
    if case=='admission-point':admission['point_in_time_only']=False
    if case=='admission-authority':admission['production_execution_authorized']=True
    if case.startswith('admission-') and case!='admission-attempt':raw[E+'admission.json']=f.encode(admission)
    if case=='expected-scope':
        scope=f.parse(raw[E+'expected-scope.json']);scope['history_sha256']='0'*64;raw[E+'expected-scope.json']=f.encode(scope)
    if case=='admission-attempt':raw[E+'ADMISSION_ATTEMPT']=b'one source admission attempt\nagain\n'
    meta=f.parse(raw[F+'collection.json']);first=next(iter(meta['raw_files']))
    if case=='inventory-hash':meta['raw_files'][first]['sha256']='0'*64
    if case=='inventory-size-bool':meta['raw_files'][first]['bytes']=True
    if case=='inventory-omission':del meta['raw_files'][first]
    if case=='directories-duplicate':meta['directories'].append(meta['directories'][0])
    if case=='directories-omission':meta['directories'].pop()
    if case=='directories-traversal':meta['directories'][0]='../outside'
    if case=='collection-report-pin':meta['report_sha256']='0'*64
    if case=='collection-authority':meta['process_origin_authenticated']=True
    if case=='origin-promotion':
        meta['origin']='observed_model_child_exit';meta['observation']=dict(mode=meta['origin'],child_exited=True,
             returncode=0,binary_sha256=meta['build_reference']['receiver_sha256'])
    raw[F+'collection.json']=f.encode(meta)
    if case=='collection-attempt':raw[F+'ATTEMPT']=b'two final collection attempts\n'
    if case=='stream-copy':raw[F+'process.stdout']+=b'changed\n'
    if case=='collection-extra':raw[F+'unexpected']=b'not declared'
    saved=f.parse(raw[F+'analysis.json'])
    if case=='summary-packet':saved['entry']['sdk']['epochs'][1]['urb_id']+=1
    if case=='summary-total':saved['entry']['sdk']['total_bytes']+=1
    if case=='summary-quiet':saved['entry']['sdk']['observation_window_ns']+=1
    if case=='summary-authority':saved['entry']['production_permit_authenticated']=True
    if case.startswith('summary-'):raw[F+'analysis.json']=f.encode(saved)
    envelope=f.parse(raw[E+'envelope.json'])
    if case=='envelope-exit-bool':envelope['producer_exited']=1
    if case=='envelope-full-claim':envelope['complete_injected_model_chain']=False
    if case=='envelope-report-state':envelope['report_state']='malformed'
    if case=='envelope-delivery':envelope['control_delivery']='partial'
    if case.startswith('envelope-'):raw[E+'envelope.json']=f.encode(envelope)
    if case=='envelope-attempt':raw[E+'FINAL_ATTEMPT']=b'again\n'
    if case=='envelope-extra':raw[E+'unexpected']=b'not declared'
    factory.epochs.rebuild_seals(raw)
    return raw


def exercise(bundle):
    builds,journal,roots=factory.load_bundle(bundle);base={n:journal[0].read(n) for n in journal[0].files}
    cases={};gate=dict(active=False,opens=[])
    def hook(event,args):
        if gate['active'] and event=='open':gate['opens'].append(str(args[0]));raise ValueError('consumer opened file')
    sys.addaudithook(hook)
    for case,expected in CASES.items():
        raw=variant(base,case);js=journal if case=='normal' else factory.journal_spec(raw,journal[4],journal[2])
        links=factory.link_bytes(builds['receiver'],builds['supervisor'],js,roots)
        profile=f.encode(model.clock.profile(builds['receiver'],js));gate['active']=True
        try:result=model.consume(builds['receiver'],builds['supervisor'],js,links,f.sha(links),profile,f.sha(profile))
        finally:gate['active']=False
        f.require(result['errors']==expected,'unexpected '+case+': '+str(result))
        cases[case]=dict(result=result,constructed_model=case!='normal',journal_manifest_sha256=js[3],clock_profile_sha256=f.sha(profile))
    f.require(not gate['opens'],'consumer opened paths')
    return dict(passed=True,cases=cases,consumer_filesystem_opens=0,**model.FALSE)


def replay(root,pin):
    root=a.canonical(root);_,_,digest=a.sealed(root);f.require(f.hex64(pin) and digest==pin,'external review pin differs')
    result=exercise(root/'bundle');f.require(f.encode(result)==a.read(root/'results.json'),'saved results differ');return result


def run(output):
    import audit_a23_pinned_view as old
    w=old.w;output=a.canonical(output);f.require(not output.exists(),'new collection-links review required')
    frozen=sources();parent=f.load(w.A/PARENT/'closeout.json');ref=parent['references']['review']
    source=Path(ref['directory']);_,_,digest=a.sealed(source);f.require(digest==ref['manifest_sha256'],'parent review differs')
    output.mkdir(mode=0o700)
    for name,digest in frozen.items():
        value=w.plain(w.b.REPO/name);f.require(f.sha(value)==digest,'source drift');a.put(output,'source/'+name,value)
    shutil.copytree(source/'bundle',output/'bundle');result=exercise(output/'bundle');a.put(output,'results.json',f.encode(result))
    f.require(sources()==frozen,'source drift after review')
    a.put(output,'audit.json',f.encode(dict(passed=True,source_count=434,prior_sources_unchanged=431,source_hashes=frozen,
          model_cases=len(CASES),semantic_rejections=sum(bool(v) for v in CASES.values()),consistent_subset_cases=sum(not v for v in CASES.values()),
          consumer_filesystem_opens=0,usb_requests=0,sd_accesses=0,real_sdk_objects=0,native_executions=0,formal_records=0,formal_reservations=0,**model.FALSE)))
    a.seal(output);return dict(passed=True,review_sha256=f.sha(a.read(output/'SHA256SUMS')),model_cases=len(CASES))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--output',type=Path);group.add_argument('--check',type=Path);parser.add_argument('--expected-sha256');args=parser.parse_args()
    if args.check and not args.expected_sha256:parser.error('--check requires --expected-sha256')
    try:result=run(args.output) if args.output else replay(args.check,args.expected_sha256)
    except (ValueError,OSError,KeyError,TypeError) as exc:print(json.dumps(dict(passed=False,error=str(exc))));raise SystemExit(2)
    print(json.dumps(result,indent=2))
