"""Complete the 96-member byte scope and join saved bootstrap declarations.

Saved stat tuples and worker exits are declarations, never fresh OS evidence.
The supported successful profile requires a declared zero worker exit status.
"""
import stat
import a23_cached_collection_links as collection

prior=collection.prior
permit=collection.permit
view,ar,a,f=collection.view,collection.ar,collection.a,collection.f
NAMES=('FORENSIC_ATTEMPT','analysis.json','capture.json','job.json')
CAPTURE_FLAGS=(*collection.ENVELOPE_FLAGS,'retry_authorized','worker_origin_authenticated','bootstrap_repair_authorized')
JOURNAL_FLAGS=tuple(k for k in CAPTURE_FLAGS if k!='bootstrap_repair_authorized')
FALSE={**collection.FALSE,'historical_stat_identity_authenticated':False,
       'bootstrap_worker_exit_authenticated':False,'whole_archive_runtime_semantics_verified':False}
SCRATCH='journal/envelope/supervision/scratch'


def contract(raw,journal):
    return dict(schema='A23-cached-outer-contract-1',source_manifest_sha256=journal[3],
                raw_contract_sha256=f.sha(f.encode(journal[1])),files=a.inventory(raw),**FALSE)


def outer_scope(spec,journal):
    f.require(type(spec) is tuple and len(spec)==3,'outer cache tuple differs')
    cache,expected,commit=spec
    f.require(type(cache) is view.PinnedBytes and cache.files==NAMES,'outer cache file scope differs')
    raw={n:cache.read(n) for n in cache.files}
    f.require(all(type(v) is bytes and len(v)<=65536 for v in raw.values()) and
              sum(map(len,raw.values()))<=131072,'outer byte budget differs')
    wanted=contract(raw,journal)
    collection.equal(expected,wanted,'outer contract differs')
    f.require(cache.contract_sha256==f.sha(f.encode(wanted)),'outer cache contract pin differs')
    f.require(type(commit) is bytes and commit==(journal[3]+'\n').encode(),'outer COMMITTED differs')
    entries=prior.partial.manifest_entries(journal[2],journal[3])
    jraw=prior.verify_scope(*journal)
    union={**raw,**{'raw/'+n:v for n,v in jraw.items()}}
    f.require(set(entries)==set(union) and a.sums(union)==journal[2],
              'outer plus raw bytes do not exactly cover manifest')
    f.require(raw['job.json']==journal[4],'outer job differs from cached worker declaration')
    f.require(raw['FORENSIC_ATTEMPT']==b'one bootstrap forensic copy\n','bootstrap forensic attempt differs')
    return raw,jraw


def capture_shape(outer,receiver,supervisor):
    meta=prior.partial.json_object(outer['capture.json'])
    f.require(set(meta)=={'schema','receiver_build','supervisor_build','capture','raw_files','raw_directories',
              'observation',*CAPTURE_FLAGS} and meta['schema']=='A23-bootstrap-capture-1' and
              all(meta[k] is False for k in CAPTURE_FLAGS),'capture shape/authority differs')
    collection.equal(meta['receiver_build'],receiver['reference'],'capture receiver differs')
    collection.equal(meta['supervisor_build'],supervisor['reference'],'capture supervisor differs')
    return meta


def inventory(meta,raw,journal):
    collection.equal(meta['raw_files'],a.inventory(raw),'capture raw inventory differs')
    # Empty source scratch is a historical declaration. "empty" belongs only
    # to the later detached-cache contract; neither is file-manifest evidence.
    declared=sorted(set(a.prefixes(raw))|{SCRATCH})
    collection.equal(meta['raw_directories'],declared,'historical directory profile differs')
    f.require(journal[1]['directories']==sorted(set(a.prefixes(raw))|{'empty'}),'detached cache directory profile differs')
    return dict(raw_files=len(raw),historical_declared_directories=len(declared),
                historical_empty_directories=[SCRATCH],detached_only_directories=['empty'])


def identities(meta,raw):
    capture=meta['capture']
    f.require(type(capture) is dict and set(capture)=={'source','marker','journal'},'capture components differ')
    seen=set()
    for name,part in capture.items():
        f.require(type(part) is dict and set(part)=={'state','stable','identity','skipped'} and
                  part['state']==('regular' if name=='marker' else 'directory') and
                  part['stable'] is True and part['skipped']==[],'successful capture component differs')
        ident=part['identity']
        f.require(type(ident) is list and len(ident)==6 and
                  all(permit.session.number(v) for v in ident) and 0<ident[1] and ident[2]<=65535,
                  'saved stat tuple type/range differs')
        f.require((stat.S_ISREG(ident[2]) if name=='marker' else stat.S_ISDIR(ident[2])),
                  'saved stat mode differs from component')
        key=tuple(ident[:2]);f.require(key not in seen,'distinct capture components share stat identity');seen.add(key)
        if name=='marker':f.require(ident[3]==len(raw['source-marker']),'saved marker size differs')
    return dict(declared_stable=True,declared_safe=True,stat_tuples_checked=3,
                live_stat_queries=0,stat_times_compared_to_driver=False)


