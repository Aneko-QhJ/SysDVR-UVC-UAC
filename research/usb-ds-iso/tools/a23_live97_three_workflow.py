"""Source-bound three-round workflow. Explicit new authorization precedes issue."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile
import types
import build_a23_live97_three as builder
w=builder.w

def module(build,name):
    p=Path(build)/'generated'/(name+'.py');m=types.ModuleType(name);m.__file__=str(p);sys.modules[name]=m;exec(compile(w.plain(p),str(p),'exec'),m.__dict__);return m

def analyze_entry(root,build,*,simulation=False):
    builder.verify(build,current=False);module(build,'sdk_analysis');entry=module(build,'entry_analysis').analyze(Path(root))
    d=w.load(Path(build)/'descriptor.json');_,bound=builder.generated(Path(build)/'source',{k:v for k,v in d.items() if k!='generated_hashes'})
    proof=module(build,'export_analysis').accept(Path(root),expected_binding=bound,simulation=simulation)
    w.require(proof['entry_binding']==w.load(Path(root)/'entry-current.json')['binding'],'export/entry binding differs');return dict(entry,checked_export=proof)

def analyze_host(host,build,*,simulation=False):
    with tempfile.TemporaryDirectory(prefix='a23-three-analysis-',dir='/private/tmp') as temp:
        stage=Path(temp)/'host';shutil.copytree(host,stage)
        for n in ('entry-current.json','entry-final-status.json','result.json','receipt-status.json'):shutil.copyfile(Path(host)/'live-final'/n,stage/n)
        return analyze_entry(stage,build,simulation=simulation)

def implementation(build):builder.verify(build);return module(build,'workflow')
def preview(build):return implementation(build).preview(build)
def engine_module(build):return implementation(build).engine_module(build)
def issue(build,*,authorized=False):return implementation(build).issue(build,authorized=authorized)
def capture(build,job,*,execution_mode=None):return implementation(build).capture(build,job,execution_mode=execution_mode)
def collect(run):return implementation(Path(w.load(Path(run)/'workflow.json')['build'])).collect(run)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,required=True);s=p.add_subparsers(dest='mode',required=True);s.add_parser('preview');q=s.add_parser('issue');q.add_argument('--authorized-three-epoch-test',action='store_true');q=s.add_parser('capture');q.add_argument('job',type=Path);q.add_argument('--execution-mode',choices=['require_escalated'],required=True);args=p.parse_args()
    if args.mode=='preview':value=preview(args.build)
    elif args.mode=='issue':value=issue(args.build,authorized=args.authorized_three_epoch_test)
    else:value=capture(args.build,args.job,execution_mode=args.execution_mode)
    print(json.dumps(value,indent=2))
