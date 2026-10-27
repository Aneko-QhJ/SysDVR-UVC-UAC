#import "io_usb_host_evidence.h"
#include <CommonCrypto/CommonDigest.h>
#include <errno.h>
#include <fcntl.h>
#include <stddef.h>
#include <sys/stat.h>
#include <unistd.h>

_Static_assert(sizeof(IOUSBHostIsochronousTransaction) == 28, "SDK transaction size changed");
_Static_assert(offsetof(IOUSBHostIsochronousTransaction, status) == 0, "SDK status moved");
_Static_assert(offsetof(IOUSBHostIsochronousTransaction, requestCount) == 4, "SDK request moved");
_Static_assert(offsetof(IOUSBHostIsochronousTransaction, offset) == 8, "SDK offset moved");
_Static_assert(offsetof(IOUSBHostIsochronousTransaction, completeCount) == 12, "SDK actual moved");
_Static_assert(offsetof(IOUSBHostIsochronousTransaction, timeStamp) == 16, "SDK timestamp moved");
_Static_assert(offsetof(IOUSBHostIsochronousTransaction, options) == 24, "SDK options moved");

static BOOL fail(NSError **error, NSString *message)
{
    if (error) *error = [NSError errorWithDomain:@"A23OfflineEvidence" code:1
        userInfo:@{NSLocalizedDescriptionKey:message}];
    return NO;
}
static NSString *boundedText(NSString *text)
{
    NSData *utf8 = [text dataUsingEncoding:NSUTF8StringEncoding];
    if (utf8.length<=384) return text;
    NSUInteger limit = 384; NSString *prefix = nil;
    while (!prefix && limit) prefix = [[NSString alloc] initWithData:[utf8 subdataWithRange:NSMakeRange(0,limit--)] encoding:NSUTF8StringEncoding];
    return prefix ?: @"";
}
NSDictionary *A23PreparationErrorDetails(NSError *error)
{
    NSMutableDictionary *details = [@{@"domain":error.domain,@"code":@(error.code),
        @"code_u32":@((uint32_t)error.code),@"description":boundedText(error.localizedDescription)} mutableCopy];
    if (error.localizedFailureReason) details[@"failure_reason"] = boundedText(error.localizedFailureReason);
    if (error.localizedRecoverySuggestion.length) details[@"recovery_suggestion"] = boundedText(error.localizedRecoverySuggestion);
    id stage = error.userInfo[@"A23PreparationStage"];
    if ([stage isKindOfClass:NSString.class]) details[@"preparation_stage"] = boundedText(stage);
    return details;
}

CFMutableDictionaryRef A23CreateMatchingDictionary(void)
{
    NSMutableDictionary *properties = CFBridgingRelease([IOUSBHostInterface createMatchingDictionaryWithVendorID:@0x1209 productID:@0xca57
        bcdDevice:nil interfaceNumber:@2 configurationValue:nil interfaceClass:@0xff
        interfaceSubclass:@0x49 interfaceProtocol:@1 speed:@(kIOUSBHostConnectionSpeedHigh)
        productIDArray:nil]);
    if (!properties) return NULL;
    // IOService matching needs explicit property matching. The SDK's flat
    // dictionary did not select this registered interface on the current OS.
    [properties removeObjectForKey:@"IOProviderClass"];
    CFMutableDictionaryRef matching = IOServiceMatching("IOUSBHostInterface");
    if (matching) CFDictionarySetValue(matching, CFSTR(kIOPropertyMatchKey), (__bridge CFDictionaryRef)properties);
    return matching;
}

