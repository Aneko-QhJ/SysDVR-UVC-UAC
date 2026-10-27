#pragma once
#include "ep0_session_capture.h"
#include "ep0_startup_runtime.h"
/* Bridge is appended only to the new generated startup runtime copy. */
const Ep0StartupJournal *Ep0StartupJournalForSession(void);
uint64_t Ep0StartupWriterForSession(void);
bool Ep0SessionBind(uint64_t writer,const uint8_t boot[16],const uint8_t session[16],const uint8_t recipe[32]);
bool Ep0SessionStartupOnly(const uint8_t recipe[32]);
bool Ep0SessionJoined(const uint8_t recipe[32],uint64_t exporter,uint32_t video_join,uint32_t audio_join,bool diagnostic_returned);
const uint8_t *Ep0SessionBytes(size_t *n); /* Immutable after successful one-shot capture. */
