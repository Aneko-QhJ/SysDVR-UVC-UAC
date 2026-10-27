#pragma once
#include "ep0_lifecycle_capsule.h"
/* MAIN only. This API grants no owner/DMA access and no cleanup permission. */
enum { EP0_LF_IDENTITY=1,EP0_LF_NONCE,EP0_LF_SD_OPEN,EP0_LF_CREATE,EP0_LF_FILE_OPEN,
       EP0_LF_WRITE,EP0_LF_FLUSH,EP0_LF_SIZE,EP0_LF_READ,EP0_LF_COMPARE,EP0_LF_COMMIT,EP0_LF_READY };
uint32_t Ep0LifePrepare(const uint8_t recipe[32]);
bool Ep0LifeNote(unsigned stage,uint32_t result,uint32_t arg0,uint32_t arg1);
bool Ep0LifeContext(const uint8_t boot[16],const uint8_t session[16]);
void Ep0LifeClose(void);
void Ep0LifeFinish(unsigned stage,uint32_t result,uint32_t reason);
uint32_t Ep0LifeLastPhase(void);
uint32_t Ep0LifeLastResult(void);
