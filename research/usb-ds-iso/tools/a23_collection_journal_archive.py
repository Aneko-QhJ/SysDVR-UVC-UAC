"""Read-only partial journal inspection and separately sealed forensic copies."""
from pathlib import Path
import subprocess,sys
import a23_collection_journal as j
a=j.a;f=j.f;FALSE={**j.ar.old.FALSE,'retry_authorized':False,'worker_origin_authenticated':False}

def inspect(root,receiver,supervisor):
    root=a.canonical(root);files,dirs=a.snapshot(root,maximum=2048,total_limit=32*1024*1024);attempt=f.parse(files['attempt.json']);scope,ref=a.build_scope(receiver);supref=j.ar.old.sv.build_info(supervisor)
    expected={'schema','nonce','source','journal','receiver_build','supervisor_build','child_pid','control_delivery','model_only','production_execution_authorized'};f.require(type(attempt) is dict and set(attempt)==expected and attempt['schema']=='A23-collection-attempt-1' and f.hex64(attempt['nonce']),'journal attempt differs');f.require(files['SOURCE_ATTEMPT']==files['attempt.json'] and files['attempt.json']==f.encode(attempt),'source marker copy differs');f.require(f.encode(attempt['receiver_build'])==f.encode(ref) and f.encode(attempt['supervisor_build'])==f.encode(supref) and scope['receiver_sha256']==supref['binary_sha256'],'journal build differs');f.require(attempt['model_only'] is True and attempt['production_execution_authorized'] is False and type(attempt['child_pid']) is int and attempt['child_pid']>0 and attempt['control_delivery'] in ('none','whole_written','partial_or_failed'),'journal authority differs')
    for key in ('source','journal'):f.require(type(attempt[key]) is str and Path(attempt[key]).is_absolute() and '..' not in Path(attempt[key]).parts and Path(attempt[key]).is_relative_to('/private/tmp'),'journal logical path differs')
    events=sorted(n for n in files if n.startswith('events/'));f.require(len(events)<=len(j.PHASES) and events==['events/%02d.json'%i for i in range(len(events))],'journal events differ');previous=f.sha(files['attempt.json'])
    for i,name in enumerate(events):
        expected=dict(schema='A23-collection-event-1',index=i,phase=j.PHASES[i],attempt_sha256=f.sha(files['attempt.json']),previous_sha256=previous);f.require(files[name]==f.encode(expected),'journal event chain differs');previous=f.sha(files[name])
    top={'attempt.json','SOURCE_ATTEMPT',*events}|{n for n in ('failure.json','SHA256SUMS','COMMITTED') if n in files};f.require(set(files)==top|{n for n in files if n.startswith('envelope/')},'journal inventory differs');f.require(dirs==a.prefixes(files) or dirs==sorted(set(a.prefixes(files))|{n for n in dirs if n=='envelope' or n.startswith('envelope/')}),'journal directories differ')
    failure=None
    if 'failure.json' in files:
        failure=f.parse(files['failure.json']);f.require(type(failure) is dict and set(failure)=={'schema','after_event','error_type','reason','retry_authorized','cleanup_authorized'} and failure['schema']=='A23-collection-failure-1' and type(failure['after_event']) is int and failure['after_event']==len(events)-1 and type(failure['error_type']) is str and type(failure['reason']) is str and failure['retry_authorized'] is False and failure['cleanup_authorized'] is False,'journal failure differs')
    committed='COMMITTED' in files and 'SHA256SUMS' in files;inner=None
    if committed:
        a.sealed(root);f.require(len(events)==len(j.PHASES) and failure is None,'journal committed before completion');inner=j.ar.analyze(root/'envelope',receiver,supervisor)
    inner_sealed='envelope/COMMITTED' in files and 'envelope/SHA256SUMS' in files
    # A complete inner envelope never promotes an unfinished transaction.
    return dict(schema='A23-collection-journal-analysis-1',journal_committed=committed,classification='completed_model_collection' if committed else 'partial_model_collection',complete_injected_model_chain=bool(committed and inner['complete_injected_model_chain']),last_event=j.PHASES[len(events)-1] if events else None,events=len(events),failure_recorded=failure is not None,inner_envelope_sealed=inner_sealed,attempt_sha256=f.sha(files['attempt.json']),**FALSE)

def observe(worker,static_model):
    f.require(type(static_model) is bool and (static_model != (worker is not None)),'explicit static journal or owned worker required')
    if static_model:return dict(mode='supplied_static_journal',worker_exited=False,pid=None,returncode=None,job_sha256=None)
    f.require(isinstance(worker,subprocess.Popen) and type(worker.poll()) is int,'worker still running or unknown');f.require(type(worker.args) in (list,tuple) and len(worker.args)==4 and worker.args[0]==str(Path(sys.executable).resolve()) and worker.args[1]=='-B' and Path(worker.args[2]).name=='a23_collection_worker.py','file worker command differs')
    f.require(f.sha(a.read(a.canonical(Path(worker.args[2]))))==f.sha(a.read(Path(__file__).resolve().with_name('a23_collection_worker.py'))),'worker source differs');return dict(mode='observed_file_worker_exit',worker_exited=True,pid=worker.pid,returncode=worker.returncode,job_sha256=f.sha(a.read(a.canonical(Path(worker.args[3])))))

