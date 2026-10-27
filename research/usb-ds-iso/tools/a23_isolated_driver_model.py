"""Derive a finite model-only link scope from pinned, frozen sources."""
import audit_a23_quiet_driver_copy as previous
f=previous.f
BASE='research/usb-ds-iso/'
PINS={'research/usb-ds-iso/host/a23_clock_candidate.c': '137345b616cfd0de504ec1db50a5853c95191df5fcf73734d68fc9e03ba80ab7',
 'research/usb-ds-iso/host/a23_clock_candidate.h': '30b3039fe3e78dc66fa8d398b270eb372c6a2effe06df966dd6db9c80c58c2df',
 'research/usb-ds-iso/host/a23_execution_context.h': '931ddc389527c51eae1fc7575e271ac24dec123aa5085807af4d088f391037f9',
 'research/usb-ds-iso/host/a23_lead32_policy.h': 'dd5e57e8f263cde3d664dd6837301dcaeec061310f8c33409a83c93a91f9a170',
 'research/usb-ds-iso/host/a23_paired_sdk_adapter.h': 'ce71d8d0b20374b3474e4bd891c61deffce98fcbb782ef55e2ea4cc49ddbfa38',
 'research/usb-ds-iso/host/a23_paired_sdk_adapter.m': 'c71926ab4aa71bd546d539cff0d982efb8385f5cc71b983e4280a363309ee876',
 'research/usb-ds-iso/host/a23_passive_wait_adapter.h': 'b941cb9c3ec96fe3e5afe0bea4faa776c258d17ac7977ef6d06f5b907581d465',
 'research/usb-ds-iso/host/a23_passive_wait_policy.h': '437dfd7f719e7167815848e18c4c0f891e4d91701c1c2769f2c18d0871e6ab7a',
 'research/usb-ds-iso/host/a23_quiet_driver_clock_candidate.h': '4dd89ce7d0cb3d62e6652df4f0fdbe7a1ef336f64641af0e6269a1f9b775df73',
 'research/usb-ds-iso/host/a23_quiet_poll_candidate.h': '2ef135f9fdbb61c43942104e240efcc99350bb52b597531ba16a166d7814c8cf',
 'research/usb-ds-iso/host/a23_scope_verifier.h': '67be1aee6c278c41a9c2b9d2e20162093d7e8096944b03d86cd96882e9df5c6c',
 'research/usb-ds-iso/host/a23_shared_sequence_permit.h': 'cf52ae9adbf04f7aa6f0f245d1aa9f0dcbc5205d97df4d109406fb0ab7ec1fdb',
 'research/usb-ds-iso/host/a23_two_epoch_entry.h': 'f3dc737b0d657fbc0f2175b29595346e79f92db6c0f079e86a199a2ebd233fd3',
 'research/usb-ds-iso/host/a23_two_epoch_receiver.h': '97761cc72bfa9481af787e52022a38c8148c7a8beee129511bf03faa5ba93607',
 'research/usb-ds-iso/host/a23_two_epoch_sdk_driver.h': '808cbf0fbdf5a2e27824838fa2ebb7466b81a04bb52bb273eb3c99e828a851a7',
 'research/usb-ds-iso/host/a23_two_epoch_sdk_driver.m': '4f7f46345f1dbadf12b02bcf8c2322caacde33a63addd219976c9b942bfe8797',
 'research/usb-ds-iso/host/a23_waiting_burst_entry.h': 'd7746cb67ea42dbb4ca9a065e3dab2501fc358572b3a70c5cfb06df5a48eee72',
 'research/usb-ds-iso/host/a23_waiting_receiver.h': 'c0816d6df867801776c6a35802c9fed86b78f1d9c62f4cfab68a81fdea61f7fc',
 'research/usb-ds-iso/host/io_usb_host_burst_entry.h': '6138c99866b2da5f04c1387aef4d323b0753641243f2b57562ef37393ba18269',
 'research/usb-ds-iso/host/io_usb_host_burst_executor.h': '8a76fee2ef63642df80ebe0e7fdaab83c92693a4d325269b14bde04b9f0ee3f1',
 'research/usb-ds-iso/host/io_usb_host_burst_sdk_driver.h': '7d39cfd8e83641b5be471dcea74c54db97ba5bafeaf3baca4ca3e0551cc98c28',
 'research/usb-ds-iso/host/io_usb_host_burst_sdk_transport.h': '75f30601cb3c31df7361d9558e4e540848a5e3fe217327a6929765b74371da9c',
 'research/usb-ds-iso/host/io_usb_host_evidence.h': 'a5765cdca255d789089788cc756ff400f22ad753ed62d80f229e17093420fe3f',
 'research/usb-ds-iso/host/io_usb_host_evidence.m': '3e5d622e56cd9ccd49085b7930345d99f942b8c6f237f91762a6f038ef44aecd',
 'research/usb-ds-iso/host/io_usb_host_no_td_driver.h': 'e946a5134a6082c094734fabdd3af29f4cfdc886f806b8b158ff8ae4e9f66c96',
 'research/usb-ds-iso/host/io_usb_host_runtime_guard.h': '6df52e22fa86e157b30e360f20fa7c77c44e8f25f83cd35d68abbc54fba2e7c9',
 'research/usb-ds-iso/host/io_usb_host_runtime_guard.m': '3dcbd497a11349d1e4242a34cb8e6d8264abcefa07a751cdff36b966e016d282',
 'research/usb-ds-iso/host/io_usb_host_sdk_adapter.h': '8eb836a20745c2b6da47fea82bceca0bbd03fae8ef15274a350731c54990c550',
 'research/usb-ds-iso/host/io_usb_host_session.h': 'c02e906621e194d738cca9111e202cae8e77d595ef345616b04043245fac3a34',
 'research/usb-ds-iso/host/io_usb_host_session.m': '6fe51c61f3d0d408ec8d206669ab148769fadc25b11b222353e2542713933499',
 'research/usb-ds-iso/host/io_usb_host_transaction_owner.h': 'c2d17aa8149bc327af60d92e44e8ad4020e3282babe1fb7e6a7e1d6e25e6dd78',
 'research/usb-ds-iso/host/io_usb_host_transaction_owner.m': '01851a51a8dab35b5c2c35f80fd68abb4503b9ac702252bbfb3e181b5fb5a70c',
 'research/usb-ds-iso/tests/a23_paired_sdk_fixture.inc': '5756c8f810dad5e0f5eb1fb61852b0036e0b1e5a941c84abbd2cfbf14708e3e9',
 'research/usb-ds-iso/tests/a23_two_epoch_receiver_test.m': '9f4ab384939381664e0451099597bb47bdfc09f47a7d9ef8f9c77627c9787cfd',
 'research/usb-ds-iso/tests/a23_two_epoch_sdk_fixture.inc': 'd73e2bc9a8cb69487a13da33df2935bd8971cf703ab297854fba6e810e46887f',
 'source/uvc/iso_probe_protocol.h': 'eedebc97e50f14890660fb7d2dba2103a60372d1e479896d41b569d7c9ec7bea'}


