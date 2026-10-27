"""Fixed saved75 successor workflow. Preview never reserves or acquires USB."""
import argparse,importlib.util,json,sys,types
from pathlib import Path
import build_a23_live75_two_epoch as builder
w=builder.w


def analyze_entry(root,build):
    build=w.canonical(build);builder.verify(build,current=False)
    loaded={}
    for name in ('a23_live75_sdk_analysis','a23_live75_entry_analysis'):
        path=build/'generated'/(name+'.py');spec=importlib.util.spec_from_file_location(name,path)
        module=importlib.util.module_from_spec(spec);loaded[name]=module
        # Dependencies are the verified generated files in this exact build.
        sys.modules[name]=module;exec(compile(w.plain(path),str(path),'exec'),module.__dict__)
    return loaded['a23_live75_entry_analysis'].analyze(Path(root))


def implementation(build):
    build=w.canonical(build);builder.verify(build)
    raw=w.plain(build/'source/research/usb-ds-iso/tools/a23_live_two_epoch_workflow.py').decode()
    module=types.ModuleType('A23_live75_frozen_workflow')
    exec(compile(builder.render_workflow(raw),'<A23-live75-frozen-workflow>','exec'),module.__dict__)
    return module


def preview(build):return implementation(build).preview(build)
def engine_module(build):return implementation(build).engine_module(build)
def fresh_scope(build):return implementation(build).fresh_scope(build)
def issue(build,*,authorized=False):return implementation(build).issue(build,authorized=authorized)
def capture(build,job,*,execution_mode=None):return implementation(build).capture(build,job,execution_mode=execution_mode)
def collect(run):
    run=w.canonical(run);return implementation(Path(w.load(run/'workflow.json')['build'])).collect(run)
def acknowledge_power_off(run,*,confirmed=False):
    # Same operator-off receipt and retained creator protocol, with no restart.
    from a23_live_two_epoch_workflow import acknowledge_power_off as acknowledge
    return acknowledge(run,confirmed=confirmed)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path);sub=p.add_subparsers(dest='mode',required=True)
    sub.add_parser('preview');q=sub.add_parser('issue');q.add_argument('--authorized-two-epoch-test',action='store_true')
    q=sub.add_parser('capture');q.add_argument('job',type=Path);q.add_argument('--execution-mode',choices=['require_escalated'],required=True)
    q=sub.add_parser('acknowledge-power-off');q.add_argument('run',type=Path);q.add_argument('--confirmed',action='store_true')
    args=p.parse_args()
    if args.mode!='acknowledge-power-off' and args.build is None:p.error('--build is required')
    try:
        if args.mode=='preview':result=preview(args.build)
        elif args.mode=='issue':result=issue(args.build,authorized=args.authorized_two_epoch_test)
        elif args.mode=='capture':result=capture(args.build,args.job,execution_mode=args.execution_mode)
        else:result=acknowledge_power_off(args.run,confirmed=args.confirmed)
    except (ValueError,OSError,KeyError,TypeError) as error:print(json.dumps(dict(passed=False,error=str(error))));raise SystemExit(2)
    print(json.dumps(result,indent=2))
