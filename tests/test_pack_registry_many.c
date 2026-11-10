/* SPDX-License-Identifier: GPL-3.0-only */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "fenestra_pack_registry.h"
static FxPackRegistry r;static FxPlatform base={.abi=1};static uint32_t checks,entry_calls,publish_order,abort_order,mode;
#define CHECK(v) do{++checks;assert(v);}while(0)
typedef struct{uint32_t id,stop_calls,resume_calls,poll_calls,pending,published,aborted;} State;
static State states[3];static FxNativePackProvider providers[3];static FxNativePackSymbol symbols[3];
static FxResult resource(void *ctx,uint32_t op,uint64_t owner,uint64_t token,uint64_t *cookie,const FxServiceRequest *q,FxServiceReply *a){(void)ctx;(void)op;(void)owner;(void)token;(void)cookie;(void)q;(void)a;return FX_OK;}
static FxResult event(void *ctx,uint32_t ev){State *s=ctx;
    if(ev==FX_NATIVE_PACK_PUBLISH){CHECK(!r.ready);++s->published;publish_order=publish_order*10u+s->id+1u;return FX_OK;}
    if(ev==FX_NATIVE_PACK_ABORT){++s->aborted;abort_order=abort_order*10u+s->id+1u;if(mode==4u&&s->id==1u&&s->aborted==1u)return FX_BUSY;return FX_OK;}
    if(ev==FX_NATIVE_PACK_STOP||ev==FX_NATIVE_PACK_FAULT){CHECK(r.stopping);++s->stop_calls;if(mode==3u&&s->id==0u&&s->stop_calls==1u)return FX_BUSY;return FX_OK;}
    if(ev==FX_NATIVE_PACK_RESUME){CHECK(r.stopping);++s->resume_calls;if(mode==5u&&s->id==0u){mode=0u;CHECK(fx_pack_registry_event(&r,FX_NATIVE_PACK_STOP)==FX_BUSY);CHECK(r.stopping==1u);}if(mode==3u&&s->id==1u&&s->resume_calls==1u)return FX_BUSY;return FX_OK;}
    if(ev==FX_NATIVE_PACK_GUI_POLL){++s->poll_calls;return FX_OK;}return FX_ARGUMENT;}
static uint32_t pending(void *ctx){return ((State *)ctx)->pending;}
static FxResult entry_n(const FxNativePackHost *host,FxNativePackExports *out,uint32_t n){++entry_calls;uintptr_t at=0u;
    if(n){CHECK(host->lookup(host->context,n==1u?"first.fn":"second.fn",1u,&at)==FX_OK);CHECK(at==(uintptr_t)resource);}
    *out=(FxNativePackExports){.abi=1,.bytes=sizeof(*out),.provider_count=1,.symbol_count=1,.providers=&providers[n],.symbols=&symbols[n],.context=&states[n],.event=event,.pending=pending};
    if(mode==1u&&n==1u)return FX_CAPABILITY;if(mode==2u&&n==1u)memcpy(providers[1].name,providers[0].name,64u);return FX_OK;}
static FxResult first(const FxNativePackHost *h,FxNativePackExports *e){return entry_n(h,e,0u);}static FxResult second(const FxNativePackHost *h,FxNativePackExports *e){return entry_n(h,e,1u);}static FxResult bridge(const FxNativePackHost *h,FxNativePackExports *e){return entry_n(h,e,2u);}
static int in(uintptr_t at,uint32_t n,const void *p,size_t bytes){uintptr_t b=(uintptr_t)p;return at>=b&&at-b<=bytes&&n<=bytes-(at-b);}
static int data(void *ctx,uintptr_t at,uint32_t n){(void)ctx;return in(at,n,states,sizeof(states))||in(at,n,providers,sizeof(providers))||in(at,n,symbols,sizeof(symbols));}
static int code(void *ctx,uintptr_t at){(void)ctx;return at==(uintptr_t)first||at==(uintptr_t)second||at==(uintptr_t)bridge||at==(uintptr_t)resource||at==(uintptr_t)event||at==(uintptr_t)pending;}
FxPackRegistry *fx_native_pack_registry(void){return &r;}
static void reset(uint32_t which){mode=which;entry_calls=publish_order=abort_order=0u;memset(states,0,sizeof(states));memset(providers,0,sizeof(providers));memset(symbols,0,sizeof(symbols));
    const char *names[]={"first","second","bridge"},*sn[]={"first.fn","second.fn","bridge.fn"};for(uint32_t i=0;i<3u;++i){states[i].id=i;memcpy(providers[i].name,names[i],strlen(names[i])+1u);providers[i].version=1;providers[i].kind=4;providers[i].call_abi=4;providers[i].resource=resource;providers[i].context=&states[i];memcpy(symbols[i].name,sn[i],strlen(sn[i])+1u);symbols[i].version=1;symbols[i].flags=1;symbols[i].address=(uintptr_t)resource;}
    fx_pack_registry_init(&r,&base,(FxPackRegistryIO){.data=data,.code=code});}
