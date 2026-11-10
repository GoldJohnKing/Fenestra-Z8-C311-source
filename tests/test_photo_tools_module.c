#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../modules/photo_tools/module.c"
static FxServiceExchange exchange;
static FxServiceModule api;
static FxPlatformOwner module_owner;
static FxPhotoToolsControl service;
static uint64_t cookie;
static FxUiControl controls[8];
static FxUiEvent input;
static uint32_t have_input,next_revision,missing,starts,gui_waiting,queries;
static FxResult begin(FxPhotoToolsControl *s){(void)s;++starts;return FX_OK;}
static const FxPhotoToolsOps operations={begin,0,0};
static uint32_t defer_count,deferred_seen,defer_saved;
static FxServiceRequest deferred_request;
static void step(void){
    assert(fenestra_module_entry(&api.base)==0);FxServiceRequest *q=&exchange.request;FxServiceReply r={.sequence=q->sequence,.result=FX_OK};
    if(q->operation==FX_S_LIFECYCLE)assert(q->arg[0]==FX_LIFE_CONFIGURE&&q->arg[1]==FX_MODULE_EXTENSION);
    else if(q->operation==FX_S_PLATFORM){
        if(q->arg[0]==FX_BIND_OPEN){assert(!strcmp((char *)q->data,"camera.photo.tools")&&q->arg[1]==1);r.result=missing?FX_CAPABILITY:fx_photo_tools_resource(&service,FX_RESOURCE_ATTACH,&module_owner,91,&cookie,0,0);r.value[0]=91;}
        else {assert(q->arg[0]==FX_BIND_CALL&&q->arg[1]==91);if(q->arg[2]==FX_PHOTO_TOOLS_QUERY)++queries;
        if(q->arg[2]==FX_PHOTO_TOOLS_QUERY&&gui_waiting){r.result=FX_BUSY;r.reserved=FX_SERVICE_DEFERRED;}
        else if((q->arg[2]==FX_PHOTO_TOOLS_START||q->arg[2]==FX_PHOTO_TOOLS_CANCEL)&&defer_count){
            if(!defer_saved){deferred_request=*q;defer_saved=1;}else {assert(q->sequence!=deferred_request.sequence&&q->bytes==deferred_request.bytes&&!memcmp(q->arg,deferred_request.arg,sizeof(q->arg))&&!memcmp(q->data,deferred_request.data,q->bytes));deferred_request.sequence=q->sequence;}
            --defer_count;++deferred_seen;r.result=FX_BUSY;r.reserved=FX_SERVICE_DEFERRED;
        }else r.result=fx_photo_tools_resource(&service,FX_RESOURCE_CALL,&module_owner,91,&cookie,q,&r);}
    }else{
        assert(q->operation==FX_S_UI);
        if(q->arg[0]==FX_UI_PUT){FxUiControl c;memcpy(&c,q->data,sizeof(c));assert(c.id>=1&&c.id<=8);controls[c.id-1]=c;r.value[0]=++next_revision;}
        else {assert(q->arg[0]==FX_UI_POLL);r.result=have_input?FX_OK:FX_EMPTY;if(have_input){r.bytes=sizeof(input);memcpy(r.data,&input,sizeof(input));have_input=0;}}
    }
    exchange.reply=r;
}
static void ticks(uint32_t n){while(n--)step();}
static void event(uint32_t id,uint32_t kind,uint32_t value,uint32_t rev){input=(FxUiEvent){.control=id,.event=kind,.value=value,.reserved=rev};have_input=1;ticks(40);}
static void reset(void){
    defer_count=deferred_seen=defer_saved=0;client=(FxSdkClient){0};stage=0;ui_id=1;unavailable=published=armed=mode=0;binding=0;memset(revision,0,sizeof(revision));
    current=(FxPhotoToolsStatus){0};shown=current;exchange=(FxServiceExchange){0};memset(controls,0,sizeof(controls));
    api=(FxServiceModule){.base={.bytes=sizeof(api)},.service_abi=FX_SERVICE_ABI,.generation=3,.exchange=&exchange};
    fx_photo_tools_init(&service,FX_PHOTO_PRECAPTURE|FX_PHOTO_MERGE,&operations);cookie=0;next_revision=have_input=missing=starts=gui_waiting=queries=0;
}

