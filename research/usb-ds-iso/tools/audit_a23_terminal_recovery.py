"""Read-only cached local recovery classification; never starts a fixture."""
from pathlib import Path
import argparse,copy,json,shutil,sys
import a23_terminal_recovery_materials as model
import audit_a23_terminal_commit as previous
f,a=previous.f,previous.a
BASE=previous.BASE
PARENT='A23-terminal-commit-closeout-20261021'
PARENT_SUM='15abd9507a526ea449f75bb937cd99aab78bf1e88b35adf0c1fe76238456dce1'
SOURCE_REVIEW_SUM='b06a9e7477c76d40306b04e432d1e97e13f88ceb0e6471d2d206dd1b6127e417'
NEW=('tools/a23_terminal_recovery_materials.py','tools/audit_a23_terminal_recovery.py','tests/test_a23_terminal_recovery.py')
FALSE=previous.FALSE
seal,sealed,reference,cache=previous.seal,previous.sealed,previous.reference,previous.cache
CONTROLS=('absent','requester-absent','worker-commit-not-linked','worker-empty-use','opaque-frame-part')
MUTANTS=('use-missing','use-binding','empty-use-with-records','frame-job-coherent-rehash','frame-pid-coherent-rehash','exit-pid-bool','exit-nonce','exit-code-promoted','exit-exception','transport-errno','transport-delivery','transport-localwait','commit-job','commit-pid-bool','commit-wait','commit-record-hash','commit-path','commit-size-bool','commit-role','record-part-mismatch','record-part-missing','commit-part-missing','record-final-missing','final-commit-malformed')


def sources():
    import audit_a23_pinned_view as old
    w=old.w;root=w.A/PARENT;w.card.seal_verify(root);f.require(f.sha(w.plain(root/'SHA256SUMS'))==PARENT_SUM,'parent pin differs')
    saved=w.load(root/'closeout.json');out=previous.sources();f.require(out==saved['source_hashes'] and len(out)==551,'prior551 drift')
    for n in NEW:
        key=BASE+n;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/n))
    return dict(sorted(out.items()))


def args_at(directory):return [a.read(directory/'anchor.json'),f.sha(a.read(directory/'anchor.json')),cache(directory/'files')]
def semantic(r):return {k:v for k,v in r.items() if k!='fixture_job_id'}


def variant(name,args):
    raw,pin,files=copy.deepcopy(args)
    def store(suffix,data):files['worker-'+suffix]=files['worker-'+suffix+'.part']=data
    def rehash_commit():
        c=model.parse(files['worker-terminal-commit.json'])
        for key in c['records']:
            if key in files:c['records'][key]=dict(sha256=f.sha(files[key]),size=len(files[key]))
        store('terminal-commit.json',model.encode(c))
    def change(suffix,fn,rebind=False):
        v=model.parse(files['worker-'+suffix]);fn(v);store(suffix,model.encode(v))
        if rebind:rehash_commit()
    if name=='absent':files={}
    if name=='requester-absent':files={n:v for n,v in files.items() if not n.startswith('requester-')}
    if name=='worker-commit-not-linked':files.pop('worker-terminal-commit.json')
    if name=='worker-empty-use':files={n:v for n,v in files.items() if not n.startswith('worker-')};files['worker-terminal-use.json']=b''
    if name=='opaque-frame-part':files['worker-failed-status.bin.part']=b'opaque unfinished bytes'
    if name=='use-missing':files.pop('worker-terminal-use.json')
    if name=='use-binding':v=model.parse(files['worker-terminal-use.json']);v['launch_nonce']='0'*64;files['worker-terminal-use.json']=model.encode(v)
    if name=='empty-use-with-records':files['worker-terminal-use.json']=b''
    if name.startswith('frame-'):
        v=model.parse(files['worker-failed-status.bin'])
        if name=='frame-job-coherent-rehash':v['fixture_job_id']='00000000-0000-4000-8000-000000000001'
        if name=='frame-pid-coherent-rehash':v['worker_pid']+=1
        data=model.encode(v)+b'\n';store('failed-status.bin',data)
        change('transport.json',lambda x:x.update(failed_frame_sha256=f.sha(data),failed_frame_size=len(data)))
        rehash_commit()
    if name=='exit-pid-bool':change('exit.json',lambda v:v.update(actor_pid=True),True)
    if name=='exit-nonce':change('exit.json',lambda v:v.update(launch_nonce='0'*64),True)
    if name=='exit-code-promoted':change('exit.json',lambda v:v.update(reported_exit_code=0,exception_type=None),True)
    if name=='exit-exception':change('exit.json',lambda v:v.update(exception_type='BrokenPipeError'),True)
    if name=='transport-errno':change('transport.json',lambda v:v.update(errno=0),True)
    if name=='transport-delivery':change('transport.json',lambda v:v.update(delivery_confirmed=True),True)
    if name=='transport-localwait':change('transport.json',lambda v:v.update(creator_wait_observed=True),True)
    if name=='commit-job':change('terminal-commit.json',lambda v:v.update(fixture_job_id='00000000-0000-4000-8000-000000000001'))
    if name=='commit-pid-bool':change('terminal-commit.json',lambda v:v.update(actor_pid=True))
    if name=='commit-wait':change('terminal-commit.json',lambda v:v.update(process_wait_verified=True))
    if name=='commit-record-hash':change('terminal-commit.json',lambda v:v['records']['worker-exit.json'].update(sha256='0'*64))
    if name=='commit-path':change('terminal-commit.json',lambda v:v['records'].update({'../outside':v['records'].pop('worker-exit.json')}))
    if name=='commit-size-bool':change('terminal-commit.json',lambda v:v['records']['worker-exit.json'].update(size=True))
    if name=='commit-role':change('terminal-commit.json',lambda v:v.update(role='requester'))
    if name=='record-part-mismatch':files['worker-exit.json.part']+=b' '
    if name=='record-part-missing':files.pop('worker-exit.json.part')
    if name=='commit-part-missing':files.pop('worker-terminal-commit.json.part')
    if name=='record-final-missing':files.pop('worker-exit.json')
    if name=='final-commit-malformed':store('terminal-commit.json',b'{invalid')
    return [raw,pin,files]