int main(void){FxNativePackEntry entries[]={first,second,bridge};reset(0);CHECK(fx_pack_registry_stage_many(&r,entries,3u)==FX_OK);CHECK(entry_calls==3u&&r.provider_count==3u&&r.symbol_count==3u&&!r.ready);CHECK(fx_pack_registry_platform(&r,&base)==&base);fx_pack_registry_publish(&r);CHECK(r.ready&&publish_order==123u);fx_pack_registry_publish(&r);CHECK(publish_order==123u);CHECK(fx_pack_registry_abort(&r)==FX_STATE);
    reset(1);CHECK(fx_pack_registry_stage_many(&r,entries,3u)==FX_CAPABILITY);CHECK(entry_calls==2u&&!r.ready);fx_pack_registry_publish(&r);CHECK(!r.ready&&!publish_order);CHECK(fx_pack_registry_abort(&r)==FX_OK);CHECK(abort_order==21u&&!r.staged);
    reset(2);CHECK(fx_pack_registry_stage_many(&r,entries,3u)==FX_INTEGRITY);CHECK(entry_calls==2u&&!r.ready);CHECK(fx_pack_registry_abort(&r)==FX_OK&&abort_order==21u);
    reset(4);CHECK(fx_pack_registry_stage_many(&r,entries,3u)==FX_OK);CHECK(fx_pack_registry_abort(&r)==FX_BUSY);CHECK(abort_order==321u&&r.staged);CHECK(fx_pack_registry_abort(&r)==FX_OK);CHECK(abort_order==3212u);
    reset(0);FxNativePackEntry bad[]={first,(FxNativePackEntry)(uintptr_t)0x10000u};CHECK(fx_pack_registry_stage_many(&r,bad,2u)==FX_INTEGRITY&&entry_calls==0u);CHECK(fx_pack_registry_stage_many(&r,entries,33u)==FX_STATE&&entry_calls==0u);
    reset(3);CHECK(fx_pack_registry_stage_many(&r,entries,3u)==FX_OK);fx_pack_registry_publish(&r);CHECK(fx_pack_registry_event(&r,FX_NATIVE_PACK_STOP)==FX_BUSY);CHECK(states[0].stop_calls==1u&&states[1].stop_calls==1u&&states[2].stop_calls==1u&&r.stopping);CHECK(fx_pack_registry_event(&r,FX_NATIVE_PACK_STOP)==FX_OK);CHECK(states[0].stop_calls==2u&&states[1].stop_calls==1u&&states[2].stop_calls==1u);
    states[2].pending=1;CHECK(fx_pack_registry_event(&r,FX_NATIVE_PACK_RESUME)==FX_BUSY);CHECK(!states[0].resume_calls&&!states[1].resume_calls&&!states[2].resume_calls);fx_pack_registry_poll(&r);CHECK(states[0].poll_calls==1u&&states[1].poll_calls==1u&&states[2].poll_calls==1u);states[2].pending=0;
    CHECK(fx_pack_registry_event(&r,FX_NATIVE_PACK_RESUME)==FX_BUSY&&r.stopping);CHECK(states[0].resume_calls==1u&&states[1].resume_calls==1u&&states[2].resume_calls==1u);CHECK(fx_pack_registry_event(&r,FX_NATIVE_PACK_RESUME)==FX_OK&&!r.stopping);CHECK(states[0].resume_calls==1u&&states[1].resume_calls==2u&&states[2].resume_calls==1u);CHECK(fx_pack_registry_event(&r,FX_NATIVE_PACK_RESUME)==FX_OK);CHECK(states[1].resume_calls==2u);
    reset(5);CHECK(fx_pack_registry_stage_many(&r,entries,3u)==FX_OK);fx_pack_registry_publish(&r);CHECK(fx_pack_registry_event(&r,FX_NATIVE_PACK_STOP)==FX_OK);CHECK(fx_pack_registry_event(&r,FX_NATIVE_PACK_RESUME)==FX_BUSY&&r.stopping==1u);CHECK(!r.event_lock);CHECK(fx_pack_registry_event(&r,FX_NATIVE_PACK_STOP)==FX_OK);CHECK(states[0].stop_calls==2u&&states[1].stop_calls==2u&&states[2].stop_calls==2u);CHECK(fx_pack_registry_event(&r,FX_NATIVE_PACK_RESUME)==FX_OK&&!r.stopping);
    printf("PASS: %u checks; staged dependency lookup, all-owner publish, reverse abort retry, invalid EL0 callback refusal, STOP visits all and per-owner RESUME ACK admission\n",checks);return 0;}
