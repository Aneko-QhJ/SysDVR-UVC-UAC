"""One-attempt, file-only collection journal around frozen fake SDK evidence.

The durable source marker precedes execution-tree reads. Checkpoints are
explicit offline fault injection, never a production retry or cleanup path.
"""
from pathlib import Path
import os,shutil,uuid
import a23_failure_collector as old
ar=old.ar;a=old.a;f=a.f
PHASES=('reserved','snapshotted','final_started','final_frozen','envelope_prepared','revalidated','completed')
MARKER='JOURNAL_COLLECTION_ATTEMPT'

def collect(receipt,journal,checkpoint=None):
    f.require(type(receipt) is old.ExitedModelFiles,'model file receipt required');root=a.canonical(receipt.root);receiver=a.canonical(receipt.receiver);supervisor=a.canonical(receipt.supervisor);journal=a.canonical(journal)
    f.require(root.is_relative_to('/private/tmp') and journal.is_relative_to('/private/tmp'),'private temporary model roots required');f.require(not journal.exists() and not journal.is_relative_to(root) and not root.is_relative_to(journal) and not journal.is_relative_to(receiver) and not receiver.is_relative_to(journal) and not journal.is_relative_to(supervisor) and not supervisor.is_relative_to(journal),'new nonoverlapping journal required')
    ar.old.sv.analyze(root/'supervision',supervisor);sr=f.load(root/'supervision/result.json');f.require(type(receipt.child_pid) is int and sr['child_pid']==receipt.child_pid and sr['producer_exited'] is True,'exited source model required');scope,ref=a.build_scope(receiver);supref=ar.old.sv.build_info(supervisor)
    attempt=dict(schema='A23-collection-attempt-1',nonce=uuid.uuid4().hex+uuid.uuid4().hex,source=str(root),journal=str(journal),receiver_build=ref,supervisor_build=supref,child_pid=receipt.child_pid,control_delivery=receipt.control_delivery,model_only=True,production_execution_authorized=False)
    raw=f.encode(attempt);a.put(root,MARKER,raw) # Exclusive burn before any execution snapshot.
    journal.mkdir(mode=0o700);f.sync(journal.parent);a.put(journal,'attempt.json',raw);a.put(journal,'SOURCE_ATTEMPT',raw);previous=f.sha(raw);index=0
    def event(phase):
        nonlocal previous,index
        f.require(index<len(PHASES) and PHASES[index]==phase,'journal phase order differs');row=dict(schema='A23-collection-event-1',index=index,phase=phase,attempt_sha256=f.sha(raw),previous_sha256=previous);encoded=f.encode(row);a.put(journal,'events/%02d.json'%index,encoded);previous=f.sha(encoded);index+=1
        if checkpoint:checkpoint(phase)
    try:
        event('reserved');before,dirs=a.snapshot(root/'execution',maximum=512,total_limit=16*1024*1024);report=before.get('report.json',b'');f.require(len(report)<=1024*1024,'model report too large');event('snapshotted')
        output=journal/'envelope';output.mkdir(mode=0o700);a.put(output,'FINAL_ATTEMPT',b'one model failure envelope attempt\n');shutil.copytree(root/'supervision',output/'supervision')
        old.final.freeze(root/'execution',receiver,output/'final',static_model=True,report=report,stdout=a.read(root/'supervision/stdout.bin'),stderr=a.read(root/'supervision/stderr.bin'),checkpoint=lambda stage:event('final_started') if stage=='reserved' else None);event('final_frozen')
        for name in ('plan.json','scope.json','expected-scope.json','control.json','STOP','admission.json','ADMISSION_ATTEMPT'):
            if (root/name).exists():a.put(output,name,a.read(root/name))
        meta=dict(schema='A23-model-failure-envelope-1',receiver_build=ref,supervisor_build=supref,producer_exited=True,child_pid=receipt.child_pid,control_delivery=receipt.control_delivery,complete_injected_model_chain=False,report_state=ar.report_state(before),**ar.old.FALSE);a.put(output,'envelope.json',f.encode(meta));files,tree=a.snapshot(output);result=ar.evaluate(output,receiver,supervisor,files,tree,check_saved=False);meta['complete_injected_model_chain']=result['complete_injected_model_chain'];p=output/'envelope.final.tmp';f.exclusive(p,f.encode(meta));os.replace(p,output/'envelope.json');f.sync(output);event('envelope_prepared')
        f.require(a.snapshot(root/'execution',maximum=512,total_limit=16*1024*1024)==(before,dirs),'execution changed during journal collection');f.require(a.build_scope(receiver)==(scope,ref) and ar.old.sv.build_info(supervisor)==supref,'build changed during journal collection');event('revalidated');a.seal(output);ar.analyze(output,receiver,supervisor);event('completed');a.seal(journal)
        return result
    except (ValueError,OSError,KeyError,TypeError) as e:
        # A failed journal is left uncommitted. Original partial output is never
        # completed or rewritten by inspection or forensic freezing.
        a.put(journal,'failure.json',f.encode(dict(schema='A23-collection-failure-1',after_event=index-1,error_type=type(e).__name__,reason=str(e)[:1024],retry_authorized=False,cleanup_authorized=False)))
        raise
