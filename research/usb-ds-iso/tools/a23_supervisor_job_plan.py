"""Pinned static integration evidence and an unapplied read-only adapter diff."""
import difflib,hashlib
BASE='research/usb-ds-iso/'
ANCHORS={
 'host/a23_waiting_receiver.h':('A23MakeWaitingBoundPermit(',),
 'host/a23_two_epoch_entry.h':('@protocol A23TwoEpochEntryPermit',),
 'host/a23_two_epoch_entry.m':('if(![_permit claimProcess:', '![_permit claimSelection:', '_driver=[[A23TwoEpochSDKDriver alloc]'),
 'host/a23_shared_sequence_permit.m':('- (BOOL)claimProcess:', '- (BOOL)claimSelection:', '_binding=@{@"schema":@"A23-two-epoch-entry-binding-1"'),
 'host/a23_two_epoch_sdk_driver.m':('_binding=@{@"session_id":', '- (BOOL)saveReceiptOnce'),
 'tools/a23_shared_sequence32.py':('def consume(self,job):','def binding(self,job):'),
 'tools/collect_a23_two_epoch_final.py':('def producer_check(', 'def freeze('),
 'tools/collect_a23_waiting_execution.py':('def analyze_inputs(',),
 'tools/collect_a23_bound_execution.py':('def binding_analysis(',)}
TARGET=BASE+'tools/collect_a23_supervised_job_review.py'
WRAPPER=b'''"""Unapplied read-only correspondence adapter. Never issues or consumes permits."""
import argparse,json
from pathlib import Path
import audit_a23_supervisor_job_link as audit

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('case_directory',type=Path);p.add_argument('--expected-sha256',required=True)
    args=p.parse_args()
    try:result=audit.read_case(args.case_directory,args.expected_sha256)
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print(json.dumps(dict(readonly_review_valid=False,error=str(exc))));return 2
    print(json.dumps(result,indent=2));return 0 if not result['errors'] else 2

if __name__=='__main__':raise SystemExit(main())
'''

def render(source):
    evidence={}
    for name,anchors in ANCHORS.items():
        raw=(source/BASE/name).read_bytes();lines=raw.decode().splitlines();hits=[]
        for needle in anchors:
            matched=[i for i,line in enumerate(lines,1) if needle in line]
            if len(matched)!=1:raise ValueError('integration anchor differs '+name+' '+needle)
            n=matched[0];hits.append(dict(line=n,anchor=needle,line_sha256=hashlib.sha256(lines[n-1].encode()).hexdigest()))
        evidence[BASE+name]=dict(sha256=hashlib.sha256(raw).hexdigest(),anchors=hits)
    diff=''.join(difflib.unified_diff([],WRAPPER.decode().splitlines(True),fromfile='/dev/null',tofile='candidate/'+TARGET)).encode()
    return dict(schema='A23-supervisor-job-static-plan-1',source_evidence=evidence,candidate_path=TARGET,candidate_sha256=hashlib.sha256(WRAPPER).hexdigest(),
        patch_applied=False,production_entry_changed=False,model_job_and_sdk_receipt_are_distinct_schemas=True,
        proposed_readonly_sink='post-exit collection review only',forbidden_sinks=['SharedSequence32.issue','SharedSequence32.consume','claimProcess','claimSelection','A23MakeWaitingBoundPermit'],
        missing_live_prerequisites=['prelaunch_job_to_child_binding','observed_process_provenance','fresh_build_and_consumption_validation','actual_clock_domain_mapping','actual_sdk_runtime','quiet_and_callback_drain','production_permit'],
        correspondence_kind='declared_cross_model_correspondence'),WRAPPER,diff
