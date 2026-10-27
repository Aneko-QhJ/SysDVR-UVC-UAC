"""Dedicated two-epoch preview, explicitly authorized issue, capture and collection."""
from pathlib import Path
import argparse,json,os,shutil,signal,subprocess,sys,tempfile,threading,types,uuid
import a23_shared_sequence32 as old_engine
import build_a23_live_two_epoch as builder
from a23_sequence32_model import encode,sha,require
from analyze_a23_two_epoch_entry import analyze as entry_analyze
w=builder.w


def engine_module(build):
    # Only the verified frozen source is executed, with reviewed schema/capability
    # substitutions. This does not mutate the old engine or its namespace.
    builder.verify(build);module=types.ModuleType('a23_live_shared32')
    raw=(Path(build)/'source/research/usb-ds-iso/tools/a23_shared_sequence32.py').read_text()
    exec(compile(builder.render_engine(raw),'<A23-live-shared32-frozen>','exec'),module.__dict__)
    return module


def fresh_scope(build):
    ref=builder.verify(build)
    child=subprocess.run([str(Path(build)/'verified-entry'),'--check-build',str(build)],capture_output=True,timeout=30)
    require(child.returncode==0,'native fresh live build check rejected')
    value=json.loads(child.stdout);expected=builder.runtime_scope(build)
    require(value['scope']==expected and value['verifier']['failed'] is False,'native/Python live scope differs')
    require(ref==builder.verify(build),'build changed during native check');return expected


def preview(build):
    build=w.canonical(build);scope=fresh_scope(build)
    return dict(schema='A23-live-two-epoch-preview-1',build=builder.verify(build),scope=scope,
        requires_new_explicit_test_authorization=True,record_written=False,sequence_reserved=False,
        receiver_launched=False,remaining=0,usb_requests=0,sd_accesses=0)



def prepare_job(store):
    job=str(uuid.uuid4());ns=store.validate()
    authorization=dict(schema='A23-shared32-authorization-1',job_id=job,scope_sha256=ns['scope_sha256'],
        maximum_invocations=1,simulation=store.simulation,hardware_test_authorized=not store.simulation)
    store.prepare(job,authorization);return job

def issue(build,*,authorized=False):
    require(authorized is True,'new explicit two-epoch test authorization required')
    build=w.canonical(build);module=engine_module(build)
    engine=module.SharedSequence32(builder.FORMAL_ROOT,simulation=False,fresh_scope=lambda:fresh_scope(build))
    if not builder.FORMAL_ROOT.exists():
        historical=builder.previous.authority.inputs()[4];engine.initialize(historical)
    job=prepare_job(engine);issued=engine.issue(job)
    return dict(schema='A23-live-two-epoch-issued-1',job_id=job,job=str(builder.FORMAL_ROOT/'jobs'/job),
        build=str(build),remaining=1,reservation=issued,receiver_launched=False,usb_requests=0,sd_accesses=0)


def context_preflight(build):
    child=subprocess.run([str(Path(build)/'verified-entry'),'--inspect-context'],capture_output=True,timeout=15)
    require(child.returncode==0,'native context inspection failed');r=json.loads(child.stdout)
    require(r['policy_pass'] is True,'native execution context policy failed; no consumption or launch')
    return r


def collect(run):
    run=w.canonical(run);state=w.load(run/'workflow.json')
    require(state['stage']=='exited' and state['creator_wait_verified'] is True and type(state['exit_code']) is int and state['exit_code']==0,'actual parent wait/exit0 missing')
    host=run/'host';w.card.seal_verify(host/'live-final')
    stage=Path(tempfile.mkdtemp(prefix='a23-live-collect-',dir='/private/tmp'))/'host';shutil.copytree(host,stage)
    for name in ('entry-current.json','entry-final-status.json','result.json','receipt-status.json'):
        require(not (stage/name).exists(),'native direct export collision');shutil.copyfile(host/'live-final'/name,stage/name)
    result=entry_analyze(stage)
    scope=state['scope'];binding=w.load(stage/'entry-current.json')['binding'];job=Path(state['job'])
    expected=dict(schema='A23-two-epoch-entry-binding-1',build_manifest_sha256=scope['build_manifest_sha256'],receiver_sha256=scope['receiver_sha256'],
        authorization_receipt_sha256=sha(w.plain(job/'consumed.json')),first_sequence=81,last_sequence=112)
    require(binding==expected,'live collector consumption/entry binding differs')
    for name in ('native-context.json','native-process-claim.json','native-sdk-claim.json'):require((job/name).is_file(),'native claim missing')
    require(w.load(job/'native-context.json')==w.load(stage/'context.json'),'live native/entry context differs')
    selected=w.load(job/'native-sdk-claim.json');host_selected=w.load(stage/'sdk-claim.json')
    require(selected['identity']['device_id']==host_selected['device_id'] and selected['identity']['interface_id']==host_selected['interface_id'] and selected['pid']==host_selected['pid'],'live selected identity differs')
    return dict(schema='A23-live-two-epoch-collection-1',supplied_entry_chain_complete=result['supplied_entry_chain_complete'],entry_analysis=result,
        input_origin=result['sdk']['input_origin'],archive_kind='live_cli_export',hardware_verified=False,physical_run_authenticated=False,continuous_streaming_verified=False,callback_drain_verified=False)



