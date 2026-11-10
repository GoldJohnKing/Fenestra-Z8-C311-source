/* SPDX-License-Identifier: GPL-3.0-only
 * Explicit synthetic copied-message transport; no camera is accessed.
 */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "fenestra_native_profile.h"
static FxNativeProfile profile;
static FxSdkClient shared;
static FxServiceExchange exchange;
static FxServiceModule api;
static FxBindingInfo entry;
static uint8_t stock[32];
static uint32_t last_sequence,requests,reads,read_attempts,declares,declare_attempts,native_calls;
static int mismatch,identity_wrong,read_busy,declare_busy,malformed_info;
static void reset(void) {
    memset(&profile,0,sizeof(profile));memset(&exchange,0,sizeof(exchange));
    shared=(FxSdkClient){.sequence=37u};last_sequence=37u;
    api=(FxServiceModule){.base={.bytes=sizeof(api)},.service_abi=FX_SERVICE_ABI,.owner=17u,.generation=9u,
        .capabilities=FX_SDK_QUERY|FX_SDK_NATIVE|FX_SDK_BINDING,.exchange=&exchange};
    entry=(FxBindingInfo){.name="nikon.test.c311",.kind=FX_BIND_FUNCTION,.abi=FX_CALL_U64_8,
        .version=1u,.flags=FX_BIND_ESCAPE,.address=UINT64_C(0x41000004)};
    for(uint32_t i=0u;i<16u;++i)entry.original[i]=(uint8_t)(i+1u);
    for(uint32_t i=0u;i<32u;++i)stock[i]=(uint8_t)(i+17u);
    requests=reads=read_attempts=declares=declare_attempts=native_calls=0u;
    mismatch=-1;identity_wrong=read_busy=declare_busy=malformed_info=0;
}
static FxResult start(void){return fx_native_profile_start(&profile,&shared,&entry,stock,UINT64_C(0x40160000),UINT64_C(0x44f00000));}
static void transport(void) {
    FxServiceRequest *q=&exchange.request;FxServiceReply r={.sequence=q->sequence,.result=FX_OK};
    assert(q->operation==FX_S_PLATFORM && q->generation==9u && q->sequence==last_sequence+1u);
    last_sequence=q->sequence;++requests;
    if(q->arg[0]==FX_BIND_INFO) {
        assert(!q->bytes && !q->arg[1] && !q->arg[2] && !q->arg[3]);
        FxPlatformInfo info={.abi=FX_PLATFORM_ABI,.bytes=sizeof(info),.owner=17u,.generation=9u};
        /* Deliberately DIFFERENT platform identity: the stock module identity
         * is in reply.value, and must be checked using that exact wire field. */
        memset(info.identity,0xcc,sizeof(info.identity));memcpy(r.data,&info,sizeof(info));r.bytes=malformed_info?0u:sizeof(info);
        memcpy(r.value,stock,sizeof(stock));if(identity_wrong)((uint8_t *)(void *)r.value)[11]^=1u;
    } else if(q->arg[0]==FX_BIND_OPEN) {
        assert(q->bytes==64u && q->arg[1]==1u && !q->arg[2] && !q->arg[3]);
        if(!strcmp((const char *)q->data,"core.machine")){r.value[0]=91u;r.value[1]=FX_BIND_DEVICE;r.value[2]=FX_CALL_DEVICE;}
        else {assert(!strcmp((const char *)q->data,entry.name) && reads==16u && declares==1u);
            r.value[0]=99u;r.value[1]=FX_BIND_FUNCTION;r.value[2]=entry.abi;}
    } else if(q->arg[0]==FX_BIND_DECLARE) {
        ++declare_attempts;assert(reads==16u && mismatch<0 && !identity_wrong);
        assert(q->bytes==sizeof(entry) && !memcmp(q->data,&entry,sizeof(entry)));
        if(declare_busy){declare_busy=0;r.result=FX_BUSY;}else ++declares;
    } else if(q->arg[0]==FX_BIND_CALL && q->arg[1]==91u) {
        ++read_attempts;assert(q->arg[2]==FX_MACHINE_READ && !q->arg[3] && q->bytes==sizeof(FxMachineRequest));
        FxMachineRequest machine;memcpy(&machine,q->data,sizeof(machine));
        assert(machine.address==entry.address+reads && machine.bytes==1u && !machine.value && !machine.reserved);
        if(read_busy){read_busy=0;r.result=FX_BUSY;}
        else {r.value[0]=entry.original[reads];if((int)reads==mismatch)r.value[0]^=1u;++reads;}
    } else {++native_calls;assert(0 && "wrapper must never CALL a native function");}
    exchange.reply=r;
}
static FxResult finish(void) {
    FxResult result=FX_BUSY;
    for(uint32_t tick=0u;tick<100u;++tick) {
        result=fx_native_profile_tick(&profile,&api);
        if(result!=FX_BUSY)break;
        assert(shared.pending);transport();
    }
    return result;
}
int main(void) {
    reset();assert(start()==FX_OK);assert(!requests && !shared.pending && !profile.handle);
    /* Waiting on an unmatched reply cannot resubmit an intended read. */
    assert(fx_native_profile_tick(&profile,&api)==FX_BUSY);uint32_t pending=shared.pending;
    assert(fx_native_profile_tick(&profile,&api)==FX_BUSY && shared.pending==pending);transport();
    assert(finish()==FX_OK && profile.stage==FX_NATIVE_PROFILE_DONE && profile.handle==99u);
    assert(profile.checked_bytes==16u && reads==16u && declares==1u && !native_calls && shared.sequence==57u);
    uint32_t before=requests;assert(fx_native_profile_tick(&profile,&api)==FX_OK && requests==before);
    /* The caller can continue using the SAME sequence client for ordinary UI. */
    assert(fx_sdk_events(&shared,&api)==FX_OK && shared.sequence==58u);shared.pending=0u;
    reset();entry.abi=FX_CALL_AAPCS64;read_busy=declare_busy=1;
    assert(start()==FX_OK && finish()==FX_OK && read_attempts==17u && declare_attempts==2u && declares==1u);
    for(int index=0;index<16;++index) {
        reset();mismatch=index;assert(start()==FX_OK && finish()==FX_INTEGRITY);
        assert(!declares && !declare_attempts && !native_calls && !profile.handle && profile.checked_bytes==(uint32_t)index);
        before=requests;assert(fx_native_profile_tick(&profile,&api)==FX_INTEGRITY && requests==before);
    }
    reset();identity_wrong=1;assert(start()==FX_OK && finish()==FX_INTEGRITY && requests==1u && !reads && !declares);
    reset();malformed_info=1;assert(start()==FX_OK && finish()==FX_INTEGRITY && requests==1u && !reads && !declares);
    reset();shared.pending=7u;assert(start()==FX_BUSY && !requests);
    reset();entry.kind=FX_BIND_TABLE;assert(start()==FX_ARGUMENT && !shared.pending);
    reset();entry.flags=FX_BIND_PROVIDER;assert(start()==FX_ARGUMENT);
    reset();entry.bytes=4u;assert(start()==FX_ARGUMENT);
    reset();memset(entry.original,0,sizeof(entry.original));assert(start()==FX_ARGUMENT);
    reset();memset(stock,0,sizeof(stock));assert(start()==FX_ARGUMENT);
    reset();entry.address=UINT64_C(0xa10001000);assert(start()==FX_ARGUMENT);
    reset();entry.address=(uint64_t)(uintptr_t)fx_native_profile_tick;
    uint64_t page=entry.address&~UINT64_C(4095);
    assert(fx_native_profile_start(&profile,&shared,&entry,stock,page,page+8192u)==FX_ARGUMENT);
    reset();assert(start()==FX_OK && finish()==FX_OK);++api.generation;
    assert(fx_native_profile_tick(&profile,&api)==FX_STALE && !profile.handle);
    reset();assert(start()==FX_OK);api.capabilities=FX_SDK_BINDING;
    assert(fx_native_profile_tick(&profile,&api)==FX_CAPABILITY && !requests);
    puts("PASS: native profile async identity/16-byte verification; all mismatch bytes reject before DECLARE, shared sequence, BUSY retries, no native CALL, stock-only scope");
}
