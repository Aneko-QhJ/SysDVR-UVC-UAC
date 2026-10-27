"""Derive a new fault fixture while retaining the frozen driver/link scope."""
import a23_isolated_driver_model as old_model
f=old_model.f
BASE=old_model.BASE
PINS={'research/usb-ds-iso/tests/a23_isolated_driver_clock.inc': '1c5aa9bd60ef8f21b5651388d8e866a927d981bba94dd7324b42caef389a1bfb', 'research/usb-ds-iso/tests/a23_isolated_driver_main.inc': '3901a0b68353770a640ad43eae7b95a9641f44bce1642e67a4d986e700d2e146'}


def once(text,old,new):
    f.require(text.count(old)==1,'fault fixture anchor missing or repeated');return text.replace(old,new,1)


def render(source):
    for name,h in PINS.items():f.require(f.sha((source/name).read_bytes())==h,'old model fixture pin differs')
    out=old_model.render(source);key=BASE+'tests/model_main.m';text=out[key].decode()
    clock=(source/BASE/'tests/a23_isolated_driver_clock.inc').read_text()
    faultclock=(source/BASE/'tests/a23_driver_fault_clock.inc').read_text()
    text=once(text,clock,clock+'\n'+faultclock+'\n')
    marker='// Model-only faults at documented event boundaries; no production entry point.'
    f.require(text.count(marker)==1,'old model main marker differs')
    text=text[:text.index(marker)]+(source/BASE/'tests/a23_driver_fault_main.inc').read_text()
    for token in ('mach_absolute_time','mach_timebase_info','initWithIOService:','A23ReadExecutionContext'):
        f.require(token not in text,'fault fixture crossed model scope')
    out[key]=text.encode();return out
