"""Frozen current91 workflow and checked exporter; explicit authorization only."""
import argparse,json,sys,types,tempfile,shutil
from pathlib import Path
import build_a23_live91_checked as builder
w=builder.w


def module(build,name):
    path=Path(build)/'generated'/(name+'.py');loaded=types.ModuleType(name);loaded.__file__=str(path);sys.modules[name]=loaded
    exec(compile(w.plain(path),str(path),'exec'),loaded.__dict__);return loaded


def analyze_entry(root,build,*,simulation=False):
    builder.verify(build,current=False);module(build,'a23_live75_sdk_analysis');entry=module(build,'a23_live75_entry_analysis').analyze(Path(root))
    consumer=module(build,'a23_live91_export_analysis');d=w.load(Path(build)/'descriptor.json');_,binding=builder.generated(Path(build)/'source',d)
    proof=consumer.accept(Path(root),expected_binding=binding,simulation=simulation)
    w.require(proof['entry_binding']==w.load(Path(root)/'entry-current.json')['binding'],'checked/SDK binding differs')
    return dict(entry,checked_export=proof)


def implementation(build):
    builder.verify(build);return module(build,'a23_live91_workflow')


def preview(build):return implementation(build).preview(build)
def engine_module(build):return implementation(build).engine_module(build)
def fresh_scope(build):return implementation(build).fresh_scope(build)
def issue(build,*,authorized=False):return implementation(build).issue(build,authorized=authorized)
def capture(build,job,*,execution_mode=None):return implementation(build).capture(build,job,execution_mode=execution_mode)
def collect(run):return implementation(Path(w.load(Path(run)/'workflow.json')['build'])).collect(run)


def analyze_host(host,build,*,simulation=False):
    with tempfile.TemporaryDirectory(prefix='a23-live91-analysis-',dir='/private/tmp') as temporary:
        overlay=Path(temporary)/'host';shutil.copytree(host,overlay)
        for n in ('entry-current.json','entry-final-status.json','result.json','receipt-status.json'):shutil.copyfile(Path(host)/'live-final'/n,overlay/n)
        return analyze_entry(overlay,build,simulation=simulation)


def acknowledge_power_off(run,*,confirmed=False):
    from a23_live_two_epoch_workflow import acknowledge_power_off as acknowledge
    return acknowledge(run,confirmed=confirmed)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path);s=p.add_subparsers(dest='mode',required=True);s.add_parser('preview')
    q=s.add_parser('issue');q.add_argument('--authorized-two-epoch-test',action='store_true');q=s.add_parser('capture');q.add_argument('job',type=Path);q.add_argument('--execution-mode',choices=['require_escalated'],required=True)
    q=s.add_parser('acknowledge-power-off');q.add_argument('run',type=Path);q.add_argument('--confirmed',action='store_true');args=p.parse_args()
    if args.mode!='acknowledge-power-off' and args.build is None:p.error('--build required')
    try:
        if args.mode=='preview':result=preview(args.build)
        elif args.mode=='issue':result=issue(args.build,authorized=args.authorized_two_epoch_test)
        elif args.mode=='capture':result=capture(args.build,args.job,execution_mode=args.execution_mode)
        else:result=acknowledge_power_off(args.run,confirmed=args.confirmed)
    except (ValueError,OSError,TypeError,KeyError) as error:print(json.dumps(dict(passed=False,error=str(error))));raise SystemExit(2)
    print(json.dumps(result,indent=2))
