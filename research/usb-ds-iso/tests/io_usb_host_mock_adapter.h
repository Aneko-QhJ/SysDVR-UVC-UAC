#pragma once
#import "../host/io_usb_host_sdk_adapter.h"
#include <assert.h>
#include <mach/mach_time.h>
#include <string.h>
#include <unistd.h>

static NSDictionary *candidate(void)
{
    uint8_t d[] = {18,1,0,2,0,0,0,64,9,0x12,0x57,0xca,0,1,0,0,0,1};
    uint8_t c[] = {9,2,25,0,1,1,0,0x80,50,9,4,2,0,1,0xff,0x49,1,0,7,5,0x83,1,0,1,1};
    return @{@"service_token":@7,@"device_id":@101,@"interface_id":@102,@"parent_device_id":@101,
        @"connection_speed":@3,@"device_descriptor":[NSData dataWithBytes:d length:sizeof(d)],
        @"configuration_descriptor":[NSData dataWithBytes:c length:sizeof(c)]};
}
@interface AdapterPipe : NSObject <A23TransactionTransport>
@property NSUInteger submissions;
@property NSUInteger aborts;
@property BOOL abortAllowed;
@property unsigned enqueueDelayUS;
@property NSMutableData *data;
@property IOUSBHostIsochronousTransaction *rows;
@property(copy) IOUSBHostIsochronousTransactionCompletionHandler callback;
@end
@implementation AdapterPipe
- (BOOL)enqueueIORequestWithData:(NSMutableData *)data transactionList:(IOUSBHostIsochronousTransaction *)rows
    transactionListCount:(NSUInteger)count firstFrameNumber:(uint64_t)frame options:(IOUSBHostIsochronousTransferOptions)options
    error:(NSError **)error completionHandler:(IOUSBHostIsochronousTransactionCompletionHandler)completion
{
    (void)error; assert(data.length == 184320 && count == 960 && frame == 100 && options == 0);
    assert(++_submissions == 1); _data = data; _rows = rows; _callback = completion;
    if (_enqueueDelayUS) usleep(_enqueueDelayUS);
    return YES;
}
- (BOOL)abortWithOption:(IOUSBHostAbortOption)option error:(NSError **)error
{
    assert(option == IOUSBHostAbortOptionAsynchronous && ++_aborts == 1);
    if (!_abortAllowed && error) *error = [NSError errorWithDomain:@"mock-abort" code:-18 userInfo:nil];
    return _abortAllowed;
}
@end
@interface AdapterInterface : NSObject <A23AdapterInterface>
@property NSString *fault;
@property NSUInteger destroys, allocations;
@property AdapterPipe *pipe;
@property NSData *reply;
@property(copy) void (^beforeDestroy)(void);
@end
@implementation AdapterInterface
- (NSDictionary *)descriptorBytes:(NSError **)error
{
    (void)error; if ([_fault isEqual:@"descriptors-nil"]) return nil;
    NSMutableDictionary *d = [candidate() mutableCopy];
    uint8_t a[] = {9,4,2,0,1,0xff,0x49,1,0};
    if ([_fault isEqual:@"active-alt"]) a[3] = 1;
    d[@"active_interface"] = [NSData dataWithBytes:a length:9];
    if ([_fault isEqual:@"config-changed"]) {
        NSMutableData *c = [d[@"configuration_descriptor"] mutableCopy]; ((uint8_t *)c.mutableBytes)[8] = 51;
        d[@"configuration_descriptor"] = c;
    }
    if ([_fault isEqual:@"device-changed"]) {
        NSMutableData *c = [d[@"device_descriptor"] mutableCopy]; ((uint8_t *)c.mutableBytes)[13] = 2;
        d[@"device_descriptor"] = c;
    }
    return d;
}
- (id<A23TransactionTransport>)copyTransport:(NSError **)error
{ (void)error; return [_fault isEqual:@"pipe-nil"] ? nil : _pipe; }
- (NSData *)currentEndpointBytes
{
    uint8_t e[] = {7,5,0x83,1,0,1,1}; if ([_fault isEqual:@"endpoint-wrong"]) e[6] = 2;
    return [NSData dataWithBytes:e length:7];
}
- (NSMutableData *)allocate:(NSUInteger)length shared:(BOOL)shared error:(NSError **)error
{
    (void)error; ++_allocations; assert((length == 184320 && !shared) || (length == 26880 && shared));
    if ([_fault isEqual:shared ? @"transactions-nil" : @"data-nil"]) return nil;
    if ([_fault isEqual:shared ? @"transactions-short" : @"data-short"]) --length;
    NSMutableData *data = [NSMutableData dataWithLength:length]; memset(data.mutableBytes,0x5a,length); return data;
}
- (NSDictionary *)readStatus
{
    uint64_t begin = mach_absolute_time(); NSData *raw = [_reply copy]; uint64_t end = mach_absolute_time();
    NSMutableDictionary *obs = [@{@"source":@"mock_control_reply",@"accepted":@YES,@"bytes_transferred":@(raw.length),
        @"begin_ticks":@(begin),@"end_ticks":@(end),@"control":@{@"request_type":@193,@"request":@81,
            @"value":@0,@"index":@2,@"length":@168,@"timeout_ms":@3000}} mutableCopy];
    if ([_fault isEqual:@"error-after"]) {
        obs[@"accepted"] = @NO; obs[@"error"] = @{@"domain":@"mock-status",@"code":@-9};
    }
    if ([_fault isEqual:@"overflow-after"]) obs[@"bytes_transferred"] = @169;
    return @{@"data":raw,@"observation":obs};
}
- (void)destroy { if (_beforeDestroy) _beforeDestroy(); assert(++_destroys == 1); }
@end
@interface AdapterOperations : NSObject <A23AdapterOperations>
@property BOOL simulation;
@property NSString *fault;
@property NSUInteger identities, opens;
@property NSUInteger retains, releases;
@property AdapterInterface *interface;
@end
@implementation AdapterOperations
- (BOOL)retainService:(io_service_t)service error:(NSError **)error
{
    (void)error; assert(_simulation && service == 7 && ++_retains == 1); return ![_fault isEqual:@"retain-failed"];
}
- (void)releaseService:(io_service_t)service
{ assert(service == 7 && ++_releases == 1 && _retains == 1); }
- (NSDictionary *)identityForService:(io_service_t)service error:(NSError **)error
{
    (void)error; assert(_simulation && service == 7); ++_identities;
    assert(_retains == 1 && _releases == 0);
    NSMutableDictionary *idn = [@{@"device_id":@101,@"interface_id":@102,@"parent_device_id":@101,@"connection_speed":@3} mutableCopy];
    if ([_fault isEqual:@"pre-identity"] || ([_fault isEqual:@"post-identity"] && _identities == 2)) idn[@"interface_id"] = @103;
    if ([_fault isEqual:@"float-identity"]) idn[@"interface_id"] = @102.0;
    return idn;
}
- (id<A23AdapterInterface>)openService:(io_service_t)service queue:(dispatch_queue_t)queue
    interest:(A23AdapterInterest)interest error:(NSError **)error
{
    (void)queue; (void)interest; (void)error; assert(_simulation && service == 7); ++_opens;
    return [_fault isEqual:@"open-failed"] ? nil : _interface;
}
@end
static AdapterOperations *operations(NSString *fault)
{
    AdapterOperations *op = [AdapterOperations new]; op.simulation = ![fault isEqual:@"real-blocked"]; op.fault = fault;
    op.interface = [AdapterInterface new]; op.interface.fault = fault; op.interface.pipe = [AdapterPipe new];
    __weak AdapterOperations *weak = op;
    op.interface.beforeDestroy = ^{ assert(weak && weak.retains == 1 && weak.releases == 0); };
    return op;
}
static inline A23AdapterSimulationProvider *provider(AdapterOperations *op, dispatch_queue_t queue)
{ return [[A23AdapterSimulationProvider alloc] initWithOperations:op queue:queue interest:^(uint32_t message) { (void)message; assert(!"Unexpected interest"); }]; }
static BOOL allZero(NSData *data)
{ const uint8_t *p = data.bytes; for (NSUInteger i = 0; i < data.length; ++i) if (p[i]) return NO; return YES; }