static void progress_boundaries(void){
    const uint32_t statuses[]={0u,5u,7u,11u,16u,17u,18u,UINT32_MAX};
    const uint32_t flags[]={0u,FX_PHOTO_FAULT,FX_PHOTO_REVOKED,FX_PHOTO_RUNNING,FX_PHOTO_RUNNING|FX_PHOTO_CANCELLING};
    for(uint32_t i=0u;i<sizeof(statuses)/sizeof(statuses[0]);++i)for(uint32_t j=0u;j<sizeof(flags)/sizeof(flags[0]);++j){
        current=(FxPhotoToolsStatus){.serial=1u,.status=statuses[i],.flags=flags[j],.rows=UINT32_MAX,.total=UINT32_MAX};unavailable=0u;
        char guarded[FX_UI_TEXT+2u];memset(guarded,0x55,sizeof(guarded));progress(guarded+1u);
        assert(guarded[0]==0x55&&guarded[FX_UI_TEXT+1u]==0x55&&strlen(guarded+1u)<FX_UI_TEXT);
        assert(strstr(guarded+1u,"4294967295/4294967295"));assert(!strncmp(guarded+1u,state(),strlen(state())));
    }
    char small[8];memset(small,0x55,sizeof(small));uint32_t at=0u;append_text(small,4u,&at,"资源");assert(at==3u&&!strcmp(small,"资")&&small[4]==0x55);
    at=0u;append_text(small,3u,&at,"资源");assert(at==0u&&!small[0]);
}
int main(void){
    /* The directory takes its snapshot before its page-open callback captures
     * the GUI task. Queries cannot complete until that callback has run. */
    reset();gui_waiting=1;ticks(8);
    assert(queries>=2&&controls[0].kind==FX_UI_PAGE&&!controls[0].parent&&
        (controls[0].flags&(FX_UI_VISIBLE|FX_UI_ENABLED))==(FX_UI_VISIBLE|FX_UI_ENABLED)&&
        !strcmp(controls[0].label,"照片工具")&&!controls[4].id&&!starts);
    gui_waiting=0;ticks(40);assert(controls[3].kind==FX_UI_CHOICE&&controls[3].option_count==2u&&!strcmp(controls[3].options[0],"否")&&!strcmp(controls[3].options[1],"是"));assert(binding&&controls[2].option_count==2&&!(controls[4].flags&FX_UI_ENABLED)&&!starts);
    event(5,FX_INPUT_ACTIVATE,0,revision[5]);assert(!starts); /* no implicit confirmation */
    event(4,FX_INPUT_CHANGE,1,revision[4]);assert(armed&&(controls[4].flags&FX_UI_ENABLED));
    uint32_t stale=revision[5];event(3,FX_INPUT_CHANGE,1,revision[3]);assert(mode==1&&!armed);
    event(5,FX_INPUT_ACTIVATE,0,stale);assert(!starts); /* stale start cannot launch */
    event(4,FX_INPUT_CHANGE,1,revision[4]);defer_count=3;defer_saved=0;event(5,FX_INPUT_ACTIVATE,0,revision[5]);
    assert(deferred_seen==3);
    assert(starts==1&&service.running&&service.mode==FX_PHOTO_ALL&&!armed&&!(controls[4].flags&FX_UI_ENABLED));
    assert(controls[5].flags&FX_UI_ENABLED);defer_count=2;defer_saved=0;event(6,FX_INPUT_ACTIVATE,0,revision[6]);assert(service.cancel&&deferred_seen==5);
    fx_photo_tools_finish(&service,7,2,2,1,1,9);ticks(40);assert(strstr(controls[6].text,"已取消"));
    reset();missing=1;ticks(40);assert(unavailable&&!(controls[4].flags&FX_UI_ENABLED)&&strstr(controls[6].text,"功能未准备完成"));
    progress_boundaries();
    puts("PASS: real WLM state machine, explicit confirmation, stale-event rejection, newest/all modes, cancellation, old-core capability handling");
}
