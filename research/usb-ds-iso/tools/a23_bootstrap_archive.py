"""Read-only bootstrap evidence, including absent or malformed legacy journals."""
from pathlib import Path
import a23_collection_journal_archive as old
a=old.a;f=a.f
FALSE={**old.FALSE,'bootstrap_repair_authorized':False}

def derive(root,meta,job,receiver,supervisor):
    scope,ref=a.build_scope(receiver);supref=old.j.ar.old.sv.build_info(supervisor);capture=meta['capture'];raw,dirs=a.snapshot(root/'raw');errors=[];marker=None;inner=None
    def error(ok,why):
        if not ok:errors.append(why)
    stable=all(capture[k]['stable'] for k in ('source','marker','journal'));safe=not capture['journal']['skipped'] and capture['marker']['state']!='blocked' and capture['journal']['state']!='blocked'
    error(stable,'capture changed during read');error(safe,'some evidence could not be captured safely')
    if capture['marker']['state']=='regular':
        try:
            marker=f.parse(raw['source-marker']);expected={'schema','nonce','source','journal','receiver_build','supervisor_build','child_pid','control_delivery','model_only','production_execution_authorized'};f.require(type(marker) is dict and set(marker)==expected and marker['schema']=='A23-collection-attempt-1' and f.hex64(marker['nonce']),'invalid source attempt');f.require(marker['model_only'] is True and marker['production_execution_authorized'] is False and f.encode(marker['receiver_build'])==f.encode(ref) and f.encode(marker['supervisor_build'])==f.encode(supref),'source attempt scope differs');f.require(type(marker['child_pid']) is int and marker['child_pid']>0 and old.job_matches(job,marker),'source attempt does not bind declared job')
        except (ValueError,KeyError,TypeError):marker=None;errors.append('source attempt malformed or unbound')
    else:errors.append('source attempt absent or unreadable')
    if capture['journal']['state']!='directory':errors.append('journal not established')
    elif stable and safe and marker is not None:
        try:
            f.require(raw.get('journal/attempt.json')==raw['source-marker'] and raw.get('journal/SOURCE_ATTEMPT')==raw['source-marker'],'bootstrap copies differ');inner=old.inspect(root/'raw/journal',receiver,supervisor)
        except (ValueError,OSError,KeyError,TypeError):errors.append('journal bootstrap incomplete or inconsistent')
    committed=bool(not errors and inner and inner['journal_committed']);classification='completed_model_collection' if committed else 'incomplete_bootstrap_evidence'
    return dict(schema='A23-bootstrap-analysis-1',classification=classification,capture_stable=stable,capture_safe=safe,source_attempt_valid=marker is not None,journal_committed=committed,complete_injected_model_chain=bool(committed and inner['complete_injected_model_chain']),journal_inspection=inner,errors=errors,**FALSE)

def analyze(root,receiver,supervisor):
    root=a.canonical(root);files,dirs,_=a.sealed(root);meta=f.parse(files['capture.json']);job=f.parse(files['job.json']);_,ref=a.build_scope(receiver);supref=old.j.ar.old.sv.build_info(supervisor)
    expected={'schema','receiver_build','supervisor_build','capture','raw_files','raw_directories','observation',*FALSE};f.require(type(meta) is dict and set(meta)==expected and meta['schema']=='A23-bootstrap-capture-1' and all(meta[k] is False for k in FALSE),'bootstrap metadata/authority differs');f.require(f.encode(meta['receiver_build'])==f.encode(ref) and f.encode(meta['supervisor_build'])==f.encode(supref),'bootstrap build differs');f.require(type(job) is dict and job.get('schema')=='A23-collection-worker-job-1' and type(job.get('child_pid')) is int and job['child_pid']>0 and job.get('control_delivery') in ('none','whole_written','partial_or_failed'),'bootstrap job differs')
    for name in ('root','journal'):
        p=Path(job[name]);f.require(type(job[name]) is str and p.is_absolute() and p.is_relative_to('/private/tmp') and '..' not in p.parts,'bootstrap logical root differs')
    raw={n[4:]:v for n,v in files.items() if n.startswith('raw/')};f.require(files['FORENSIC_ATTEMPT']==b'one bootstrap forensic copy\n' and set(files)=={'FORENSIC_ATTEMPT','capture.json','job.json','analysis.json'}|{'raw/'+n for n in raw},'bootstrap inventory differs');f.require(f.encode(a.inventory(raw))==f.encode(meta['raw_files']),'bootstrap raw inventory differs');f.require(type(meta['raw_directories']) is list and dirs==sorted(set(a.prefixes(files))|{'raw'}|{'raw/'+n for n in meta['raw_directories']}),'bootstrap directories differ')
    c=meta['capture'];f.require(type(c) is dict and set(c)=={'source','marker','journal'},'capture component inventory differs')
    for name,part in c.items():
        f.require(type(part) is dict and set(part)=={'state','stable','identity','skipped'} and type(part['stable']) is bool and type(part['skipped']) is list,'capture component differs');f.require(part['state'] in ('directory','regular','absent','blocked') and (part['identity'] is None or type(part['identity']) is list and len(part['identity'])==6 and all(type(v) is int for v in part['identity'])),'capture identity differs')
        for item in part['skipped']:f.require(type(item) is dict and set(item)=={'path','reason'} and type(item['path']) is str and type(item['reason']) is str,'skipped metadata differs')
    f.require(c['source']['state']=='directory' and c['source']['skipped']==[] and c['marker']['skipped']==[] and (c['marker']['state']=='regular')==('source-marker' in raw),'capture marker differs');f.require(all(n=='source-marker' or n.startswith('journal/') for n in raw) and (c['journal']['state']=='directory' or not any(n.startswith('journal/') for n in raw)),'capture journal raw differs')
    observation=meta['observation'];f.require(type(observation) is dict and set(observation)=={'mode','worker_exited','pid','returncode','job_sha256'} and observation['job_sha256']==f.sha(files['job.json']),'bootstrap worker observation differs')
    if observation['mode']=='supplied_static_bootstrap':f.require(observation['worker_exited'] is False and observation['pid'] is None and observation['returncode'] is None,'static bootstrap claims exit')
    else:f.require(observation['mode']=='observed_bootstrap_worker_exit' and observation['worker_exited'] is True and type(observation['pid']) is int and observation['pid']>0 and type(observation['returncode']) is int and -255<=observation['returncode']<=255,'bootstrap worker exit differs')
    result=derive(root,meta,job,receiver,supervisor);f.require(files['analysis.json']==f.encode(result),'saved bootstrap analysis differs');return dict(schema='A23-bootstrap-archive-analysis-1',archive_integrity_valid=True,analysis=result,observation=observation,**FALSE)
if __name__=='__main__':
    import argparse,json
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive',type=Path);p.add_argument('--receiver-build',type=Path,required=True);p.add_argument('--supervisor-build',type=Path,required=True);v=p.parse_args()
    try:r=analyze(v.archive,v.receiver_build,v.supervisor_build)
    except (ValueError,OSError,KeyError,TypeError) as e:print(json.dumps(dict(archive_integrity_valid=False,error=str(e))));raise SystemExit(2)
    print(json.dumps(r,indent=2))