def wait_retained(child,*,power_off_confirmed=lambda:False):
    require(threading.current_thread() is threading.main_thread(),'foreground creator main thread required')
    received=set();errors=[];ack_sent=False;saved={n:signal.getsignal(n) for n in (signal.SIGINT,signal.SIGTERM)}
    def request(number,frame):
        del frame
        received.add(int(number))
        try:child.send_signal(number)
        except OSError as exc:
            if len(errors)<2:errors.append(type(exc).__name__)
    try:
        for n in saved:signal.signal(n,request)
        while True:
            try:return child.wait(timeout=0.5),sorted(received),errors
            except subprocess.TimeoutExpired:
                if not ack_sent:
                    try:confirmed=power_off_confirmed()
                    except (ValueError,OSError,TypeError,KeyError):confirmed=False
                    if confirmed:request(signal.SIGUSR1,None);ack_sent=True
            except KeyboardInterrupt:request(signal.SIGINT,None)
    finally:
        for n,handler in saved.items():signal.signal(n,handler)


def off_receipt(run,job):
    return dict(schema='A23-live-device-off-confirmation-1',run=str(run),job=str(job),operator_power_off_confirmed=True)


def acknowledge_power_off(run,*,confirmed=False):
    require(confirmed is True,'operator must explicitly confirm the Switch is completely powered off')
    run=w.canonical(run);state=w.load(run/'workflow.json')
    require(state['stage']=='running' and state['receiver_launched'] is True and state['run']==str(run),'no running live invocation')
    raw=w.plain(run/'stdout.txt',65536)
    lines=raw.split(b'\n')[:-1]
    require(any(json.loads(line).get('stage')=='unresolved_keep_alive' for line in lines),'native retained-failure report missing')
    value=off_receipt(run,Path(state['job']));w.write(run/'device-off-confirmed.json',value);return value

def capture(build,job,*,execution_mode=None):
    require(execution_mode=='require_escalated','explicit unsandboxed execution mode required')
    require(threading.current_thread() is threading.main_thread(),'foreground creator main thread required')
    build=w.canonical(build);job=w.canonical(job)
    require(job.parent==builder.FORMAL_ROOT/'jobs','formal live job path required')
    module=engine_module(build);module.job_id(job.name)
    engine=module.SharedSequence32(builder.FORMAL_ROOT,simulation=False,fresh_scope=lambda:fresh_scope(build))
    engine.validate();module.check_issue(builder.FORMAL_ROOT,job.name);context=context_preflight(build)
    scope=fresh_scope(build)
    # The consumption attempt is permanent and precedes any receiver launch.
    engine.consume(job.name)
    run=w.ROOT/'private/runs'/('A-two-epoch-'+job.name);run.mkdir(mode=0o700)
    command=[str(build/'verified-entry'),'--acquire-once',str(build),str(job),str(run)]
    state=dict(schema='A23-live-two-epoch-workflow-1',stage='consumed',job=str(job),build=str(build),run=str(run),scope=scope,
        execution_mode=execution_mode,context_preflight=context,command=command,remaining=0,
        automatic_retry=False,creator_wait_verified=False,receiver_launched=False)
    w.write(run/'workflow.json',state)
    with (run/'stdout.txt').open('xb') as out,(run/'stderr.txt').open('xb') as err:
        try:child=subprocess.Popen(command,stdout=out,stderr=err)
        except OSError as exc:
            state.update(stage='launch_failed_no_retry',error=str(exc));w.replace(run/'workflow.json',state);w.b.seal(run);return state
        state.update(stage='running',receiver_launched=True,receiver_pid=child.pid);w.replace(run/'workflow.json',state)
        print(json.dumps(dict(stage='receiver_launched',run=str(run),remaining=0)),flush=True)
        # Native SIGINT/TERM requests stop. A retained native failure deliberately
        # keeps alive; this foreground creator continues holding its direct child.
        code,stops,stop_errors=wait_retained(child,power_off_confirmed=lambda:(run/'device-off-confirmed.json').exists() and w.plain(run/'device-off-confirmed.json')==encode(off_receipt(run,job)))
        state.update(stage='exited',exit_code=code,creator_wait_verified=True,requested_stops=stops,stop_forward_errors=stop_errors);w.replace(run/'workflow.json',state)
    if code==0:
        try:w.write(run/'analysis.json',collect(run))
        except (ValueError,OSError,KeyError,TypeError) as exc:w.write(run/'analysis-error.json',dict(error=str(exc)))
    w.b.seal(run);return state


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path);sub=p.add_subparsers(dest='mode',required=True)
    sub.add_parser('preview');q=sub.add_parser('issue');q.add_argument('--authorized-two-epoch-test',action='store_true')
    q=sub.add_parser('capture');q.add_argument('job',type=Path);q.add_argument('--execution-mode',choices=['require_escalated'],required=True)
    q=sub.add_parser('acknowledge-power-off');q.add_argument('run',type=Path);q.add_argument('--confirmed',action='store_true')
    args=p.parse_args()
    if args.mode!='acknowledge-power-off' and args.build is None:p.error('--build is required for preview/issue/capture')
    try:
        if args.mode=='acknowledge-power-off':r=acknowledge_power_off(args.run,confirmed=args.confirmed)
        elif args.mode=='preview':r=preview(args.build)
        elif args.mode=='issue':r=issue(args.build,authorized=args.authorized_two_epoch_test)
        else:r=capture(args.build,args.job,execution_mode=args.execution_mode)
    except (ValueError,OSError,KeyError,TypeError) as exc:print(json.dumps(dict(passed=False,error=str(exc))));raise SystemExit(2)
    print(json.dumps(r,indent=2))
