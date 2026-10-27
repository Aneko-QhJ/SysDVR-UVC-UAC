"""Read-only joined model envelope. Checks both actual and injected contexts."""
from pathlib import Path
import copy
import a23_broker_supervision as sv
import a23_final_archive as final
a=final;f=a.f
FALSE={**sv.FALSE,'production_execution_authorized':False,'same_physical_run_verified':False}

def context_expected(actual,injected):
    f.require(type(injected) is bool,'injection flag type differs');c=copy.deepcopy(actual)
    if injected:c.update(sandbox_query_available=True,sandbox_query_result=0,sandbox_query_errno=0)
    return c

def evaluate(root,receiver,supervisor,files,dirs,check_saved=True):
    root=a.canonical(root);meta=f.parse(files['envelope.json']);scope,ref=a.build_scope(receiver);supref=sv.build_info(supervisor)
    f.require(scope['receiver_sha256']==supref['binary_sha256'],'child binary roles differ')
    f.require(set(meta)=={'schema','receiver_build','supervisor_build','producer_exited','child_pid','control_delivery','complete_injected_model_chain',*FALSE} and type(meta['complete_injected_model_chain']) is bool,'broker metadata inventory differs')
    f.require(meta['schema']=='A23-broker-model-envelope-1' and all(meta.get(k) is False for k in FALSE),'broker authority differs');f.require(meta['receiver_build']==ref and meta['supervisor_build']==supref,'broker build references differ')
    f.require(files['FINAL_ATTEMPT']==b'one model envelope attempt\n' and meta['producer_exited'] is True and type(meta['child_pid']) is int,'broker final producer differs')
    prefixes={'supervision/','final/'};top={'FINAL_ATTEMPT','envelope.json','plan.json','scope.json','expected-scope.json'}
    if 'control.json' in files:top.add('control.json')
    if 'STOP' in files:top.add('STOP')
    f.require(set(files)==top|{n for n in files if any(n.startswith(p) for p in prefixes)},'broker envelope inventory differs')
    expected_dirs=set(a.prefixes(files))
    # Nested forensic collections may intentionally retain empty directories.
    for prefix in ('supervision','final'):
        _,nested,_=a.sealed(root/prefix);expected_dirs.update(prefix+'/'+n for n in nested)
    f.require(dirs==sorted(expected_dirs),'broker envelope directories differ')
    f.require(f.encode(f.parse(files['expected-scope.json']))==f.encode(scope),'expected receiver scope differs')
    supervision=sv.analyze(root/'supervision',supervisor);collection=final.analyze(root/'final',receiver);plan=f.parse(files['plan.json']);report=f.parse(a.read(root/'final/report.json'));sr=f.parse(a.read(root/'supervision/result.json'));hello=f.parse(a.read(root/'supervision/stdout.bin'))
    f.require(sr['child_pid']==meta['child_pid'] and sr['producer_exited'] is True,'supervised process differs');f.require(type(plan['inject_policy']) is bool,'plan injection differs');errors=[]
    def require(ok,why):
        if not ok:errors.append(why)
    require(f.encode(report.get('actual_context'))==f.encode(hello['context']),'actual child context differs')
    expected=context_expected(hello['context'],plan['inject_policy']);require(report.get('execution_context_injected') is plan['inject_policy'],'execution injection declaration differs');require(f.encode(report.get('execution_context'))==f.encode(expected),'execution context substitution')
    require(f.encode(f.parse(files['scope.json']))==f.encode(scope),'scope changed');require(meta['control_delivery']=='whole_written','control not fully delivered')
    if 'control.json' in files:
        control=f.parse(files['control.json']);handoff=f.parse(a.read(root/'supervision/handoff-original.json'));require(control.get('nonce')==handoff['nonce'],'control nonce differs');require(f.encode(control.get('actual_context'))==f.encode(hello['context']),'command actual context differs');require(control.get('action')=='execute_model','environment gate denied execution')
        namespace=root/'final/inputs/namespace'
        if (namespace/'namespace.json').exists():
            ns=f.load(namespace/'namespace.json');info=f.load(root/'final/inputs/case-info.json');require(control.get('job_path')==str(Path(ns['root'])/'jobs'/info['job_id']),'control job path differs')
    else:errors.append('no execution command')
    require(supervision['supervision_complete'],'supervision not complete');require(collection['analysis']['supplied_model_chain_complete'],'receiver model chain not complete');require('STOP' not in files,'stop retained')
    result=dict(schema='A23-broker-model-analysis-1',archive_integrity_valid=True,complete_injected_model_chain=not errors,actual_environment_accepted=supervision['child_execution_policy_pass'],injected_policy_used=plan['inject_policy'],errors=errors,supervision=supervision,collection=collection,**FALSE)
    if check_saved:f.require(meta['complete_injected_model_chain'] is result['complete_injected_model_chain'],'saved broker verdict differs')
    return result

def analyze(root,receiver,supervisor):
    root=a.canonical(root);files,dirs,_=a.sealed(root);return evaluate(root,receiver,supervisor,files,dirs)

if __name__=='__main__':
    import argparse,json
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive',type=Path);p.add_argument('--receiver-build',type=Path,required=True);p.add_argument('--supervisor-build',type=Path,required=True);v=p.parse_args()
    try:r=analyze(v.archive,v.receiver_build,v.supervisor_build)
    except (ValueError,OSError,KeyError,TypeError) as e:print(json.dumps(dict(archive_integrity_valid=False,error=str(e))));raise SystemExit(2)
    print(json.dumps(r,indent=2))
