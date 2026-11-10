/* Actual C311 PTP backend + portable FXP2 transport; native boundaries synthetic. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../src/platform/z8_c311_full/ptp.c"
static FxPtp fixture_ptp;
static uint32_t fixture_mode,fixture_active,rtos_calls,linux_calls,tick_calls,last_tick_enabled;
FxPtp *fx_z8_menu_ptp(void){return &fixture_ptp;}
int fx_z8_menu_ptp_active(void){return fixture_active!=0u;}
uint32_t fx_z8_menu_ptp_mode(void){return fixture_mode;}
int fx_z8_menu_ptp_available(void){return fixture_mode!=FX_Z8_DEBUG_OFF;}
uint32_t fx_rtos_debug(const uint8_t *in,uint32_t bytes,uint8_t *out,uint32_t *count){
    assert(bytes>=4u);++rtos_calls;fx_ptp_put32(out,fx_ptp_get32(in));*count=4u;return FX_PTP_OK;
}
uint32_t fx_linux_request(const uint8_t *in,uint32_t bytes,uint8_t *out,uint32_t *count){
    (void)in;(void)bytes;++linux_calls;out[0]=1u;*count=1u;return FX_PTP_OK;
}
void fx_linux_tick(uint64_t session,uint32_t generation,int enabled){
    (void)session;(void)generation;++tick_calls;last_tick_enabled=(uint32_t)enabled;
}
void fx_linux_revoke(void){}
const FxNativePtpDescriptor *fx_z8_ptp_original_lookup(uint32_t op){(void)op;return 0;}
void fx_z8_ptp_original_session(uint32_t session){(void)session;}
uint32_t fx_z8_ptp_original_operations(uint8_t *out,uint32_t cap,const uint8_t *in){(void)out;(void)cap;(void)in;return 0u;}
const FxNativePtpDescriptor *fx_native_ptp_lookup(uint32_t op){(void)op;return 0;}
void fx_native_ptp_session(uint32_t session){(void)session;}
uint32_t fx_native_ptp_operations(uint8_t *out,uint32_t cap,const uint8_t *in){(void)out;(void)cap;(void)in;return 0u;}
static uint32_t requests;
static uint32_t query(uint16_t operation,const uint8_t *data,uint32_t bytes,uint8_t *out,uint32_t *got){
    uint8_t hello[64],request[FX_PTP_FRAME]={0},reply[FX_PTP_FRAME],control[32];
    assert(fx_ptp_hello(&fixture_ptp,hello)==FX_PTP_OK);
    uint64_t session=fx_ptp_get64(hello+8);uint32_t id=++requests;
    memcpy(request,"FXP2",4u);request[4]=2u;request[6]=(uint8_t)operation;request[7]=(uint8_t)(operation>>8);
    fx_ptp_put64(request+8,session);fx_ptp_put32(request+16,id);fx_ptp_put32(request+20,bytes);
    if(bytes)memcpy(request+32,data,bytes);fx_ptp_put32(request+28,fx_ptp_crc(request,bytes+32u));
    assert(fx_ptp_submit(&fixture_ptp,request,bytes+32u)==FX_PTP_OK);
    fx_z8_ptp_poll();uint32_t n=0u;
    assert(fx_ptp_fetch(&fixture_ptp,session,id,0u,reply,sizeof(reply),&n)==FX_PTP_OK);
    assert(n>=32u && fx_ptp_get32(reply+28)==fx_ptp_crc(reply,n));
    *got=fx_ptp_get32(reply+20);assert(n==32u+*got);
    if(*got)memcpy(out,reply+32,*got);
    assert(fx_ptp_control(&fixture_ptp,session,id,FX_PTP_JOB_RELEASE,control)==FX_PTP_OK);
    return fx_ptp_get32(reply+24)&0x7fffffffu;
}
static void policy(void){
    assert(fx_z8_diagnostic_mode(0)==FX_Z8_DEBUG_OFF);
    FxZ8DiagnosticGate s={.cold_phase=FX_COLD_FAILED,.cold_error=FX_BUDGET};
    assert(fx_z8_diagnostic_mode(&s)==FX_Z8_DEBUG_READ_ONLY);
    s.shutdown=1u;assert(fx_z8_diagnostic_mode(&s)==FX_Z8_DEBUG_OFF);s.shutdown=0u;
    s.startup_shutdown=1u;assert(fx_z8_diagnostic_mode(&s)==FX_Z8_DEBUG_OFF);s.startup_shutdown=0u;
    s.fault_record=1u;assert(fx_z8_diagnostic_mode(&s)==FX_Z8_DEBUG_OFF);s.fault_record=0u;
    for(uint32_t phase=0u;phase<=7u;++phase){s.cold_phase=phase;assert(fx_z8_diagnostic_mode(&s)==(phase==FX_COLD_FAILED?FX_Z8_DEBUG_READ_ONLY:FX_Z8_DEBUG_OFF));}
    s.cold_phase=FX_COLD_FAILED;s.cold_error=FX_OK;assert(fx_z8_diagnostic_mode(&s)==FX_Z8_DEBUG_OFF);
    s.cold_phase=FX_COLD_READY;s.startup_phase=FX_STARTUP_IO_ERROR;assert(fx_z8_diagnostic_mode(&s)==FX_Z8_DEBUG_READ_ONLY);
    s.startup_phase=FX_STARTUP_RUNNING;assert(fx_z8_diagnostic_mode(&s)==FX_Z8_DEBUG_OFF);
    s.activation=1u;assert(fx_z8_diagnostic_mode(&s)==FX_Z8_DEBUG_FULL);
    s.fault_record=1u;assert(fx_z8_diagnostic_mode(&s)==FX_Z8_DEBUG_OFF);
    assert(fx_z8_diagnostic_result(FX_COLD_FAILED,FX_BUDGET,FX_IO,FX_STATE)==FX_BUDGET);
    assert(fx_z8_diagnostic_result(FX_COLD_CANCELLED,FX_INTERRUPTED,FX_IO,FX_STATE)==FX_INTERRUPTED);
    assert(fx_z8_diagnostic_result(FX_COLD_FAILED,FX_OK,FX_IO,FX_STATE)==FX_IO);
    assert(fx_z8_diagnostic_result(FX_COLD_READY,FX_BUDGET,FX_IO,FX_STATE)==FX_IO);
    assert(fx_z8_diagnostic_result(FX_COLD_READY,FX_OK,FX_OK,FX_STATE)==FX_STATE);
}
static void labels(void){
    static const char hex[]="0123456789ABCDEF";
    for(uint32_t b=0u;b<8u;++b)for(uint32_t e=0u;e<14u;++e){
        uint32_t n=0u;const uint16_t *p=fx_z8_diagnostic_label(e,b,&n);
        assert(n==34u && p[17]==0u && p[12]=='0' && p[13]==(uint16_t)hex[e] && p[16]==(uint16_t)('0'+b));
        assert(p==fx_z8_diagnostic_label(e,b,0));
        const uint16_t *other=fx_z8_diagnostic_label((e+1u)%14u,(b+1u)%8u,0);
        assert(p!=other && p[13]==(uint16_t)hex[e] && p[16]==(uint16_t)('0'+b));
    }
    const uint16_t *unknown=fx_z8_diagnostic_label(UINT32_MAX,6u,0);
    assert(unknown[12]=='?' && unknown[13]=='?' && unknown[16]=='?');
    assert(unknown==fx_z8_diagnostic_label(FX_IO,UINT32_MAX,0));
}
static void resume_labels(void){
    static const char hex[]="0123456789ABCDEF";
    for(uint32_t r=0u;r<=FX_Z8_RESUME_BLOCKED;++r)for(uint32_t e=0u;e<=FX_INTERRUPTED;++e){
        uint64_t record=fx_z8_resume_diagnostic_word(r,e);uint32_t n=0u;
        assert((uint32_t)(record>>32)==r && (uint32_t)record==e);
        const uint16_t *p=fx_z8_resume_diagnostic_label(record,&n);
        assert(n==30u && p[15]==0u && p[10]==(uint16_t)hex[r] && p[13]=='0' && p[14]==(uint16_t)hex[e]);
        assert(p==fx_z8_resume_diagnostic_label(record,0));
        const uint16_t *other=fx_z8_resume_diagnostic_label(fx_z8_resume_diagnostic_word((r+1u)%12u,(e+1u)%14u),0);
        assert(p!=other && p[10]==(uint16_t)hex[r] && p[14]==(uint16_t)hex[e]);
    }
    const uint16_t *unknown=fx_z8_resume_diagnostic_label(fx_z8_resume_diagnostic_word(UINT32_MAX,FX_BUSY),0);
    assert(unknown[10]=='?' && unknown[13]=='?' && unknown[14]=='?');
    assert(unknown==fx_z8_resume_diagnostic_label(fx_z8_resume_diagnostic_word(FX_Z8_RESUME_MANAGER,UINT32_MAX),0));
}
static void protocol(void){
    uint8_t out[FX_PTP_PAYLOAD],q[8]={0},hello[64];uint32_t n=0u;
    fx_z8_ptp_init(&fixture_ptp);fixture_mode=FX_Z8_DEBUG_READ_ONLY;fixture_active=0u;
    assert(fx_native_ptp_profile.active() && !fx_z8_menu_ptp_active());
    fx_z8_ptp_poll();assert(!atomic_load(&fixture_ptp.enabled));
    assert(fx_ptp_hello(&fixture_ptp,hello)==FX_PTP_CLOSED);assert(tick_calls==0u);
    /* This is the explicit local toggle, never an automatic error policy. */
    fx_ptp_enable(&fixture_ptp,1);
    assert(query(FX_PTP_STATUS,0,0u,out,&n)==FX_PTP_OK && n==32u);
    assert(fx_ptp_get32(out)==311u && fx_ptp_get32(out+4)==0u && fx_ptp_get32(out+8)==CAPS);
    assert(query(FX_PTP_IDENTITY,0,0u,out,&n)==FX_PTP_OK && n==256u && !memcmp(out,"FXI1",4u));
    assert(query(FX_PTP_ECHO,(const uint8_t *)"readonly",8u,out,&n)==FX_PTP_OK && n==8u && !memcmp(out,"readonly",8u));
    for(uint32_t op=0u;op<10u;++op){fx_ptp_put32(q,op);uint32_t prior=rtos_calls;
        uint32_t answer=query(FX_PTP_RTOS_MONITOR,q,4u,out,&n);
        int allowed=op==0u || op==1u || op==2u || op==4u;
        assert(answer==(allowed?FX_PTP_OK:FX_PTP_CLOSED));assert(rtos_calls==prior+(uint32_t)allowed);
        if(!allowed)assert(n==0u);
    }
    assert(query(FX_PTP_RTOS_MONITOR,q,3u,out,&n)==FX_PTP_CLOSED);
    assert(query(FX_PTP_LINUX_BRIDGE,q,4u,out,&n)==FX_PTP_CLOSED && linux_calls==0u);
    assert(query(FX_PTP_STATUS,q,1u,out,&n)==FX_PTP_CLOSED);
    assert(query(FX_PTP_DIAGNOSTICS,0,0u,out,&n)==FX_PTP_CLOSED);
    assert(tick_calls==0u);
    /* Normal running mode keeps all existing backend paths and real Active. */
    fixture_mode=FX_Z8_DEBUG_FULL;fixture_active=1u;
    fx_ptp_put32(q,3u);uint32_t prior=rtos_calls;
    assert(query(FX_PTP_RTOS_MONITOR,q,4u,out,&n)==FX_PTP_OK && rtos_calls==prior+1u);
    fx_ptp_put32(q,5u);assert(query(FX_PTP_RTOS_MONITOR,q,4u,out,&n)==FX_PTP_OK);
    assert(query(FX_PTP_LINUX_BRIDGE,q,4u,out,&n)==FX_PTP_OK && linux_calls==1u);
    assert(query(FX_PTP_STATUS,0,0u,out,&n)==FX_PTP_OK && fx_ptp_get32(out+4)==1u);
    assert(tick_calls && last_tick_enabled==1u);
    /* Shutdown/fault does not inherit the read-only exception. */
    fixture_mode=FX_Z8_DEBUG_OFF;fixture_active=0u;fx_z8_ptp_poll();
    assert(!atomic_load(&fixture_ptp.enabled) && last_tick_enabled==0u);
    assert(fx_ptp_hello(&fixture_ptp,hello)==FX_PTP_CLOSED);
}
int main(void){policy();labels();resume_labels();protocol();puts("PASS: actual C311 diagnostic backend/FXP2; 112 immutable labels, 168 immutable resume labels, error priority, explicit local read-only access, denied mutations, unchanged Active and shutdown");return 0;}
