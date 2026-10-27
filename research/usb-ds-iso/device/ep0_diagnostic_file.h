#pragma once
#include "ep0_diagnostic_sink.h"
/* Only after both real joins and rejected Finish. Never authorizes cleanup. */
bool Ep0CandidateSaveDiagnostic(uint64_t exporter,uint32_t video_join,uint32_t audio_join,const uint8_t recipe[32]);
const Ep0SinkState *Ep0CandidateDiagnosticFileObservation(void);
const uint8_t *Ep0CandidateDiagnosticBytes(size_t *size);
