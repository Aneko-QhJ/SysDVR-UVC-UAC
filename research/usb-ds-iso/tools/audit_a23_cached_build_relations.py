"""Offline structural build-link subset, with rehashed semantic counterexamples."""
from pathlib import Path
from types import MappingProxyType
import argparse
import json
import shutil
import sys
import a23_cached_build_relations as model
import audit_a23_cached_journal_epochs as epochs

grouped = model.grouped
view, ar, a, f = model.view, model.ar, model.a, model.f
PARENT = 'A23-grouped-build-closeout-20261020'
PARENT_SUM = '6e21a24320a2660a4db875ab219e615efc3d30847300ea497bcb142d0037d961'
NEW = ('tools/a23_cached_build_relations.py', 'tools/audit_a23_cached_build_relations.py',
       'tests/test_a23_cached_build_relations.py')
CASES = {'normal': [], **{k:['receiver'] for k in (
    'receiver-source', 'receiver-table', 'receiver-header', 'receiver-binary',
    'receiver-extra', 'descriptor-extra', 'descriptor-duplicate', 'descriptor-authority',
    'descriptor-path', 'descriptor-digest-bool', 'baseline-manifest', 'baseline-inventory')},
    **{k:['supervisor'] for k in ('supervisor-source','supervisor-binary','supervisor-authority','supervisor-extra')},
    **{k:['role_pair'] for k in ('source-pair','binary-pair')},
    **{k:['build_links'] for k in ('worker-root','marker-count','envelope-reference','final-reference',
                                  'handoff-reference','namespace-scope','entry-binding','final-entry-binding','binding-range-bool')},
    'marker-bool-count':['journal_subset']}


def sources():
    import audit_a23_grouped_build_bytes as previous
    import audit_a23_pinned_view as old
    w = old.w; root = w.A/PARENT
    w.card.seal_verify(root)
    f.require(f.sha(w.plain(root/'SHA256SUMS')) == PARENT_SUM, 'parent pin differs')
    parent = w.load(root/'closeout.json'); out = previous.sources()
    f.require(out == parent['source_hashes'] and len(out) == 419, 'prior419 drift')
    for name in NEW:
        key = 'research/usb-ds-iso/'+name
        f.require(key not in out, 'source overlap')
        out[key] = f.sha(w.plain(w.ROOT/name))
    return dict(sorted(out.items()))


def spec(raw):
    manifest = a.sums(raw); digest = f.sha(manifest)
    catalog, groups = grouped.prepare(raw, manifest, digest)
    caches = tuple(view.PinnedBytes(MappingProxyType(dict(g)), f.sha(f.encode(c)))
                   for g,c in zip(groups,catalog['groups']))
    return (caches, catalog, f.sha(f.encode(catalog)), manifest, digest)


def journal_spec(raw, worker, origin_manifest):
    entries = model.prior.partial.manifest_entries(origin_manifest, f.sha(origin_manifest))
    entries = {n:h for n,h in entries.items() if not n.startswith('raw/')}
    entries.update({'raw/'+n:f.sha(value) for n,value in raw.items()})
    entries['job.json'] = f.sha(worker)
    manifest = ''.join(h+'  '+n+'\n' for n,h in sorted(entries.items())).encode()
    contract = ar.contract(dict(schema='A23-pinned-byte-contract-1',
               source_manifest_sha256=f.sha(manifest), source_prefix='raw/',
               files=a.inventory(raw), directories=sorted(set(a.prefixes(raw))|{'empty'}), **ar.FALSE))
    return (view.PinnedBytes(MappingProxyType(dict(raw)),f.sha(f.encode(contract))),
            contract, manifest, f.sha(manifest), worker)


def link_bytes(receiver, supervisor, journal, roots):
    return f.encode(dict(schema='A23-cached-build-links-1',
              builds={role:dict(logical_root=roots[role],manifest_sha256=build[4],catalog_sha256=build[2])
                      for role,build in (('receiver',receiver),('supervisor',supervisor))},
              journal_manifest_sha256=journal[3], **model.FALSE))


