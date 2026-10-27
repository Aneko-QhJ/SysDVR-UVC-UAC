#include "a23_lead32_policy.h"
#include <assert.h>
#include <stdio.h>
int main(void) {
    assert(A23Lead32Admission(2000000,4000000));
    assert(!A23Lead32Admission(2000001,4000000));
    assert(!A23Lead32Admission(2000000,4000001));
    assert(A23Lead32Call(2000000));assert(!A23Lead32Call(2000001));
    assert(A23Lead32Trigger(2000000,8000000));
    assert(!A23Lead32Trigger(2000001,8000000));
    assert(!A23Lead32Trigger(2000000,8000001));
    assert(!A23Lead32Trigger(UINT64_MAX,UINT64_MAX));
    assert(!A23Lead32Admission(UINT64_MAX,UINT64_MAX));
    assert(!A23Lead32Call(UINT64_MAX));
    puts("11 exact boundary/overflow checks passed; no device access");
}
