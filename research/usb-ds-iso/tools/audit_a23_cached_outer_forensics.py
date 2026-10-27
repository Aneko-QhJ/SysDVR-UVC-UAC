"""Offline full-manifest byte coverage and bootstrap declaration counterexamples."""
from pathlib import Path
from types import MappingProxyType
import argparse,json,shutil,sys
import a23_cached_outer_forensics as model
import audit_a23_cached_collection_links as previous

factory=previous.factory
view,ar,a,f=model.view,model.ar,model.a,model.f
PARENT='A23-collection-links-closeout-20261020'
PARENT_SUM='d43d35caa5b255718b59df7954eb715d7e6c2c2c77ced19d246cb3161a406efa'
ORIGIN='A23-window-review-20261019-r3/models/normal/first'
ORIGIN_SUM='e915949e41941b5bbb909468a8ac4148c93f25c9fa1cdac7c03abf40794f581c'
NEW=('tools/a23_cached_outer_forensics.py','tools/audit_a23_cached_outer_forensics.py',
     'tests/test_a23_cached_outer_forensics.py')
CASES={**{k:[] for k in ('normal','stat-inodes-shift','worker-pid-shift','static-bootstrap')},
       **{k:['outer_scope'] for k in ('scope-extra-manifest','scope-missing-manifest','scope-cache-pin',
          'scope-commit','scope-missing-file','scope-extra-file','scope-job-copy','scope-attempt','scope-authority','scope-size')},
       **{k:['capture_shape'] for k in ('capture-schema','capture-authority','capture-receiver',
          'capture-supervisor','capture-extra','capture-duplicate')},
       **{k:['capture_inventory'] for k in ('inventory-hash','inventory-size-bool','inventory-omission',
          'directories-duplicate','directories-cache-empty','directories-traversal')},
       **{k:['capture_identities'] for k in ('stat-bool','stat-short','stat-mode','stat-marker-size',
          'stat-unstable','stat-skipped','stat-alias','stat-time-bool')},
       **{k:['worker_observation'] for k in ('worker-job-pin','worker-pid-bool','worker-exit-bool',
          'worker-nonzero','worker-static-exit','worker-mode','worker-pid-zero')},
       **{k:['saved_summary'] for k in ('summary-events','summary-full-claim','summary-attempt',
          'summary-authority','summary-errors')},'prior-receipt':['prior_subset']}


def sources():
    import audit_a23_pinned_view as old
    w=old.w;root=w.A/PARENT;w.card.seal_verify(root)
    f.require(f.sha(w.plain(root/'SHA256SUMS'))==PARENT_SUM,'parent pin differs')
    parent=w.load(root/'closeout.json');out=previous.sources()
    f.require(out==parent['source_hashes'] and len(out)==434,'prior434 drift')
    for name in NEW:
        key='research/usb-ds-iso/'+name;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/name))
    return dict(sorted(out.items()))


def load_bundle(bundle):
    builds,journal,roots=factory.load_bundle(bundle)
    raw,_=a.snapshot(bundle/'outer/data');expected=f.load(bundle/'outer/contract.json')
    cache=view.PinnedBytes(MappingProxyType(dict(raw)),f.sha(f.encode(expected)))
    outer=(cache,expected,a.read(bundle/'outer/origin-COMMITTED'))
    return builds,journal,roots,outer


