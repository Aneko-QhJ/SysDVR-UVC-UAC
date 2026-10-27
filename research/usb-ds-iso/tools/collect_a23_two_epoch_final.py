"""Freeze supplied static models or an already exited supervised model child."""
import argparse,json,subprocess
from pathlib import Path
import a23_final_archive as a
f=a.f

def producer_check(process,binary_sha256):
    f.require(isinstance(process,subprocess.Popen),'owned model child required');code=process.poll();f.require(type(code) is int,'producer still running; collection deferred');f.require(type(process.args) in (list,tuple) and len(process.args)==2,'model child command differs');f.require(f.sha(a.read(Path(process.args[0])))==binary_sha256,'model binary changed');return code

def freeze(source,build,output,*,static_model=False,process=None,binary_sha256=None,stdout=b'',stderr=b'',report=None,checkpoint=None):
    source=a.canonical(source);build=a.canonical(build);output=a.canonical(output);f.require(type(static_model) is bool and (static_model != (process is not None)),'explicit static model or exited child required')
    if static_model:
        observation=dict(mode='supplied_static_model',child_exited=False,returncode=None,binary_sha256=None)
    else:observation=dict(mode='observed_model_child_exit',child_exited=True,returncode=producer_check(process,binary_sha256),binary_sha256=binary_sha256)
    f.require(not output.exists() and not output.is_relative_to(source) and not source.is_relative_to(output) and not output.is_relative_to(build) and not build.is_relative_to(output),'new nonoverlapping output required')
    scope,reference=a.build_scope(build);before,dirs=a.snapshot(source,maximum=512,total_limit=16*1024*1024)
    if report is None:report=before.get('summary.json',b'') if static_model else stdout
    f.require(type(report) is bytes and type(stdout) is bytes and type(stderr) is bytes and len(report)<=1024*1024 and len(stdout)+len(stderr)<=2*1024*1024,'invalid process bytes')
    output.mkdir(mode=0o700);f.sync(output.parent);a.put(output,'ATTEMPT',b'one final collection attempt\n')
    if checkpoint:checkpoint('reserved')
    for name in dirs:(output/'inputs'/name).mkdir(parents=True,exist_ok=True)
    (output/'inputs').mkdir(exist_ok=True)
    for name,raw in before.items():a.put(output,'inputs/'+name,raw)
    for name,raw in (('report.json',report),('process.stdout',stdout),('process.stderr',stderr)):a.put(output,name,raw)
    meta=dict(schema='A23-final-collection-1',origin=observation['mode'],build_reference=reference,raw_files=a.inventory(before),directories=dirs,report_sha256=f.sha(report),observation=observation,**a.FALSE);a.put(output,'collection.json',f.encode(meta))
    result=a.analyze_inputs(output/'inputs',scope,report,observation);a.put(output,'analysis.json',f.encode(result))
    if checkpoint:checkpoint('before_commit')
    f.require(a.snapshot(source,maximum=512,total_limit=16*1024*1024)==(before,dirs),'source changed during final collection');f.require(a.build_scope(build)==(scope,reference),'build changed during final collection')
    if not static_model:f.require(producer_check(process,binary_sha256)==observation['returncode'],'producer exit changed')
    a.seal(output);return a.analyze(output,build)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--static-model',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);v=p.parse_args()
    try:result=freeze(v.static_model,v.build,v.output,static_model=True)
    except (ValueError,OSError,KeyError,TypeError) as e:print(json.dumps(dict(archive_integrity_valid=False,error=str(e))));raise SystemExit(2)
    print(json.dumps(result,indent=2))
