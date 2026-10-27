"""Test-only interruption injection around the frozen journal bootstrap writes.

Hooks affect only this disposable process; frozen source bytes stay unchanged.
No production collection entry is implemented here.
"""
from pathlib import Path
import json,os,sys
import a23_collection_journal as j
a=j.a;f=j.f
FAULTS=('normal','hold-marker','marker-empty','marker-partial','marker-full','journal-directory','attempt-empty','attempt-partial','attempt-full','copy-empty','copy-partial','copy-full','event-partial','event-full','float-marker','malformed-marker-complete','mismatched-marker-complete')
def run(path):
    job=f.load(a.canonical(path));f.require(job['schema']=='A23-collection-worker-job-1' and job['fault'] in FAULTS,'bootstrap fault job differs');source=Path(job['root']);journal=Path(job['journal']);fault=job['fault'];put=a.put;mkdir=os.mkdir
    def injected_put(root,name,raw):
        stage='marker' if root==source and name==j.MARKER else 'attempt' if root==journal and name=='attempt.json' else 'copy' if root==journal and name=='SOURCE_ATTEMPT' else 'event' if root==journal and name=='events/00.json' else None
        if stage=='marker' and fault=='float-marker':v=f.parse(raw);v['child_pid']=float(v['child_pid']);put(root,name,f.encode(v));os._exit(74)
        if stage=='marker' and fault=='malformed-marker-complete':return put(root,name,b'{')
        if stage=='marker' and fault=='mismatched-marker-complete':v=f.parse(raw);v['child_pid']=123;return put(root,name,f.encode(v))
        if stage and fault.startswith(stage+'-'):
            mode=fault[len(stage)+1:];put(root,name,b'' if mode=='empty' else b'{' if mode=='partial' else raw);os._exit(74)
        put(root,name,raw)
        if stage=='marker' and fault=='hold-marker':print('READY',flush=True);f.require(sys.stdin.buffer.read(1)==b'x','explicit model release required');os._exit(74)
    def injected_mkdir(path,*args,**kwargs):
        result=mkdir(path,*args,**kwargs)
        if Path(path)==journal and fault=='journal-directory':os._exit(74)
        return result
    a.put=injected_put;os.mkdir=injected_mkdir
    try:
        receipt=j.old.ExitedModelFiles(source,Path(job['receiver']),Path(job['supervisor']),job['child_pid'],job['control_delivery']);j.collect(receipt,journal)
    finally:a.put=put;os.mkdir=mkdir
    return dict(completed=True)
if __name__=='__main__':
    try:f.require(len(sys.argv)==2,'one bootstrap model job required');r=run(Path(sys.argv[1]))
    except (ValueError,OSError,KeyError,TypeError) as e:print(json.dumps(dict(completed=False,error=str(e))));raise SystemExit(2)
    print(json.dumps(r))
