"""Validate supplied context bytes. Agreement never proves process provenance."""
from pathlib import Path
import re
from analyze_io_usb_host_evidence import require

POLICY=dict(schema='A23-execution-context-policy-1',sample_before='process_claim_and_native_wait',
    required_os_build='26A434',required_framework_uuid='B0D41EEF-C9BF-39DD-A1C4-226DCB94E78B',
    sandbox_query='sandbox_check(self,NULL,0)',required_sandbox_result=0,
    usb_open_permission_proven=False,automatic_privilege_change=False)
KEYS={'schema','pid','ppid','uid','euid','gid','egid','os_build','os_version','machine','receiver_path','receiver_sha256',
    'framework_uuid','sandbox_query_available','sandbox_query_result','sandbox_query_errno','sample_begin_ticks',
    'sample_end_ticks','usb_open_permission_proven','automatic_privilege_change'}

def validate(value,receiver_sha):
    require(type(value) is dict and set(value)==KEYS and value['schema']=='A23-execution-context-1','invalid context schema/inventory')
    for key in ('pid','ppid','uid','euid','gid','egid','sample_begin_ticks','sample_end_ticks','sandbox_query_result','sandbox_query_errno'):
        require(type(value[key]) is int and value[key]>=0,'invalid context number '+key)
    for key in ('os_build','os_version','machine','receiver_path','receiver_sha256','framework_uuid'):
        require(type(value[key]) is str and value[key],'invalid context string '+key)
    require(value['pid']>0 and 0<value['sample_begin_ticks']<=value['sample_end_ticks'],'invalid context process/ticks')
    require(Path(value['receiver_path']).is_absolute() and type(receiver_sha) is str and re.fullmatch('[0-9a-f]{64}',receiver_sha) and
        value['receiver_sha256']==receiver_sha,'context receiver differs')
    require(value['os_build']==POLICY['required_os_build'] and value['framework_uuid']==POLICY['required_framework_uuid'],'context system/framework differs')
    require(value['sandbox_query_available'] is True and value['sandbox_query_result']==0 and value['sandbox_query_errno']==0,'sandbox state unknown or active')
    require(value['usb_open_permission_proven'] is False and value['automatic_privilege_change'] is False,'context grants unsupported authority')
    return dict(supplied_context_consistent=True,process_origin_authenticated=False,usb_open_permission_proven=False)

def model(receiver_sha,receiver_path):
    """Synthetic static bytes for injected/file-only tests, never a live probe."""
    return dict(schema='A23-execution-context-1',pid=123,ppid=122,uid=501,euid=501,gid=20,egid=20,
        os_build=POLICY['required_os_build'],os_version='27.0.1',machine='arm64',receiver_path=str(receiver_path),receiver_sha256=receiver_sha,
        framework_uuid=POLICY['required_framework_uuid'],sandbox_query_available=True,sandbox_query_result=0,sandbox_query_errno=0,
        sample_begin_ticks=1,sample_end_ticks=2,usb_open_permission_proven=False,automatic_privilege_change=False)
