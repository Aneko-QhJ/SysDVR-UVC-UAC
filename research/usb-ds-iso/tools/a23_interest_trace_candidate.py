"""Keep every interest fatal; record provider ingress in an isolated derivative."""
import a23_three_epoch_candidate as three

def render(raw):
    raw='#include "a23_interest_trace.h"\n#include <mach/mach_time.h>\n'+raw
    raw=three.change(raw,'@public atomic_bool arrived;','@public atomic_bool arrived;A23InterestTrace trace;')
    raw=three.change(raw,'atomic_init(&arrived,false);','{atomic_init(&arrived,false);a23_interest_init(&trace);}')
    raw=three.change(raw,'atomic_store(&signal->arrived,true);',
        'atomic_store(&signal->arrived,true);\n            a23_interest_record(&signal->trace,message,mach_absolute_time());')
    return three.change(raw,'@"interest_seen":@(atomic_load(&_signal->arrived)),',
        '@"interest_seen":@(atomic_load(&_signal->arrived)),@"interest_trace":a23_interest_dictionary(&_signal->trace,atomic_load(&_signal->arrived)),')
