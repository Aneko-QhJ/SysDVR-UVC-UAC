// Inspect this process's loaded framework code only. No USB object is created,
// no registry is enumerated, and no I/O method or stub target is invoked.
#import <Foundation/Foundation.h>
#import <IOUSBHost/IOUSBHost.h>
#include <dlfcn.h>
#include <mach-o/dyld.h>
#include <mach-o/getsect.h>
#include <ptrauth.h>
#include <string.h>

static uintptr_t adrpTarget(uint32_t word, uintptr_t pc)
{
    int64_t immediate = ((word >> 5 & 0x7ffff) << 2) | (word >> 29 & 3);
    if (immediate & 0x100000) immediate -= 0x200000;
    return (pc & ~(uintptr_t)4095) + immediate * 4096;
}

int main(int argc, const char **argv)
{
    @autoreleasepool {
        if (argc != 1) { (void)argv; return 2; }
        // A class address keeps the framework linked; it does not open a device.
        Class pipeClass = NSClassFromString(@"IOUSBHostPipe");
        if (!pipeClass || !dlopen("/System/Library/Frameworks/IOUSBHost.framework/Versions/A/IOUSBHost", RTLD_NOW)) return 3;
        const char *path = "/System/Library/Frameworks/IOUSBHost.framework/Versions/A/IOUSBHost";
        const struct mach_header_64 *header = NULL;
        intptr_t slide = 0;
        for (uint32_t i = 0; i < _dyld_image_count(); ++i) {
            if (!strcmp(_dyld_get_image_name(i), path)) {
                header = (const struct mach_header_64 *)_dyld_get_image_header(i);
                slide = _dyld_get_image_vmaddr_slide(i);
                break;
            }
        }
        if (!header) return 4;
        const uint8_t expected[16] = {0xb0,0xd4,0x1e,0xef,0xc9,0xbf,0x39,0xdd,0xa1,0xc4,0x22,0x6d,0xcb,0x94,0xe7,0x8b};
        bool matched = false;
        const struct load_command *command = (const void *)(header + 1);
        for (uint32_t i = 0; i < header->ncmds; ++i) {
            if (command->cmd == LC_UUID) matched = !memcmp(((const struct uuid_command *)command)->uuid, expected, 16);
            command = (const void *)((const uint8_t *)command + command->cmdsize);
        }
        if (!matched) { fprintf(stderr, "Framework UUID differs from audited image\n"); return 5; }
        uintptr_t addresses[] = {0x1980c5430,0x1980ee2f0,0x1980ee330,0x19811fa50,
            0x1980fc160,0x1980c53f0,0x1980c5620,0x1980c5630,0x198004670,
            0x1980043a0,0x198104590,0x1980ee300,0x1980ee2e0};
        NSMutableArray *rows = [NSMutableArray array];
        for (size_t i = 0; i < sizeof(addresses) / sizeof(*addresses); ++i) {
            uintptr_t pc = addresses[i] + slide;
            uint32_t words[4]; memcpy(words, (void *)pc, sizeof(words));
            NSMutableDictionary *row = [@{@"stub": @(addresses[i])} mutableCopy];
            if ((words[0] & 0x9f00001f) == 0x90000001 &&
                (words[1] & 0xff8003ff) == 0x91000021 &&
                (words[2] & 0xfc000000) == 0x14000000) {
                uintptr_t selector = adrpTarget(words[0], pc) +
                    ((words[1] >> 10 & 0xfff) << ((words[1] & (1 << 22)) ? 12 : 0));
                row[@"selector"] = [NSString stringWithUTF8String:(const char *)selector];
            } else if ((words[0] & 0x9f00001f) == 0x90000011 &&
                (words[1] & 0xff8003ff) == 0x91000231 &&
                words[2] == 0xf9400230 && words[3] == 0xd71f0a11) {
                uintptr_t got = adrpTarget(words[0], pc) +
                    ((words[1] >> 10 & 0xfff) << ((words[1] & (1 << 22)) ? 12 : 0));
                void *target; memcpy(&target, (void *)got, sizeof(target));
                target = ptrauth_strip(target, ptrauth_key_function_pointer);
                Dl_info info;
                if (!dladdr(target, &info) || !info.dli_sname) return 6;
                row[@"symbol"] = [NSString stringWithUTF8String:info.dli_sname];
                row[@"image"] = [NSString stringWithUTF8String:info.dli_fname];
                row[@"target"] = @((uintptr_t)target - slide);
            } else { fprintf(stderr, "Unrecognized stub at %llx\n", (unsigned long long)addresses[i]); return 7; }
            [rows addObject:row];
        }
        NSData *json = [NSJSONSerialization dataWithJSONObject:@{
            @"schema": @"A23-framework-stubs-1", @"usb_accessed": @NO,
            @"framework_uuid": @"b0d41eefc9bf39dda1c4226dcb94e78b", @"stubs": rows}
            options:NSJSONWritingPrettyPrinted | NSJSONWritingSortedKeys error:NULL];
        if (!json || fwrite(json.bytes, 1, json.length, stdout) != json.length) return 8;
        putchar('\n');
    }
    return 0;
}
