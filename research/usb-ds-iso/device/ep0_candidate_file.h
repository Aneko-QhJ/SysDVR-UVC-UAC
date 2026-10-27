#pragma once
#include "ep0_candidate_sink.h"
/* Called once, after successful Finish and both real joins, by the exporter. */
bool Ep0CandidateSaveCapture(void);
const Ep0SinkState *Ep0CandidateFileObservation(void);
