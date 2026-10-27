"""Deterministic synthetic log for the injected BurstMock ISO7 snapshot only."""
from audit_io_usb_host_device import BUILD_ID


def group(request_type,request,value,length):
    lines=[]
    for interface in (0,1):
        lines.extend([f'EP0[{interface}]: reqType=0x{request_type:02x} req=0x{request:02x} wVal=0x{value:04x} wIdx=0x0002 wLen={length}',
                      f'EP0[{interface}]: wIndex mismatch, ignoring'])
    return '\n'.join(lines)+'\n'


def synthetic_log():
    # Numbers are mock constants matching BurstMock, not copied hardware data.
    startup=f'''SysDVR-UVC 1.0.0 initializing...
SysDVR-UVC starting...
ISO diagnostic revision A23 HS ISO7 bInterval1 followup-SIA experiment
ISO HOS 22.5.0
ISO firmware query rc=0x0
ISO usb pid=86 query rc=0x0
ISO usb module query rc=0x0 count=1
ISO usb module[0] BuildID={BUILD_ID} base=b9ac00000 size=369000
ISO usb debug attach rc=0x0
ISO runtime patch result=0 record=21 last-rc=0x0
UVC device initialized
SysDVR-UVC running (video + audio)
USB host connected
'''
    events='''ISO submit seq=1 speed=3 length=3072 rc=0x0 urb=42
ISO timing seq=1 urb=42 frequency=19200000 trigger=10 post-before=11 post-after=12 ack-before=13 ack-after=14
'''
    terminal='''ISO seq=1 URB=42 requested=3072 raw-count=3072 status=3 diag-word2=1203770385
USB host disconnected
'''
    return (startup+group(0xc1,0x51,0,168)+group(0x41,0x54,1,0)+events+group(0xc1,0x51,0,168)+terminal).encode()