def job_matches(job,attempt):
    return type(job) is dict and job.get('schema')=='A23-collection-worker-job-1' and job.get('root')==attempt['source'] and job.get('journal')==attempt['journal'] and type(job.get('child_pid')) is int and job['child_pid']==attempt['child_pid'] and job.get('control_delivery')==attempt['control_delivery']

def freeze(journal,receiver,supervisor,output,*,worker=None,static_model=False):
    observation=observe(worker,static_model);journal=a.canonical(journal);receiver=a.canonical(receiver);supervisor=a.canonical(supervisor);output=a.canonical(output);f.require(not output.exists() and all(not output.is_relative_to(p) and not p.is_relative_to(output) for p in (journal,receiver,supervisor)),'new nonoverlapping forensic output required');before,dirs=a.snapshot(journal,maximum=2048,total_limit=32*1024*1024);result=inspect(journal,receiver,supervisor);raw_job=None
    if worker is not None:
        raw_job=a.read(a.canonical(Path(worker.args[3])));f.require(job_matches(f.parse(raw_job),f.parse(before['attempt.json'])),'worker job does not own journal')
    output.mkdir(mode=0o700);a.put(output,'FORENSIC_ATTEMPT',b'one read-only model journal copy\n')
    for name in dirs:(output/'journal'/name).mkdir(parents=True,exist_ok=True)
    for name,raw in before.items():a.put(output,'journal/'+name,raw)
    if raw_job is not None:a.put(output,'worker-job.json',raw_job)
    _,ref=a.build_scope(receiver);supref=j.ar.old.sv.build_info(supervisor);meta=dict(schema='A23-collection-forensic-1',receiver_build=ref,supervisor_build=supref,journal_files=a.inventory(before),journal_directories=dirs,observation=observation,**FALSE);a.put(output,'forensic.json',f.encode(meta));a.put(output,'analysis.json',f.encode(result));f.require(a.snapshot(journal,maximum=2048,total_limit=32*1024*1024)==(before,dirs),'journal changed during forensic copy');f.require(observe(worker,static_model)==observation,'worker exit changed');a.seal(output);return analyze(output,receiver,supervisor)

def analyze(root,receiver,supervisor):
    root=a.canonical(root);files,dirs,_=a.sealed(root);meta=f.parse(files['forensic.json']);scope,ref=a.build_scope(receiver);supref=j.ar.old.sv.build_info(supervisor);expected={'schema','receiver_build','supervisor_build','journal_files','journal_directories','observation',*FALSE};f.require(type(meta) is dict and set(meta)==expected and meta['schema']=='A23-collection-forensic-1' and all(meta[k] is False for k in FALSE),'forensic metadata/authority differs');f.require(f.encode(meta['receiver_build'])==f.encode(ref) and f.encode(meta['supervisor_build'])==f.encode(supref),'forensic build differs');raw={n[8:]:v for n,v in files.items() if n.startswith('journal/')};f.require(f.encode(a.inventory(raw))==f.encode(meta['journal_files']) and files['FORENSIC_ATTEMPT']==b'one read-only model journal copy\n','forensic raw inventory differs');f.require(set(files)=={'FORENSIC_ATTEMPT','forensic.json','analysis.json'}|{'journal/'+n for n in raw}|({'worker-job.json'} if 'worker-job.json' in files else set()),'forensic inventory differs');f.require(type(meta['journal_directories']) is list and meta['journal_directories']==sorted(set(meta['journal_directories'])) and dirs==sorted(set(a.prefixes(files))|{'journal/'+n for n in meta['journal_directories']}),'forensic directories differ')
    observation=meta['observation'];f.require(type(observation) is dict and set(observation)=={'mode','worker_exited','pid','returncode','job_sha256'},'forensic observation differs')
    if observation['mode']=='supplied_static_journal':f.require(f.encode(observation)==f.encode(dict(mode='supplied_static_journal',worker_exited=False,pid=None,returncode=None,job_sha256=None)),'static journal claims exit')
    else:f.require(observation['mode']=='observed_file_worker_exit' and observation['worker_exited'] is True and type(observation['pid']) is int and observation['pid']>0 and type(observation['returncode']) is int and -255<=observation['returncode']<=255 and f.hex64(observation['job_sha256']),'worker exit differs')
    if observation['mode']=='supplied_static_journal':f.require('worker-job.json' not in files,'static journal has worker job')
    else:
        f.require('worker-job.json' in files and f.sha(files['worker-job.json'])==observation['job_sha256'],'worker job bytes differ');job=f.parse(files['worker-job.json']);attempt=f.parse(files['journal/attempt.json']);f.require(job_matches(job,attempt),'worker job does not own journal')
    result=inspect(root/'journal',receiver,supervisor);f.require(files['analysis.json']==f.encode(result),'saved journal analysis differs');return dict(schema='A23-collection-forensic-analysis-1',archive_integrity_valid=True,observation=observation,analysis=result,**FALSE)
if __name__=='__main__':
    import argparse,json
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive',type=Path);p.add_argument('--receiver-build',type=Path,required=True);p.add_argument('--supervisor-build',type=Path,required=True);v=p.parse_args()
    try:r=analyze(v.archive,v.receiver_build,v.supervisor_build)
    except (ValueError,OSError,KeyError,TypeError) as e:print(json.dumps(dict(archive_integrity_valid=False,error=str(e))));raise SystemExit(2)
    print(json.dumps(r,indent=2))
