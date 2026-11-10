/* SPDX-License-Identifier: GPL-3.0-only */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "fenestra_suite_video.h"
_Static_assert(sizeof(FxSuiteVideoSelection)==sizeof(FxProResSelection),"ProRes request compatibility");
_Static_assert(sizeof(FxSuiteVideoStatus)==sizeof(FxProResStatus),"ProRes reply compatibility");
static FxSuiteVideoControl state;
static _Atomic uint8_t values[3];
static FxPlatformOwner owners[3],other;
static uint64_t cookies[3],other_cookie;
static FxServiceRequest request;
static FxServiceReply response;
static FxResult call(uint32_t channel,uint32_t op) {
    return fx_suite_video_resource(&state,channel,op,&owners[channel],71u+channel,&cookies[channel],&request,&response);
}
static void reset(void) {
    for(uint32_t i=0u;i<3u;++i){values[i]=0u;cookies[i]=0u;}
    fx_suite_video_init(&state,&values[0],&values[1],&values[2]);
    other_cookie=0u;request=(FxServiceRequest){0};response=(FxServiceReply){0};
}
static FxResult select(uint32_t channel,uint32_t grade) {
    FxSuiteVideoSelection selection={FX_SUITE_VIDEO_ABI,sizeof(selection),grade,0u};
    request=(FxServiceRequest){.bytes=sizeof(selection),.arg={0u,0u,FX_SUITE_VIDEO_SELECT,0u}};
    memcpy(request.data,&selection,sizeof(selection));return call(channel,FX_RESOURCE_CALL);
}
int main(void) {
    reset();const uint32_t limits[]={4u,5u,3u};
    for(uint32_t c=0u;c<3u;++c) {
        assert(call(c,FX_RESOURCE_ATTACH)==FX_OK && cookies[c]==71u+c);
        for(uint32_t i=0u;i<limits[c];++i){assert(select(c,i)==FX_OK);assert(values[c]==i);}
        assert(select(c,limits[c])==FX_ARGUMENT && values[c]==limits[c]-1u);
        request.data[0]=2u;assert(call(c,FX_RESOURCE_CALL)==FX_ARGUMENT);
        assert(fx_suite_video_resource(&state,c,FX_RESOURCE_CALL,&other,71u+c,&cookies[c],&request,&response)==FX_STALE);
        assert(fx_suite_video_resource(&state,c,FX_RESOURCE_ATTACH,&other,99u,&other_cookie,0,0)==FX_BUSY);
        request=(FxServiceRequest){.arg={0u,0u,FX_SUITE_VIDEO_QUERY,0u}};
        assert(call(c,FX_RESOURCE_CALL)==FX_OK && response.bytes==sizeof(FxSuiteVideoStatus));
        FxSuiteVideoStatus status;memcpy(&status,response.data,sizeof(status));
        assert(status.abi==1u && status.grades==limits[c] && status.selected==limits[c]-1u && status.flags==FX_PRORES_ENABLED);
    }
    /* One observed MOV freezes every channel, including a different owner. */
    fx_suite_video_movie_open(&state,0x1234u);assert(state.active==1u);
    for(uint32_t c=0u;c<3u;++c){assert(select(c,0u)==FX_BUSY);assert(call(c,FX_RESOURCE_DETACH)==FX_BUSY);}
    fx_suite_video_movie_close(&state,0x4321u);assert(state.active==1u);
    fx_suite_video_movie_close(&state,0x1234u);assert(state.active==0u);
    for(uint32_t c=0u;c<3u;++c) {
        assert(!state.channel[c].enabled && select(c,0u)==FX_STATE);
        assert(call(c,FX_RESOURCE_DETACH)==FX_OK && !cookies[c] && !state.channel[c].owner);
        assert(values[c]==limits[c]-1u); /* closing a UI preserves native bank settings */
    }
    reset();fx_suite_video_movie_open(&state,1u);assert(call(0u,FX_RESOURCE_ATTACH)==FX_BUSY);
    fx_suite_video_movie_close(&state,1u);assert(call(0u,FX_RESOURCE_ATTACH)==FX_OK);
    assert(call(1u,FX_RESOURCE_ATTACH)==FX_OK);assert(select(0u,2u)==FX_OK);assert(select(1u,4u)==FX_OK);
    fx_suite_video_movie_open(&state,2u);assert(call(0u,FX_RESOURCE_PANIC)==FX_OK);
    assert(state.channel[0].enabled && state.channel[1].enabled);
    fx_suite_video_movie_close(&state,2u);assert(!state.channel[0].enabled && state.channel[1].enabled);
    assert(call(0u,FX_RESOURCE_DETACH)==FX_OK);assert(select(1u,1u)==FX_OK);
    reset();assert(call(0u,FX_RESOURCE_ATTACH)==FX_OK);
    for(uintptr_t i=1u;i<=FX_SUITE_VIDEO_MOVIES;++i)fx_suite_video_movie_open(&state,i);
    assert(state.active==FX_SUITE_VIDEO_MOVIES);fx_suite_video_movie_open(&state,999u);
    assert(state.fault==FX_BUDGET && state.uncertain);
    for(uintptr_t i=1u;i<=FX_SUITE_VIDEO_MOVIES;++i)fx_suite_video_movie_close(&state,i);
    assert(select(0u,1u)==FX_STATE && call(0u,FX_RESOURCE_DETACH)==FX_BUSY && state.channel[0].enabled);
    reset();assert(call(0u,FX_RESOURCE_ATTACH)==FX_OK);
    fx_suite_video_movie_open(&state,1u);fx_suite_video_movie_open(&state,1u);
    assert(state.active==1u && state.fault==FX_INTEGRITY && state.uncertain);
    reset();assert(call(0u,FX_RESOURCE_ATTACH)==FX_OK);state.gate=1u;
    fx_suite_video_movie_open(&state,1u);assert(state.uncertain && state.fault==FX_BUSY);state.gate=0u;
    assert(select(0u,1u)==FX_STATE && call(0u,FX_RESOURCE_DETACH)==FX_BUSY);
    reset();values[2]=0xffu;assert(call(2u,FX_RESOURCE_ATTACH)==FX_OK && values[2]==0xffu);
    request=(FxServiceRequest){.arg={0u,0u,FX_SUITE_VIDEO_QUERY,0u}};assert(call(2u,FX_RESOURCE_CALL)==FX_OK);
    FxSuiteVideoStatus status;memcpy(&status,response.data,sizeof(status));assert(!status.selected && values[2]==0xffu);
    assert(select(2u,2u)==FX_OK && values[2]==2u);
    reset();values[0]=0xffu;assert(call(0u,FX_RESOURCE_ATTACH)==FX_OK && values[0]==0xffu);
    request=(FxServiceRequest){.arg={0u,0u,FX_SUITE_VIDEO_QUERY,0u}};assert(call(0u,FX_RESOURCE_CALL)==FX_OK);
    memcpy(&status,response.data,sizeof(status));assert(status.selected==3u && values[0]==0xffu);
    puts("PASS: ProRes wire compatibility, all 12 grades, independent leases, shared MOV lock, deferred stop, panic isolation, saturation/contention faults and native-bank preservation");
}
