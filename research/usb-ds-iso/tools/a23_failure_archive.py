"""Read-only complete/incomplete model archives, including absent child reports."""
from pathlib import Path
import copy
import a23_broker_archive as old
a=old.a;f=a.f

def report_state(files):
    if 'report.json' not in files:return 'missing'
    raw=files['report.json']
    if not raw:return 'empty'
    try:value=f.parse(raw)
    except (ValueError,TypeError):return 'malformed'
    return 'object' if type(value) is dict else 'non_object'

def evaluate(root,receiver,supervisor,files,dirs,check_saved=True):
    root=a.canonical(root);meta=f.parse(files['envelope.json']);scope,ref=a.build_scope(receiver);supref=old.sv.build_info(supervisor)
    keys={'schema','receiver_build','supervisor_build','producer_exited','child_pid','control_delivery','complete_injected_model_chain','report_state',*old.FALSE}
    f.require(type(meta) is dict and set(meta)==keys and meta['schema']=='A23-model-failure-envelope-1','failure metadata differs');f.require(all(meta[k] is False for k in old.FALSE) and type(meta['complete_injected_model_chain']) is bool,'failure authority differs');f.require(f.encode(meta['receiver_build'])==f.encode(ref) and f.encode(meta['supervisor_build'])==f.encode(supref) and scope['receiver_sha256']==supref['binary_sha256'],'failure build references differ');f.require(files['FINAL_ATTEMPT']==b'one model failure envelope attempt\n' and meta['producer_exited'] is True and type(meta['child_pid']) is int and meta['child_pid']>0 and meta['control_delivery'] in ('none','whole_written','partial_or_failed'),'failure producer differs')
    top={'FINAL_ATTEMPT','envelope.json','plan.json','scope.json','expected-scope.json','admission.json','ADMISSION_ATTEMPT'}|{n for n in ('control.json','STOP') if n in files};f.require(set(files)==top|{n for n in files if n.startswith(('supervision/','final/'))},'failure inventory differs')
    wanted=set(a.prefixes(files))
    for name in ('supervision','final'):
        _,nested,_=a.sealed(root/name);wanted.update(name+'/'+n for n in nested)
    f.require(dirs==sorted(wanted),'failure directories differ');f.require(f.encode(f.parse(files['expected-scope.json']))==f.encode(scope),'failure expected scope differs')
    admission=f.parse(files['admission.json']);expected=dict(schema='A23-model-source-admission-1',source_sha256=scope['workflow_source_sha256'],observed_sha256=scope['workflow_source_sha256'],source_count=ref['frozen_source_count'],source_match=True,receiver_build=ref,supervisor_build=supref,point_in_time_only=True,production_execution_authorized=False);f.require(files['ADMISSION_ATTEMPT']==b'one source admission attempt\n' and f.encode(admission)==f.encode(expected),'source admission differs')
    supervision=old.sv.analyze(root/'supervision',supervisor);collection=a.analyze(root/'final',receiver);sr=f.parse(files['supervision/result.json']);f.require(sr['child_pid']==meta['child_pid'] and sr['producer_exited'] is True,'failure supervised producer differs');f.require(files['final/process.stdout']==files['supervision/stdout.bin'] and files['final/process.stderr']==files['supervision/stderr.bin'],'failure streams differ')
    raw={n[len('final/inputs/'):]:v for n,v in files.items() if n.startswith('final/inputs/')};state=report_state(raw);f.require(state==meta['report_state'] and files['final/report.json']==raw.get('report.json',b''),'failure raw report differs');plan=f.parse(files['plan.json']);f.require(type(plan.get('inject_policy')) is bool,'failure injection flag differs');errors=[];joined=None
    hello=None
    try:
        hello=f.parse(files['supervision/stdout.bin']);f.require(type(hello) is dict and type(hello.get('context')) is dict,'missing hello context')
    except (ValueError,TypeError,KeyError):hello=None
    if state=='object' and hello is not None:
        # Reuse the frozen full join without changing its schema or source.
        adapted=dict(files);adapted['FINAL_ATTEMPT']=b'one model envelope attempt\n';base=copy.deepcopy(meta);base.pop('report_state');base['schema']='A23-broker-model-envelope-1';adapted['envelope.json']=f.encode(base)
        for name in ('admission.json','ADMISSION_ATTEMPT'):adapted.pop(name)
        joined=old.evaluate(root,receiver,supervisor,adapted,[n for n in dirs],check_saved=False);errors.extend(joined['errors'])
    else:
        if state!='object':errors.append('report '+state)
        if hello is None:errors.append('hello missing or malformed')
        errors.append('complete child report join unavailable')
    if not supervision['supervision_complete'] and 'supervision not complete' not in errors:errors.append('supervision not complete')
    if not collection['analysis']['supplied_model_chain_complete'] and 'receiver model chain not complete' not in errors:errors.append('receiver model chain not complete')
    if 'STOP' in files and 'stop retained' not in errors:errors.append('stop retained')
    result=dict(schema='A23-model-failure-analysis-1',archive_integrity_valid=True,complete_injected_model_chain=not errors,report_state=state,actual_environment_accepted=supervision['child_execution_policy_pass'],injected_policy_used=plan['inject_policy'],errors=errors,supervision=supervision,collection=collection,**old.FALSE)
    if check_saved:f.require(meta['complete_injected_model_chain'] is result['complete_injected_model_chain'],'saved failure verdict differs')
    return result

def analyze(root,receiver,supervisor):
    files,dirs,_=a.sealed(a.canonical(root));return evaluate(root,receiver,supervisor,files,dirs)
if __name__=='__main__':
    import argparse,json
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive',type=Path);p.add_argument('--receiver-build',type=Path,required=True);p.add_argument('--supervisor-build',type=Path,required=True);v=p.parse_args()
    try:r=analyze(v.archive,v.receiver_build,v.supervisor_build)
    except (ValueError,OSError,KeyError,TypeError) as e:print(json.dumps(dict(archive_integrity_valid=False,error=str(e))));raise SystemExit(2)
    print(json.dumps(r,indent=2))