def coherent_declared_pid_forgery(args):
    v=model.parse(args[0]);v['actors']={role:pid+100000 for role,pid in v['actors'].items()};raw=model.encode(v);files={}
    for role in model.ROLES:
        metadata=model.metadata(v,role);records={role+'-exit.json':model.terminal(v,role,0)}
        files[role+'-terminal-use.json']=model.encode(model.prior.publication.use_record(metadata))
        for name,data in {**records,role+'-terminal-commit.json':model.encode(model.prior.publication.commit_record(metadata,records))}.items():files[name]=files[name+'.part']=data
    return [raw,model.sha(raw),files]


def exercise(inputs,output):
    output.mkdir(mode=0o700);rows={};variants={}
    for case in previous.model.CASES:
        args=args_at(inputs/'jobs'/case);r=model.classify(*args);f.require(r['classification'] in ('incomplete','commit_associated'),'base disk snapshot conflicts '+case)
        rows[case]=semantic(r);a.put(output,'cases/'+case+'.json',f.encode(r))
    for name in (*CONTROLS,*MUTANTS):
        base='worker-frame-half' if name=='opaque-frame-part' else 'guardian-loss';r=model.classify(*variant(name,args_at(inputs/'jobs'/base)))
        expected='conflict' if name in MUTANTS else 'absent' if name=='absent' else 'incomplete'
        f.require(r['classification']==expected,'recovery variant differs '+name+': '+str(r));variants[name]=semantic(r);a.put(output,'variants/'+name+'.json',f.encode(r))
    counts={label:sum(r['classification']==label for r in (*rows.values(),*variants.values())) for label in ('absent','incomplete','commit_associated','conflict')}
    f.require(counts==dict(absent=1,incomplete=56,commit_associated=6,conflict=24),'recovery classification totals differ')
    return dict(passed=True,model_cases=87,disk_snapshots=58,controls=5,conflict_variants=24,semantic=rows,variants=variants,classification_counts=counts,
        new_fixture_processes=0,new_fixture_jobs=0,process_queries=0,fixture_execution=False,usb_requests=0,sd_accesses=0,real_sdk_objects=0,formal_records=0,formal_reservations=0,authorization_consumptions=0,permit_claim_invocations=0,**FALSE)


