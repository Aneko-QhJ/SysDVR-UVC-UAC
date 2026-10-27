"""Independent exact-integer audit of provided simulation clock observations."""
from analyze_io_usb_host_evidence import require, integer


def duration_ns(begin,end,numerator,denominator):
    if not all(integer(v) for v in (begin,end)) or end < begin or not integer(numerator,1,2**32-1) or not integer(denominator,1,2**32-1):
        return None
    result=((end-begin)*numerator+denominator-1)//denominator
    return result if result <= 2**64-1 else None


def audit_admission(detail,frame,hardware=False):
    require(detail.get('source')==('sdk_runtime_budget' if hardware else 'mock_runtime_budget'), 'invalid admission source')
    for key in ('check_ticks','return_ticks','query_ns','age_ns','call_ns'):
        require(integer(detail.get(key)),f'invalid admission {key}')
    for key in ('timebase_numerator','timebase_denominator'):
        require(integer(detail.get(key),0,2**32-1) and detail[key]==frame[key], 'admission/frame timebase mismatch')
    for key in ('converted','duration_valid','admitted','forwarded','accepted','budget_pass'):
        require(type(detail.get(key)) is bool,f'invalid admission {key}')
    n,d=detail['timebase_numerator'],detail['timebase_denominator']
    ordered=frame['begin_ticks'] <= frame['end_ticks'] <= detail['check_ticks']
    query=duration_ns(frame['begin_ticks'],frame['end_ticks'],n,d) if ordered else None
    age=duration_ns(frame['begin_ticks'],detail['check_ticks'],n,d) if query is not None else None
    converted=ordered and query is not None and age is not None
    admitted=converted and query<=2000000 and age<=4000000
    call=duration_ns(detail['check_ticks'],detail['return_ticks'],n,d)
    passed=bool(admitted and call is not None and call<=2000000)
    require(detail['query_ns']==(query or 0) and detail['age_ns']==(age or 0) and detail['call_ns']==(call or 0) and
            detail['converted']==converted and detail['duration_valid']==(call is not None) and
            detail['admitted']==admitted and detail['forwarded']==admitted and detail['budget_pass']==passed,
            'admission calculation mismatch')
    require(admitted or (detail['accepted'] is False and detail['return_ticks']==detail['check_ticks']),
            'rejected admission fabricated an enqueue')
    return passed
