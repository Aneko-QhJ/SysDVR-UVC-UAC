/* Exact report ABI, injected service outcomes. Each accepted control post gets
 * a fresh ID; the prior lightweight fixtures used constant IDs and empty reports.
 * ISO reports are absent until a test explicitly injects one. */
static u32 next_urb=100,last_ctrl_id[4][2],last_iso_id;
static u32 iso_report_count,iso_report_status=3,iso_report_id,iso_report_rc;
static u32 ctrl_report_status=3,ctrl_report_count=1,ctrl_report_id_offset;
static u32 late_ctrl_id;
static unsigned iso_report_calls,ctrl_report_calls,out_posts;

static Result usbDsEndpoint_PostBufferAsync(UsbDsEndpoint *e,void *b,size_t n,u32 *id) {
    (void)e;(void)b;assert(n==3072);posts++;*id=next_urb++;last_iso_id=*id;return post_rc;
}
static Result usbDsEndpoint_GetReportData(UsbDsEndpoint *e,UsbDsReportData *r) {
    (void)e;iso_report_calls++;if(iso_report_rc)return iso_report_rc;
    memset(r,0,sizeof(*r));r->report_count=iso_report_count;
    for(u32 i=0;i<iso_report_count && i<8;i++)
        r->report[i]=(UsbDsReportEntry){iso_report_id ? iso_report_id : last_iso_id,3072,3072,iso_report_status};
    return 0;
}
static Result usbDsEndpoint_Cancel(UsbDsEndpoint *e) { (void)e;return 0; }
static Result usbDsInterface_CtrlInPostBufferAsync(UsbDsInterface *i,void *b,size_t n,u32 *id) {
    (void)b;in_posts++;*id=next_urb++;last_ctrl_id[i->interface_index][0]=*id;
    if(n==168)status_writes++;
    if(n==0 && ack_post_rc)return ack_post_rc;
    i->CtrlInCompletionEvent.signaled=true;return 0;
}
static Result usbDsInterface_CtrlOutPostBufferAsync(UsbDsInterface *i,void *b,size_t n,u32 *id) {
    (void)b;(void)n;out_posts++;*id=next_urb++;last_ctrl_id[i->interface_index][1]=*id;
    i->CtrlOutCompletionEvent.signaled=true;return 0;
}
static Result candidate_ctrl_report(UsbDsInterface *i,UsbDsReportData *r,unsigned direction) {
    ctrl_report_calls++;
    if(!direction && ack_report_rc)return ack_report_rc;
    memset(r,0,sizeof(*r));r->report_count=ctrl_report_count;
    if(!direction && late_ctrl_id) {
        r->report_count=2;r->report[0]=(UsbDsReportEntry){late_ctrl_id,0,0,3};
        r->report[1]=(UsbDsReportEntry){last_ctrl_id[i->interface_index][0],0,0,3};
        late_ctrl_id=0;return 0;
    }
    for(u32 j=0;j<ctrl_report_count && j<8;j++)
        r->report[j]=(UsbDsReportEntry){last_ctrl_id[i->interface_index][direction]+ctrl_report_id_offset,
                                      0,0,ack_parse_rc ? 4 : ctrl_report_status};
    return 0;
}
static Result usbDsInterface_GetCtrlInReportData(UsbDsInterface *i,UsbDsReportData *r) {
    return candidate_ctrl_report(i,r,0);
}
static Result usbDsInterface_GetCtrlOutReportData(UsbDsInterface *i,UsbDsReportData *r) {
    return candidate_ctrl_report(i,r,1);
}
static Result usbDsParseReportData(UsbDsReportData *r,u32 id,u32 *requested,u32 *actual) {
    if(ack_parse_rc)return ack_parse_rc;
    for(u32 j=0;j<r->report_count && j<8;j++)if(r->report[j].id==id) {
        u32 s=r->report[j].urb_status;
        if(s!=3)return s==4 ? 0x828c : s==5 ? 0x748c : 0x108c;
        if(requested)*requested=r->report[j].requestedSize;
        if(actual)*actual=r->report[j].transferredSize;
        return 0;
    }
    return 0x1359;
}