def variant(base,outer,case):
    raw=dict(base);out=dict(outer);cap=f.parse(out['capture.json']);o=cap['observation']
    if case=='prior-receipt':raw=previous.variant(base,'prior-receipt')
    if case=='stat-inodes-shift':
        for v in cap['capture'].values():v['identity'][1]+=10000
    if case=='worker-pid-shift':o['pid']+=100
    if case=='static-bootstrap':o.update(mode='supplied_static_bootstrap',worker_exited=False,pid=None,returncode=None)
    if case=='capture-schema':cap['schema']='unknown'
    if case=='capture-authority':cap['worker_origin_authenticated']=True
    if case=='capture-receiver':cap['receiver_build']['descriptor_sha256']='0'*64
    if case=='capture-supervisor':cap['supervisor_build']['binary_sha256']='0'*64
    if case=='capture-extra':cap['runtime_authenticated']=True
    first=next(iter(cap['raw_files']))
    if case=='inventory-hash':cap['raw_files'][first]['sha256']='0'*64
    if case=='inventory-size-bool':cap['raw_files'][first]['bytes']=True
    if case=='inventory-omission':del cap['raw_files'][first]
    if case=='directories-duplicate':cap['raw_directories'].append(cap['raw_directories'][0])
    if case=='directories-cache-empty':cap['raw_directories'].remove(model.SCRATCH);cap['raw_directories'].append('empty');cap['raw_directories'].sort()
    if case=='directories-traversal':cap['raw_directories'][0]='../outside'
    marker=cap['capture']['marker']
    if case=='stat-bool':marker['identity'][1]=True
    if case=='stat-short':marker['identity'].pop()
    if case=='stat-mode':marker['identity'][2]=16877
    if case=='stat-marker-size':marker['identity'][3]+=1
    if case=='stat-unstable':marker['stable']=False
    if case=='stat-skipped':marker['skipped']=[dict(path='hidden',reason='skipped')]
    if case=='stat-alias':cap['capture']['journal']['identity'][:2]=cap['capture']['source']['identity'][:2]
    if case=='stat-time-bool':marker['identity'][4]=True
    if case=='worker-job-pin':o['job_sha256']='0'*64
    if case=='worker-pid-bool':o['pid']=True
    if case=='worker-exit-bool':o['worker_exited']=1
    if case=='worker-nonzero':o['returncode']=7
    if case=='worker-static-exit':o['mode']='supplied_static_bootstrap'
    if case=='worker-mode':o['mode']='observed_model_child_exit'
    if case=='worker-pid-zero':o['pid']=0
    out['capture.json']=f.encode(cap)
    if case=='capture-duplicate':out['capture.json']=out['capture.json'][:-2]+b',"schema":"A23-bootstrap-capture-1"}\n'
    if case=='scope-size':out['capture.json']=b' '*65537
    saved=f.parse(out['analysis.json'])
    if case=='summary-events':saved['journal_inspection']['events']=6
    if case=='summary-full-claim':saved['complete_injected_model_chain']=False
    if case=='summary-attempt':saved['journal_inspection']['attempt_sha256']='0'*64
    if case=='summary-authority':saved['journal_inspection']['worker_origin_authenticated']=True
    if case=='summary-errors':saved['errors']=['incomplete']
    if case.startswith('summary-'):out['analysis.json']=f.encode(saved)
    if case=='scope-job-copy':out['job.json']+=b' '
    if case=='scope-attempt':out['FORENSIC_ATTEMPT']=b'two bootstrap copies\n'
    if case=='scope-missing-file':out.pop('analysis.json')
    if case=='scope-extra-file':out['unexpected']=b'not declared'
    return raw,out


def exercise(bundle):
    builds,journal,roots,outer=load_bundle(bundle)
    base={n:journal[0].read(n) for n in journal[0].files};obase={n:outer[0].read(n) for n in outer[0].files}
    cases={};gate=dict(active=False,opens=[])
    def hook(event,args):
        if gate['active'] and event=='open':gate['opens'].append(str(args[0]));raise ValueError('consumer opened file')
    sys.addaudithook(hook)
    for case,expected in CASES.items():
        raw,out=variant(base,obase,case)
        allfiles={**out,**{'raw/'+n:v for n,v in raw.items()}}
        if case=='scope-extra-manifest':allfiles['unexpected']=b'not copied'
        if case=='scope-missing-manifest':del allfiles['analysis.json']
        manifest=a.sums(allfiles)
        js=factory.journal_spec(raw,journal[4],manifest)
        if case=='normal':f.require(js[2]==journal[2],'normal historical manifest differs')
        contract=model.contract(out,js)
        if case=='scope-authority':contract['worker_origin_authenticated']=True
        cache=view.PinnedBytes(MappingProxyType(dict(out)),'0'*64 if case=='scope-cache-pin' else f.sha(f.encode(contract)))
        commit=b'0'*64+b'\n' if case=='scope-commit' else (js[3]+'\n').encode()
        spec=(cache,contract,commit)
        links=factory.link_bytes(builds['receiver'],builds['supervisor'],js,roots)
        profile=f.encode(model.collection.clock.profile(builds['receiver'],js));gate['active']=True
        try:result=model.consume(builds['receiver'],builds['supervisor'],js,links,f.sha(links),profile,f.sha(profile),spec)
        finally:gate['active']=False
        f.require(result['errors']==expected,'unexpected '+case+': '+str(result))
        cases[case]=dict(result=result,constructed_model=case!='normal',journal_manifest_sha256=js[3],
                         outer_contract_sha256=f.sha(f.encode(contract)))
    f.require(not gate['opens'],'consumer opened paths')
    return dict(passed=True,cases=cases,consumer_filesystem_opens=0,**model.FALSE)


