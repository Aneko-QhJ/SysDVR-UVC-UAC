"""Record a first model capture plus two descriptor-based reobservations.

Later observations retain inventories/hashes/identities, not a second raw copy.
Changes after the final observation remain explicitly unproven.
"""
from pathlib import Path
import a23_capture_window_archive as ar
a=ar.a;f=a.f;c=ar.c

def reobserve(job):
    try:metadata,files,dirs=c.capture(job);return ar.observed(metadata,files,dirs)
    except (ValueError,OSError) as e:return dict(status='blocked',capture=None,raw_files={},raw_directories=[],error_type=type(e).__name__,errno=getattr(e,'errno',None))

def freeze(job_path,receiver,supervisor,output,*,worker=None,static_model=False,checkpoint=None):
    observation,raw_job=c.observe(Path(job_path),worker,static_model);job=f.parse(raw_job);receiver=a.canonical(receiver);supervisor=a.canonical(supervisor);output=a.canonical(output);roots=tuple(Path(job[k]) for k in ('root','journal'));f.require(not output.exists() and all(not output.is_relative_to(p) and not p.is_relative_to(output) for p in (*roots,receiver,supervisor)),'new nonoverlapping observation window required');_,ref=a.build_scope(receiver);supref=c.ar.old.j.ar.old.sv.build_info(supervisor)
    output.mkdir(mode=0o700);a.put(output,'ATTEMPT',b'one model observation window attempt\n')
    first=c.freeze(job_path,receiver,supervisor,output/'first',worker=worker,static_model=static_model,checkpoint=lambda stage:checkpoint('first.'+stage) if checkpoint else None);fm=f.load(output/'first/capture.json');baseline=dict(status='captured',capture=fm['capture'],raw_files=fm['raw_files'],raw_directories=fm['raw_directories'],error_type=None,errno=None)
    if checkpoint:checkpoint('first_frozen')
    recheck=reobserve(job);a.put(output,'recheck.json',f.encode(recheck))
    if checkpoint:checkpoint('recheck_recorded')
    final=reobserve(job);a.put(output,'final-observation.json',f.encode(final))
    if checkpoint:checkpoint('final_observed')
    meta=dict(schema='A23-capture-window-envelope-1',receiver_build=ref,supervisor_build=supref,first_observation_sha256=f.sha(f.encode(baseline)),recheck_sha256=f.sha(f.encode(recheck)),final_observation_sha256=f.sha(f.encode(final)),**ar.FALSE);a.put(output,'window.json',f.encode(meta));a.put(output,'analysis.json',f.encode(ar.derive(first,baseline,recheck,final)));f.require(c.observe(Path(job_path),worker,static_model)[0]==observation,'observed worker changed');a.seal(output);return ar.analyze(output,receiver,supervisor)