NSDictionary *A23ValidateDescriptors(NSData *device, NSData *configuration,
    NSUInteger connectionSpeed, NSError **error)
{
    const uint8_t *d = device.bytes, *c = configuration.bytes;
    if (device.length != 18 || d[0] != 18 || d[1] != 1 || d[8] != 9 || d[9] != 0x12 ||
        d[10] != 0x57 || d[11] != 0xca || connectionSpeed != kIOUSBHostConnectionSpeedHigh ||
        configuration.length < 9 || c[0] != 9 || c[1] != 2 || c[5] == 0 ||
        ((NSUInteger)c[2] | (NSUInteger)c[3] << 8) != configuration.length) {
        fail(error, @"Device identity/speed or configuration header mismatch"); return nil;
    }
    NSMutableSet *interfaces = [NSMutableSet set], *alternates = [NSMutableSet set];
    NSUInteger candidates = 0, endpoints = 0, expectedEndpoints = 0;
    BOOL haveInterface = NO, target = NO, endpointOK = NO;
    for (NSUInteger pos = 9; pos < configuration.length;) {
        if (configuration.length - pos < 2 || c[pos] < 2 || c[pos] > configuration.length - pos) {
            fail(error, @"Truncated/zero-length descriptor"); return nil;
        }
        const uint8_t *r = c + pos;
        if (r[1] == 4) {
            if (r[0] != 9 || (haveInterface && endpoints != expectedEndpoints)) {
                fail(error, @"Interface/endpoint count mismatch"); return nil;
            }
            NSString *key = [NSString stringWithFormat:@"%u:%u", r[2], r[3]];
            if ([alternates containsObject:key]) { fail(error, @"Duplicate alternate"); return nil; }
            [alternates addObject:key]; [interfaces addObject:@(r[2])];
            haveInterface = YES; endpoints = 0; expectedEndpoints = r[4];
            target = r[5] == 0xff && r[6] == 0x49;
            if (target) {
                ++candidates;
                if (r[2] != 2 || r[3] != 0 || r[4] != 1 || r[7] != 1) {
                    fail(error, @"Unexpected experiment interface/alternate/protocol"); return nil;
                }
            }
        } else if (r[1] == 5) {
            if (!haveInterface || r[0] != 7) { fail(error, @"Invalid endpoint descriptor"); return nil; }
            ++endpoints;
            if (target) {
                // A23 interval1/MPS256, not the legacy probe's interval4.
                endpointOK = r[2] == 0x83 && r[3] == 1 && r[4] == 0 && r[5] == 1 && r[6] == 1;
                if (!endpointOK) { fail(error, @"Not the A23 HS interval1/MPS256 endpoint"); return nil; }
            }
        } else if (r[1] == 2 || r[1] == 1 || r[1] == 0x30 || r[1] == 0x31) {
            fail(error, @"Unexpected nested or SuperSpeed descriptor"); return nil;
        }
        pos += r[0];
    }
    if (!haveInterface || endpoints != expectedEndpoints || interfaces.count != c[4] ||
        candidates != 1 || !endpointOK) { fail(error, @"Missing/ambiguous interface or endpoint"); return nil; }
    return @{@"vendor_id":@0x1209, @"product_id":@0xca57, @"connection_speed":@(connectionSpeed),
        @"configuration_value":@(c[5]), @"interface":@2, @"alternate":@0, @"endpoint":@0x83,
        @"mps":@256, @"interval":@1, @"source":@"supplied_descriptor_bytes"};
}

static NSString *sha(NSData *data)
{
    unsigned char digest[CC_SHA256_DIGEST_LENGTH];
    CC_SHA256(data.bytes, (CC_LONG)data.length, digest);
    NSMutableString *value = [NSMutableString string];
    for (NSUInteger i = 0; i < sizeof(digest); ++i) [value appendFormat:@"%02x", digest[i]];
    return value;
}

static BOOL writeVerified(int directory, NSString *name, NSData *data, NSError **error)
{
    int fd = openat(directory, name.fileSystemRepresentation, O_RDWR | O_CREAT | O_EXCL | O_NOFOLLOW, 0600);
    if (fd < 0) return fail(error, [NSString stringWithFormat:@"Exclusive create failed: %@ (%d)", name, errno]);
    const uint8_t *bytes = data.bytes;
    NSUInteger pos = 0;
    BOOL ok = YES;
    while (pos < data.length) {
        ssize_t amount = write(fd, bytes + pos, data.length - pos);
        if (amount < 0 && errno == EINTR) continue;
        if (amount <= 0) { ok = NO; break; }
        pos += (NSUInteger)amount;
    }
    if (ok) ok = fsync(fd) == 0 && lseek(fd, 0, SEEK_SET) == 0;
    NSMutableData *readback = [NSMutableData dataWithLength:data.length];
    pos = 0;
    while (ok && pos < data.length) {
        ssize_t amount = read(fd, (uint8_t *)readback.mutableBytes + pos, data.length - pos);
        if (amount < 0 && errno == EINTR) continue;
        if (amount <= 0) { ok = NO; break; }
        pos += (NSUInteger)amount;
    }
    uint8_t extra;
    if (ok) ok = read(fd, &extra, 1) == 0 && [readback isEqualToData:data];
    if (close(fd) != 0) ok = NO;
    return ok ? YES : fail(error, [NSString stringWithFormat:@"Write/fsync/readback failed: %@", name]);
}

