#import <Foundation/Foundation.h>

// Process/code observations only. No registry, user client, device or SD access.
NSDictionary *A23ExecutionContextPolicy(void);
NSDictionary *A23ReadExecutionContext(NSString *binary);
BOOL A23ValidateExecutionContext(NSDictionary *context, NSString *receiverSHA);
