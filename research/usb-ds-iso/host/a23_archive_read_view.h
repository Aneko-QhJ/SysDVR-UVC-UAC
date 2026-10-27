#import <Foundation/Foundation.h>
NS_ASSUME_NONNULL_BEGIN
// Isolated file-verifier candidate. One archive call owns one view. No view or
// content survives validateUnchanged; this is not an atomic filesystem snapshot.
@interface A23ArchiveReadView : NSObject
- (instancetype)init NS_UNAVAILABLE;
+ (instancetype)new NS_UNAVAILABLE;
- (nullable instancetype)initWithRoot:(NSString *)root;
- (nullable NSData *)readFile:(NSString *)path maximumBytes:(NSUInteger)limit;
- (BOOL)validateUnchanged;
@property(readonly) NSDictionary *metrics;
@end
NS_ASSUME_NONNULL_END
