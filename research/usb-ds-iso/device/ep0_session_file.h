#pragma once
#include "ep0_candidate_sink.h"
bool Ep0SessionSaveJoined(uint32_t video_join,uint32_t audio_join);
const Ep0SinkState *Ep0SessionFileObservation(void); /* Main only, after this save returns. */
