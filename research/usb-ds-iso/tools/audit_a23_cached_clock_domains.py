"""Offline clock-domain profiles, timing boundaries and coherent file models."""
from pathlib import Path
import argparse,json,shutil,sys
import a23_cached_clock_domains as model
import audit_a23_cached_permit_context as previous

factory=previous.factory
view,ar,a,f=model.view,model.ar,model.a,model.f
PARENT='A23-permit-context-closeout-20261020'
PARENT_SUM='1e9164ee9ee19c0c3fb9bdc726998b31c06f176ba62e7d00f8e91fa072f5a0d0'
NEW=('tools/a23_cached_clock_domains.py','tools/audit_a23_cached_clock_domains.py','tests/test_a23_cached_clock_domains.py')
CASES={**{k:[] for k in ('normal','owner-clock-shift','schedule-normal','queued-delay','callback-limits','budget-limits','quiet-minimum')},
       **{k:['driver_timing'] for k in ('query-late','frame-old','enqueue-slow','trigger-late','iso-late','control-late',
          'budget-arithmetic','trigger-arithmetic','callback-after-log','after-before-callback','save-before-observation-end','sample-reversed','check-bool')},
       **{k:['quiet_timing'] for k in ('quiet-short','quiet-reversed','quiet-before-saved','quiet-after-event')},
       **{k:['clock_profile'] for k in ('profile-owner-as-driver','profile-mapping','profile-bool-ratio','profile-source','profile-authority')},
       'prior-receipt':['prior_subset']}

def sources():
    import audit_a23_pinned_view as old
    w=old.w;root=w.A/PARENT;w.card.seal_verify(root);f.require(f.sha(w.plain(root/'SHA256SUMS'))==PARENT_SUM,'parent pin differs')
    parent=w.load(root/'closeout.json');out=previous.sources();f.require(out==parent['source_hashes'] and len(out)==428,'prior428 drift')
    for name in NEW:
        key='research/usb-ds-iso/'+name;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/name))
    return dict(sorted(out.items()))

def schedule(base,**options):
    raw=dict(base);H=model.HOST
    def obj(name):return f.parse(raw[H+name])
    def put(name,value):raw[H+name]=f.encode(value)
    rows=[f.parse(v) for v in raw[H+'session.jsonl'].splitlines()]
    by={(r['event'],r['details'].get('epoch')):r for r in rows}
    start=by['before_intent',0]['ticks']
    for e in (0,1):
        m=obj('epoch-%d/metadata.json'%e)
        query=options.get('query',0);age=options.get('age',query+500);call=options.get('call',100);gap=options.get('gap',300)
        sample_begin=start+300;sample_end=sample_begin+query
        submit=sample_end+400;check=sample_begin+age;returned=check+call;trigger=returned+gap
        iso=submit+options.get('iso',max(800,trigger-submit+300));control=trigger+options.get('control',200)
        logged=max(iso,control,trigger+100)+options.get('queue_lag',0)
        times={'before_intent':start,'before':start+200,'iso_intent':sample_end+300,'iso_return':returned+100,
               'trigger_intent':returned+200,'trigger_return':trigger+100,'control_callback':logged+100,
               'iso_callback':logged+200,'after_intent':logged+300,'save_intent':logged+600,'saved':logged+700}
        for event,value in times.items():by[event,e]['ticks']=value
        m['sample'].update(begin_ticks=sample_begin,end_ticks=sample_end)
        m['before_observation'].update(begin_ticks=start+100,end_ticks=start+100)
        m['after_observation'].update(begin_ticks=logged+400,end_ticks=logged+400)
        m['budget'].update(check_ticks=check,return_ticks=returned,query_ns=query,age_ns=age,call_ns=call)
        m.update(submit_ticks=submit,trigger_ticks=trigger,iso_arrival_ticks=iso,control_arrival_ticks=control)
        by['trigger_return',e]['details'].update(gap_ns=gap,age_ns=trigger-sample_begin)
        put('epoch-%d/metadata.json'%e,m);start=times['saved']+200
    by['epochs_saved',None]['ticks']=start
    qstart=start+100;qend=qstart+options.get('quiet',250000101)
    by['observation_complete',None]['ticks']=qend+100
    by['observation_complete',None]['details'].update(quiet_start_ticks=qstart,quiet_end_ticks=qend)
    driver=obj('result.json');driver.update(quiet_start_ticks=qstart,quiet_end_ticks=qend)
    for name in ('result.json','entry-final/driver.json','sdk-receipt/snapshot.json'):put(name,driver)
    receipt=obj('sdk-receipt/receipt.json');receipt.update(snapshot=driver,snapshot_sha256=f.sha(raw[H+'sdk-receipt/snapshot.json']));put('sdk-receipt/receipt.json',receipt)
    for name in ('entry-current.json','entry-final/entry.json'):
        entry=obj(name);entry['driver']=driver;put(name,entry)
    entry_rows=[f.parse(v) for v in raw[H+'entry.jsonl'].splitlines()]
    entry_rows[-1]['ticks']=by['observation_complete',None]['ticks']+100
    raw[H+'entry.jsonl']=b''.join(f.encode(v) for v in entry_rows)
    raw[H+'session.jsonl']=b''.join(f.encode(v) for v in rows)
    return raw

