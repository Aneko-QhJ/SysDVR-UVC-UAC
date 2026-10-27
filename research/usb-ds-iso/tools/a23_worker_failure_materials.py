"""Pure byte admission for the specified offline worker fixtures, not provenance."""
from a23_concurrent_diagnostics import require,encode,sha,parse,bundle
NAMES=('normal-readonly','normal-finish','error-before-begin','exit-before-begin','unfinished-return','unfinished-exit','abort-error','invalid-finish','wrong-ticket','exhausted-begin','last-finish-exhausted','replacement-store','explicit-abort-after-join')
U64=2**64-1
FILES=('clock.json','manifest.json','worker.json')


def expected(name):
    require(name in NAMES,'unknown worker schedule')
    no_begin=name in ('normal-readonly','error-before-begin','exit-before-begin','replacement-store')
    exit_code=9 if name in ('exit-before-begin','unfinished-exit') else 7 if name in ('error-before-begin','unfinished-return','abort-error','explicit-abort-after-join') else 0
    unfinished=name in ('unfinished-return','unfinished-exit','wrong-ticket')
    poisoned=name in ('invalid-finish','exhausted-begin','last-finish-exhausted')
    begin_generation=U64-1 if name=='exhausted-begin' else U64-3 if name=='last-finish-exhausted' else 2
    generation=begin_generation if no_begin or name=='exhausted-begin' else begin_generation+1 if unfinished else begin_generation+2
    end_status=5 if poisoned else 3 if unfinished else 0
    end_generation=0 if end_status else 2 if name=='replacement-store' else generation
    evaluate=-1 if end_status else 4 if name in ('normal-finish','abort-error','replacement-store','explicit-abort-after-join') else 0
    worker=dict(created=True,joined=True,join_status=0,exit_code=exit_code,tail_reached=name not in ('exit-before-begin','unfinished-exit'),begin_attempted=not no_begin,
                begin_status=-1 if no_begin else 6 if name=='exhausted-begin' else 0,
                finish_status=2 if name=='invalid-finish' else 4 if name=='wrong-ticket' else 0 if name in ('normal-finish','last-finish-exhausted') else -1,
                abort_status=0 if name=='abort-error' else -1,ticket=0 if no_begin or name=='exhausted-begin' else begin_generation+1)
    clock=dict(pre_status=0,end_status=end_status,pre_generation=begin_generation,end_generation=end_generation,generation=generation,poisoned=poisoned,
               reader_calls=1 if end_status else 2,evaluate=evaluate,minimum_met=evaluate==0,end_zeroed=bool(end_status),
               same_store=not end_status and name!='replacement-store',recovery_status=0 if name=='explicit-abort-after-join' else -1,
               exhaustion_status=6 if name=='last-finish-exhausted' else -1)
    return dict(case=name,worker=worker,clock=clock)


def package(row):
    """Serialize observed native output. Does not independently authenticate it."""
    name=row['case'];cache={}
    for key in ('worker','clock'):cache[key+'.json']=encode(dict(schema='A23-worker-'+key+'-1',case=name,value=row[key]))
    cache['manifest.json']=encode(dict(schema='A23-worker-materials-1',case=name,worker_sha256=sha(cache['worker.json']),clock_sha256=sha(cache['clock.json'])))
    sums=''.join(sha(cache[n])+'  '+n+'\n' for n in FILES).encode();cache['SHA256SUMS']=sums;cache['COMMITTED']=(sha(sums)+'\n').encode();return cache


def admit(name,cache):
    require(name in NAMES and type(cache) is dict,'declared worker materials required')
    require(all(type(k) is str and type(v) is bytes for k,v in cache.items()),'worker materials must be bytes')
    bundle(cache,'',FILES)
    values={}
    for key in ('worker','clock'):
        obj=parse(cache[key+'.json'])
        require(type(obj) is dict and set(obj)=={'schema','case','value'} and obj['schema']=='A23-worker-'+key+'-1' and obj['case']==name,'worker export binding differs')
        values[key]=obj['value']
    manifest=dict(schema='A23-worker-materials-1',case=name,worker_sha256=sha(cache['worker.json']),clock_sha256=sha(cache['clock.json']))
    require(encode(parse(cache['manifest.json']))==encode(manifest),'worker manifest differs')
    row=dict(case=name,**values);require(encode(row)==encode(expected(name)),'specified worker outcome differs')
    w=values['worker'];c=values['clock']
    healthy=w['exit_code']==0 and w['tail_reached'] and all(w[k] in (-1,0) for k in ('begin_status','finish_status','abort_status'))
    quiet=c['evaluate']==0 and c['minimum_met']
    return dict(passed=True,case=name,evidence_complete=True,worker_success=healthy,clock_eligible=quiet,completion_eligible=healthy and quiet,
                consumer_filesystem_calls=0,provenance_authenticated=False,full_driver_executed=False)
