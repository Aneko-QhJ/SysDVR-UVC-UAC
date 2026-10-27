"""Pure guardian-owned worker handoff/wait comparison; never production authority."""
import a23_parent_crash_materials as prior
import a23_fixture_recovery as publication
integrated=prior.integrated
require,encode,parse,sha=prior.require,prior.encode,prior.parse,prior.sha
FALSE=prior.FALSE
CASES=('normal','before-request','after-request','worker-unrecorded','owner-partial','owner-synced','after-handoff',
    'child-payload.begin','child-receipt.partial','child-receipt.link','child-stdout.emit','after-parent-report',
    'handoff-job-mismatch','handoff-nonce-mismatch','handoff-repeat','guardian-gate-closed')
NO_WORKER={'before-request','after-request'}
EARLY_KILL={'worker-unrecorded','owner-partial','owner-synced'}
SELF_EXIT={'before-request','after-request','after-handoff','after-parent-report'}
REJECT={'handoff-job-mismatch','handoff-nonce-mismatch','handoff-repeat'}


def plan(case,files,code,source_pin):
    return dict(schema='A23-guardian-owned-plan-1',scenario=case,launch_sha256=sha(files['launch.json']),
        integrated_plan_sha256=sha(files['integrated-plan.json']),code_sha256=code,source_review_sha256=source_pin,
        worker_creator='guardian',maximum_handoffs=1,model_only=True,production_execution_authorized=False)


def use_record(raw,v):return dict(schema='A23-guardian-owned-use-1',owned_plan_sha256=sha(raw),launch_sha256=v['launch_sha256'],maximum_calls=1,model_only=True)


def handoff(raw,v,launch,g,p,w):
    return dict(schema='A23-guardian-owned-handoff-1',fixture_job_id=launch['fixture_job_id'],launch_nonce=launch['launch_nonce'],
        owned_plan_sha256=sha(raw),launch_sha256=v['launch_sha256'],integrated_plan_sha256=v['integrated_plan_sha256'],
        requester_pid=p,guardian_pid=g,worker_pid=w,maximum_accepts=1,model_only=True,production_execution_authorized=False)


def requester(kind,launch,pin,g,p,**extra):
    return dict(schema='A23-guardian-requester-message-1',kind=kind,requester_pid=p,guardian_pid=g,fixture_job_id=launch['fixture_job_id'],
        launch_nonce=launch['launch_nonce'],owned_plan_sha256=pin,model_only=True,**extra)


def result(h,rc):return dict(schema='A23-guardian-owned-result-1',handoff_sha256=sha(encode(h)),worker_pid=h['worker_pid'],returncode=rc,
    worker_waited=True,model_only=True,production_execution_authorized=False)


def check(raw,pin,files):
    require(type(raw) is bytes and integrated.binding.digest(pin) and sha(raw)==pin,'external guardian owned plan pin differs')
    v=parse(raw);require(type(v) is dict and v.get('scenario') in CASES,'guardian owned scenario differs')
    require(type(v['code_sha256']) is dict and len(v['code_sha256'])==6 and all(type(n) is str and not n.startswith('/') and '..' not in n.split('/') and integrated.binding.digest(h) for n,h in v['code_sha256'].items()),'guardian owned code pins differ')
    require(integrated.binding.digest(v['source_review_sha256']),'guardian source pin differs')
    integrated.binding.same(v,plan(v['scenario'],files,v['code_sha256'],v['source_review_sha256']),'guardian owned plan differs')
    require(files['owned-plan.json']==raw and files['crash-plan.json']==raw,'frozen worker compatibility plan alias differs')
    integrated.check_plan(files['integrated-plan.json'],v['integrated_plan_sha256'],files['launch.json']);return v