def refresh(raw):
    H=model.HOST;rows=[f.parse(v) for v in raw[H+'session.jsonl'].splitlines()]
    by={(r['event'],r['details'].get('epoch')):r for r in rows}
    for e in (0,1):
        m=f.parse(raw[H+'epoch-%d/metadata.json'%e])
        by['iso_intent',e]['details']['sample']=m['sample'];by['iso_return',e]['details']['budget']=m['budget']
        by['control_callback',e]['details']['arrival_ticks']=m['control_arrival_ticks']
        by['saved',e]['details']['metadata_sha256']=f.sha(raw[H+'epoch-%d/metadata.json'%e])
    driver=f.parse(raw[H+'result.json']);quiet=by['observation_complete',None]['details']
    driver.update(quiet_start_ticks=quiet['quiet_start_ticks'],quiet_end_ticks=quiet['quiet_end_ticks'])
    for name in ('result.json','entry-final/driver.json','sdk-receipt/snapshot.json'):raw[H+name]=f.encode(driver)
    receipt=f.parse(raw[H+'sdk-receipt/receipt.json']);receipt.update(snapshot=driver,snapshot_sha256=f.sha(raw[H+'sdk-receipt/snapshot.json']));raw[H+'sdk-receipt/receipt.json']=f.encode(receipt)
    for name in ('entry-current.json','entry-final/entry.json'):
        row=f.parse(raw[H+name]);row['driver']=driver;raw[H+name]=f.encode(row)
    report=f.parse(raw[model.permit.INPUTS+'report.json']);report['entry']=f.parse(raw[H+'entry-current.json'])
    for name in (model.permit.INPUTS+'report.json',model.permit.ENV+'final/report.json'):raw[name]=f.encode(report)
    raw[H+'session.jsonl']=b''.join(f.encode(v) for v in rows)
    factory.epochs.rebuild_seals(raw)

