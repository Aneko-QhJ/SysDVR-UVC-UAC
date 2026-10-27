"""Read-only repeated-observation model evidence; no atomic/current-source claim."""
import re
from pathlib import Path
import a23_bootstrap_capture as c
a=c.a;f=c.f
FALSE={**c.ar.FALSE,'atomic_snapshot_verified':False,'source_unchanged_through_commit_proven':False,'post_final_changes_excluded':False}

def observed(capture,files,dirs):return dict(status='captured',capture=capture,raw_files=a.inventory(files),raw_directories=dirs,error_type=None,errno=None)
def validate_observation(row):
    f.require(type(row) is dict and set(row)=={'status','capture','raw_files','raw_directories','error_type','errno'},'window observation inventory differs')
    if row['status']=='blocked':f.require(row['capture'] is None and row['raw_files']=={} and row['raw_directories']==[] and row['error_type'] in ('OSError','ValueError','FileNotFoundError','NotADirectoryError','PermissionError') and (row['errno'] is None or type(row['errno']) is int),'blocked observation differs');return
    f.require(row['status']=='captured' and row['error_type'] is None and row['errno'] is None,'captured observation differs');cap=row['capture'];f.require(type(cap) is dict and set(cap)=={'source','marker','journal'},'window capture components differ')
    for part in cap.values():
        f.require(type(part) is dict and set(part)=={'state','stable','identity','skipped'} and part['state'] in ('directory','regular','absent','blocked') and type(part['stable']) is bool and type(part['skipped']) is list,'window capture component differs');f.require(part['identity'] is None or type(part['identity']) is list and len(part['identity'])==6 and all(type(v) is int for v in part['identity']),'window identity differs')
        for entry in part['skipped']:f.require(type(entry) is dict and set(entry)=={'path','reason'} and all(type(v) is str for v in entry.values()),'window skipped component differs')
    f.require(type(row['raw_files']) is dict and type(row['raw_directories']) is list and row['raw_directories']==sorted(set(row['raw_directories'])),'window raw tables differ')
    for n,v in row['raw_files'].items():f.require(type(n) is str and re.fullmatch(r'[A-Za-z0-9_.\-/]+',n) and '..' not in Path(n).parts and not n.startswith('/') and type(v) is dict and set(v)=={'bytes','sha256'} and type(v['bytes']) is int and 0<=v['bytes']<=1024*1024 and f.hex64(v['sha256']),'window raw entry differs')
    for n in row['raw_directories']:f.require(type(n) is str and re.fullmatch(r'[A-Za-z0-9_.\-/]+',n) and '..' not in Path(n).parts and not n.startswith('/'),'window raw directory differs')

def derive(first,baseline,recheck,final):
    for row in (baseline,recheck,final):validate_observation(row)
    second_equal=f.encode(baseline)==f.encode(recheck);final_equal=f.encode(baseline)==f.encode(final);errors=[]
    if not first['analysis']['complete_injected_model_chain']:errors.append('first model evidence incomplete')
    if not second_equal:errors.append('recheck differs from first capture')
    if not final_equal:errors.append('final observation differs from first capture')
    return dict(schema='A23-capture-window-analysis-1',observations_agree=second_equal and final_equal,recheck_matches_first=second_equal,final_matches_first=final_equal,accepted_model_evidence=not errors,complete_injected_model_chain=not errors,first_capture_complete=first['analysis']['complete_injected_model_chain'],errors=errors,**FALSE)

def analyze(root,receiver,supervisor):
    root=a.canonical(root);files,dirs,_=a.sealed(root);first=c.ar.analyze(root/'first',receiver,supervisor);fm=f.parse(files['first/capture.json']);baseline=dict(status='captured',capture=fm['capture'],raw_files=fm['raw_files'],raw_directories=fm['raw_directories'],error_type=None,errno=None);recheck=f.parse(files['recheck.json']);final=f.parse(files['final-observation.json']);meta=f.parse(files['window.json']);_,ref=a.build_scope(receiver);supref=c.ar.old.j.ar.old.sv.build_info(supervisor)
    f.require(type(meta) is dict and set(meta)=={'schema','receiver_build','supervisor_build','first_observation_sha256','recheck_sha256','final_observation_sha256',*FALSE} and meta['schema']=='A23-capture-window-envelope-1' and all(meta[k] is False for k in FALSE),'window metadata/authority differs');f.require(f.encode(meta['receiver_build'])==f.encode(ref) and f.encode(meta['supervisor_build'])==f.encode(supref),'window build differs');f.require(meta['first_observation_sha256']==f.sha(f.encode(baseline)) and meta['recheck_sha256']==f.sha(files['recheck.json']) and meta['final_observation_sha256']==f.sha(files['final-observation.json']),'window observation digest differs')
    f.require(files['ATTEMPT']==b'one model observation window attempt\n' and set(files)=={'ATTEMPT','window.json','recheck.json','final-observation.json','analysis.json'}|{n for n in files if n.startswith('first/')},'window inventory differs');_,nested,_=a.sealed(root/'first');f.require(dirs==sorted(set(a.prefixes(files))|{'first/'+n for n in nested}),'window directories differ');result=derive(first,baseline,recheck,final);f.require(files['analysis.json']==f.encode(result),'saved window analysis differs');return dict(schema='A23-capture-window-archive-analysis-1',archive_integrity_valid=True,analysis=result,first_capture=first,**FALSE)
if __name__=='__main__':
    import argparse,json
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive',type=Path);p.add_argument('--receiver-build',type=Path,required=True);p.add_argument('--supervisor-build',type=Path,required=True);v=p.parse_args()
    try:r=analyze(v.archive,v.receiver_build,v.supervisor_build)
    except (ValueError,OSError,KeyError,TypeError) as e:print(json.dumps(dict(archive_integrity_valid=False,error=str(e))));raise SystemExit(2)
    print(json.dumps(r,indent=2))