def worker(meta,outer,raw):
    o=meta['observation']
    f.require(type(o) is dict and set(o)=={'mode','worker_exited','pid','returncode','job_sha256'} and
              o['job_sha256']==f.sha(outer['job.json']),'bootstrap worker observation/job differs')
    if o['mode']=='supplied_static_bootstrap':
        f.require(o['worker_exited'] is False and o['pid'] is None and o['returncode'] is None,
                  'static bootstrap claims exit')
    else:
        f.require(o['mode']=='observed_bootstrap_worker_exit' and o['worker_exited'] is True and
                  permit.session.number(o['pid'],1,2**31-1) and permit.session.number(o['returncode'],0,0),
                  'successful bootstrap worker exit declaration differs')
    # The worker PID describes the collector, not its supervised model child.
    marker=prior.partial.attempt_shape(raw['source-marker'])
    return dict(mode=o['mode'],worker_exit_declared=o['worker_exited'],declared_worker_pid=o['pid'],
                declared_returncode=o['returncode'],model_child_pid=marker['child_pid'])


def saved_summary(outer,raw):
    journal=dict(schema='A23-collection-journal-analysis-1',journal_committed=True,
                 classification='completed_model_collection',complete_injected_model_chain=True,
                 last_event=prior.PHASES[-1],events=len(prior.PHASES),failure_recorded=False,
                 inner_envelope_sealed=True,attempt_sha256=f.sha(raw['source-marker']),
                 **{k:False for k in JOURNAL_FLAGS})
    expected=dict(schema='A23-bootstrap-analysis-1',classification='completed_model_collection',
                  capture_stable=True,capture_safe=True,source_attempt_valid=True,journal_committed=True,
                  complete_injected_model_chain=True,journal_inspection=journal,errors=[],
                  **{k:False for k in CAPTURE_FLAGS})
    collection.equal(prior.partial.json_object(outer['analysis.json']),expected,'saved bootstrap summary differs')
    return dict(saved_full_chain_claim=True,saved_journal_events=len(prior.PHASES),
                summary_fields_match_cached_subsets=True)


def consume(receiver,supervisor,journal,link_bytes,link_digest,profile_bytes,profile_digest,outer):
    result=dict(schema='A23-cached-outer-forensics-1',classification='inconsistent_cached_outer_forensics_subset',
                errors=[],reasons={},observations={},complete_manifest_byte_coverage=False,
                prior_subsets_consistent=False,**FALSE)
    def check(name,action):
        try:return action()
        except (ValueError,KeyError,TypeError,UnicodeError,RecursionError,IndexError) as exc:
            result['errors'].append(name);result['reasons'][name]=str(exc);return None
    scope=check('outer_scope',lambda:outer_scope(outer,journal))
    if scope is None:return result
    out,raw=scope;result['complete_manifest_byte_coverage']=True
    result['observations']['byte_scope']=dict(raw_files=len(raw),outer_files=len(out),manifest_members=len(raw)+len(out))
    base=collection.consume(receiver,supervisor,journal,link_bytes,link_digest,profile_bytes,profile_digest)
    if base['errors']:
        result['errors']=['prior_subset'];result['reasons']['prior_subset']=','.join(base['errors']);return result
    result['prior_subsets_consistent']=True
    rcache,_=permit.session.build.grouped.consume(*receiver)
    scache,_=permit.session.build.grouped.consume(*supervisor)
    r=permit.session.build.verify_receiver(rcache);s=permit.session.build.verify_supervisor(scache)
    meta=check('capture_shape',lambda:capture_shape(out,r,s))
    if meta is not None:
        for name,action in (('capture_inventory',lambda:inventory(meta,raw,journal)),
                            ('capture_identities',lambda:identities(meta,raw)),
                            ('worker_observation',lambda:worker(meta,out,raw)),
                            ('saved_summary',lambda:saved_summary(out,raw))):
            value=check(name,action)
            if value is not None:result['observations'][name]=value
    if not result['errors']:result['classification']='consistent_cached_outer_forensics_declarations_subset'
    return result
