"""Isolated Python invocation for explicit file-only collection fault models.

Fresh process/environment is not an OS sandbox or a privilege boundary.
"""
from pathlib import Path
import json,os,sys
import a23_collection_journal as j
a=j.a;f=j.f

def run(job):
    value=f.load(a.canonical(job));keys={'schema','root','receiver','supervisor','journal','child_pid','control_delivery','fault','forbidden_path'};f.require(type(value) is dict and set(value)==keys and value['schema']=='A23-collection-worker-job-1','worker job differs')
    fault=value['fault'];f.require(fault in ('normal','hold-reserved','error-reserved','source-drift') or fault in {'crash-'+n for n in j.PHASES},'unknown offline fault');blocked=Path(value['forbidden_path']).resolve() if value['forbidden_path'] else None
    def guard(event,args):
        if event=='open' and isinstance(args[0],(str,bytes)):
            p=Path(args[0]).resolve()
            if p==blocked or p.is_relative_to('/Volumes'):raise RuntimeError('forbidden file open '+str(p))
    sys.addaudithook(guard)
    def checkpoint(phase):
        if fault=='crash-'+phase:os._exit(73)
        if fault=='hold-reserved' and phase=='reserved':print('READY',flush=True);f.require(sys.stdin.buffer.read(1)==b'x','explicit model release required')
        if fault=='error-reserved' and phase=='reserved':raise OSError('injected collection write failure')
        if fault=='source-drift' and phase=='envelope_prepared':(Path(value['root'])/'execution/config.json').write_bytes(b'{')
    receipt=j.old.ExitedModelFiles(*(Path(value[k]) for k in ('root','receiver','supervisor')),value['child_pid'],value['control_delivery']);result=j.collect(receipt,Path(value['journal']),checkpoint=checkpoint);return dict(completed=True,complete_injected_model_chain=result['complete_injected_model_chain'])
if __name__=='__main__':
    try:
        f.require(len(sys.argv)==2,'one private model job required');result=run(Path(sys.argv[1]))
    except (ValueError,OSError,KeyError,TypeError) as e:print(json.dumps(dict(completed=False,error=str(e))));raise SystemExit(2)
    print(json.dumps(result))