def cut(text,begin,end):
    f.require(text.count(begin)==1 and text.count(end)==1,'model extraction anchor differs')
    return text[text.index(begin):text.index(end)]


def render(source):
    # All inputs are pinned by the parent registry; no generated source is read
    # from a live build directory or an actual execution context.
    def read(name):return (source/BASE/name).read_text()
    expected=PINS
    for name,digest in expected.items():
        f.require(f.sha((source/name).read_bytes())==digest,'model input pin differs '+name)
    out={}
    for path in sorted((source/BASE/'host').glob('*.h')):
        key=BASE+'host/'+path.name
        if key in expected:out[key]=path.read_bytes()
    out[previous.PROTOCOL]=(source/previous.PROTOCOL).read_bytes()
    out[BASE+'host/a23_clock_candidate.c']=(source/BASE/'host/a23_clock_candidate.c').read_bytes()
    original=(source/previous.DRIVER).read_bytes()
    out[previous.DRIVER]=previous.patch.render(original)
    text=read('host/a23_paired_sdk_adapter.m')
    out[BASE+'host/a23_paired_sdk_adapter.m']=(text[:text.index('// SDK accessor bodies')]+text[text.index('static BOOL positive(id v)'):]).replace('#include <mach/mach_time.h>\n','').encode()
    text=read('host/io_usb_host_runtime_guard.m')
    out[BASE+'host/io_usb_host_runtime_guard.m']=(text[:text.index('@implementation A23LocalMachClock')]+text[text.index('@implementation A23BudgetTransport'):]).replace('#include <mach/mach_time.h>\n','').encode()
    text=read('host/io_usb_host_transaction_owner.m')
    prefix='''#import "io_usb_host_transaction_owner.h"
#include <string.h>
#include <stdatomic.h>
// Independent injected owner domain: no mapping to driver ticks is asserted.
static atomic_uint_fast64_t ownerModelTicks=100;
static uint64_t ownerModelNow(void){return atomic_fetch_add(&ownerModelTicks,1);}
_Static_assert(sizeof(IOUSBHostIsochronousTransaction)==28,"SDK layout changed");
'''
    out[BASE+'host/io_usb_host_transaction_owner.m']=(prefix+text[text.index('@implementation A23TransactionOwner'):].replace('mach_absolute_time()','ownerModelNow()')).encode()
    text=read('host/io_usb_host_evidence.m')
    out[BASE+'host/model_descriptor.m']=('#import "io_usb_host_evidence.h"\n'+cut(text,'static BOOL fail(','static NSString *boundedText')+cut(text,'NSDictionary *A23ValidateDescriptors(','static NSString *sha(')).encode()
    text=read('host/io_usb_host_session.m')
    out[BASE+'host/model_journal.m']=(text[:text.index('static BOOL registryNumber')]).replace('#include <mach/mach_time.h>\n','').encode()
    two=read('tests/a23_two_epoch_receiver_test.m').split('\nint main(',1)[0]
    numeric=read('tests/a23_isolated_driver_clock.inc')
    two=two[:two.index('@interface TwoClock')]+numeric+two[two.index('@interface TwoResources'):]
    two=two.replace('#include <mach/mach_time.h>\n','')
    pair=read('tests/a23_paired_sdk_fixture.inc').split('\nint main(',1)[0]
    sdk=read('tests/a23_two_epoch_sdk_fixture.inc').split('\nint main(',1)[0]
    out[BASE+'tests/model_main.m']=(two+pair+sdk+read('tests/a23_isolated_driver_main.inc')).encode()
    # Headers provide ABI/types only. Every executable implementation is checked.
    for name,raw in out.items():
        if not name.endswith(('.m','.c','.inc')):continue
        for token in ('mach_absolute_time','mach_timebase_info','#include <mach/',
                      'initWithIOService:','IOServiceMatching','IOServiceOpen','IOObjectRetain','IOObjectRelease',
                      'A23ReadExecutionContext','@implementation A23ExistingPipeTransport',
                      '@implementation A23PairedSDKOperations','@implementation A23LocalMachClock'):
            f.require(token.encode() not in raw,'executable model scope contains '+token+' in '+name)
    return dict(sorted(out.items()))
