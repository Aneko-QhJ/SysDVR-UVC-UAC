#import "io_usb_host_session.h"
#include <CommonCrypto/CommonDigest.h>
#include <errno.h>
#include <fcntl.h>
#include <mach/mach_time.h>
#include <sys/stat.h>
#include <unistd.h>
#include "../../../source/uvc/iso_probe_protocol.h"

static BOOL sessionError(NSError **error, NSString *message)
{
    if (error) *error = [NSError errorWithDomain:@"A23SimulationSession" code:1
        userInfo:@{NSLocalizedDescriptionKey:message}];
    return NO;
}
@implementation A23SimulationJournal {
    int _fd;
    BOOL _failed;
    NSUInteger _events;
}
- (instancetype)initWithPath:(NSString *)path error:(NSError **)error
{
    if ((self = [super init])) {
        _fd = open(path.fileSystemRepresentation, O_CREAT | O_EXCL | O_NOFOLLOW | O_RDWR, 0600);
        if (_fd < 0) { sessionError(error,@"Journal exclusive create failed"); return nil; }
    }
    return self;
}
- (void)dealloc { if (_fd >= 0) close(_fd); }
- (BOOL)append:(NSDictionary *)event error:(NSError **)error
{
    if (_failed || _events >= 128 || ![NSJSONSerialization isValidJSONObject:event]) {
        _failed = YES; return sessionError(error,@"Journal failed, full or invalid");
    }
    NSData *json = [NSJSONSerialization dataWithJSONObject:event options:NSJSONWritingSortedKeys error:error];
    if (!json || json.length > 4095) { _failed = YES; return sessionError(error,@"Journal event too large"); }
    NSMutableData *line = [json mutableCopy]; [line appendBytes:"\n" length:1];
    off_t start = lseek(_fd,0,SEEK_END);
    NSUInteger done = 0;
    BOOL ok = start >= 0;
    while (ok && done < line.length) {
        ssize_t n = write(_fd,(const uint8_t *)line.bytes + done,line.length - done);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) { ok = NO; break; }
        done += (NSUInteger)n;
    }
    if (ok) ok = fsync(_fd) == 0;
    NSMutableData *copy = [NSMutableData dataWithLength:line.length]; done = 0;
    while (ok && done < line.length) {
        ssize_t n = pread(_fd,(uint8_t *)copy.mutableBytes + done,line.length - done,start + (off_t)done);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) { ok = NO; break; }
        done += (NSUInteger)n;
    }
    ok = ok && [copy isEqualToData:line];
    if (!ok) { _failed = YES; return sessionError(error,@"Journal append/fsync/readback failed"); }
    ++_events; return YES;
}
@end

static BOOL registryNumber(id value)
{
    return [value isKindOfClass:[NSNumber class]] && CFGetTypeID((__bridge CFTypeRef)value) != CFBooleanGetTypeID() &&
        !CFNumberIsFloatType((__bridge CFNumberRef)value) && [value compare:@0] == NSOrderedDescending;
}

static NSString *manifestSHA(NSString *path)
{
    NSData *data = [NSData dataWithContentsOfFile:[path stringByAppendingPathComponent:@"SHA256SUMS"]];
    if (!data) return nil;
    unsigned char digest[CC_SHA256_DIGEST_LENGTH]; CC_SHA256(data.bytes,(CC_LONG)data.length,digest);
    NSMutableString *result = [NSMutableString string];
    for (NSUInteger i = 0; i < sizeof(digest); ++i) [result appendFormat:@"%02x",digest[i]];
    return result;
}

static NSString *dataSHA(NSData *data)
{
    unsigned char digest[CC_SHA256_DIGEST_LENGTH]; CC_SHA256(data.bytes,(CC_LONG)data.length,digest);
    NSMutableString *result = [NSMutableString string];
    for (NSUInteger i = 0; i < sizeof(digest); ++i) [result appendFormat:@"%02x",digest[i]];
    return result;
}
static BOOL unsignedNumber(id value)
{
    return [value isKindOfClass:NSNumber.class] && CFGetTypeID((__bridge CFTypeRef)value) != CFBooleanGetTypeID() &&
        !CFNumberIsFloatType((__bridge CFNumberRef)value) && [value compare:@0] != NSOrderedAscending;
}

