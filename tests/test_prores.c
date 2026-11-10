#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "fenestra_prores.h"
static FxProResControl state;
static _Atomic uint8_t value;
static FxPlatformOwner owner,other;
static uint64_t cookie,other_cookie;
static FxServiceRequest request;
static FxServiceReply response;
static FxResult call(uint32_t op){return fx_prores_resource(&state,op,&owner,71u,&cookie,&request,&response);}
static void reset(void){atomic_store(&value,0u);fx_prores_init(&state,&value);cookie=other_cookie=0u;request=(FxServiceRequest){0};response=(FxServiceReply){0};}
static FxResult select(uint32_t grade) {
    FxProResSelection selection={FX_PRORES_ABI,sizeof(selection),grade,0u};
    request=(FxServiceRequest){.bytes=sizeof(selection),.arg={0u,0u,FX_PRORES_SELECT,0u}};
    memcpy(request.data,&selection,sizeof(selection));return call(FX_RESOURCE_CALL);
}
int main(void) {
    reset();assert(fx_prores_selected(&state)==UINT32_MAX);
    assert(call(FX_RESOURCE_ATTACH)==FX_OK && cookie==71u);
    for(uint32_t i=0u;i<4u;++i){assert(select(i)==FX_OK);assert(fx_prores_selected(&state)==i);}
    assert(select(4u)==FX_ARGUMENT && value==3u);
    request.data[0]=2u;assert(call(FX_RESOURCE_CALL)==FX_ARGUMENT && value==3u);
    assert(fx_prores_resource(&state,FX_RESOURCE_CALL,&other,71u,&cookie,&request,&response)==FX_STALE);
    assert(fx_prores_resource(&state,FX_RESOURCE_ATTACH,&other,99u,&other_cookie,0,0)==FX_BUSY);
    fx_prores_movie_open(&state,0x1234u);assert(state.active==1u);
    assert(select(1u)==FX_BUSY && value==3u);
    assert(call(FX_RESOURCE_DETACH)==FX_BUSY && state.enabled==1u && cookie==71u);
    assert(select(1u)==FX_STATE && value==3u);
    fx_prores_movie_close(&state,0x4321u);assert(state.active==1u && state.enabled==1u);
    fx_prores_movie_close(&state,0x1234u);assert(state.active==0u && state.enabled==0u);
    assert(call(FX_RESOURCE_DETACH)==FX_OK && !cookie && !state.owner && value==3u);
    assert(fx_prores_selected(&state)==UINT32_MAX);
    assert(call(FX_RESOURCE_ATTACH)==FX_OK && fx_prores_selected(&state)==3u);
    assert(call(FX_RESOURCE_PANIC)==FX_OK && !state.enabled && state.owner==(uintptr_t)&owner);
    assert(select(2u)==FX_STATE);
    assert(call(FX_RESOURCE_DETACH)==FX_OK);
    reset();fx_prores_movie_open(&state,1u);assert(call(FX_RESOURCE_ATTACH)==FX_BUSY);
    fx_prores_movie_close(&state,1u);assert(call(FX_RESOURCE_ATTACH)==FX_OK);
    assert(select(2u)==FX_OK);fx_prores_movie_open(&state,2u);
    assert(call(FX_RESOURCE_PANIC)==FX_OK && state.enabled==1u && value==2u);
    fx_prores_movie_close(&state,2u);assert(!state.enabled && call(FX_RESOURCE_DETACH)==FX_OK);
    reset();assert(call(FX_RESOURCE_ATTACH)==FX_OK);
    for(uintptr_t i=1u;i<=FX_PRORES_MOVIES;++i)fx_prores_movie_open(&state,i);
    assert(state.active==FX_PRORES_MOVIES);fx_prores_movie_open(&state,999u);
    assert(state.fault==FX_BUDGET && state.uncertain);
    for(uintptr_t i=1u;i<=FX_PRORES_MOVIES;++i)fx_prores_movie_close(&state,i);
    assert(select(1u)==FX_STATE && call(FX_RESOURCE_DETACH)==FX_BUSY && state.enabled);
    reset();assert(call(FX_RESOURCE_ATTACH)==FX_OK);fx_prores_movie_open(&state,1u);fx_prores_movie_open(&state,1u);
    assert(state.active==1u && state.fault==FX_INTEGRITY && state.uncertain);
    reset();assert(call(FX_RESOURCE_ATTACH)==FX_OK);state.gate=1u;
    fx_prores_movie_open(&state,1u);assert(state.uncertain && state.fault==FX_BUSY);state.gate=0u;
    assert(select(1u)==FX_STATE && call(FX_RESOURCE_DETACH)==FX_BUSY);
    reset();value=0xffu;assert(call(FX_RESOURCE_ATTACH)==FX_OK && value==0u);
    assert(call(FX_RESOURCE_DETACH)==FX_OK);value=2u;
    assert(fx_prores_selected(&state)==UINT32_MAX && call(FX_RESOURCE_ATTACH)==FX_OK && fx_prores_selected(&state)==2u);
    request=(FxServiceRequest){.arg={0u,0u,FX_PRORES_QUERY,0u}};
    assert(call(FX_RESOURCE_CALL)==FX_OK && response.bytes==sizeof(FxProResStatus));
    FxProResStatus status;memcpy(&status,response.data,sizeof(status));
    assert(status.abi==1u && status.grades==4u && status.selected==2u && status.flags==FX_PRORES_ENABLED);
    puts("PASS: four grades, validation, exclusive ownership, MOV lock, deferred stop/panic, capacity and contention retention, bank value restore");
}
