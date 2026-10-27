"""Q1 workflow facade. Software capability never substitutes for new human authorization."""
import argparse
import json
import types
from pathlib import Path
import build_a23_live132_q1 as builder

def implementation(build):
    builder.verify(build);p=Path(build)/'generated/workflow.py';m=types.ModuleType('a23_q1_runtime');m.__file__=str(p)
    exec(compile(builder.w.plain(p),str(p),'exec'),m.__dict__)
    builder.require(m.builder is builder,'Q1 generated workflow builder mismatch');return m

def preview(build):return implementation(build).preview(build)
def issue(build,*,authorized=False):
    builder.require(authorized is True,'new explicit Q1 three-epoch authorization required')
    return implementation(build).issue(build,authorized=True)
def capture(build,job,*,execution_mode=None):return implementation(build).capture(build,job,execution_mode=execution_mode)
def collect(run):
    state=builder.w.load(Path(run)/'workflow.json');return implementation(Path(state['build'])).collect(run)
def acknowledge_power_off(run,*,confirmed=False):
    state=builder.w.load(Path(run)/'workflow.json');return implementation(Path(state['build'])).acknowledge_power_off(run,confirmed=confirmed)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',required=True,type=Path)
    s=p.add_subparsers(dest='mode',required=True);s.add_parser('preview');q=s.add_parser('issue');q.add_argument('--authorized-Q1-test',action='store_true')
    q=s.add_parser('capture');q.add_argument('job',type=Path);q.add_argument('--execution-mode',choices=['require_escalated'],required=True)
    args=p.parse_args()
    value=preview(args.build) if args.mode=='preview' else issue(args.build,authorized=args.authorized_Q1_test) if args.mode=='issue' else capture(args.build,args.job,execution_mode=args.execution_mode)
    print(json.dumps(value,indent=2))