NSDictionary *A23NoTDObservationPlan(void)
{
    return @{@"schema":@"A23-no-td-observation-plan-1",@"execution_mode":@"simulation",@"scenario":@{@"kind":@"no_td"},
        @"first_frame_lead":@64,@"transaction_count":@960,@"request_bytes_per_transaction":@192,@"transfer_options":@0,
        @"max_submissions":@1,@"max_device_triggers":@0,@"max_async_aborts":@1,@"repeat":@0,
        @"hardware_entry_enabled":@NO,@"hardware_verified":@NO,@"empty_status_policy":@"unverified",
        @"post_completion_requests":@"status_then_save_only",@"pending_exit":@"retain_until_process_exit"};
}
NSDictionary *A23BudgetedNoTDObservationPlan(void)
{
    NSMutableDictionary *plan = [A23NoTDObservationPlan() mutableCopy];
    plan[@"schema"] = @"A23-no-td-runtime-plan-2";
    plan[@"runtime_budget"] = A23RuntimeBudget();
    plan[@"service_reference"] = @"retain_before_identity_release_after_destroy";
    plan[@"pending_exit"] = @"abort_once_wait_then_report_retained";
    return [plan copy];
}
BOOL A23NoTDControlAllowed(uint8_t type, uint8_t request, uint16_t value, uint16_t index, uint16_t length)
{ return type == 0xc1 && request == 0x51 && value == 0 && index == 2 && length == 168; }

