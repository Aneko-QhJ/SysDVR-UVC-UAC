#pragma once
/* File-format/observer prototype only. No SDK, owner access or cleanup authority.
 * A future MAIN-only adapter must prepare the file before USB initialization.
 * write_once must write/flush/readback/commit once; a failed call disables notes.
 * Complete bytes never authenticate that call's final commit or physical origin.
 */
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>

#define EP0_LCP_HEADER 128u
#define EP0_LCP_RECORD 96u
#define EP0_LCP_CAPACITY 40u
#define EP0_LCP_MAX (EP0_LCP_HEADER+EP0_LCP_RECORD*EP0_LCP_CAPACITY)
enum {
 EP0_L_PREPARED=1,EP0_L_USB_INIT_CALL,EP0_L_USB_INIT_RESULT,EP0_L_QUIET_ENTER,
 EP0_L_MAIN_LOOP_LEFT,EP0_L_CLEANUP_RESULT,EP0_L_VIDEO_JOIN_CALL,EP0_L_VIDEO_JOIN_RESULT,
 EP0_L_AUDIO_JOIN_CALL,EP0_L_AUDIO_JOIN_RESULT,EP0_L_EXPORTER_RESULT,EP0_L_OWNER_FINISH_RESULT,
 EP0_L_PRIMARY_SAVE_CALL,EP0_L_PRIMARY_SAVE_RESULT,EP0_L_EXEC_BUILD_RESULT,
 EP0_L_EXEC_SAVE_CALL,EP0_L_EXEC_SAVE_RESULT,EP0_L_SD_OPEN_CALL,EP0_L_SD_OPEN_RESULT,
 EP0_L_FILE_CREATE_CALL,EP0_L_FILE_CREATE_RESULT,EP0_L_CONTEXT,EP0_L_RETAIN,EP0_L_MAIN_RETURN
};
typedef uint32_t (*Ep0LcpWrite)(void *,size_t,const void *,size_t);
typedef struct {
 uint64_t writer,last_tick;uint32_t count,last_stage,join_mask,last_result,join_calls,join_seen;
 bool disabled,deferred,closed;void *io;Ep0LcpWrite write_once;
} Ep0LifecycleCapsule;
static inline void ep0_lcp_u16(uint8_t *p,uint16_t x) { p[0]=(uint8_t)x;p[1]=(uint8_t)(x>>8); }
static inline void ep0_lcp_u32(uint8_t *p,uint32_t x) { for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(x>>(8*i)); }
static inline void ep0_lcp_u64(uint8_t *p,uint64_t x) { for(unsigned i=0;i<8;i++)p[i]=(uint8_t)(x>>(8*i)); }
static inline uint32_t ep0_lcp_crc(const uint8_t *p,size_t n) {
 uint32_t c=~0u;for(size_t i=0;i<n;i++) { c^=p[i];for(unsigned j=0;j<8;j++)c=(c>>1)^(0xedb88320u&-(c&1u)); }return ~c;
}
static inline bool ep0_lcp_nonzero(const uint8_t *p,size_t n) {
 if(!p)return false;uint8_t x=0;for(size_t i=0;i<n;i++)x|=p[i];return x!=0;
}
static inline bool ep0_lcp_init(Ep0LifecycleCapsule *s,void *io,Ep0LcpWrite write_once,
 uint64_t writer,uint64_t frequency,uint64_t start,const uint8_t nonce[16],const uint8_t recipe[32]) {
 /* s must be zero-initialized once, e.g. static storage. Never refill it. */
 if(!s || s->writer || s->write_once || !write_once || !writer || !frequency || !ep0_lcp_nonzero(nonce,16) || !ep0_lcp_nonzero(recipe,32))return false;
 memset(s,0,sizeof(*s));s->writer=writer;s->last_tick=start;s->io=io;s->write_once=write_once;
 uint8_t h[EP0_LCP_HEADER]={0};memcpy(h,"EP0LCP1",7);
 ep0_lcp_u16(h+8,1);ep0_lcp_u16(h+10,EP0_LCP_HEADER);ep0_lcp_u16(h+12,EP0_LCP_RECORD);ep0_lcp_u16(h+14,EP0_LCP_CAPACITY);
 ep0_lcp_u64(h+16,writer);ep0_lcp_u64(h+24,frequency);ep0_lcp_u64(h+32,start);
 memcpy(h+40,nonce,16);memcpy(h+56,recipe,32);ep0_lcp_u32(h+124,ep0_lcp_crc(h,124));
 s->last_result=write_once(io,0,h,sizeof(h));s->disabled=s->last_result!=0;return !s->disabled;
}
static inline bool ep0_lcp_note(Ep0LifecycleCapsule *s,uint64_t writer,unsigned stage,uint64_t tick,
 uint32_t result,uint32_t arg0,uint32_t arg1,const uint8_t *joined_context32) {
 if(!s || s->disabled || s->closed || !s->write_once || writer!=s->writer ||
    stage<EP0_L_PREPARED || stage>EP0_L_MAIN_RETURN || tick<s->last_tick || s->count>=EP0_LCP_CAPACITY)return false;
 if(!s->count && stage!=EP0_L_PREPARED)return false;
 if(s->deferred && stage!=EP0_L_MAIN_LOOP_LEFT)return false;
 if(stage==EP0_L_MAIN_LOOP_LEFT && !s->deferred)return false;
 if(stage==EP0_L_QUIET_ENTER && s->deferred)return false;
 if(stage==EP0_L_VIDEO_JOIN_CALL && (s->join_calls&1))return false;
 if(stage==EP0_L_AUDIO_JOIN_CALL && (s->join_calls&2))return false;
 if(stage==EP0_L_VIDEO_JOIN_RESULT && s->last_stage!=EP0_L_VIDEO_JOIN_CALL)return false;
 if(stage==EP0_L_AUDIO_JOIN_RESULT && s->last_stage!=EP0_L_AUDIO_JOIN_CALL)return false;
 if(stage==EP0_L_VIDEO_JOIN_RESULT && (s->join_seen&1))return false;
 if(stage==EP0_L_AUDIO_JOIN_RESULT && (s->join_seen&2))return false;
 bool needs_joins=(stage>=EP0_L_OWNER_FINISH_RESULT && stage<=EP0_L_FILE_CREATE_RESULT) || stage==EP0_L_CONTEXT;
 if(needs_joins && s->join_mask!=3)return false;
 /* Validate the gate BEFORE touching an optional owner-context pointer. */
 if(joined_context32 && (stage!=EP0_L_CONTEXT || s->join_mask!=3))return false;
 if(stage==EP0_L_CONTEXT && (!ep0_lcp_nonzero(joined_context32,16) || !ep0_lcp_nonzero(joined_context32+16,16)))return false;
 uint8_t r[EP0_LCP_RECORD]={0};memcpy(r,"LCPE",4);ep0_lcp_u32(r+4,s->count+1);
 ep0_lcp_u16(r+8,(uint16_t)stage);ep0_lcp_u16(r+10,joined_context32?1:0);ep0_lcp_u64(r+12,tick);
 ep0_lcp_u32(r+20,result);ep0_lcp_u32(r+24,arg0);ep0_lcp_u32(r+28,arg1);
 if(joined_context32)memcpy(r+32,joined_context32,32);ep0_lcp_u32(r+92,ep0_lcp_crc(r,92));
 s->last_result=s->write_once(s->io,EP0_LCP_HEADER+s->count*EP0_LCP_RECORD,r,sizeof(r));
 if(s->last_result) { s->disabled=true;return false; } /* No overwrite, retry or cleanup decision. */
 s->count++;s->last_stage=stage;s->last_tick=tick;
 if(stage==EP0_L_QUIET_ENTER)s->deferred=true;
 if(stage==EP0_L_MAIN_LOOP_LEFT)s->deferred=false;
 if(stage==EP0_L_VIDEO_JOIN_CALL)s->join_calls|=1;
 if(stage==EP0_L_AUDIO_JOIN_CALL)s->join_calls|=2;
 if(stage==EP0_L_VIDEO_JOIN_RESULT)s->join_seen|=1;
 if(stage==EP0_L_AUDIO_JOIN_RESULT)s->join_seen|=2;
 if(stage==EP0_L_VIDEO_JOIN_RESULT && !result)s->join_mask|=1;
 if(stage==EP0_L_AUDIO_JOIN_RESULT && !result)s->join_mask|=2;
 if(stage==EP0_L_RETAIN || stage==EP0_L_MAIN_RETURN)s->closed=true;
 return true;
}
