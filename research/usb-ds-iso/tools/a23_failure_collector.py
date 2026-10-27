"""Collect already sealed model supervision and bounded raw execution files.

No launch, sequence issuer or process-control API is imported here. An observed
exit is validated from the supplied sealed model record, not authenticated as
an OS security assertion. Running-child ownership remains with the supervisor.
"""
from dataclasses import dataclass
from pathlib import Path
import os,shutil
import a23_failure_archive as ar
import collect_a23_two_epoch_final as final
a=ar.a;f=a.f
@dataclass(frozen=True)
class ExitedModelFiles:
    root:Path
    receiver:Path
    supervisor:Path
    child_pid:int
    control_delivery:str

def collect(receipt,output):
    f.require(type(receipt) is ExitedModelFiles,'exited model file receipt required');root=a.canonical(receipt.root);receiver=a.canonical(receipt.receiver);supervisor=a.canonical(receipt.supervisor);output=a.canonical(output)
    f.require(root.is_relative_to('/private/tmp'),'temporary model producer required');f.require(not output.exists() and not output.is_relative_to(root) and not root.is_relative_to(output) and not output.is_relative_to(receiver) and not receiver.is_relative_to(output) and not output.is_relative_to(supervisor) and not supervisor.is_relative_to(output),'new nonoverlapping failure envelope required')
    ar.old.sv.analyze(root/'supervision',supervisor);sr=f.load(root/'supervision/result.json');f.require(sr['child_pid']==receipt.child_pid and sr['producer_exited'] is True,'exited producer differs')
    scope,ref=a.build_scope(receiver);supref=ar.old.sv.build_info(supervisor);before,dirs=a.snapshot(root/'execution',maximum=512,total_limit=16*1024*1024);report=before.get('report.json',b'');f.require(len(report)<=1024*1024,'model report too large')
    a.put(root,'FAILURE_COLLECTION_ATTEMPT',b'one exited model collection attempt\n');output.mkdir(mode=0o700);a.put(output,'FINAL_ATTEMPT',b'one model failure envelope attempt\n');shutil.copytree(root/'supervision',output/'supervision')
    final.freeze(root/'execution',receiver,output/'final',static_model=True,report=report,stdout=a.read(root/'supervision/stdout.bin'),stderr=a.read(root/'supervision/stderr.bin'))
    for name in ('plan.json','scope.json','expected-scope.json','control.json','STOP','admission.json','ADMISSION_ATTEMPT'):
        if (root/name).exists():a.put(output,name,a.read(root/name))
    meta=dict(schema='A23-model-failure-envelope-1',receiver_build=ref,supervisor_build=supref,producer_exited=True,child_pid=receipt.child_pid,control_delivery=receipt.control_delivery,complete_injected_model_chain=False,report_state=ar.report_state(before),**ar.old.FALSE)
    a.put(output,'envelope.json',f.encode(meta));files,tree=a.snapshot(output);result=ar.evaluate(output,receiver,supervisor,files,tree,check_saved=False);meta['complete_injected_model_chain']=result['complete_injected_model_chain'];p=output/'envelope.final.tmp';f.exclusive(p,f.encode(meta));os.replace(p,output/'envelope.json');f.sync(output)
    f.require(a.snapshot(root/'execution',maximum=512,total_limit=16*1024*1024)==(before,dirs),'execution changed during failure collection');a.seal(output);return ar.analyze(output,receiver,supervisor)
