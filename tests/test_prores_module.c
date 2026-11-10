#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../examples/prores/module.c"
static FxServiceExchange exchange;
static FxServiceModule api;
static FxPlatformOwner module_owner;
static FxProResControl control;
static _Atomic uint8_t grade_byte;
static uint64_t cookie;
static FxUiControl controls[3];
static FxUiEvent input;
static uint32_t have_input,revision,missing;
static uint32_t defer_count,deferred_seen,defer_saved,selection_calls;
static FxServiceRequest deferred_request;
static void step(void) {
    assert(fenestra_module_entry(&api.base)==0);
    FxServiceRequest *q=&exchange.request;
    FxServiceReply r={.sequence=q->sequence,.result=FX_OK};
    if(q->operation==FX_S_LIFECYCLE){assert(q->arg[0]==FX_LIFE_CONFIGURE && q->arg[1]==FX_MODULE_EXTENSION);}
    else if(q->operation==FX_S_PLATFORM) {
        if(q->arg[0]==FX_BIND_OPEN) {
            assert(!strcmp((const char *)q->data,"camera.video.prores") && q->arg[1]==1u);
            r.result=missing?FX_CAPABILITY:fx_prores_resource(&control,FX_RESOURCE_ATTACH,&module_owner,91u,&cookie,0,0);
            r.value[0]=91u;
        } else {
            assert(q->arg[0]==FX_BIND_CALL && q->arg[1]==91u);
            if(q->arg[2]==FX_PRORES_SELECT&&defer_count){
                if(!defer_saved){deferred_request=*q;defer_saved=1;}else {assert(q->sequence!=deferred_request.sequence&&q->bytes==deferred_request.bytes&&!memcmp(q->arg,deferred_request.arg,sizeof(q->arg))&&!memcmp(q->data,deferred_request.data,q->bytes));deferred_request.sequence=q->sequence;}
                --defer_count;++deferred_seen;r.result=FX_BUSY;r.reserved=FX_SERVICE_DEFERRED;
            }else {if(q->arg[2]==FX_PRORES_SELECT)++selection_calls;r.result=fx_prores_resource(&control,FX_RESOURCE_CALL,&module_owner,91u,&cookie,q,&r);}
        }
    } else {
        assert(q->operation==FX_S_UI);
        if(q->arg[0]==FX_UI_PUT) {
            FxUiControl c;memcpy(&c,q->data,sizeof(c));assert(c.id>=1u && c.id<=3u);
            controls[c.id-1u]=c;r.value[0]=++revision;
        } else {
            assert(q->arg[0]==FX_UI_POLL);r.result=have_input?FX_OK:FX_EMPTY;
            if(have_input){r.bytes=sizeof(input);memcpy(r.data,&input,sizeof(input));have_input=0u;}
        }
    }
    exchange.reply=r;
}
static void ticks(uint32_t n){for(uint32_t i=0u;i<n;++i)step();}
static void reset(void) {
    defer_count=deferred_seen=defer_saved=selection_calls=0u;client=(FxSdkClient){0};stage=unavailable=published=desired=choice_revision=0u;binding=0u;
    current=(FxProResStatus){0};shown=current;exchange=(FxServiceExchange){0};
    api=(FxServiceModule){.base={.bytes=sizeof(api)},.service_abi=FX_SERVICE_ABI,.generation=3u,.exchange=&exchange};
    grade_byte=0u;fx_prores_init(&control,&grade_byte);cookie=0u;revision=0u;have_input=missing=0u;
    memset(controls,0,sizeof(controls));
}
static void choose(uint32_t grade,uint32_t version){input=(FxUiEvent){.control=2u,.event=FX_INPUT_CHANGE,.value=grade,.reserved=version};have_input=1u;}
int main(void) {
    reset();ticks(30u);assert(control.enabled && controls[1].option_count==4u && controls[1].value==0u);
    assert(controls[1].flags&FX_UI_ENABLED);assert(!strcmp(controls[2].text,"准备完成"));
    choose(3u,choice_revision);ticks(20u);assert(grade_byte==3u && controls[1].value==3u);
    uint32_t old_revision=choice_revision;
    fx_prores_movie_open(&control,123u);ticks(20u);
    assert(!(controls[1].flags&FX_UI_ENABLED) && !strcmp(controls[2].text,"录制中，已锁定"));
    choose(1u,old_revision);ticks(12u);assert(grade_byte==3u);
    fx_prores_movie_close(&control,123u);ticks(20u);assert(controls[1].flags&FX_UI_ENABLED);
    choose(2u,choice_revision);
    /* Stop immediately before the SELECT RPC is serviced; recording wins. */
    for(uint32_t i=0u;i<20u && !(stage==SELECT && exchange.reply.sequence==client.pending);++i) {
        step();
        if(exchange.request.operation==FX_S_UI && exchange.request.arg[0]==FX_UI_POLL && exchange.reply.bytes==sizeof(FxUiEvent)) {
            assert(fenestra_module_entry(&api.base)==0);assert(stage==SELECT);break;
        }
    }
    assert(stage==SELECT);fx_prores_movie_open(&control,456u);
    exchange.reply=(FxServiceReply){.sequence=client.pending,.result=FX_BUSY};
    ticks(15u);assert(grade_byte==3u && stage!=SELECT);
    fx_prores_movie_close(&control,456u);ticks(20u);assert(grade_byte==3u); /* no delayed write */
    choose(2u,choice_revision);ticks(20u);assert(grade_byte==2u && controls[1].value==2u);
    choose(0u,old_revision);ticks(12u);assert(grade_byte==2u); /* stale picker event */
    uint32_t before=selection_calls;defer_count=3u;defer_saved=0u;choose(0u,choice_revision);ticks(40u);
    assert(grade_byte==0u&&deferred_seen==3u&&selection_calls==before+1u);
    reset();missing=1u;ticks(30u);
    assert(unavailable && !control.enabled && !(controls[1].flags&FX_UI_ENABLED));
    assert(!strcmp(controls[2].text,"功能未准备完成"));
    puts("PASS: actual async ProRes module, native selection ACK, recording lock, stale input rejection, no delayed SET, old-core message");
}
