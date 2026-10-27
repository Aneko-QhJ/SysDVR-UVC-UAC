#pragma once
#include "ep0_startup_journal.h"
bool Ep0StartupBegin(const uint8_t recipe[32]);
void Ep0StartupCall(unsigned step);
void Ep0StartupResult(unsigned step,uint32_t result);
void Ep0StartupVoid(unsigned step);
void Ep0StartupFatal(uint32_t result); /* Records/seals only; caller keeps original fatalThrow. */
bool Ep0StartupSeal(void);
void Ep0StartupBindThreads(const void *video,const void *audio);
unsigned Ep0StartupCreateStep(const void *thread);
unsigned Ep0StartupStartStep(const void *thread);
size_t Ep0StartupSnapshot(uint8_t *out,size_t cap);
unsigned Ep0StartupStatus(void); /* 0 unattempted, 1 initializing, 2 enabled, 3 disabled. */
uint32_t Ep0StartupIdentityResult(void); /* Result only meaningful after completed attempt. */
