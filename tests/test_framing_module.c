/* SPDX-License-Identifier: GPL-3.0-only */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../examples/framing/module.c"
static FxServiceExchange exchange;
static FxServiceModule api;
static FxPlatformOwner module_owner;
static FxFramingControl control;
static uint64_t cookie;
static FxUiControl controls[5];
static FxUiEvent input;
static uint32_t have_input,revision,missing,recording,native_nraw,native_ap,writes,deny;
static FxResult read_native(void *context,FxFramingStatus *v) {
    (void)context;v->capabilities=7u;v->nraw=native_nraw;v->desqueeze=native_ap;
    v->flags=recording?FX_FRAMING_RECORDING:0u;v->open_gate=1u;v->rate=4u;return FX_OK;
}
static FxResult write_native(void *context,uint32_t setting,uint32_t value) {
    (void)context;if(recording)return FX_BUSY;if(deny)return FX_STATE;
    ++writes;if(setting==FX_FRAMING_NRAW)native_nraw=value;else native_ap=value;return FX_OK;
}
static uint32_t defer_count,deferred_seen,defer_saved,selection_calls;
static FxServiceRequest deferred_request;
static void step(void) {
    assert(fenestra_module_entry(&api.base)==0);
    FxServiceRequest *q=&exchange.request;
    FxServiceReply r={.sequence=q->sequence,.result=FX_OK};
    if(q->operation==FX_S_LIFECYCLE){assert(q->arg[0]==FX_LIFE_CONFIGURE && q->arg[1]==FX_MODULE_EXTENSION);}
    else if(q->operation==FX_S_PLATFORM) {
        if(q->arg[0]==FX_BIND_OPEN) {
            assert(!strcmp((const char *)q->data,"camera.video.framing") && q->arg[1]==1u);
            r.result=missing?FX_CAPABILITY:fx_framing_resource(&control,FX_RESOURCE_ATTACH,&module_owner,91u,&cookie,0,0);
            r.value[0]=91u;
        } else {
            assert(q->arg[0]==FX_BIND_CALL && q->arg[1]==91u);
            if(q->arg[2]==FX_FRAMING_SELECT&&defer_count){
                if(!defer_saved){deferred_request=*q;defer_saved=1;}else {assert(q->sequence!=deferred_request.sequence&&q->bytes==deferred_request.bytes&&!memcmp(q->arg,deferred_request.arg,sizeof(q->arg))&&!memcmp(q->data,deferred_request.data,q->bytes));deferred_request.sequence=q->sequence;}
                --defer_count;++deferred_seen;r.result=FX_BUSY;r.reserved=FX_SERVICE_DEFERRED;
            }else {if(q->arg[2]==FX_FRAMING_SELECT)++selection_calls;r.result=fx_framing_resource(&control,FX_RESOURCE_CALL,&module_owner,91u,&cookie,q,&r);}
        }
    } else {
        assert(q->operation==FX_S_UI);
        if(q->arg[0]==FX_UI_PUT) {
            FxUiControl c;memcpy(&c,q->data,sizeof(c));assert(c.id>=1u && c.id<=5u);
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
    defer_count=deferred_seen=defer_saved=selection_calls=0u;client=(FxSdkClient){0};stage=unavailable=published=desired=selected_control=0u;
    nraw_revision=desqueeze_revision=0u;binding=0u;current=(FxFramingStatus){0};shown=current;
    exchange=(FxServiceExchange){0};
    api=(FxServiceModule){.base={.bytes=sizeof(api)},.service_abi=FX_SERVICE_ABI,.generation=3u,.exchange=&exchange};
    fx_framing_init(&control,0,read_native,write_native);cookie=0u;revision=0u;have_input=missing=recording=native_nraw=native_ap=writes=deny=0u;
    memset(controls,0,sizeof(controls));
}
static void choose(uint32_t id,uint32_t value,uint32_t version){input=(FxUiEvent){.control=id,.event=FX_INPUT_CHANGE,.value=value,.reserved=version};have_input=1u;}
int main(void) {
    reset();ticks(40u);assert(control.owner && controls[1].option_count==4u && controls[2].option_count==8u);
    assert(controls[1].flags&FX_UI_ENABLED);assert(controls[2].flags&FX_UI_ENABLED);
    assert(!strcmp(controls[3].label,"已选择开放画幅"));assert(!(controls[3].flags&FX_UI_ENABLED));
    assert(strstr(controls[3].text,"原始画幅"));
    for(uint32_t grade=0u;grade<4u;++grade){choose(2u,grade,nraw_revision);ticks(30u);assert(native_nraw==grade && controls[1].value==grade);}
    for(uint32_t ap=0u;ap<8u;++ap){choose(3u,ap,desqueeze_revision);ticks(30u);assert(native_ap==ap && controls[2].value==ap);}
    uint32_t old_revision=nraw_revision;recording=1u;ticks(30u);
    assert(!(controls[1].flags&FX_UI_ENABLED) && !(controls[2].flags&FX_UI_ENABLED));
    choose(2u,0u,old_revision);ticks(20u);assert(native_nraw==3u);
    recording=0u;ticks(30u);choose(2u,0u,old_revision);ticks(20u);assert(native_nraw==3u);
    deny=1u;choose(3u,0u,desqueeze_revision);ticks(30u);assert(native_ap==7u);deny=0u;ticks(30u);assert(native_ap==7u);
    /* A native recording beginning after the UI event, before SET, wins. */
    choose(2u,1u,nraw_revision);
    for(uint32_t i=0u;i<30u;++i) {
        step();
        if(exchange.request.operation==FX_S_UI && exchange.request.arg[0]==FX_UI_POLL && exchange.reply.bytes==sizeof(FxUiEvent)) {
            assert(fenestra_module_entry(&api.base)==0);assert(stage==SELECT);break;
        }
    }
    assert(stage==SELECT);recording=1u;
    exchange.reply=(FxServiceReply){.sequence=client.pending,.result=fx_framing_resource(&control,FX_RESOURCE_CALL,&module_owner,91u,&cookie,&exchange.request,&exchange.reply)};
    ticks(30u);assert(native_nraw==3u && stage!=SELECT);recording=0u;ticks(30u);assert(native_nraw==3u);
    recording=0u;ticks(20u);uint32_t before_deferred=selection_calls;defer_count=3u;defer_saved=0u;
    choose(2u,1u,nraw_revision);ticks(40u);assert(native_nraw==1u&&deferred_seen==3u&&selection_calls==before_deferred+1u);
    FxServiceRequest bad={.bytes=sizeof(FxFramingSelection),.arg={0,0,FX_FRAMING_SELECT,0}};FxServiceReply out={0};
    FxFramingSelection selection={1u,sizeof(selection),2u,0u};memcpy(bad.data,&selection,sizeof(selection));
    uint32_t before=writes;assert(fx_framing_resource(&control,FX_RESOURCE_CALL,&module_owner,91u,&cookie,&bad,&out)==FX_ARGUMENT && writes==before);
    assert(fx_framing_resource(&control,FX_RESOURCE_PANIC,&module_owner,91u,&cookie,0,0)==FX_OK);
    assert(fx_framing_resource(&control,FX_RESOURCE_DETACH,&module_owner,91u,&cookie,0,0)==FX_OK);
    assert(!cookie && !control.owner && native_ap==7u && native_nraw==1u);
    reset();missing=1u;ticks(40u);assert(unavailable && !(controls[1].flags&FX_UI_ENABLED) && !(controls[2].flags&FX_UI_ENABLED));
    assert(!strcmp(controls[4].text,"功能未准备完成"));
    puts("PASS: framing provider and async module; all choices, readback, stale input, recording lock, no delayed SET, native open-gate guidance, old-core state");
}