def variant(base,case):
    if case=='normal':return dict(base)
    if case=='owner-clock-shift':return previous.previous.variant(base,'owner-clock-shift')
    if case=='prior-receipt':return previous.variant(base,'session-receipt')
    options={'queued-delay':dict(queue_lag=25000000),'callback-limits':dict(iso=2000000000,control=16000000),
             'budget-limits':dict(query=2000000,age=16000000,call=8000000,gap=8000000),
             'quiet-minimum':dict(quiet=250000000),'query-late':dict(query=2000001),'frame-old':dict(age=16000001),
             'enqueue-slow':dict(call=8000001),'trigger-late':dict(gap=8000001),'iso-late':dict(iso=2000000001),
             'control-late':dict(control=16000001),'quiet-short':dict(quiet=249999999),'quiet-reversed':dict(quiet=-1)}
    raw=schedule(base,**options.get(case,{}));H=model.HOST
    m=f.parse(raw[H+'epoch-0/metadata.json']);rows=[f.parse(v) for v in raw[H+'session.jsonl'].splitlines()]
    by={(r['event'],r['details'].get('epoch')):r for r in rows}
    if case=='budget-arithmetic':m['budget']['query_ns']+=1
    if case=='trigger-arithmetic':by['trigger_return',0]['details']['gap_ns']+=1
    if case=='callback-after-log':m['iso_arrival_ticks']=by['iso_callback',0]['ticks']+1
    if case=='after-before-callback':m['after_observation'].update(begin_ticks=m['trigger_ticks'],end_ticks=m['trigger_ticks'])
    if case=='save-before-observation-end':by['save_intent',0]['ticks']=m['after_observation']['end_ticks']-1
    if case=='sample-reversed':m['sample']['end_ticks']=m['sample']['begin_ticks']-1
    if case=='check-bool':m['budget']['check_ticks']=True
    if case=='quiet-before-saved':by['observation_complete',None]['details']['quiet_start_ticks']=by['epochs_saved',None]['ticks']-1
    if case=='quiet-after-event':by['observation_complete',None]['details']['quiet_end_ticks']=by['observation_complete',None]['ticks']+1
    raw[H+'epoch-0/metadata.json']=f.encode(m);raw[H+'session.jsonl']=b''.join(f.encode(v) for v in rows)
    refresh(raw);return raw

def exercise(bundle):
    builds,journal,roots=factory.load_bundle(bundle);base={n:journal[0].read(n) for n in journal[0].files}
    cases={};gate=dict(active=False,opens=[])
    def hook(event,args):
        if gate['active'] and event=='open':gate['opens'].append(str(args[0]));raise ValueError('consumer opened file')
    sys.addaudithook(hook)
    for case,expected in CASES.items():
        raw=variant(base,case);js=journal if case=='normal' else factory.journal_spec(raw,journal[4],journal[2])
        links=factory.link_bytes(builds['receiver'],builds['supervisor'],js,roots)
        profile=model.profile(builds['receiver'],js)
        if case=='profile-owner-as-driver':profile['domains'][model.DRIVER]=dict(profile['domains'][model.OWNER])
        if case=='profile-mapping':profile['cross_domain_mappings']=[dict(offset=0,verified=True)]
        if case=='profile-bool-ratio':profile['domains'][model.DRIVER]['numerator']=True
        if case=='profile-source':profile['source_hashes'][next(iter(profile['source_hashes']))]='0'*64
        if case=='profile-authority':profile['hardware_verified']=True
        encoded=f.encode(profile);gate['active']=True
        try:result=model.consume(builds['receiver'],builds['supervisor'],js,links,f.sha(links),encoded,f.sha(encoded))
        finally:gate['active']=False
        f.require(result['errors']==expected,'unexpected '+case+': '+str(result))
        cases[case]=dict(result=result,constructed_model=case!='normal',journal_manifest_sha256=js[3],clock_profile_sha256=f.sha(encoded))
    f.require(not gate['opens'],'consumer opened paths')
    return dict(passed=True,cases=cases,consumer_filesystem_opens=0,**model.FALSE)

def replay(root,pin):
    root=a.canonical(root);_,_,digest=a.sealed(root);f.require(f.hex64(pin) and digest==pin,'external review pin differs')
    result=exercise(root/'bundle');f.require(f.encode(result)==a.read(root/'results.json'),'saved results differ');return result

def run(output):
    import audit_a23_pinned_view as old
    w=old.w;output=a.canonical(output);f.require(not output.exists(),'new clock-domain review required')
    frozen=sources();parent=f.load(w.A/PARENT/'closeout.json');ref=parent['references']['review']
    source=Path(ref['directory']);_,_,digest=a.sealed(source);f.require(digest==ref['manifest_sha256'],'parent review differs')
    output.mkdir(mode=0o700)
    for name,digest in frozen.items():
        value=w.plain(w.b.REPO/name);f.require(f.sha(value)==digest,'source drift');a.put(output,'source/'+name,value)
    shutil.copytree(source/'bundle',output/'bundle');result=exercise(output/'bundle');a.put(output,'results.json',f.encode(result))
    f.require(sources()==frozen,'source drift after review')
    a.put(output,'audit.json',f.encode(dict(passed=True,source_count=431,prior_sources_unchanged=428,source_hashes=frozen,
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