def assess(raw,pin,files,observation,parent_messages,worker_messages):
    v=check(raw,pin,files);case=v['scenario'];launch=parse(files['launch.json']);errors=[];wait=False;owner=False;accepted=False;child=None;prefix=False
    g=observation.get('guardian_pid');p=observation.get('requester_pid');w=observation.get('worker_pid');seen=case not in NO_WORKER
    try:
        integrated.binding.same(parse(files['guardian-use.json']),use_record(raw,v),'guardian use differs')
        require(type(g) is int and type(p) is int and g>0 and p>0 and g!=p,'guardian/requester PID differs')
        require(observation['schema']=='A23-guardian-owned-observation-1' and observation['provenance_authenticated'] is False,'guardian observation schema differs')
        require(type(observation['requester_returncode']) is int and observation['requester_waited'] is True,'requester wait differs')
        expected_parent=79 if case in SELF_EXIT else 82 if case in REJECT else -9 if case in EARLY_KILL or case.startswith('child-') else 0
        require(observation['requester_returncode']==expected_parent,'requester interruption result differs')
        require(type(observation['worker_seen']) is bool and observation['worker_seen']==seen and observation['journal_pid_signals']==0 and type(observation['journal_pid_signals']) is int,'worker count/signal differs')
        if seen:
            require(type(w) is int and w>0 and w not in (g,p),'guardian worker PID differs')
            require(observation['worker_creator_pid']==g and type(observation['worker_creator_pid']) is int and observation['worker_waited'] is True and type(observation['worker_returncode']) is int,'direct guardian worker wait differs');wait=True
        else:require(w is None and observation['worker_creator_pid'] is None and observation['worker_waited'] is False and observation['worker_returncode'] is None,'unspawned guardian claims wait')
    except (ValueError,KeyError,TypeError,UnicodeError):errors.append('guardian_wait')
    h=handoff(raw,v,launch,g,p,w) if seen else None
    try:
        if seen:
            expected=[prior.message('ready',launch,pin,p,w)]
            if case.startswith('child-'):expected.append(prior.message('checkpoint',launch,pin,p,w,event=case.removeprefix('child-')))
            rc=87 if case=='guardian-gate-closed' else 0 if case in ('normal','after-parent-report') else 86
            reason='guardian_closed' if rc==87 else 'inner_exit' if rc==0 else 'parent_pipe_eof'
            expected.append(prior.message('end',launch,pin,p,w,exit_code=rc,reason=reason))
            integrated.binding.same(worker_messages,expected,'owned worker pipe binding differs')
            require(observation['worker_returncode']==rc,'wait status and worker end disagree')
            trace=[parse(line) for line in files['trace.jsonl'].splitlines()]
            expected_trace=[dict(event=x,outcome='completed') for x in (*integrated.io.PRE_EVENTS,'launch.ready',*integrated.io.CHILD_EVENTS)]
            require(bool(trace) and len(trace)<=len(expected_trace),'owned publication prefix length differs')
            integrated.binding.same(trace,expected_trace[:len(trace)],'owned publication prefix differs');prefix=True
        else:require(worker_messages==[],'unspawned worker has messages')
    except (ValueError,KeyError,TypeError,UnicodeError):errors.append('worker_binding')
    try:
        expected=[] if case=='before-request' else [requester('request',launch,pin,g,p)]
        if seen and case not in EARLY_KILL:
            sent=dict(h)
            if case=='handoff-job-mismatch':sent['fixture_job_id']='00000000-0000-0000-0000-000000000001'
            if case=='handoff-nonce-mismatch':sent['launch_nonce']='0'*64
            require(files['handoff-sent.json']==encode(sent),'sent handoff differs')
            if case in ('handoff-job-mismatch','handoff-nonce-mismatch'):expected.append(requester('rejected',launch,pin,g,p,reason='handoff_binding'))
            else:
                require(files['parent-accept.json']==encode(h),'requester accepted different handoff');accepted=True
                expected.append(requester('accepted',launch,pin,g,p,handoff_sha256=sha(encode(h))))
                if case=='handoff-repeat':
                    require(files['handoff-repeat.json']==encode(h),'repeated handoff differs')
                    expected.append(requester('rejected',launch,pin,g,p,reason='handoff_repeat'))
                if case in ('normal','after-parent-report','guardian-gate-closed'):
                    r=result(h,observation['worker_returncode']);require(files['parent-result.json']==encode(r),'requester result binding differs')
                    expected.append(requester('reported',launch,pin,g,p,result_sha256=sha(encode(r))))
        integrated.binding.same(parent_messages,expected,'requester protocol differs')
    except (ValueError,KeyError,TypeError,UnicodeError):errors.append('handoff')
    if seen:
        try:require(files['guardian-owner.json']==encode(h),'guardian owner journal differs');owner=True
        except (ValueError,KeyError,TypeError):pass
        if case not in ('worker-unrecorded','owner-partial') and not owner:errors.append('owner')
        try:
            # Mechanical projection removes the new launch.ready boundary for
            # the frozen publication consumer. Actual guardian wait/exit remain
            # separate checks above; synthetic plan grants no authority.
            projected=dict(files);projected['trace.jsonl']=b'\n'.join(encode(parse(line)) for line in files['trace.jsonl'].splitlines() if parse(line)['event']!='launch.ready')+b'\n'
            pub=encode(publication.plan(files['launch.json'],v['code_sha256']['lib/a23_fixture_publication.py']))
            projected['publication-plan.json']=pub;out=files['worker-stdout.bin'];err=files['worker-stderr.bin']
            child=publication.assess(pub,sha(pub),projected,out,err,publication.observation(observation['worker_returncode'],out,err))
        except (ValueError,KeyError,TypeError,UnicodeError):errors.append('publication')
    complete=bool(case=='normal' and not errors and wait and owner and accepted and prefix and child and child['publication_model_complete'])
    return dict(schema='A23-guardian-owned-result-analysis-1',scenario=case,fixture_job_id=launch['fixture_job_id'],model_only=True,
        guardian_worker_wait_model_valid=wait,owner_record_valid=owner,missing_or_partial_owner_with_wait=bool(wait and not owner),
        handoff_accepted=accepted,publication_prefix_valid=prefix,worker_publication_model_complete=child['publication_model_complete'] if child else False,
        guardian_owned_model_complete=complete,errors=errors,consumer_filesystem_calls=0,**FALSE)