static BOOL saveEvidence(A23TransactionOwner *owner, NSString *parent,
    NSString *name, NSDictionary *scenario, BOOL hardware, NSDictionary *binding, NSError **error)
{
    NSDictionary *snapshot = owner.evidence;
    if ((owner.state != A23TransactionCompleted && owner.state != A23TransactionRejected) ||
        !owner.storageRetained || !snapshot || [snapshot[@"raw"] length] != 184320 ||
        [snapshot[@"transactions"] length] != 26880 || !name.length ||
        [name containsString:@"/"] || [name isEqualToString:@"."] || [name isEqualToString:@".."] ||
        [name rangeOfString:@"\0"].location != NSNotFound) return fail(error, @"Not a saveable snapshot/path");
    NSMutableDictionary *metadata = [snapshot mutableCopy];
    [metadata removeObjectForKey:@"raw"]; [metadata removeObjectForKey:@"transactions"];
    metadata[@"bundle_schema"] = hardware ? @"A23-hardware-transaction-bundle-1" : @"A23-transaction-bundle-1";
    metadata[@"execution_mode"] = hardware ? @"hardware" : @"simulation";
    if (hardware) metadata[@"backend"] = @"iousbhost-no-td-1";
    if (binding) {
        metadata[@"bundle_schema"] = @"A23-burst-hardware-transaction-bundle-1";
        metadata[@"backend"] = @"iousbhost-single-burst-1";
        metadata[@"binding"] = binding;
    }
    metadata[@"hardware_verified"] = @NO;
    metadata[@"scenario"] = scenario;
    metadata[@"owner_state"] = @(owner.state);
    metadata[@"callback_count_at_save"] = @(owner.callbackCount);
    if (owner.abortError) metadata[@"abort_error"] = @{@"domain":owner.abortError.domain, @"code":@(owner.abortError.code)};
    if (![NSJSONSerialization isValidJSONObject:metadata]) return fail(error, @"Metadata is not JSON serializable");
    NSData *json = [NSJSONSerialization dataWithJSONObject:metadata options:NSJSONWritingSortedKeys error:error];
    if (!json) return NO;
    int parentFD = open(parent.fileSystemRepresentation, O_RDONLY | O_DIRECTORY | O_NOFOLLOW);
    if (parentFD < 0) return fail(error, @"Cannot open trusted parent directory");
    if (mkdirat(parentFD, name.fileSystemRepresentation, 0700) != 0) {
        close(parentFD); return fail(error, @"Directory exists or exclusive mkdir failed");
    }
    int directory = openat(parentFD, name.fileSystemRepresentation, O_RDONLY | O_DIRECTORY | O_NOFOLLOW);
    if (directory < 0) { close(parentFD); return fail(error, @"Cannot open new directory"); }
    NSArray *names = @[@"raw.bin", @"transactions.bin", @"metadata.json"];
    NSArray *files = @[snapshot[@"raw"], snapshot[@"transactions"], json];
    NSMutableString *manifest = [NSMutableString string];
    BOOL ok = YES;
    for (NSUInteger i = 0; ok && i < names.count; ++i) {
        ok = writeVerified(directory, names[i], files[i], error);
        [manifest appendFormat:@"%@  %@\n", sha(files[i]), names[i]];
    }
    NSData *sums = [manifest dataUsingEncoding:NSUTF8StringEncoding];
    if (ok) ok = writeVerified(directory, @"SHA256SUMS", sums, error);
    if (ok && fsync(directory) != 0) ok = fail(error, @"Directory fsync failed");
    NSData *commit = [[sha(sums) stringByAppendingString:@"\n"] dataUsingEncoding:NSUTF8StringEncoding];
    if (ok) ok = writeVerified(directory, @"COMMITTED", commit, error);
    if (ok && (fsync(directory) != 0 || fsync(parentFD) != 0)) ok = fail(error, @"Final directory fsync failed");
    close(directory); close(parentFD);
    // A durable directory is separate from native transfer success.
    return ok && [owner acknowledgeEvidenceSaved];
}
BOOL A23SaveSimulationEvidence(A23TransactionOwner *owner, NSString *parent, NSString *name, NSDictionary *scenario, NSError **error)
{ return saveEvidence(owner,parent,name,scenario,NO,nil,error); }
BOOL A23SaveHardwareObservation(A23TransactionOwner *owner, NSString *parent, NSString *name, NSError **error)
{ return saveEvidence(owner,parent,name,@{@"kind":@"no_td"},YES,nil,error); }

