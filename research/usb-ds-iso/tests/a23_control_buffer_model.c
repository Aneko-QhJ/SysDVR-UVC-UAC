/* Native-only ownership hypothesis; no DMA/thread/HOS execution. Snapshot
 * accepted spans until an existing matching raw terminal report is observed.
 * A zero-length post holds an address identity but covers ZERO data bytes. */
typedef struct { void *buffer;size_t length;u32 id;unsigned iface,direction;bool active;u8 bytes[4096]; } ModelSpan;
static ModelSpan model_spans[64];static unsigned model_used;
static unsigned model_copy_overlaps,model_copy_bytes,model_changed_bytes,model_pointer_reposts;
static unsigned model_out_wait_rc,model_out_report_rc;
static void model_before_copy(void *buffer,size_t n) {
    for(unsigned i=0;i<model_used;i++) {
        ModelSpan *s=&model_spans[i];
        if(!s->active || s->buffer!=buffer || !s->length || !n)continue;
        model_copy_overlaps++;model_copy_bytes+=(unsigned)(n<s->length ? n:s->length);
    }
}
static void model_after_copy(void *buffer,size_t n) {
    for(unsigned i=0;i<model_used;i++) {
        ModelSpan *s=&model_spans[i];
        if(!s->active || s->buffer!=buffer)continue;
        size_t limit=n<s->length ? n:s->length;
        for(size_t j=0;j<limit;j++)if(((u8 *)buffer)[j]!=s->bytes[j])model_changed_bytes++;
    }
}
static void model_post(unsigned iface,unsigned direction,void *buffer,size_t n,u32 id) {
    assert(n<=4096 && model_used<64);
    for(unsigned i=0;i<model_used;i++)if(model_spans[i].active && model_spans[i].buffer==buffer)model_pointer_reposts++;
    ModelSpan *s=&model_spans[model_used++];
    *s=(ModelSpan){.buffer=buffer,.length=n,.id=id,.iface=iface,.direction=direction,.active=true};
    memcpy(s->bytes,buffer,n);
}
static void model_report(unsigned iface,unsigned direction,const UsbDsReportData *r) {
    if(r->report_count>8)return;
    for(u32 i=0;i<r->report_count;i++)for(u32 j=0;j<i;j++)if(r->report[i].id==r->report[j].id)return;
    for(u32 i=0;i<r->report_count;i++) {
        u32 status=r->report[i].urb_status;if(status!=3 && status!=4 && status!=5)continue;
        for(unsigned j=0;j<model_used;j++) {
            ModelSpan *s=&model_spans[j];
            if(s->iface==iface && s->direction==direction && s->id==r->report[i].id)s->active=false;
        }
    }
}