@implementation A23SimulationSession {
    dispatch_queue_t _queue;
    id<A23SessionJournal> _journal;
    NSDictionary *_identity;
    id<A23SessionResources> _resources;
    A23TransactionOwner *_owner;
    A23SimulationSession *_monitor;
    NSString *_sessionID;
    NSUInteger _eventIndex;
    A23SessionState _state;
    BOOL _stopped, _journalFailed, _detached;
    BOOL _requireStatus, _beforeObserved, _beforeValid, _afterObserved;
    uint64_t _lastEventTicks, _readyTicks, _snapshotTicks;
    BOOL _noTDPlan, _frameObserved;
    uint64_t _beforeEndTicks, _plannedFirstFrame;
    id<A23RuntimeClock> _clock;
    NSDictionary *_frameSample;
    A23BudgetTransport *_budgetTransport;
    BOOL _exitRequested, _exitExpired;
    uint64_t _exitBegin;
}
- (instancetype)initWithQueue:(dispatch_queue_t)queue journal:(id<A23SessionJournal>)journal
{
    return [self initWithQueue:queue journal:journal requireStatusBinding:NO];
}
- (instancetype)initWithQueue:(dispatch_queue_t)queue journal:(id<A23SessionJournal>)journal requireStatusBinding:(BOOL)required
{
    if (!queue || !journal) return nil;
    if ((self = [super init])) { _queue = queue; _journal = journal; _sessionID = NSUUID.UUID.UUIDString; _requireStatus = required; }
    return self;
}
- (instancetype)initNoTDWithQueue:(dispatch_queue_t)queue journal:(id<A23SessionJournal>)journal
{
    if ((self = [self initWithQueue:queue journal:journal requireStatusBinding:YES])) _noTDPlan = YES;
    return self;
}
- (instancetype)initBudgetedNoTDWithQueue:(dispatch_queue_t)queue journal:(id<A23SessionJournal>)journal clock:(id<A23RuntimeClock>)clock
{
    if (!clock || !clock.numerator || !clock.denominator) return nil;
    if ((self = [self initNoTDWithQueue:queue journal:journal])) _clock = clock;
    return self;
}
- (BOOL)hardwareContext { return NO; }
- (BOOL)event:(NSString *)name details:(NSDictionary *)details
{
    if (_journalFailed) return NO;
    _lastEventTicks = mach_absolute_time();
    NSDictionary *record = @{@"schema":@"A23-session-event-1", @"execution_mode":[self hardwareContext] ? @"hardware" : @"simulation",
        @"session_id":_sessionID, @"index":@(++_eventIndex), @"ticks":@(_lastEventTicks),
        @"event":name, @"details":details};
    if (![_journal append:record error:NULL]) { _journalFailed = YES; _stopped = YES; return NO; }
    return YES;
}
- (void)stop:(NSString *)reason
{
    _stopped = YES;
    [self event:@"stop" details:@{@"reason":reason}];
}
- (void)releaseResources
{
    if (![self event:@"resources_closing" details:@{}]) return;
    [_resources closeWhenNoIO]; _resources = nil;
    if (!_monitor) _owner = nil; // No submission, so no possible borrowed DMA storage.
    _state = A23SessionClosed;
    [self event:@"resources_closed" details:@{}];
}
- (BOOL)prepareCandidates:(NSArray<NSDictionary *> *)candidates provider:(id<A23SessionProvider>)provider
{
    dispatch_assert_queue(_queue);
    if (_state != A23SessionNew || _stopped || !provider) return NO;
    NSMutableDictionary *preparation = [@{@"candidate_count":@(candidates.count),@"requires_status_binding":@(_requireStatus)} mutableCopy];
    if (_noTDPlan) preparation[@"probe_plan"] = [self hardwareContext] ? A23HardwareNoTDObservationPlan() :
        (_clock ? A23BudgetedNoTDObservationPlan() : A23NoTDObservationPlan());
    if (![self event:@"prepare_begin" details:preparation]) return NO;
    if (candidates.count != 1) { _state = A23SessionStopped; [self stop:@"candidate_not_unique"]; return NO; }
    NSDictionary *candidate = [candidates[0] copy];
    if (![candidate isKindOfClass:[NSDictionary class]] || !registryNumber(candidate[@"device_id"]) ||
        !registryNumber(candidate[@"interface_id"]) || !registryNumber(candidate[@"parent_device_id"]) ||
        ![candidate[@"device_id"] isEqual:candidate[@"parent_device_id"]] ||
        [candidate[@"device_id"] isEqual:candidate[@"interface_id"]] ||
        (![self hardwareContext] && (![candidate[@"device_descriptor"] isKindOfClass:[NSData class]] ||
        ![candidate[@"configuration_descriptor"] isKindOfClass:[NSData class]])) ||
        !registryNumber(candidate[@"connection_speed"])) {
        _state = A23SessionStopped; [self stop:@"candidate_identity_invalid"]; return NO;
    }
    NSDictionary *descriptor = A23ValidateDescriptors(candidate[@"device_descriptor"],
        candidate[@"configuration_descriptor"],[candidate[@"connection_speed"] unsignedIntegerValue],NULL);
    if (!descriptor && ![self hardwareContext]) { _state = A23SessionStopped; [self stop:@"descriptor_invalid"]; return NO; }
    _identity = @{@"device_id":candidate[@"device_id"], @"interface_id":candidate[@"interface_id"],
        @"parent_device_id":candidate[@"parent_device_id"]};
    if (![self event:@"candidate_selected" details:_identity]) return NO;
    NSError *openError = nil;
    _resources = [provider openCandidate:candidate error:&openError];
    if (!_resources) {
        _state = A23SessionStopped;
        if ([self hardwareContext] && openError) {
            _stopped = YES; [self event:@"stop" details:@{@"reason":@"open_failed",
                @"error":A23PreparationErrorDetails(openError)}];
        } else [self stop:@"open_failed"];
        return NO;
    }
    if (![self event:@"resources_opened" details:@{}]) return NO;
    if ([self hardwareContext]) {
        NSDictionary *bytes = [_resources respondsToSelector:@selector(descriptorBytes)] ? _resources.descriptorBytes : nil;
        descriptor = A23ValidateDescriptors(bytes[@"device_descriptor"],bytes[@"configuration_descriptor"],
            [candidate[@"connection_speed"] unsignedIntegerValue],NULL);
        if (!descriptor) { [self stop:@"descriptor_invalid"]; [self releaseResources]; return NO; }
        NSMutableDictionary *live = [descriptor mutableCopy]; live[@"source"] = @"sdk_descriptor_bytes"; descriptor = live;
    }
    if (_detached || ![_resources.identity isEqual:_identity]) {
        [self stop:_detached ? @"detach_during_open" : @"identity_changed"];
        [self releaseResources]; return NO;
    }
    _owner = [[A23TransactionOwner alloc] initWithData:_resources.dataStorage
        transactions:_resources.transactionStorage queue:_queue];
    if (!_owner || !_resources.transport) { [self stop:@"allocation_or_pipe_failed"]; [self releaseResources]; return NO; }
    __weak A23SimulationSession *weakSelf = self;
    BOOL observing = [_owner observeCompletions:^(NSDictionary *record) {
        A23SimulationSession *session = weakSelf;
        if (!session) return;
        [session event:@"callback" details:record];
        if ([record[@"count"] unsignedIntegerValue] != 1 || session->_state == A23SessionClosed)
            [session stop:session->_state == A23SessionClosed ? @"callback_after_close" : @"duplicate_callback"];
        if ([record[@"pointer_mismatch"] boolValue]) [session stop:@"foreign_callback_pointer"];
    }];
    if (!observing) { [self stop:@"observer_failed"]; [self releaseResources]; return NO; }
    _state = A23SessionReady;
    BOOL logged = [self event:@"ready" details:descriptor]; _readyTicks = _lastEventTicks; return logged;
}
- (BOOL)submitFirstFrame:(uint64_t)firstFrame
{
    dispatch_assert_queue(_queue);
    if (_state != A23SessionReady || _stopped || !firstFrame || (_requireStatus && !_beforeValid)) return NO;
    if (_noTDPlan && !_frameObserved) return NO;
    if (_noTDPlan && firstFrame != _plannedFirstFrame) { [self stop:@"planned_frame_mismatch"]; return NO; }
    if (![self event:@"submit_begin" details:@{@"first_frame":@(firstFrame)}]) return NO;
    _state = A23SessionPending; _monitor = self;
    __weak A23SimulationSession *weakSelf = self;
    id<A23TransactionTransport> transport = _resources.transport;
    if (_clock) { _budgetTransport = [[([self hardwareContext] ? A23SDKBudgetTransport.class : A23BudgetTransport.class) alloc]
        initWithTransport:transport clock:_clock sample:_frameSample]; transport = _budgetTransport; }
    BOOL accepted = [_owner submitTo:transport firstFrame:firstFrame finished:^(NSDictionary *e) {
        A23SimulationSession *session = weakSelf;
        if (!session) return;
        session->_state = session->_owner.state == A23TransactionRetained ? A23SessionRetained : A23SessionCompleted;
        NSMutableDictionary *details = [@{@"owner_state":@(session->_owner.state)} mutableCopy];
        if (e[@"overall_u32"]) details[@"overall_u32"] = e[@"overall_u32"];
        [session event:@"snapshot_ready" details:details];
        session->_snapshotTicks = session->_lastEventTicks;
        if (session->_state == A23SessionRetained) [session stop:@"owner_retained"];
        else if (e[@"overall_u32"] && [e[@"overall_u32"] unsignedIntValue] != 0) [session stop:@"native_overall_error"];
    }];
    if (_clock) {
        [self event:@"admission_checked" details:_budgetTransport.result];
        if (![_budgetTransport.result[@"budget_pass"] boolValue]) [self stop:accepted ? @"enqueue_budget_exceeded" : @"admission_or_enqueue_failed"];
    }
    [self event:@"submit_result" details:@{@"accepted":@(accepted)}];
    if (!accepted) [self stop:@"submit_rejected"];
    return accepted && !_journalFailed;
}
- (BOOL)recordFrameSample:(NSDictionary *)sample
{
    dispatch_assert_queue(_queue);
    if (!_noTDPlan || _state != A23SessionReady || _stopped || !_beforeValid || _frameObserved || _journalFailed) return NO;
    NSString *source = [self hardwareContext] ? @"sdk_frame_number" : @"mock_frame_number";
    if (![sample isKindOfClass:NSDictionary.class] || ![sample[@"source"] isEqual:source] ||
        !unsignedNumber(sample[@"current_frame"]) || !registryNumber(sample[@"begin_ticks"]) || !registryNumber(sample[@"end_ticks"])) {
        [self stop:@"frame_sample_invalid"]; return NO;
    }
    uint64_t frame = [sample[@"current_frame"] unsignedLongLongValue];
    uint64_t begin = [sample[@"begin_ticks"] unsignedLongLongValue], end = [sample[@"end_ticks"] unsignedLongLongValue];
    if (frame > UINT64_MAX - 64 || begin < _beforeEndTicks || begin > end || end > mach_absolute_time()) {
        [self stop:@"frame_sample_invalid"]; return NO;
    }
    _plannedFirstFrame = frame + 64;
    NSMutableDictionary *details = [@{@"source":source,@"current_frame":@(frame),@"begin_ticks":@(begin),
        @"end_ticks":@(end),@"first_frame":@(_plannedFirstFrame),@"frame_lead":@64} mutableCopy];
    if (_clock) { details[@"timebase_numerator"] = @(_clock.numerator); details[@"timebase_denominator"] = @(_clock.denominator); }
    if ([self hardwareContext]) {
        if (!unsignedNumber(sample[@"frame_time"]) || !frame) { [self stop:@"frame_sample_invalid"]; return NO; }
        details[@"frame_time"] = sample[@"frame_time"];
    }
    if (![self event:@"frame_sample" details:details]) return NO;
    _frameObserved = YES; _frameSample = [details copy]; return YES;
}
- (BOOL)recordStatusPhase:(NSString *)phase data:(NSData *)data observation:(NSDictionary *)observation
{
    dispatch_assert_queue(_queue);
    if (![phase isKindOfClass:NSString.class] || ![data isKindOfClass:NSData.class] ||
        ![observation isKindOfClass:NSDictionary.class]) return NO;
    BOOL before = [phase isEqual:@"before"], after = [phase isEqual:@"after"];
    if (!_requireStatus || _journalFailed || (!before && !after) ||
        (before && (_state != A23SessionReady || _beforeObserved || _stopped)) ||
        (after && (_state != A23SessionCompleted || _owner.state != A23TransactionCompleted || _afterObserved))) return NO;
    NSDictionary *control = observation[@"control"];
    NSDictionary *expected = @{@"request_type":@0xc1,@"request":@0x51,@"value":@0,@"index":@2,@"length":@168,@"timeout_ms":@3000};
    BOOL valid = [data isKindOfClass:NSData.class] && data.length <= 2048 &&
        [observation[@"source"] isEqual:[self hardwareContext] ? @"sdk_control_reply" : @"mock_control_reply"] &&
        [observation[@"accepted"] isKindOfClass:NSNumber.class] &&
        CFGetTypeID((__bridge CFTypeRef)observation[@"accepted"]) == CFBooleanGetTypeID() &&
        unsignedNumber(observation[@"bytes_transferred"]) && registryNumber(observation[@"begin_ticks"]) &&
        registryNumber(observation[@"end_ticks"]) && [control isKindOfClass:NSDictionary.class] && [control isEqual:expected];
    for (NSString *key in expected) valid = valid && unsignedNumber(control[key]);
    if (!valid) { [self stop:@"status_observation_invalid"]; return NO; }
    uint64_t begin = [observation[@"begin_ticks"] unsignedLongLongValue], end = [observation[@"end_ticks"] unsignedLongLongValue];
    valid = valid && begin <= end && end <= mach_absolute_time() &&
        begin >= (before ? _readyTicks : _snapshotTicks) &&
        (!after || begin >= [_owner.evidence[@"callback_arrival_ticks"] unsignedLongLongValue]);
    id error = observation[@"error"];
    if (error) valid = valid && [error isKindOfClass:NSDictionary.class] && [error[@"domain"] isKindOfClass:NSString.class] &&
        [error[@"domain"] length] > 0 && [error[@"code"] isKindOfClass:NSNumber.class] &&
        CFGetTypeID((__bridge CFTypeRef)error[@"code"]) != CFBooleanGetTypeID() && !CFNumberIsFloatType((__bridge CFNumberRef)error[@"code"]);
    if (!valid) { [self stop:@"status_observation_invalid"]; return NO; }
    NSData *original = [data copy];
    if (![self event:@"status_observed" details:@{@"phase":phase,@"raw_base64":[original base64EncodedStringWithOptions:0],
        @"raw_sha256":dataSHA(original),@"observation":[observation copy]}]) return NO;
    if (before) _beforeObserved = YES; else _afterObserved = YES;
    valid = original.length == 168 && [observation[@"bytes_transferred"] unsignedLongLongValue] == 168 &&
        [observation[@"accepted"] boolValue] && !error;
    IsoProbeStatus status = {0};
    if (valid) memcpy(&status,original.bytes,sizeof(status));
    valid = valid && status.magic == ISO_PROBE_STATUS_MAGIC && status.version == 1 && status.endpoint == 0x83 &&
        status.sequence <= UINT16_MAX && status.state <= ISO_PROBE_RETAINED;
    if (before) valid = valid && status.sequence == 0 && status.state == ISO_PROBE_IDLE && status.post_result == 0 &&
        status.urb_id == 0 && status.report_id == 0 && status.requested == 0 && status.transferred == 0 &&
        status.urb_status == 0 && status.report_count == 0 && status.report_result == 0 && (status.speed == 0 || status.speed == 3);
    if (before) { _beforeValid = valid; _beforeEndTicks = end; }
    if (!valid) [self stop:before ? @"status_before_failed" : @"status_after_failed"];
    return valid;
}
- (BOOL)deadlineReached
{
    dispatch_assert_queue(_queue);
    if (_state != A23SessionPending || _detached || _stopped) return NO;
    if (![self event:@"deadline" details:@{}]) return NO;
    BOOL accepted = [_owner deadlineReached];
    [self event:@"abort_result" details:@{@"accepted":@(accepted)}];
    if (!accepted) _state = A23SessionRetained;
    [self stop:@"deadline_reached"]; return accepted;
}
- (BOOL)requestExit
{
    dispatch_assert_queue(_queue);
    if (!_clock || _exitRequested || _journalFailed) return NO;
    _exitRequested = YES; _exitBegin = [_clock nowTicks];
    if (![self event:@"exit_requested" details:@{@"begin_ticks":@(_exitBegin),@"state":@(_state),
        @"timebase_numerator":@(_clock.numerator),@"timebase_denominator":@(_clock.denominator)}]) return NO;
    // A prior failure does not prevent this one shutdown abort. A prior abort,
    // detach or foreign pointer does prevent repeating or misdirecting it.
    if (_owner.state == A23TransactionPending && !_detached) {
        if (![self event:@"deadline" details:@{}]) return NO;
        BOOL accepted = [_owner deadlineReached];
        [self event:@"abort_result" details:@{@"accepted":@(accepted)}];
        if (!accepted) _state = A23SessionRetained;
    }
    if (_state == A23SessionSaved || _state == A23SessionClosed) _stopped = YES;
    else [self stop:@"exit_requested"];
    if (_state == A23SessionReady || _state == A23SessionSaved || _state == A23SessionNew) [self close];
    return !_journalFailed;
}
- (NSUInteger)exitDisposition
{
    dispatch_assert_queue(_queue);
    if (!_clock || !_exitRequested || _journalFailed) return 2;
    if (_state == A23SessionClosed) return 1;
    if (_exitExpired) return 2;
    uint64_t now = [_clock nowTicks], elapsed = 0;
    BOOL converted = now >= _exitBegin && A23TicksToNanoseconds(now-_exitBegin,_clock.numerator,_clock.denominator,&elapsed);
    if (!converted || elapsed >= 1000000000 || _owner.state == A23TransactionRetained) {
        _exitExpired = YES;
        [self event:@"exit_wait_expired" details:@{@"check_ticks":@(now),@"elapsed_ns":@(elapsed),@"converted":@(converted),
            @"storage_retained":@(_owner.storageRetained),@"resources_retained":@((BOOL)(_resources != nil))}];
        return 2;
    }
    return 0;
}
- (BOOL)detachedRegistryID:(uint64_t)registryID
{
    dispatch_assert_queue(_queue);
    BOOL matches = _identity && (registryID == [_identity[@"device_id"] unsignedLongLongValue] ||
        registryID == [_identity[@"interface_id"] unsignedLongLongValue]);
    if (![self event:matches ? @"detach" : @"unrelated_detach" details:@{@"registry_id":@(registryID)}]) return NO;
    if (!matches) return NO;
    _detached = YES; [self stop:@"device_detached"];
    // A removal message does not establish DMA completion. Do not abort an
    // absent service or destroy pending resources. Await the real callback.
    if (_state == A23SessionReady) [self releaseResources];
    return YES;
}
- (BOOL)saveToParent:(NSString *)parent name:(NSString *)name scenario:(NSDictionary *)scenario
{
    dispatch_assert_queue(_queue);
    if (_state != A23SessionCompleted || _journalFailed || (_requireStatus && !_afterObserved && _owner.state != A23TransactionRejected)) return NO;
    if (_noTDPlan && ![scenario isEqual:@{@"kind":@"no_td"}]) { [self stop:@"planned_scenario_mismatch"]; return NO; }
    if (![self event:@"save_begin" details:@{@"callback_count":@(_owner.callbackCount)}]) return NO;
    BOOL saved = [self hardwareContext] ? A23SaveHardwareObservation(_owner,parent,name,NULL) :
        A23SaveSimulationEvidence(_owner,parent,name,scenario,NULL);
    if (!saved) { [self stop:@"save_failed"]; return NO; }
    _state = A23SessionSaved;
    NSString *digest = manifestSHA([parent stringByAppendingPathComponent:name]);
    if (!digest) { [self stop:@"saved_manifest_unreadable"]; return NO; }
    return [self event:@"bundle_committed" details:@{@"manifest_sha256":digest, @"callback_count":@(_owner.callbackCount)}];
}
- (BOOL)close
{
    dispatch_assert_queue(_queue);
    if (_journalFailed || _state == A23SessionClosed) return NO;
    if (_owner && _owner.state != A23TransactionPrepared && _state != A23SessionSaved) return NO;
    if (_state == A23SessionPending || _state == A23SessionRetained) return NO;
    [self releaseResources];
    // Retain only the bounded owner snapshot/journal monitor after a submit.
    // This is not a framework callback drain or permission for another request.
    if (!_monitor) _owner = nil;
    return _state == A23SessionClosed && !_journalFailed;
}
- (A23SessionState)state { dispatch_assert_queue(_queue); return _state; }
- (BOOL)stopped { dispatch_assert_queue(_queue); return _stopped; }
- (BOOL)journalFailed { dispatch_assert_queue(_queue); return _journalFailed; }
- (BOOL)resourcesRetained { dispatch_assert_queue(_queue); return _resources != nil; }
- (BOOL)storageRetained { dispatch_assert_queue(_queue); return _owner.storageRetained; }
- (uint64_t)plannedFirstFrame { dispatch_assert_queue(_queue); return _plannedFirstFrame; }
@end
NSDictionary *A23HardwareNoTDObservationPlan(void)
{
    NSMutableDictionary *plan = [A23BudgetedNoTDObservationPlan() mutableCopy];
    plan[@"schema"] = @"A23-no-td-hardware-plan-1"; plan[@"execution_mode"] = @"hardware";
    plan[@"hardware_entry_enabled"] = @YES;
    plan[@"completion_deadline_ns"] = @2000000000; plan[@"post_close_monitor_ns"] = @250000000;
    return plan;
}
@implementation A23SDKNoTDSession
- (instancetype)initWithQueue:(dispatch_queue_t)queue journal:(id<A23SessionJournal>)journal clock:(id<A23RuntimeClock>)clock
{ return [super initBudgetedNoTDWithQueue:queue journal:journal clock:clock]; }
- (BOOL)hardwareContext { return YES; }
@end
