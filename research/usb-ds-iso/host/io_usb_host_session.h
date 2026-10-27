#import "io_usb_host_evidence.h"
#import "io_usb_host_runtime_guard.h"

NS_ASSUME_NONNULL_BEGIN
// Fixed offline observation plan. No service access or capture permission.
FOUNDATION_EXPORT NSDictionary *A23NoTDObservationPlan(void);
FOUNDATION_EXPORT NSDictionary *A23BudgetedNoTDObservationPlan(void);
FOUNDATION_EXPORT NSDictionary *A23HardwareNoTDObservationPlan(void);
FOUNDATION_EXPORT BOOL A23NoTDControlAllowed(uint8_t type, uint8_t request,
    uint16_t value, uint16_t index, uint16_t length);
@protocol A23SessionJournal <NSObject>
- (BOOL)append:(NSDictionary *)event error:(NSError * _Nullable * _Nullable)error;
@end

// One exclusively created JSONL file, fsync/readback per event. Parent trusted.
@interface A23SimulationJournal : NSObject <A23SessionJournal>
- (instancetype)init NS_UNAVAILABLE;
+ (instancetype)new NS_UNAVAILABLE;
- (nullable instancetype)initWithPath:(NSString *)path error:(NSError * _Nullable * _Nullable)error;
@end

// Future SDK adapter supplies these objects. Current tests use mocks exclusively.
// closeWhenNoIO releases the pipe and destroys the interface; it is not a drain.
@protocol A23SessionResources <NSObject>
@property(readonly) NSDictionary *identity;
@property(readonly, nullable) NSMutableData *dataStorage;
@property(readonly, nullable) NSMutableData *transactionStorage;
@property(readonly, nullable) id<A23TransactionTransport> transport;
- (void)closeWhenNoIO;
@optional
@property(readonly) NSDictionary *descriptorBytes;
- (NSDictionary *)readStatus;
- (NSDictionary *)readFrameSample;
@end
@protocol A23SessionProvider <NSObject>
- (nullable id<A23SessionResources>)openCandidate:(NSDictionary *)candidate
    error:(NSError * _Nullable * _Nullable)error;
@end

typedef NS_ENUM(NSUInteger, A23SessionState) {
    A23SessionNew, A23SessionReady, A23SessionPending, A23SessionCompleted,
    A23SessionSaved, A23SessionClosed, A23SessionRetained, A23SessionStopped
};

// Simulation-only, single request. All calls on the supplied serial queue;
// future SDK interest callbacks MUST dispatch asynchronously onto this queue.
// Once a submit is attempted, a bounded monitor self-retains until process exit
// so late events remain observable even after closing resources. No resubmission.
@interface A23SimulationSession : NSObject
- (instancetype)init NS_UNAVAILABLE;
+ (instancetype)new NS_UNAVAILABLE;
- (instancetype)initWithQueue:(dispatch_queue_t)queue journal:(id<A23SessionJournal>)journal;
- (instancetype)initWithQueue:(dispatch_queue_t)queue journal:(id<A23SessionJournal>)journal
    requireStatusBinding:(BOOL)required;
- (instancetype)initNoTDWithQueue:(dispatch_queue_t)queue journal:(id<A23SessionJournal>)journal;
- (nullable instancetype)initBudgetedNoTDWithQueue:(dispatch_queue_t)queue journal:(id<A23SessionJournal>)journal
    clock:(id<A23RuntimeClock>)clock;
// Supplied software frame reading only. Never queries a controller. Once after
// fresh STATUS, before enqueue; current_frame + 64 must not overflow uint64.
- (BOOL)recordFrameSample:(NSDictionary *)sample;
@property(readonly) uint64_t plannedFirstFrame;
// Records an already supplied mock reply. Never issues USB requests. Original
// bytes/count/errors survive failed or short requests; no padding/reconstruction.
- (BOOL)recordStatusPhase:(NSString *)phase data:(NSData *)data observation:(NSDictionary *)observation;
- (BOOL)prepareCandidates:(NSArray<NSDictionary *> *)candidates provider:(id<A23SessionProvider>)provider;
- (BOOL)submitFirstFrame:(uint64_t)firstFrame;
- (BOOL)deadlineReached;
// Stops further work. At most one asynchronous abort, including after an
// admission failure or earlier deadline. Never destroys an outstanding request.
- (BOOL)requestExit;
// 0 waiting, 1 closed/ready to end the mock process, 2 retain and report.
// A bounded grace expiry returns 2; it never forces destroy/reset/process exit.
- (NSUInteger)exitDisposition;
- (BOOL)detachedRegistryID:(uint64_t)registryID;
- (BOOL)saveToParent:(NSString *)parent name:(NSString *)name scenario:(NSDictionary *)scenario;
- (BOOL)close;
@property(readonly) A23SessionState state;
@property(readonly) BOOL stopped;
@property(readonly) BOOL journalFailed;
@property(readonly) BOOL resourcesRetained;
@property(readonly) BOOL storageRetained;
@end
// Explicit hardware context; old simulation initializers and provider stay closed.
@interface A23SDKNoTDSession : A23SimulationSession
- (nullable instancetype)initWithQueue:(dispatch_queue_t)queue journal:(id<A23SessionJournal>)journal
    clock:(id<A23RuntimeClock>)clock;
@end
NS_ASSUME_NONNULL_END
