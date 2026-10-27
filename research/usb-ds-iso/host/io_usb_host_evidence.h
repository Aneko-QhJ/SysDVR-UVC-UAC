#import "io_usb_host_transaction_owner.h"

NS_ASSUME_NONNULL_BEGIN
// Descriptor checks consume supplied bytes. Dictionary construction is pure;
// IOService enumeration is an explicit caller operation, never performed here.
CFMutableDictionaryRef _Nullable A23CreateMatchingDictionary(void) CF_RETURNS_RETAINED;
// Bounded diagnostic fields; preserves SDK domain/code and failure text.
NSDictionary *A23PreparationErrorDetails(NSError *error);
NSDictionary * _Nullable A23ValidateDescriptors(NSData *device, NSData *configuration,
    NSUInteger connectionSpeed, NSError * _Nullable * _Nullable error);

// Simulation-only format. Called on the owner's queue. Create a new child of a
// trusted parent directory; never overwrite. Ack only after fsync and byte-for-
// byte readback of all files. Failed partial directories are left for inspection.
BOOL A23SaveSimulationEvidence(A23TransactionOwner *owner, NSString *parent,
    NSString *name, NSDictionary *scenario, NSError * _Nullable * _Nullable error);
// Distinct hardware observation format; does not certify USB success.
BOOL A23SaveHardwareObservation(A23TransactionOwner *owner, NSString *parent,
    NSString *name, NSError * _Nullable * _Nullable error);
// Separate single-burst core. Binding is the coordinator's immutable session,
// identity and descriptor hashes. This records observations, never permission.
BOOL A23SaveBurstHardwareObservation(A23TransactionOwner *owner, NSString *parent,
    NSString *name, NSDictionary *binding, NSError * _Nullable * _Nullable error);
// Durable bounded failure/final checkpoint; does not acknowledge any owner.
BOOL A23SaveBurstCheckpoint(NSDictionary *checkpoint, NSString *parent,
    NSString *name, NSError * _Nullable * _Nullable error);
NS_ASSUME_NONNULL_END
