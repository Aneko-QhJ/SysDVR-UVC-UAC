"""Pure fixture job/launch/receipt correlation. No permit or live provenance."""
import uuid
import a23_supervisor_unified_materials as supervisor
from a23_supervisor_job_link import FALSE as PRIOR_FALSE
require,encode,parse,sha=supervisor.require,supervisor.encode,supervisor.parse,supervisor.sha
inventory=supervisor.old.inventory
MODES=('normal','abnormal-exit','timeout-after-output','spawn-error','missing-receipt',
       'partial-receipt','wrong-nonce','wrong-job','tampered-material','stderr-output')
FALSE={**PRIOR_FALSE,'cached_sdk_materials_generated_this_launch':False,
       'production_integrated':False,'os_capability_isolation_verified':False}


def same(a,b,message):require(encode(a)==encode(b),message)
def digest(v):return type(v) is str and len(v)==64 and all(c in '0123456789abcdef' for c in v)


def manifest(job_id,nonce,mode,fixture_sha,source_pin,materials):
    return dict(schema='A23-fixture-job-launch-1',fixture_job_id=job_id,launch_nonce=nonce,
        fixture_mode=mode,fixture_sha256=fixture_sha,source_review_sha256=source_pin,
        seed_files=inventory(materials),cached_materials_origin='historical_model_cache',
        maximum_launches=1,model_only=True,production_execution_authorized=False)


def check_launch(raw,pin):
    require(type(raw) is bytes and digest(pin) and sha(raw)==pin,'external launch pin differs')
    v=parse(raw)
    require(type(v) is dict and type(v.get('fixture_job_id')) is str and
        str(uuid.UUID(v['fixture_job_id']))==v['fixture_job_id'],'fixture UUID differs')
    require(v.get('fixture_mode') in MODES and digest(v.get('launch_nonce')) and
        digest(v.get('fixture_sha256')) and digest(v.get('source_review_sha256')),'fixture launch identity differs')
    files=v['seed_files']
    require(type(files) is dict and bool(files),'seed inventory required')
    for name,row in files.items():
        require(type(name) is str and not name.startswith('/') and all(p not in ('','.','..') for p in name.split('/')),'seed path differs')
        require(type(row) is dict and set(row)=={'bytes','sha256'} and type(row['bytes']) is int and
            0<=row['bytes']<=64*1024*1024 and digest(row['sha256']),'seed inventory entry differs')
    expected=dict(schema='A23-fixture-job-launch-1',fixture_job_id=v['fixture_job_id'],launch_nonce=v['launch_nonce'],
        fixture_mode=v['fixture_mode'],fixture_sha256=v['fixture_sha256'],source_review_sha256=v['source_review_sha256'],
        seed_files=files,cached_materials_origin='historical_model_cache',maximum_launches=1,
        model_only=True,production_execution_authorized=False)
    same(v,expected,'fixture launch schema/authority differs');return v


def attempt(launch_raw):
    v=parse(launch_raw)
    return dict(schema='A23-fixture-launch-attempt-1',fixture_job_id=v['fixture_job_id'],launch_nonce=v['launch_nonce'],
        launch_sha256=sha(launch_raw),attempt_number=1,spent_before_spawn=True,model_only=True)


def report(launch_raw,attempt_raw,materials):
    v=parse(launch_raw)
    return dict(schema='A23-fixture-bound-report-1',fixture_job_id=v['fixture_job_id'],launch_nonce=v['launch_nonce'],
        launch_sha256=sha(launch_raw),attempt_sha256=sha(attempt_raw),material_files=inventory(materials),
        cached_materials_origin='historical_model_cache',model_only=True,production_execution_authorized=False)


def receipt(launch_raw,attempt_raw,stdout,materials):
    v=report(launch_raw,attempt_raw,materials);v['schema']='A23-fixture-bound-receipt-1';v['stdout_sha256']=sha(stdout)
    return v


def observation(launch_raw,attempt_raw,o):
    return dict(schema='A23-fixture-job-supervision-1',launch_sha256=sha(launch_raw),
        attempt_sha256=sha(attempt_raw),fixture_mode=parse(launch_raw)['fixture_mode'],supervisor=o)


def assess(launch_raw,pin,attempt_raw,observed,out,err,materials,receipt_raw):
    v=check_launch(launch_raw,pin);errors=[];bound=False;checked=None
    try:
        same(parse(attempt_raw),attempt(launch_raw),'one-shot attempt differs')
        same(observed,observation(launch_raw,attempt_raw,observed['supervisor']),'supervision launch binding differs')
        o=observed['supervisor'];supervisor.check('normal',o,out,err)
    except (ValueError,KeyError,TypeError,UnicodeError):errors.append('attempt_or_observation');o=None
    try:
        require(type(materials) is dict and all(type(n) is str and type(raw) is bytes for n,raw in materials.items()),'byte materials required')
        same(inventory(materials),v['seed_files'],'launch input/result bytes differ')
        same(parse(out),report(launch_raw,attempt_raw,materials),'child stdout binding differs')
        same(parse(receipt_raw),receipt(launch_raw,attempt_raw,out,materials),'post-exit receipt differs')
        bound=True
    except (ValueError,KeyError,TypeError,UnicodeError):errors.append('receipt_or_materials')
    if o is not None:
        try:
            # Raw wrapper stdout counts were checked above. Only the nested cached
            # report is synthesized for the existing historical-material policy.
            cached=encode(supervisor.old.stdout_report('normal','normal',materials))
            nested={**o,'stdout_bytes':len(cached)}
            checked=supervisor.assess('normal',nested,cached,err,materials)
        except (ValueError,KeyError,TypeError,UnicodeError,IndexError):errors.append('cached_materials')
    if checked is not None and not checked['completion_admitted']:errors.append('supervisor_or_cached_failure')
    return dict(schema='A23-fixture-job-result-1',fixture_job_id=v['fixture_job_id'],fixture_mode=v['fixture_mode'],
        relation_kind='fixture_launch_result_correspondence',model_only=True,attempt_spent=True,
        receipt_binding_valid=bound,fixture_completion=bool(bound and not errors and checked and checked['completion_admitted']),
        cached_materials_valid=checked['materials_valid'] if checked else False,errors=errors,
        consumer_filesystem_calls=0,**FALSE)