def replay(root,pin):
    root=a.canonical(root);_,_,digest=a.sealed(root);f.require(f.hex64(pin) and digest==pin,'external review pin differs')
    result=exercise(root/'bundle');f.require(f.encode(result)==a.read(root/'results.json'),'saved results differ');return result


def run(output):
    import audit_a23_pinned_view as old
    w=old.w;output=a.canonical(output);f.require(not output.exists(),'new outer-forensics review required')
    frozen=sources();parent=f.load(w.A/PARENT/'closeout.json');ref=parent['references']['review']
    source=Path(ref['directory']);_,_,digest=a.sealed(source);f.require(digest==ref['manifest_sha256'],'parent review differs')
    origin=w.A/ORIGIN;files,_,digest=a.sealed(origin);f.require(digest==ORIGIN_SUM,'historical origin differs')
    manifest=a.read(source/'bundle/journal/origin-SHA256SUMS')
    f.require(a.read(origin/'SHA256SUMS')==manifest,'historical origin manifest differs')
    output.mkdir(mode=0o700)
    for name,digest in frozen.items():
        value=w.plain(w.b.REPO/name);f.require(f.sha(value)==digest,'source drift');a.put(output,'source/'+name,value)
    bundle=output/'bundle';shutil.copytree(source/'bundle',bundle)
    _,journal,_=factory.load_bundle(bundle);raw={n:files[n] for n in model.NAMES}
    for name,value in raw.items():a.put(bundle,'outer/data/'+name,value)
    a.put(bundle,'outer/contract.json',f.encode(model.contract(raw,journal)))
    a.put(bundle,'outer/origin-COMMITTED',a.read(origin/'COMMITTED'))
    a.put(bundle,'outer/origin-reference.json',f.encode(w.reference(origin)))
    result=exercise(bundle);a.put(output,'results.json',f.encode(result))
    f.require(sources()==frozen,'source drift after review')
    a.put(output,'audit.json',f.encode(dict(passed=True,source_count=437,prior_sources_unchanged=434,source_hashes=frozen,
          model_cases=len(CASES),semantic_rejections=sum(bool(v) for v in CASES.values()),consistent_subset_cases=sum(not v for v in CASES.values()),
          historical_origin_manifest_sha256=ORIGIN_SUM,complete_manifest_members=96,raw_files=92,outer_files=4,
          consumer_filesystem_opens=0,usb_requests=0,sd_accesses=0,real_sdk_objects=0,native_executions=0,formal_records=0,formal_reservations=0,**model.FALSE)))
    a.seal(output);return dict(passed=True,review_sha256=f.sha(a.read(output/'SHA256SUMS')),model_cases=len(CASES))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--output',type=Path);group.add_argument('--check',type=Path);parser.add_argument('--expected-sha256');args=parser.parse_args()
    if args.check and not args.expected_sha256:parser.error('--check requires --expected-sha256')
    try:result=run(args.output) if args.output else replay(args.check,args.expected_sha256)
    except (ValueError,OSError,KeyError,TypeError) as exc:print(json.dumps(dict(passed=False,error=str(exc))));raise SystemExit(2)
    print(json.dumps(result,indent=2))
