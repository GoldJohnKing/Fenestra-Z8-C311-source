/* Explicit synthetic copied service transport; no physical camera. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../examples/native_probe/module.c"
static FxServiceExchange wire;
static FxServiceModule api;
static FxUiControl rows[4];
static FxUiEvent event;
static uint32_t last_sequence,revision,event_waiting,reads,declares,posts,fetches;
static uint32_t identity_bad,byte_bad,task_present,context_bad,fetch_busy,operations_bad;
static void reset(void) {
    client=(FxSdkClient){0};profile=(FxNativeProfile){0};
    stage=ready=have_value=value=action_revision=failed=0u;tasks=ticket=0u;status="Checking stock profile";
    wire=(FxServiceExchange){0};memset(rows,0,sizeof(rows));
    api=(FxServiceModule){.base={.bytes=sizeof(api)},.service_abi=FX_SERVICE_ABI,.owner=7u,.generation=4u,
        .capabilities=FX_SDK_QUERY|FX_SDK_NATIVE|FX_SDK_MENU|FX_SDK_BINDING,.exchange=&wire};
    last_sequence=revision=event_waiting=reads=declares=posts=fetches=0u;
    identity_bad=byte_bad=context_bad=fetch_busy=operations_bad=0u;task_present=1u;
}
static void step(void) {
    assert(fenestra_module_entry(&api.base)==0);
    if(!client.pending)return;
    FxServiceRequest *q=&wire.request;
    if(q->sequence==last_sequence)return;
    assert(q->sequence==last_sequence+1u);last_sequence=q->sequence;
    FxServiceReply r={.sequence=q->sequence,.result=FX_OK};
    if(q->operation==FX_S_LIFECYCLE)assert(q->arg[0]==FX_LIFE_CONFIGURE && q->arg[1]==FX_MODULE_EXTENSION);
    else if(q->operation==FX_S_UI) {
        if(q->arg[0]==FX_UI_PUT) {
            FxUiControl c;memcpy(&c,q->data,sizeof(c));assert(c.id>=1u && c.id<=4u);
            rows[c.id-1u]=c;r.value[0]=++revision;
        } else {
            assert(q->arg[0]==FX_UI_POLL);r.result=FX_EMPTY;
            if(event_waiting){r.result=FX_OK;r.bytes=sizeof(event);memcpy(r.data,&event,sizeof(event));event_waiting=0u;}
        }
    } else {
        assert(q->operation==FX_S_PLATFORM);
        if(q->arg[0]==FX_BIND_INFO) {
            FxPlatformInfo info={.abi=1u,.bytes=sizeof(info),.owner=7u,.generation=4u};
            memcpy(r.data,&info,sizeof(info));r.bytes=sizeof(info);
            memcpy(r.value,fx_native_probe_stock_main_sha256,32u);if(identity_bad)r.value[0]^=1u;
        } else if(q->arg[0]==FX_BIND_OPEN) {
            const char *name=(const char *)q->data;assert(q->arg[1]==1u);
            if(!strcmp(name,"core.machine")){r.value[0]=30u;r.value[1]=FX_BIND_DEVICE;r.value[2]=FX_CALL_DEVICE;}
            else if(!strcmp(name,"probe.c311.get")){assert(declares==1u);r.value[0]=40u;r.value[1]=FX_BIND_FUNCTION;r.value[2]=FX_CALL_U64_8;}
            else {assert(!strcmp(name,"core.tasks"));r.value[0]=50u;r.value[1]=FX_BIND_DEVICE;r.value[2]=FX_CALL_DEVICE;}
        } else if(q->arg[0]==FX_BIND_DECLARE) {
            assert(reads==16u && !identity_bad && !byte_bad);++declares;
            assert(q->bytes==sizeof(FxBindingInfo) && !memcmp(q->data,&fx_native_probe_bindings[0],sizeof(FxBindingInfo)));
        } else if(q->arg[0]==FX_BIND_CALL && q->arg[1]==30u) {
            FxMachineRequest request;memcpy(&request,q->data,sizeof(request));
            assert(q->arg[2]==FX_MACHINE_READ && request.bytes==1u && request.address==fx_native_probe_bindings[0].address+reads);
            r.value[0]=fx_native_probe_bindings[0].original[reads];if(byte_bad && reads==8u)r.value[0]^=1u;++reads;
        } else {
            assert(q->arg[0]==FX_BIND_CALL && q->arg[1]==50u);
            if(q->arg[2]==FX_TASK_QUERY) {
                FxTaskInfo info={.abi=1u,.bytes=sizeof(info),.operations=63u,.task=task_present?123u:0u,.context="original.ui"};
                if(operations_bad)info.operations=1u;
                if(context_bad)info.context[0]='X';r.bytes=sizeof(info);memcpy(r.data,&info,sizeof(info));
            } else if(q->arg[2]==FX_TASK_POST) {
                FxTaskPost post;memcpy(&post,q->data,sizeof(post));
                static const char context[FX_TASK_CONTEXT_BYTES]="original.ui";
                assert(!memcmp(post.context,context,sizeof(context)) && post.binding==40u && post.call_bytes==64u && !post.reserved);
                uint64_t args[8];memcpy(args,post.call,sizeof(args));assert(args[0]==UINT64_C(0x05001261));
                for(uint32_t i=1u;i<8u;++i)assert(!args[i]);
                assert(task_present && !context_bad && !identity_bad && !byte_bad);
                ++posts;r.value[0]=11u;
            } else {
                assert(q->arg[2]==FX_TASK_FETCH && q->arg[3]==11u);++fetches;
                if(fetch_busy){--fetch_busy;r.result=FX_BUSY;}
                else {r.value[0]=11u;r.value[1]=FX_OK;r.value[2]=2u;}
            }
        }
    }
    wire.reply=r;
}
static void ticks(uint32_t n){for(uint32_t i=0u;i<n;++i)step();}
static void press(uint32_t stamp){event=(FxUiEvent){.control=4u,.event=FX_INPUT_ACTIVATE,.reserved=stamp};event_waiting=1u;}
int main(void) {
    reset();ticks(70u);assert(stage==POLL && ready && !failed && declares==1u && !posts && !have_value);
    assert(!strcmp(rows[1].text,"Verified; read only") && (rows[3].flags&FX_UI_ENABLED));
    press(action_revision+1u);ticks(10u);assert(!posts); /* stale UI publication */
    fetch_busy=3u;press(action_revision);ticks(40u);
    assert(posts==1u && fetches==4u && have_value && value==2u && !strcmp(rows[2].text,"2"));
    ticks(20u);assert(posts==1u); /* completed read is never automatically repeated */
    reset();task_present=0u;ticks(70u);assert(!ready && !failed && !posts);
    press(action_revision);ticks(15u);assert(!posts && !ready); /* Refresh is QUERY only */
    task_present=1u;press(action_revision);ticks(20u);assert(ready && !posts);
    press(action_revision);ticks(25u);assert(posts==1u && have_value);
    reset();identity_bad=1u;ticks(40u);assert(failed && !declares && !reads && !posts && !(rows[3].flags&FX_UI_ENABLED));
    press(action_revision);ticks(10u);assert(!posts);
    reset();byte_bad=1u;ticks(60u);assert(failed && reads==9u && !declares && !posts);
    reset();context_bad=1u;ticks(70u);assert(failed && !ready && !posts);
    reset();operations_bad=1u;ticks(70u);assert(failed && !ready && !posts);
    puts("PASS: real native probe module async profile/GUI task/read-only POST, FETCH busy without duplicate POST, idle Refresh, stale input and bad profile/context rejection");
}