def variant(rbase, sbase, jbase, worker, case):
    r,s,j = dict(rbase),dict(sbase),dict(jbase)
    d=f.parse(r['descriptor.json']); sb=f.parse(s['build.json'])
    source=next(iter(d['source_hashes'])); ssource=next(iter(sb['source_hashes']))
    refresh=False
    def change(name, action):
        value=f.parse(j[name]);action(value);j[name]=f.encode(value)
    if case=='receiver-source':r['source/'+source]+=b'changed'
    if case=='receiver-table':d['source_hashes'][source]='0'*64;refresh=True
    if case=='receiver-header':r['a23_verified_binding.h']+=b'changed'
    if case=='receiver-binary':r['verified-entry']+=b'changed'
    if case=='receiver-extra':r['unexpected']=b''
    if case=='descriptor-extra':d['unexpected']=0;refresh=True
    if case=='descriptor-authority':d['description']['hardware_entry_enabled']=True;refresh=True
    if case=='descriptor-path':d['source_hashes']['../escape']=d['source_hashes'].pop(source);refresh=True
    if case=='descriptor-digest-bool':d['workflow_source_sha256']=True;refresh=True
    if case=='baseline-manifest':d['baseline_manifest_sha256']='0'*64;refresh=True
    if case=='baseline-inventory':d['baseline_inventory_sha256']='0'*64;refresh=True
    if refresh:
        r['descriptor.json']=f.encode(d)
        r['a23_verified_binding.h']=b'static const unsigned char A23VerifiedDescriptor[]={'+b','.join(str(n).encode() for n in r['descriptor.json'])+b'};\n'
        binary=f.parse(r['binary.json']);binary['descriptor_sha256']=f.sha(r['descriptor.json']);r['binary.json']=f.encode(binary)
    if case=='descriptor-duplicate':r['descriptor.json']=r['descriptor.json'][:-2]+b',"schema":"A23-verified-entry-descriptor-1"}\n'
    if case=='supervisor-source':s['source/'+ssource]+=b'changed'
    if case=='supervisor-binary':s['model-child']+=b'changed'
    if case=='supervisor-authority':sb['model_only']=False;s['build.json']=f.encode(sb)
    if case=='supervisor-extra':s['unexpected']=b''
    if case=='source-pair':
        s['source/'+ssource]+=b'changed';sb['source_hashes'][ssource]=f.sha(s['source/'+ssource]);s['build.json']=f.encode(sb)
    if case=='binary-pair':
        s['model-child']+=b'changed';sb['binary_sha256']=f.sha(s['model-child']);s['build.json']=f.encode(sb)
    if case=='worker-root':
        value=f.parse(worker);value['receiver']='/private/tmp/wrong-build';worker=f.encode(value)
    if case in ('marker-count','marker-bool-count'):
        def counts(value):
            value['receiver_build']['frozen_source_count']=True if case=='marker-bool-count' else 393
            value['supervisor_build']['source_count']=True if case=='marker-bool-count' else 393
        change('source-marker',counts)
        j['journal/attempt.json']=j['journal/SOURCE_ATTEMPT']=j['source-marker']
        previous=f.sha(j['source-marker'])
        for i in range(7):
            name='journal/events/%02d.json'%i;event=f.parse(j[name]);event.update(attempt_sha256=f.sha(j['source-marker']),previous_sha256=previous);j[name]=f.encode(event);previous=f.sha(j[name])
    if case=='envelope-reference':change('journal/envelope/envelope.json',lambda v:v['receiver_build'].update(receiver_sha256='0'*64))
    if case=='final-reference':change('journal/envelope/final/collection.json',lambda v:v['build_reference'].update(receiver_sha256='0'*64))
    if case=='handoff-reference':
        for name in ('handoff.json','handoff-original.json'):
            change('journal/envelope/supervision/'+name,lambda v:v['build'].update(binary_sha256='0'*64))
    if case=='namespace-scope':change(model.prior.INPUTS+'namespace/scope.json',lambda v:v.update(workflow_source_sha256='0'*64))
    if case=='entry-binding':change(model.prior.INPUTS+'config.json',lambda v:v['binding'].update(build_manifest_sha256='0'*64))
    if case=='final-entry-binding':change(model.prior.HOST+'entry-final/entry.json',lambda v:v['binding'].update(build_manifest_sha256='0'*64))
    if case=='binding-range-bool':change(model.prior.INPUTS+'config.json',lambda v:v['binding'].update(first_sequence=True))
    if case!='normal':epochs.rebuild_seals(j)
    return r,s,j,worker


def load_bundle(bundle):
    builds={}
    for role in ('receiver','supervisor'):
        folder=bundle/'builds'/role;catalog=f.load(folder/'catalog.json');manifest=a.read(folder/'origin-SHA256SUMS')
        caches=tuple(view.PinnedBytes.load(folder/'views'/('%02d'%i),c) for i,c in enumerate(catalog['groups']))
        builds[role]=(caches,catalog,f.sha(f.encode(catalog)),manifest,f.sha(manifest))
    jfolder=bundle/'journal';contract=f.load(jfolder/'contract.json')
    journal=(view.PinnedBytes.load(jfolder/'view',contract),contract,a.read(jfolder/'origin-SHA256SUMS'),
             contract['source_manifest_sha256'],a.read(jfolder/'worker-job.json'))
    return builds,journal,f.load(bundle/'logical-roots.json')


