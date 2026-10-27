#import "io_usb_host_runtime_guard.h"
#include <mach/mach_time.h>

BOOL A23TicksToNanoseconds(uint64_t ticks, uint32_t numerator, uint32_t denominator, uint64_t *result)
{
    if (!numerator || !denominator || !result) return NO;
    __uint128_t scaled = (__uint128_t)ticks * numerator;
    scaled = (scaled + denominator - 1) / denominator; // Conservative ceiling.
    if (scaled > UINT64_MAX) return NO;
    *result = (uint64_t)scaled; return YES;
}
NSDictionary *A23RuntimeBudget(void)
{
    return @{@"schema":@"A23-runtime-budget-1",@"max_frame_query_ns":@2000000,@"max_frame_age_ns":@16000000,
        @"max_enqueue_call_ns":@8000000,@"frame_period_ns_assumption":@1000000,@"reserve_ns":@16000000,
        @"exit_grace_ns":@1000000000,@"hardware_timing_verified":@NO};
}
@implementation A23LocalMachClock {
    mach_timebase_info_data_t _info;
}
- (instancetype)init { if ((self = [super init])) mach_timebase_info(&_info); return self; }
- (uint64_t)nowTicks { return mach_absolute_time(); }
- (uint32_t)numerator { return _info.numer; }
- (uint32_t)denominator { return _info.denom; }
@end

@implementation A23BudgetTransport {
    id<A23TransactionTransport> _transport;
    id<A23RuntimeClock> _clock;
    NSDictionary *_sample, *_result;
    BOOL _attempted;
}
- (instancetype)initWithTransport:(id<A23TransactionTransport>)transport clock:(id<A23RuntimeClock>)clock sample:(NSDictionary *)sample
{
    if (!transport || !clock || !sample) return nil;
    if ((self = [super init])) { _transport = transport; _clock = clock; _sample = [sample copy]; }
    return self;
}
- (BOOL)enqueueIORequestWithData:(NSMutableData *)data transactionList:(IOUSBHostIsochronousTransaction *)rows
    transactionListCount:(NSUInteger)count firstFrameNumber:(uint64_t)frame options:(IOUSBHostIsochronousTransferOptions)options
    error:(NSError **)error completionHandler:(IOUSBHostIsochronousTransactionCompletionHandler)completion
{
    if (_attempted) return NO;
    _attempted = YES;
    uint64_t begin = [_sample[@"begin_ticks"] unsignedLongLongValue], end = [_sample[@"end_ticks"] unsignedLongLongValue];
    uint32_t numerator = _clock.numerator, denominator = _clock.denominator;
    uint64_t check = [_clock nowTicks], queryNS = 0, ageNS = 0, callNS = 0;
    BOOL ordered = begin <= end && end <= check;
    BOOL converted = ordered && A23TicksToNanoseconds(end-begin,numerator,denominator,&queryNS) &&
        A23TicksToNanoseconds(check-begin,numerator,denominator,&ageNS);
    BOOL admitted = converted && queryNS <= 2000000 && ageNS <= 16000000;
    BOOL accepted = NO;
    uint64_t finish = check;
    if (admitted) {
        accepted = [_transport enqueueIORequestWithData:data transactionList:rows transactionListCount:count
            firstFrameNumber:frame options:options error:error completionHandler:completion];
        finish = [_clock nowTicks];
    } else if (error) *error = [NSError errorWithDomain:@"A23Admission" code:1 userInfo:nil];
    BOOL durationValid = finish >= check && A23TicksToNanoseconds(finish-check,numerator,denominator,&callNS);
    BOOL budget = admitted && durationValid && callNS <= 8000000;
    _result = @{@"source":@"mock_runtime_budget",@"check_ticks":@(check),@"return_ticks":@(finish),
        @"timebase_numerator":@(numerator),@"timebase_denominator":@(denominator),@"query_ns":@(queryNS),@"age_ns":@(ageNS),
        @"call_ns":@(callNS),@"converted":@(converted),@"duration_valid":@(durationValid),@"admitted":@(admitted),
        @"forwarded":@(admitted),@"accepted":@(accepted),@"budget_pass":@(budget)};
    return accepted;
}
- (BOOL)abortWithOption:(IOUSBHostAbortOption)option error:(NSError **)error
{ return [_transport abortWithOption:option error:error]; }
- (NSDictionary *)result { return _result; }
@end
@implementation A23SDKBudgetTransport
- (NSDictionary *)result
{
    NSDictionary *original = [super result]; if (!original) return nil;
    NSMutableDictionary *record = [original mutableCopy]; record[@"source"] = @"sdk_runtime_budget"; return record;
}
@end
