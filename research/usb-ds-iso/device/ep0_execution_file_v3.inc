/* Appended only to the isolated copy of ep0_session_file.c. */
#include "ep0_execution_v3.h"
#include "ep0_execution_sink_v3.h"
static Ep0SinkState execution_file_sink;
const Ep0SinkState *Ep0ExecutionFileObservation(void) { return &execution_file_sink; }
bool Ep0ExecutionSaveJoined(uint32_t video,uint32_t audio) {
    if(video || audio || execution_file_sink.attempted)return false;
    size_t n=0;const uint8_t *bytes=Ep0ExecutionBytes(&n);
    if(!bytes || n<EP0_EXEC_HEADER || n>EP0_EXEC_MAX || memcmp(bytes,"EP0EXE3\0",8))return false;
    char path[96];static const char hex[]="0123456789abcdef";
    memcpy(path,"/ep0-",5);
    for(unsigned i=0;i<32;i++) { uint8_t x=bytes[112+i];path[5+i*2]=hex[x>>4];path[6+i*2]=hex[x&15]; }
    memcpy(path+69,".execution.bin",15);
    Ep0SessionFileIo io={0};Result rc=fsOpenSdCardFileSystem(&io.fs);
    if(R_FAILED(rc)) { execution_file_sink.attempted=true;execution_file_sink.phase=EP0_SINK_CREATE;execution_file_sink.result=rc;return false; }
    Ep0SinkIo ops={&io,session_file_create_open,session_file_write_at,session_file_flush,session_file_file_size,
        session_file_read_at,session_file_close_file,session_file_commit};
    bool ok=ep0_execution_sink_once(&execution_file_sink,&ops,path,bytes,n);
    fsFsClose(&io.fs);return ok;
}
