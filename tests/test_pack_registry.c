/* SPDX-License-Identifier: GPL-3.0-only
 * Actual generic registry with synthetic native pack and scheduling adapters.
 */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <malloc.h>
#include "fenestra_pack_registry.h"
static FxPackRegistry registry;
static FxNativePackProvider providers[2];
static FxNativePackSymbol symbols[2];
static struct {uint32_t published,stopped,pending,calls,panics,detaches,polls,aborts,publishes,mode,abort_busy;FxResult business;} state;
static uint32_t allocations,releases,wakes,case_id;
static FxPlatformOwner owner={.owner=11,.generation=7,.phase=FX_OWNER_RUNNING};
static uint64_t outer_cookie;
static FxResult during_detach,during_stop;
static FxNamedBinding builtin={.name="core.stock",.kind=FX_BIND_FUNCTION,.abi=FX_CALL_U64_8,.version=1};
static FxPlatform base={.abi=1,.count=1,.bindings=&builtin};
FxPackRegistry *fx_native_pack_registry(void){return &registry;}
static void native_function(void){}
static FxResult provider(void *,uint32_t,uint64_t,uint64_t,uint64_t *,const FxServiceRequest *,FxServiceReply *);
static FxResult event(void *c,uint32_t op){
    assert(c==&state);
    if(op==FX_NATIVE_PACK_PUBLISH){++state.publishes;state.published=1;return FX_OK;}
    if(op==FX_NATIVE_PACK_ABORT){++state.aborts;return state.abort_busy?FX_BUSY:FX_OK;}
    if(op==FX_NATIVE_PACK_STOP||op==FX_NATIVE_PACK_FAULT){state.stopped=1;return state.pending?FX_BUSY:FX_OK;}
    if(op==FX_NATIVE_PACK_RESUME){if(state.pending)return FX_BUSY;state.stopped=0;return FX_OK;}
    if(op==FX_NATIVE_PACK_GUI_POLL){++state.polls;return FX_OK;}
    return FX_ARGUMENT;
}
static uint32_t pending(void *c){assert(c==&state);return state.pending;}
static FxResult invoke(uint32_t op,uint64_t token,const FxServiceRequest *q,FxServiceReply *a){
    const FxPlatform *p=fx_pack_registry_platform(&registry,&base);assert(p->count==3);
    const FxNamedBinding *b=&p->bindings[1];
    return ((FxResult (*)(void *,uint32_t,const FxNamedBinding *,FxPlatformOwner *,uint64_t,uint64_t *,const FxServiceRequest *,FxServiceReply *))(uintptr_t)b->address)
        (0,op,b,&owner,token,&outer_cookie,q,a);
}
static FxResult provider(void *c,uint32_t op,uint64_t key,uint64_t token,uint64_t *cookie,const FxServiceRequest *q,FxServiceReply *a){
    assert(c==&state&&key==((UINT64_C(11)<<32)|7));
    if(op==FX_NATIVE_PACK_ATTACH){*cookie=token;return FX_OK;}
    assert(*cookie==token);
    if(op==FX_NATIVE_PACK_PANIC){++state.panics;return FX_OK;} /* Not a detach ACK. */
    if(op==FX_NATIVE_PACK_DETACH){if(state.pending)return FX_BUSY;++state.detaches;*cookie=0;return FX_OK;}
    assert(op==FX_NATIVE_PACK_CALL&&q&&a);++state.calls;
    if(state.mode==1){during_detach=invoke(FX_RESOURCE_DETACH,token,0,0);state.pending=1;during_stop=fx_pack_registry_event(&registry,FX_NATIVE_PACK_STOP);state.mode=0;}
    a->value[0]=state.calls;a->value[1]=q->data[0];a->reserved=0x77;return state.business;
}
static int in(uintptr_t p,uint32_t n,const void *b,size_t size){uintptr_t at=(uintptr_t)b;return p>=at&&p-at<=size&&n<=size-(p-at);}
static int data(void *c,uintptr_t p,uint32_t n){(void)c;return in(p,n,&state,sizeof(state))||in(p,n,providers,sizeof(providers))||in(p,n,symbols,sizeof(symbols));}
static FxResult entry(const FxNativePackHost *h,FxNativePackExports *out){
    uintptr_t address=0;assert(h->abi==1&&h->bytes==sizeof(*h));
    assert(h->lookup(h->context,"core.stock",1,&address)==FX_OK&&address==(uintptr_t)native_function);
    assert(h->lookup(h->context,"missing",1,&address)==FX_CAPABILITY&&!address);
    if(case_id==20)return FX_CAPABILITY;
    *out=(FxNativePackExports){.abi=1,.bytes=sizeof(*out),.provider_count=2,.symbol_count=2,.providers=providers,.symbols=symbols,.context=&state,.event=event,.pending=pending};
    switch(case_id){
    case 1:out->abi=2;break;case 2:out->provider_count=33;break;case 3:out->symbol_count=65;break;
    case 4:out->providers=(void *)1;break;case 5:out->event=(void *)1;break;case 6:out->context=(void *)1;break;
    case 7:providers[1]=providers[0];break;case 8:memcpy(providers[0].name,"core.stock",11);break;
    case 9:providers[0].resource=(void *)1;break;case 10:symbols[1]=symbols[0];break;
    case 11:symbols[0].flags=99;break;case 12:providers[0].call_context=2;break;
    default:break;}
    return FX_OK;
}
static int code(void *c,uintptr_t p){(void)c;return p==(uintptr_t)entry||p==(uintptr_t)event||p==(uintptr_t)pending||p==(uintptr_t)provider||p==(uintptr_t)native_function;}
static void *allocate(void *c,uint32_t n,uint32_t a){(void)c;assert(a==16);++allocations;return _aligned_malloc(n,a);}
static void release(void *c,void *p){(void)c;++releases;_aligned_free(p);}
static void wake(void *c){(void)c;++wakes;}
static void reset(uint32_t which){
    memset(&state,0,sizeof(state));state.business=FX_OK;case_id=which;outer_cookie=0;allocations=releases=wakes=0;owner.phase=FX_OWNER_RUNNING;
    memset(providers,0,sizeof(providers));memset(symbols,0,sizeof(symbols));builtin.address=(uintptr_t)native_function;
    for(uint32_t i=0;i<2;++i){memcpy(providers[i].name,i?"pack.worker":"pack.gui",i?12:9);providers[i].version=1;providers[i].kind=4;providers[i].call_abi=4;providers[i].call_context=i?0:1;providers[i].resource=provider;providers[i].context=&state;}
    memcpy(symbols[0].name,"pack.function",14);symbols[0].version=1;symbols[0].flags=1;symbols[0].address=(uintptr_t)native_function;
    memcpy(symbols[1].name,"pack.data",10);symbols[1].version=1;symbols[1].flags=2;symbols[1].address=(uintptr_t)&state;
    fx_pack_registry_init(&registry,&base,(FxPackRegistryIO){.allocate=allocate,.release=release,.wake_gui=wake,.data=data,.code=code});
}
int main(void){
    for(uint32_t i=1;i<=12;++i){reset(i);FxResult r=fx_pack_registry_stage(&registry,entry);assert(r!=FX_OK);fx_pack_registry_publish(&registry);assert(!registry.ready&&!state.publishes);
        FxResult a=fx_pack_registry_abort(&registry);assert(a==(i==6||i==5?FX_INTEGRITY:FX_OK));}
    reset(20);assert(fx_pack_registry_stage(&registry,entry)==FX_CAPABILITY);fx_pack_registry_publish(&registry);assert(!registry.ready);assert(fx_pack_registry_abort(&registry)==FX_OK);
    reset(0);assert(fx_pack_registry_stage(&registry,entry)==FX_OK);state.abort_busy=1;assert(fx_pack_registry_abort(&registry)==FX_BUSY&&registry.staged);assert(fx_pack_registry_stage(&registry,entry)==FX_STATE);state.abort_busy=0;assert(fx_pack_registry_abort(&registry)==FX_OK);
    reset(0);assert(fx_pack_registry_stage(&registry,entry)==FX_OK&&registry.staged==2);assert(fx_pack_registry_platform(&registry,&base)==&base);fx_pack_registry_publish(&registry);fx_pack_registry_publish(&registry);assert(state.publishes==1);
    const FxPlatform *p=fx_pack_registry_platform(&registry,&base);assert(p!=&base&&p->count==3&&!strcmp(p->bindings[1].name,"pack.gui"));
    assert(p->bindings[1].kind==FX_BIND_DEVICE&&p->bindings[1].abi==FX_CALL_DEVICE&&(p->bindings[1].flags&FX_BIND_PROVIDER));
    assert(invoke(FX_RESOURCE_ATTACH,101,0,0)==FX_OK&&outer_cookie);
    FxServiceRequest q={.sequence=10,.generation=7,.operation=FX_S_PLATFORM,.bytes=1,.arg={FX_BIND_CALL,101,22,0}};q.data[0]='X';
    FxServiceReply a={.sequence=10};assert(invoke(FX_RESOURCE_CALL,101,&q,&a)==FX_BUSY&&a.reserved==FX_SERVICE_DEFERRED&&wakes==1&&state.calls==0);
    q.sequence=11;a.sequence=11;assert(invoke(FX_RESOURCE_CALL,101,&q,&a)==FX_BUSY&&a.reserved==FX_SERVICE_DEFERRED&&wakes==1);
    q.data[0]='Y';fx_pack_registry_poll(&registry);assert(state.calls==1&&!fx_pack_registry_pending(&registry));
    a.sequence=12;assert(invoke(FX_RESOURCE_CALL,101,&q,&a)==FX_BUSY&&a.reserved==FX_SERVICE_DEFERRED); /* Different logical request cannot consume old result. */
    q.data[0]='X';q.sequence=12;assert(invoke(FX_RESOURCE_CALL,101,&q,&a)==FX_OK&&a.sequence==12&&a.value[0]==1&&a.value[1]=='X'&&a.reserved==0x77);
    assert(invoke(FX_RESOURCE_CALL,999,&q,&a)==FX_STALE);
    state.business=FX_BUSY;q.sequence=13;assert(invoke(FX_RESOURCE_CALL,101,&q,&a)==FX_BUSY&&a.reserved==FX_SERVICE_DEFERRED);fx_pack_registry_poll(&registry);
    q.sequence=14;assert(invoke(FX_RESOURCE_CALL,101,&q,&a)==FX_BUSY&&a.reserved==0x77);state.business=FX_OK;
    assert(invoke(FX_RESOURCE_PANIC,101,0,0)==FX_OK&&outer_cookie&&state.panics==1); /* Keep lease until independent DETACH ACK. */
    assert(invoke(FX_RESOURCE_DETACH,101,0,0)==FX_OK&&!outer_cookie&&state.detaches==1);
    assert(invoke(FX_RESOURCE_ATTACH,202,0,0)==FX_OK);state.mode=1;q.sequence=20;q.arg[1]=202;
    assert(invoke(FX_RESOURCE_CALL,202,&q,&a)==FX_BUSY);fx_pack_registry_poll(&registry);
    assert(during_detach==FX_BUSY&&during_stop==FX_BUSY&&state.pending&&fx_pack_registry_pending(&registry));
    assert(fx_pack_registry_event(&registry,FX_NATIVE_PACK_RESUME)==FX_BUSY);
    assert(invoke(FX_RESOURCE_DETACH,202,0,0)==FX_BUSY&&outer_cookie);
    state.pending=0;fx_pack_registry_poll(&registry);assert(!fx_pack_registry_pending(&registry));assert(invoke(FX_RESOURCE_DETACH,202,0,0)==FX_OK);
    assert(fx_pack_registry_event(&registry,FX_NATIVE_PACK_RESUME)==FX_OK&&!registry.stopping);
    assert(invoke(FX_RESOURCE_ATTACH,303,0,0)==FX_OK);q.sequence=30;q.arg[1]=303;uint32_t before=state.calls;
    assert(invoke(FX_RESOURCE_CALL,303,&q,&a)==FX_BUSY);owner.phase=FX_OWNER_STOPPING;fx_pack_registry_poll(&registry);assert(state.calls==before);
    assert(invoke(FX_RESOURCE_DETACH,303,0,0)==FX_OK);owner.phase=FX_OWNER_RUNNING;
    assert(fx_pack_registry_abort(&registry)==FX_STATE&&releases==0);
    puts("PASS: registry stage/abort validation, versioned bindings, copied GUI exactly-once/deferred retries, provider BUSY preservation, PANIC/DETACH separation, STOP/pending/resume, and retained lease storage");
}
