#ifndef A23_VERSIONED_DRIVER_BRIDGE_H
#define A23_VERSIONED_DRIVER_BRIDGE_H
#import <Foundation/Foundation.h>
#include "a23_versioned_clock_candidate.h"

typedef struct { A23VersionedClockSample version;uintptr_t object_identity; } A23VersionedDriverSample;
@protocol A23VersionedDriverClock <NSObject>
- (A23VersionedClockStatus)versionedProfile:(A23VersionedClockSample *)out;
- (A23VersionedClockStatus)versionedCapture:(A23VersionedClockSample *)out;
- (BOOL)versionedBeginCommit:(const A23VersionedClockSample *)end;
- (BOOL)versionedEndCommit:(uint64_t *)generation;
- (BOOL)versionedMatchesGeneration:(uint64_t)generation;
@end

/* Owns its embedded C store. Callers retain the adapter through evaluation.
 * Publish/Capture may overlap through the C contract; Begin/EndCommit and
 * MatchesGeneration belong to one serial driver queue. A commit ticket is held
 * across append/post-guard/settled, preventing cooperating profile publications.
 * No real clock or SDK API. Subclass supplies an injected raw tick reader.
 */
@interface A23VersionedDriverClockAdapter : NSObject <A23VersionedDriverClock>
- (instancetype)init NS_UNAVAILABLE;
+ (instancetype)new NS_UNAVAILABLE;
- (instancetype)initWithProfile:(A23CandidateClockStamp)profile incarnation:(uint64_t)incarnation;
- (BOOL)readRawTicks:(uint64_t *)out;
- (A23VersionedClockStatus)publishProfile:(A23CandidateClockStamp)profile;
@property(readonly) uint32_t numerator,denominator,profileDomain;
@property(readonly) uint64_t profileInstance,profileGeneration,writeAttempts,writeSuccesses,busyWrites;
@property(readonly) A23VersionedClockStatus lastWriteStatus;
@end

BOOL A23VersionedDriverReadProfile(id object,A23VersionedDriverSample *out);
BOOL A23VersionedDriverCapture(id object,A23VersionedDriverSample *out);
A23CandidateClockStatus A23VersionedDriverEvaluate(const A23VersionedDriverSample *,const A23VersionedDriverSample *,uint64_t minimum_ns,A23CandidateClockResult *out);
BOOL A23VersionedDriverBeginCommit(id object,const A23VersionedDriverSample *end);
BOOL A23VersionedDriverEndCommit(id object,uint64_t *generation);
BOOL A23VersionedDriverMatches(id object,uint64_t generation);
#endif