def exercise(bundle):
    builds,journal,roots=load_bundle(bundle)
    rbase,_=a.snapshot(bundle/'builds/receiver/original');sbase,_=a.snapshot(bundle/'builds/supervisor/original')
    jbase={n:journal[0].read(n) for n in journal[0].files};worker=journal[4]
    rows={};gate=dict(active=False,opens=[])
    def hook(event,args):
        if gate['active'] and event=='open':gate['opens'].append(str(args[0]));raise ValueError('consumer opened files')
    sys.addaudithook(hook)
    for case,expected_errors in CASES.items():
        r,s,j,job=variant(rbase,sbase,jbase,worker,case)
        if case=='normal':rs,ss,js=builds['receiver'],builds['supervisor'],journal
        else:rs,ss,js=spec(r),spec(s),journal_spec(j,job,journal[2])
        links=link_bytes(rs,ss,js,roots)
        gate['active']=True
        try:result=model.consume(rs,ss,js,links,f.sha(links))
        finally:gate['active']=False
        f.require(result['errors']==expected_errors,'unexpected case '+case+': '+str(result))
        rows[case]=dict(result=result,constructed_model=case!='normal',
                        receiver_manifest_sha256=rs[4],supervisor_manifest_sha256=ss[4],
                        journal_manifest_sha256=js[3],link_sha256=f.sha(links))
    f.require(not gate['opens'],'consumer opened files')
    return dict(passed=True,cases=rows,consumer_filesystem_opens=0, **model.FALSE)


def replay(root,pin):
    root=a.canonical(root);_,_,digest=a.sealed(root)
    f.require(f.hex64(pin) and digest==pin,'external review pin differs')
    result=exercise(root/'bundle')
    f.require(f.encode(result)==a.read(root/'results.json'),'saved result differs')
    return result


def run(output):
    import audit_a23_pinned_view as old
    w=old.w;output=a.canonical(output);f.require(not output.exists(),'new review required')
    frozen=sources();parent=f.load(w.A/PARENT/'closeout.json');ref=parent['references']['review']
    base=Path(ref['directory']);_,_,digest=a.sealed(base);f.require(digest==ref['manifest_sha256'],'grouped review differs')
    raw_review=w.A/'A23-cached-epochs-review-20261019-r2';a.sealed(raw_review)
    output.mkdir(mode=0o700)
    for name,digest in frozen.items():
        value=w.plain(w.b.REPO/name);f.require(f.sha(value)==digest,'source drift');a.put(output,'source/'+name,value)
    bundle=output/'bundle';shutil.copytree(base/'builds',bundle/'builds')
    prior_catalog=f.load(raw_review/'scope-catalog.json')
    roots={role:prior_catalog['external_builds'][role]['reference']['directory'] for role in ('receiver','supervisor')}
    a.put(bundle,'logical-roots.json',f.encode(roots))
    jraw,_=a.snapshot(raw_review/'bundle/selection')
    worker=a.read(raw_review/'bundle/worker-job.json');manifest=a.read(raw_review/'bundle/origin-SHA256SUMS')
    js=journal_spec(jraw,worker,manifest)
    f.require(js[2]==manifest,'normal origin manifest drift')
    import tempfile
    with tempfile.TemporaryDirectory(prefix='a23-build-links-',dir='/private/tmp') as scratch:
        scratch=Path(scratch);source=scratch/'source';source.mkdir()
        for name,value in jraw.items():a.put(source,name,value)
        (source/'empty').mkdir()
        view.materialize(source,js[1],scratch/'view')
        shutil.copytree(scratch/'view',bundle/'journal/view')
    a.put(bundle,'journal/contract.json',f.encode(js[1]));a.put(bundle,'journal/origin-SHA256SUMS',manifest)
    a.put(bundle,'journal/worker-job.json',worker)
    result=exercise(bundle);a.put(output,'results.json',f.encode(result))
    f.require(sources()==frozen,'source drift after review')
    a.put(output,'audit.json',f.encode(dict(passed=True,source_count=422,prior_sources_unchanged=419,
          source_hashes=frozen,model_cases=len(CASES),semantic_rejections=len(CASES)-1,
          consumer_filesystem_opens=0,usb_requests=0,sd_accesses=0,real_sdk_objects=0,
          formal_records=0,formal_reservations=0,native_executions=0, **model.FALSE)))
    a.seal(output);return dict(passed=True,review_sha256=f.sha(a.read(output/'SHA256SUMS')),model_cases=len(CASES))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--output',type=Path);group.add_argument('--check',type=Path)
    parser.add_argument('--expected-sha256');args=parser.parse_args()
    if args.check and not args.expected_sha256:parser.error('--check requires --expected-sha256')
    try:result=run(args.output) if args.output else replay(args.check,args.expected_sha256)
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print(json.dumps(dict(passed=False,error=str(exc))));raise SystemExit(2)
    print(json.dumps(result,indent=2))
