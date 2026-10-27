// Appended after existing frozen fake SDK prefixes, rebased only at sequence
// constants; bRequest81 remains unchanged. Real scope/permit/coordinator execute.
@interface Live75Status : SDKModelInterface
@end
@implementation Live75Status
- (NSDictionary *)readStatus {
    NSDictionary *reply=[super readStatus];NSMutableData *raw=[reply[@"data"] mutableCopy];
    if(raw.length==168 && self.statusReads>1){IsoProbeStatus *s=raw.mutableBytes;
        s->report_count=([self.fault isEqual:@"queued-delay"] || self.statusReads>=3)?0:1;
        if([self.fault isEqual:@"bad-status"] && self.statusReads==2)s->transferred=0;
    }
    return @{@"data":raw,@"observation":reply[@"observation"]};
}
@end