BOOL A23SaveBurstHardwareObservation(A23TransactionOwner *owner, NSString *parent, NSString *name, NSDictionary *binding, NSError **error)
{
    if (![binding isKindOfClass:NSDictionary.class] || binding.count!=3 ||
        ![binding[@"session_id"] isKindOfClass:NSString.class] ||
        ![[NSUUID alloc] initWithUUIDString:binding[@"session_id"]] ||
        ![binding[@"identity"] isKindOfClass:NSDictionary.class] ||
        ![binding[@"descriptor_sha256"] isKindOfClass:NSDictionary.class]) return fail(error,@"Invalid burst binding");
    NSDictionary *identity=binding[@"identity"],*hashes=binding[@"descriptor_sha256"];
    for(NSString *key in @[@"device_id",@"interface_id",@"parent_device_id"]){
        id v=identity[key];
        if(![v isKindOfClass:NSNumber.class] || CFGetTypeID((__bridge CFTypeRef)v)==CFBooleanGetTypeID() ||
            CFNumberIsFloatType((__bridge CFNumberRef)v) || [v compare:@0]!=NSOrderedDescending)return fail(error,@"Invalid burst identity");
    }
    if(identity.count!=3 || ![identity[@"device_id"] isEqual:identity[@"parent_device_id"]] || [identity[@"device_id"] isEqual:identity[@"interface_id"]] || hashes.count!=3)
        return fail(error,@"Invalid burst identity/hash binding");
    NSCharacterSet *hex=[[NSCharacterSet characterSetWithCharactersInString:@"0123456789abcdef"] invertedSet];
    for(NSString *key in @[@"device_descriptor",@"configuration_descriptor",@"active_interface"]){
        id v=hashes[key];if(![v isKindOfClass:NSString.class] || [v length]!=64 || [v rangeOfCharacterFromSet:hex].location!=NSNotFound)
            return fail(error,@"Invalid burst descriptor hash");
    }
    return saveEvidence(owner,parent,name,@{@"kind":@"single_burst",@"first_sequence":@1},YES,binding,error);
}

BOOL A23SaveBurstCheckpoint(NSDictionary *checkpoint, NSString *parent, NSString *name, NSError **error)
{
    if (![checkpoint isKindOfClass:NSDictionary.class] ||
        ![checkpoint[@"schema"] isEqual:@"A23-burst-sdk-checkpoint-1"] ||
        ![checkpoint[@"backend"] isEqual:@"iousbhost-single-burst-1"] ||
        ![checkpoint[@"hardware_verified"] isKindOfClass:NSNumber.class] ||
        CFGetTypeID((__bridge CFTypeRef)checkpoint[@"hardware_verified"])!=CFBooleanGetTypeID() ||
        [checkpoint[@"hardware_verified"] boolValue] || !name.length || [name containsString:@"/"] ||
        [name isEqual:@"."] || [name isEqual:@".."] || [name rangeOfString:@"\0"].location!=NSNotFound ||
        ![NSJSONSerialization isValidJSONObject:checkpoint]) return fail(error,@"Invalid burst checkpoint/path");
    for(NSString *key in @[@"hardware_entry_enabled",@"baseline_accepted",@"allow_next_burst",@"callback_drain_verified",@"usb_strict_pass"]){
        id v=checkpoint[key];if(![v isKindOfClass:NSNumber.class] || CFGetTypeID((__bridge CFTypeRef)v)!=CFBooleanGetTypeID() || [v boolValue])
            return fail(error,@"Checkpoint cannot grant hardware policy");
    }
    NSData *json=[NSJSONSerialization dataWithJSONObject:checkpoint options:NSJSONWritingSortedKeys error:error];
    if (!json || json.length>16384) return fail(error,@"Oversized burst checkpoint");
    int p=open(parent.fileSystemRepresentation,O_RDONLY|O_DIRECTORY|O_NOFOLLOW);
    if(p<0)return fail(error,@"Cannot open checkpoint parent");
    if(mkdirat(p,name.fileSystemRepresentation,0700)!=0){close(p);return fail(error,@"Checkpoint exists or mkdir failed");}
    int d=openat(p,name.fileSystemRepresentation,O_RDONLY|O_DIRECTORY|O_NOFOLLOW);
    if(d<0){close(p);return fail(error,@"Cannot open checkpoint directory");}
    NSData *sums=[[NSString stringWithFormat:@"%@  checkpoint.json\n",sha(json)] dataUsingEncoding:NSUTF8StringEncoding];
    BOOL ok=writeVerified(d,@"checkpoint.json",json,error) && writeVerified(d,@"SHA256SUMS",sums,error);
    if(ok && fsync(d)!=0)ok=fail(error,@"Checkpoint directory fsync failed");
    NSData *commit=[[sha(sums) stringByAppendingString:@"\n"] dataUsingEncoding:NSUTF8StringEncoding];
    if(ok)ok=writeVerified(d,@"COMMITTED",commit,error);
    if(ok && (fsync(d)!=0 || fsync(p)!=0))ok=fail(error,@"Checkpoint final fsync failed");
    close(d);close(p);return ok;
}
