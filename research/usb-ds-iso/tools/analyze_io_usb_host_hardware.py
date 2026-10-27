#!/usr/bin/env python3
"""Read-only audits of SDK-origin no-TD observations; no native policy approval."""
import argparse
import json
from pathlib import Path
from analyze_io_usb_host_evidence import analyze as transfer, require, unique_object
from analyze_io_usb_host_session import analyze as session
from analyze_io_usb_host_collection import freeze, analyze as collection
from analyze_io_usb_host_no_td import analyze as observation
from io_usb_host_probe_plan import validate_hardware_plan


def analyze_run(root):
    root=Path(root)
    require(root.is_dir() and not root.is_symlink(),'invalid run directory')
    receipt=json.loads((root/'authorization.json').read_bytes(),object_pairs_hook=unique_object)
    require(receipt.get('schema')=='A23-IOUSBHost-consumed-receipt-1' and receipt.get('attempt_consumed') is True,
            'run lacks a consumed one-use receipt')
    validate_hardware_plan(receipt.get('plan'))
    bundle=root/'transfer'; supplied=bundle if (bundle/'COMMITTED').is_file() else None
    s=session(root/'session.jsonl',supplied,hardware=True)
    require(s['probe_plan_bound'],'hardware journal lacks its fixed plan')
    native=transfer(supplied,hardware=True) if supplied else None
    outcome=None
    if (root/'receiver-result.json').is_file():
        outcome=json.loads((root/'receiver-result.json').read_bytes(),object_pairs_hook=unique_object)
        require(outcome.get('schema')=='A23-IOUSBHost-receiver-result-1' and outcome.get('execution_mode')=='hardware' and
                type(outcome.get('finished')) is bool and type(outcome.get('unresolved')) is bool and
                outcome.get('hardware_verified') is False and outcome.get('baseline_accepted') is False,
                'invalid receiver result')
        require(outcome['finished'] and not outcome['unresolved'] and s['resources_closed'] and
                outcome.get('resources_retained') is False and outcome.get('storage_retained') is False,
                'receiver result contradicts resource lifecycle')
        require(type(outcome.get('exit_code')) is int and outcome['exit_code'] in (0,1),'invalid receiver exit code')
    complete=bool(outcome and outcome['exit_code']==0 and s['simulation_session_pass'] and native and native['payload_matches'])
    return dict(schema='A23-IOUSBHost-run-analysis-1',execution_mode='hardware',journal=s,native=native,
                host_observation_complete=complete,device_log_pending=True,hardware_verified=False,usb_strict_pass=False,
                baseline_accepted=False,allow_next_burst=False,empty_status_policy_verified=False,callback_drain_verified=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__); sub=parser.add_subparsers(dest='command',required=True)
    for command in ('run','audit'):
        sub.add_parser(command).add_argument('directory',type=Path)
    make=sub.add_parser('freeze');make.add_argument('run',type=Path);make.add_argument('device_log',type=Path);make.add_argument('output',type=Path)
    args=parser.parse_args()
    try:
        if args.command=='run':
            result=analyze_run(args.directory);passed=result['host_observation_complete']
        else:
            if args.command=='freeze':
                analyze_run(args.run) # failed observations may still be frozen, never converted to success
                freeze(args.run/'session.jsonl',args.run/'transfer',args.device_log,args.output,hardware=True)
            result=observation(args.output if args.command=='freeze' else args.directory,hardware=True)
            passed=result['observation_complete']
        print(json.dumps(result,indent=2));return 0 if passed else 1
    except (OSError,ValueError,TypeError,KeyError,UnicodeError) as error:
        print(json.dumps(dict(error=str(error),hardware_verified=False,usb_strict_pass=False,baseline_accepted=False),indent=2));return 2

if __name__=='__main__': raise SystemExit(main())