def verify(root,pin):
    root=a.canonical(root);_,_,digest=sealed(root);f.require(f.hex64(pin) and pin==digest,'external review pin differs')
    audit=f.load(root/'audit.json');r=f.load(root/'results.json');f.require(audit['source_count']==554 and audit['prior_sources_unchanged']==551 and len(audit['source_hashes'])==554,'recovery source inventory differs')
    for n,h in audit['source_hashes'].items():f.require(f.sha(a.read(root/'source'/n))==h,'frozen recovery source differs')
    f.require(set(r['semantic'])==set(previous.model.CASES) and set(r['variants'])==set(CONTROLS)|set(MUTANTS),'recovery cases differ')
    for case in previous.model.CASES:
        directory=root/'inputs/jobs'/case;args=args_at(directory);checked=model.classify(*args)
        f.require(set(args[2])<=model.ALLOWED and semantic(checked)==r['semantic'][case] and f.encode(checked)==a.read(root/'work/cases'/ (case+'.json')),'saved recovery verdict differs')
    for name in (*CONTROLS,*MUTANTS):
        case='worker-frame-half' if name=='opaque-frame-part' else 'guardian-loss';checked=model.classify(*variant(name,args_at(root/'inputs/jobs'/case)))
        f.require(semantic(checked)==r['variants'][name] and f.encode(checked)==a.read(root/'work/variants'/(name+'.json')),'saved recovery variant differs')
    f.require(all(r[k] is False for k in FALSE) and r['new_fixture_processes']==0 and r['process_queries']==0,'recovery grants authority or queries process');return r


def run(output):
    import audit_a23_pinned_view as old
    w=old.w;output=a.canonical(output);f.require(not output.exists(),'new recovery review required');frozen=sources();output.mkdir(mode=0o700)
    for n,h in frozen.items():
        raw=w.plain(w.b.REPO/n);f.require(f.sha(raw)==h,'recovery source drift');a.put(output,'source/'+n,raw)
    parent=f.load(w.A/PARENT/'closeout.json');review=Path(parent['references']['review']['directory']);baseline=previous.verify(review,SOURCE_REVIEW_SUM)
    provenance={}
    for case in previous.model.CASES:
        job=review/'work/cases'/case;launch=f.load(job/'launch.json');owner=f.load(job/'guardian-owner.json');terminal_pin=baseline['plan_pins'][case]
        f.require(owner['fixture_job_id']==launch['fixture_job_id'] and owner['launch_nonce']==launch['launch_nonce'] and owner['owned_plan_sha256']==f.sha(a.read(job/'owned-plan.json')),'anchor source declarations differ')
        actors={r:owner[r+'_pid'] for r in model.ROLES};raw=model.encode(model.anchor(launch,terminal_pin,f.sha(a.read(job/'failure-plan.json')),f.sha(a.read(job/'owned-plan.json')),actors))
        directory=output/'inputs/jobs'/case;a.put(directory,'anchor.json',raw)
        for name in model.ALLOWED:
            path=job/name
            if path.is_file():a.put(directory,'files/'+name,a.read(path))
        provenance[case]=dict(source_directory=str(job),anchor_sha256=f.sha(raw),source_selected_commit_valid=baseline['semantic'][case]['local_commit_file_valid'],source_selected_directory_sync_observed=baseline['semantic'][case]['commit_directory_sync_observed'],source_creator_waits=baseline['semantic'][case]['actors_waited_by_creator'])
    a.put(output,'inputs/provenance.json',f.encode(dict(source_review=parent['references']['review'],snapshot_declarations=provenance,historical_job_ids_and_nonces_preserved=True,witness_events_and_scenarios_excluded_from_classifier_inputs=True)))
    try:r=exercise(output/'inputs',output/'work')
    except Exception as exc:a.put(output,'failure.json',f.encode(dict(error=str(exc),source_hashes=frozen,scope='disk-byte-classifier-only')));seal(output);raise
    f.require(sources()==frozen,'recovery source drift after exercise');a.put(output,'results.json',f.encode(r));a.put(output,'audit.json',f.encode(dict(passed=True,source_count=554,prior_sources_unchanged=551,source_hashes=frozen)));seal(output)
    return dict(passed=True,review_sha256=f.sha(a.read(output/'SHA256SUMS')),model_cases=87,new_fixture_processes=0)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True);g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);p.add_argument('--expected-sha256');args=p.parse_args()
    if args.check and not args.expected_sha256:p.error('--check requires --expected-sha256')
    try:r=run(args.output) if args.output else verify(args.check,args.expected_sha256)
    except (ValueError,OSError,KeyError,TypeError) as exc:print(json.dumps(dict(passed=False,error=str(exc))));raise SystemExit(2)
    print(json.dumps(r if args.output else dict(passed=True,model_cases=r['model_cases'],process_execution=False),indent=2))
