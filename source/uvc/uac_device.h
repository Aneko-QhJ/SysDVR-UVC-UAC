#pragma once
#include <switch.h>
#include "uac_descriptors.h"

// ============================================================================
// UAC Device State
// ============================================================================

typedef enum {
    UAC_STATE_STOPPED = 0,
    UAC_STATE_STREAMING,
} UacDeviceState;

// ============================================================================
// Audio Frame Data
// ============================================================================

typedef struct {
    u8* Data;           // PCM audio data
    u32 DataSize;       // Size in bytes
    u64 Timestamp;      // Timestamp in microseconds
} AudioFrame;

// ============================================================================
// UAC Device Context (managed by composite device)
// ============================================================================

typedef struct {
    UacDeviceState state;

    // USB interface
    UsbDsInterface* controlInterface;
    UsbDsInterface* streamingInterface;

    // Endpoints
    UsbDsEndpoint* audioEndpointIn;

    // Audio buffer
    u8* audioBuffer;

    // Synchronization
    Mutex streamingMutex;

    bool initialized;
} UacDeviceContext;

// ============================================================================
// Public API
// ============================================================================

/**
 * Check if UAC is streaming audio
 */
bool UacDeviceIsStreaming(void);

/**
 * Send audio data to USB host
 * @param data PCM audio data (16-bit stereo)
 * @param size Size in bytes
 * @param timestamp Timestamp in microseconds
 * @return true if sent successfully
 */
bool UacDeviceSendAudio(const void* data, size_t size, u64 timestamp);

#if defined(UAC_U2_PCM_SOURCE)
/**
 * Queue captured PCM (48 kHz stereo s16) for the U2 burst producer.
 * Safe to call from the grc:d audio thread; never blocks.
 */
void UacDevicePushPcm(const void* data, size_t size);

/** Total bytes the burst producer had to zero-fill (silence). */
uint32_t UacDevicePcmUnderrunBytes(void);
#endif
