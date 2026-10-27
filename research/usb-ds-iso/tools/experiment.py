#!/usr/bin/env python3
"""One entry point for local A23 experiment status, restoration and capture."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from workflows.artifacts import ROOT, PRIVATE, archive_path, restore, verify

def status():
    p=PRIVATE/'analysis/A23-next-test.json'
    if not p.exists():return dict(state_available=False,next_action='restore --scope capture; then verify')
    plan=json.loads(p.read_text())
    keys=['stage','revision','host_revision','latest_run','latest_collection','latest_full_log_verified',
          'next_test_repeats','next_action','current_card_cycle_ejected','serial_ring_wrap_verified','stability_verified',
          'next_diagnostic_prepared','no_td_diagnostic_stage','latest_no_td_diagnostic','latest_no_td_host_baseline_passed',
          'latest_no_td_collection','latest_no_td_strict_acceptance_passed','single_burst_prepared','single_burst_diagnostic_stage','single_burst_remaining',
          'latest_single_burst_run','latest_single_burst_host_passed','latest_single_burst_switch_log_pending',
          'latest_single_burst_collection','latest_single_burst_strict_acceptance_passed',
          'matched_serial_prepared','matched_serial_diagnostic_stage','matched_serial_remaining',
          'matched_serial_build','latest_matched_serial_run','latest_matched_serial_host_passed',
          'latest_matched_serial_collection','latest_matched_serial_strict_acceptance_passed',
          'matched_serial_awake_required','serial_independent_full_passes','serial_independent_target',
          'clock_audit_prepared','clock_audit_diagnostic_stage','clock_audit_remaining','clock_audit_build','latest_clock_audit_run',
          'serial_clock_prepared','serial_clock_diagnostic_stage','serial_clock_remaining','serial_clock_max_bursts',
          'serial_clock_build','latest_serial_clock_run']
    return dict(state_available=True,**{k:plan.get(k) for k in keys})

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('status',help='Read local experiment state without USB access')
    p=sub.add_parser('restore',help='Restore missing archive inputs, preserving active state')
    p.add_argument('--archive',type=Path);p.add_argument('--scope',choices=['capture','patch'],default='capture');p.add_argument('--dry-run',action='store_true')
    sub.add_parser('verify',help='Verify active package, host tool and evidence SHA256SUMS')
    sub.add_parser('test',help='Run the bounded serial workflow only if its stage is prepared')
    sub.add_parser('test-no-td',help='Run one separately prepared no-TD window with fresh preflight')
    sub.add_parser('test-burst',help='Run one matched-backend burst only when its separate stage is prepared')
    sub.add_parser('test-clock',help='Run one prepared frame timestamp diagnostic with awake guard')
    sub.add_parser('test-serial-clock',help='Run one prepared bounded serial timestamp diagnostic with awake guard')
    sdk=sub.add_parser('test-sdk-no-td',help='One separately prepared IOUSBHost no-TD observation')
    sdk.add_argument('--dry-run',action='store_true',help='Only inspect files; no USB or attempt consumption')
    args=parser.parse_args()
    try:
        if args.command=='status':result=status()
        elif args.command=='restore':result=restore(args.archive or archive_path(),scope=args.scope,dry_run=args.dry_run)
        elif args.command=='verify':
            folders=[PRIVATE/'packages-A23-interval1/A',PRIVATE/'host-A23-native-guard-serial']
            for pointer in ['runs/latest-A23-run.txt','collections/latest-A23.txt','deployments/latest-A23.txt']:
                folders.append(Path((PRIVATE/pointer).read_text().strip()))
            plan=json.loads((PRIVATE/'analysis/A23-next-test.json').read_text())
            for key in ['no_td_diagnostic_build','latest_no_td_diagnostic','latest_no_td_collection','single_burst_build','latest_single_burst_run','latest_single_burst_collection','matched_serial_build','latest_matched_serial_run','latest_matched_serial_collection','clock_audit_build','latest_clock_audit_run','latest_clock_audit_collection','serial_clock_build']:
                if plan.get(key):folders.append(Path(plan[key]))
            result=[verify(f) for f in folders]
        elif args.command=='test-sdk-no-td':
            command=[sys.executable,str(ROOT/'tools/workflows/capture_io_usb_host_no_td.py')]
            if args.dry_run:command.append('--dry-run')
            return subprocess.call(command,cwd=ROOT)
        elif args.command=='test-no-td':
            return subprocess.call([sys.executable,str(ROOT/'tools/workflows/capture_no_td_window.py')],cwd=ROOT)
        elif args.command=='test-burst':
            return subprocess.call([sys.executable,str(ROOT/'tools/workflows/capture_burst_window.py')],cwd=ROOT)
        elif args.command=='test-clock':
            return subprocess.call([sys.executable,str(ROOT/'tools/workflows/capture_awake_clock.py')],cwd=ROOT)
        elif args.command=='test-serial-clock':
            return subprocess.call([sys.executable,str(ROOT/'tools/workflows/capture_awake_serial_clock.py')],cwd=ROOT)
        else:
            state=status()
            if state.get('stage')=='host_serial_clock_prepared' and state.get('serial_clock_prepared'):
                return subprocess.call([sys.executable,str(ROOT/'tools/workflows/capture_awake_serial_clock.py')],cwd=ROOT)
            if state.get('stage')=='host_clock_audit_prepared' and state.get('clock_audit_prepared'):
                return subprocess.call([sys.executable,str(ROOT/'tools/workflows/capture_awake_clock.py')],cwd=ROOT)
            if state.get('stage')=='native_guard_serial_matched_prepared' and state.get('next_test_repeats')==16:
                plan=json.loads((PRIVATE/'analysis/A23-next-test.json').read_text())
                if plan.get('matched_serial_awake_required'):
                    return subprocess.call([sys.executable,str(ROOT/'tools/workflows/capture_awake_serial.py')],cwd=ROOT)
                return subprocess.call([sys.executable,str(ROOT/'tools/workflows/capture_matched_serial.py')],cwd=ROOT)
            if state.get('stage')!='native_guard_serial_prepared' or state.get('next_test_repeats')!=16:
                raise ValueError('No serial test is prepared. Review the saved failure before scheduling another capture; no USB accessed.')
            return subprocess.call([sys.executable,str(ROOT/'tools/workflows/capture_native_serial.py')],cwd=ROOT)
        print(json.dumps(result,indent=2,ensure_ascii=False));return 0
    except (OSError,ValueError,KeyError,subprocess.CalledProcessError) as e:
        print(str(e),file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
