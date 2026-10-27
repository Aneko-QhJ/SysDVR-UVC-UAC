"""Dedicated fresh126 consumer/workflow; old workflow code remains immutable."""
import argparse
import json
import types
from pathlib import Path
import build_a23_live126_interepoch as builder

# The old consumer is already in the pinned source closure. Rebase it in an
# isolated module, never mutate its globals or silently accept its old range.
_source=Path(__file__).with_name('a23_live120_lstat_workflow.py').read_text()
_source=_source.replace('import build_a23_live120_lstat as builder','import build_a23_live126_interepoch as builder').replace('==369','==417').replace('==416','==464')
_impl=types.ModuleType('a23_live126_interepoch_consumer')
_impl.__file__=__file__
exec(compile(_source,__file__,'exec'),_impl.__dict__)
for _name in ('module','binding','trace_from_entry','validate_trace','analyze_entry','analyze_host','analyze_failure','implementation','preview','engine_module','issue','capture','collect','acknowledge_power_off'):
    globals()[_name]=getattr(_impl,_name)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,required=True)
    s=p.add_subparsers(dest='mode',required=True);s.add_parser('preview')
    q=s.add_parser('issue');q.add_argument('--authorized-three-epoch-test',action='store_true')
    q=s.add_parser('capture');q.add_argument('job',type=Path);q.add_argument('--execution-mode',choices=['require_escalated'],required=True)
    a=p.parse_args();value=preview(a.build) if a.mode=='preview' else issue(a.build,authorized=a.authorized_three_epoch_test) if a.mode=='issue' else capture(a.build,a.job,execution_mode=a.execution_mode)
    print(json.dumps(value,indent=2))
