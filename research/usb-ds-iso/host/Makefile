CC ?= cc
PKG_CONFIG ?= pkg-config
ifeq ($(shell uname -s),Darwin)
LIBUSB_PREFIX ?= /opt/homebrew
CFLAGS += -I$(LIBUSB_PREFIX)/include/libusb-1.0
LDLIBS += -L$(LIBUSB_PREFIX)/lib -lusb-1.0
else
CFLAGS += $(shell $(PKG_CONFIG) --cflags libusb-1.0)
LDLIBS += $(shell $(PKG_CONFIG) --libs libusb-1.0)
endif
CFLAGS += -std=c11 -O2 -Wall -Wextra -Werror

iso-probe: iso-probe.c ../../../source/uvc/iso_probe_protocol.h
	$(CC) $(CFLAGS) $< $(LDLIBS) -o $@

clean:
	rm -f iso-probe

.PHONY: clean
