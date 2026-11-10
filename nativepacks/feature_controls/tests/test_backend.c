/* Synthetic native objects only. No native firmware address is dereferenced. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <malloc.h>
#include <string.h>
#include "internal.h"
#include "precapture_subscription_preimages.h"
_Alignas(16) static uint8_t dcf_bank[48u*0xf98u+4u];
static uint32_t dcf_cleans;
void fx_controls_test_dcf_clean(uintptr_t a,uintptr_t b){assert(a==(uintptr_t)(dcf_bank+7u*0xf98u+0x18u)&&b==(uintptr_t)(dcf_bank+7u*0xf98u+0xdcu));++dcf_cleans;}
static void dcf_stock(void){
 static const uint32_t ids[]={0x601u,0x2000688u,0x6000689u,0x200172au,0x2000600u};
 uint8_t *s=dcf_bank+7u*0xf98u;memset(dcf_bank,0,sizeof(dcf_bank));
 *(uintptr_t *)(s+8)=(uintptr_t)0x408703b4u;*(uint32_t *)(s+0x14)=0x04320000u;*(uint32_t *)(s+0x18)=5;
 for(uint32_t i=0;i<5;++i){uint32_t v=ids[i];s[0x1cu+((v>>8)&255u)*32u+((v>>3)&31u)]|=(uint8_t)(1u<<(v&7u));}
}

_Alignas(16) static uint8_t banks[32],runtime[12288],registry[16*0x301];
static FxNativePackExports exports;
static uint32_t gets,sets,republishes,creates,starts,holds,timer=17,delay=2,allocations,releases,stop_during_set;
static FxResult reentrant_stop;
static uint64_t now=100;
static uint32_t copied_parameters[7];
FxControlsProfile fx_controls_test_profile;
void fx_controls_video_open_hook(void){}
void fx_controls_video_close_hook(void){}
static uint32_t get(uint32_t property){++gets;if(property==0x0200171eu)return delay;if(property==0x0500125bu)return 30;return 1;}
static uint32_t set(uint32_t property,uint32_t value){
    ++sets;if(property==0x0200171eu)delay=value;
    else if(property==0x05001261u){*(uint32_t *)(banks+8)=value;if(stop_during_set){stop_during_set=0;reentrant_stop=exports.event(exports.context,FX_NATIVE_PACK_STOP);}}
    return 1;
}
static void republish(void){++republishes;}
static void worker(void *p){(void)p;}
static void *native_allocate(uint32_t bytes,uint32_t flags){assert(bytes==64&&!flags);return calloc(1,bytes);}
static void native_release(void *p){free(p);}
static void task_create(void *task,void (*entry)(void *),uint32_t *p){
    ++creates;memcpy(copied_parameters,p,sizeof(copied_parameters));assert(entry==worker);
    *(uint32_t *)task=9;*(uintptr_t *)((uint8_t *)task+8)=(uintptr_t)entry;
    *(uint32_t *)(registry+9*16)=9;*(uintptr_t *)(registry+9*16+8)=(uintptr_t)task;
}
static void task_start(void *task,void *argument){assert(*(uint32_t *)task==9&&!argument);++starts;}
static uint32_t timer_kind(void){return timer;}
static void timer_hold(uint32_t n){assert(n==UINT32_MAX);++holds;}
static void timer_set(uint32_t n){timer=n;}
static uint64_t ticks(void){return now;}
static uint64_t rate(void){return 1000;}
static void *allocate(void *c,uint32_t bytes,uint32_t alignment){(void)c;assert(alignment==16&&bytes<4096);++allocations;return _aligned_malloc(bytes,alignment);}
static void release(void *c,void *p){(void)c;++releases;_aligned_free(p);}
static FxNativePackProvider *find(const char *name){
    for(uint32_t i=0;i<exports.provider_count;++i)if(!memcmp(exports.providers[i].name,name,strlen(name)+1))return (FxNativePackProvider *)&exports.providers[i];
    assert(0);return 0;
}
static FxResult op(FxNativePackProvider *p,uint32_t operation,uint64_t owner,uint64_t token,uint64_t *cookie,uint32_t command,const void *data,uint32_t bytes,FxServiceReply *reply){
    FxServiceRequest q={.bytes=bytes,.arg={0,0,command,0}};if(bytes)memcpy(q.data,data,bytes);
    return p->resource(p->context,operation,owner,token,cookie,operation==FX_NATIVE_PACK_CALL?&q:0,reply);
}
static void setup(void){
    dcf_stock();
    fx_controls_test_profile=(FxControlsProfile){.prores=(_Atomic uint8_t *)banks,.h265=(_Atomic uint8_t *)(banks+1),.log=(_Atomic uint8_t *)(banks+2),
        .nraw=(_Atomic uint8_t *)(banks+8),.desqueeze=(_Atomic uint8_t *)(banks+12),.open_gate=(_Atomic uint8_t *)(banks+13),
        .psm_runtime=runtime,.task_registry=registry,.dcf_constructor=fx_dcf_constructor_original,.dcf_registration=fx_dcf_registration_original,.dcf_bank=dcf_bank,.allocate=(uintptr_t)native_allocate,.release=(uintptr_t)native_release,
        .task_create=(uintptr_t)task_create,.task_start=(uintptr_t)task_start,.get=(uintptr_t)get,.exact_get=(uintptr_t)get,.set=(uintptr_t)set,
        .timer_kind=(uintptr_t)timer_kind,.timer_hold=(uintptr_t)timer_hold,.timer_set=(uintptr_t)timer_set,
        .psm_worker=(uintptr_t)worker,.tier_republish=(uintptr_t)republish,.ticks=ticks,.tick_rate=rate};
}
int main(int argc,char **argv){
    (void)argv;setup();FxNativePackHost host={.abi=1,.bytes=sizeof(host),.allocate=allocate,.release=release};
    FxNativePackHost bad=host;bad.abi=99;assert(fx_controls_pack_entry(&bad,&exports)==FX_ARGUMENT&&allocations==0);
    assert(fx_controls_pack_entry(&host,&exports)==FX_OK);assert(allocations==1&&gets==0&&sets==0&&creates==0);
    assert(exports.provider_count==5&&exports.symbol_count==8);
    assert(*(uint32_t *)(dcf_bank+7u*0xf98u+0x18u)==5&&dcf_cleans==0);
    for(uint32_t i=0;i<5;++i)assert(exports.providers[i].call_context==FX_NATIVE_PACK_ORIGINAL_UI);
    fx_controls_movie_open(123);assert(exports.pending(exports.context)==0);
    FxNativePackProvider *pr=find("camera.video.prores");uint64_t cookie=0;FxServiceReply a={0};
    assert(op(pr,FX_NATIVE_PACK_ATTACH,7,101,&cookie,0,0,0,&a)==FX_STATE);
    assert(exports.event(exports.context,FX_NATIVE_PACK_ABORT)==FX_OK&&releases==1);
    assert(*(uint32_t *)(dcf_bank+7u*0xf98u+0x18u)==5&&dcf_cleans==0);
    assert(fx_controls_pack_entry(&host,&exports)==FX_OK&&gets==0&&sets==0&&creates==0);
    assert(exports.event(exports.context,FX_NATIVE_PACK_PUBLISH)==FX_OK);
    assert(*(uint32_t *)(dcf_bank+7u*0xf98u+0x18u)==9&&dcf_bank[7u*0xf98u+0xdcu]==0x73&&dcf_bank[7u*0xf98u+0xddu]==1&&dcf_cleans==1);
    assert(exports.event(exports.context,FX_NATIVE_PACK_PUBLISH)==FX_OK&&dcf_cleans==1);
    assert(fx_controls_pack_entry(&host,&exports)==FX_STATE);
    uint64_t cookies[5]={0};
    for(uint32_t i=0;i<5;++i){FxNativePackProvider *p=(FxNativePackProvider *)&exports.providers[i];assert(op(p,FX_NATIVE_PACK_ATTACH,7,101+i,&cookies[i],0,0,0,&a)==FX_OK);}
    assert(gets==0); /* Including framing ATTACH: no native GUI getter. */
    pr=find("camera.video.prores");FxNativePackProvider *h=find("camera.video.h265"),*log=find("camera.video.log_colour"),*fr=find("camera.video.framing"),*photo=find("camera.photo.tools");
    assert(op(fr,FX_NATIVE_PACK_CALL,7,104,&cookies[3],FX_FRAMING_QUERY,0,0,&a)==FX_OK&&gets==1);
    FxFramingStatus status;memcpy(&status,a.data,sizeof(status));assert(status.rate==30&&status.nraw==FX_FRAMING_NORMAL);
    FxSuiteVideoSelection selected={1,sizeof(selected),3,0};
    assert(op(pr,FX_NATIVE_PACK_CALL,8,101,&cookies[0],1,&selected,sizeof(selected),&a)==FX_STALE);
    assert(op(pr,FX_NATIVE_PACK_CALL,7,101,&cookies[0],1,&selected,sizeof(selected),&a)==FX_OK&&banks[0]==3);
    selected.selected=4;assert(op(h,FX_NATIVE_PACK_CALL,7,102,&cookies[1],1,&selected,sizeof(selected),&a)==FX_OK&&banks[1]==4);
    selected.selected=2;assert(op(log,FX_NATIVE_PACK_CALL,7,103,&cookies[2],1,&selected,sizeof(selected),&a)==FX_OK&&banks[2]==2&&republishes==3);
    fx_controls_movie_open(0x1234);
    if(argc>1){
        fx_controls_movie_open(0x1234);assert(exports.pending(exports.context));
        assert(exports.event(exports.context,FX_NATIVE_PACK_STOP)==FX_BUSY);
        fx_controls_movie_close(0x1234);assert(exports.pending(exports.context));
        assert(exports.event(exports.context,FX_NATIVE_PACK_RESUME)==FX_BUSY&&releases==1);
        puts("PASS: ambiguous native MOV lifetime retains image/state and blocks resume");return 0;
    }
    assert(op(pr,FX_NATIVE_PACK_CALL,7,101,&cookies[0],1,&selected,sizeof(selected),&a)==FX_BUSY);
    FxPhotoToolsStart merge={1,sizeof(merge),FX_PHOTO_NEWEST,FX_PHOTO_TOOLS_CONFIRM};
    assert(op(photo,FX_NATIVE_PACK_CALL,7,105,&cookies[4],FX_PHOTO_TOOLS_START,&merge,sizeof(merge),&a)==FX_BUSY);
    assert(exports.event(exports.context,FX_NATIVE_PACK_STOP)==FX_BUSY);
    fx_controls_movie_close(0x1234);assert(exports.event(exports.context,FX_NATIVE_PACK_STOP)==FX_OK);
    assert(op(pr,FX_NATIVE_PACK_CALL,7,101,&cookies[0],1,&selected,sizeof(selected),&a)==FX_STATE);
    assert(exports.event(exports.context,FX_NATIVE_PACK_RESUME)==FX_BUSY); /* Old owner leases still present. */
    for(uint32_t i=0;i<5;++i){FxNativePackProvider *p=(FxNativePackProvider *)&exports.providers[i];assert(op(p,FX_NATIVE_PACK_DETACH,7,101+i,&cookies[i],0,0,0,&a)==FX_OK&&cookies[i]==0);}
    assert(exports.event(exports.context,FX_NATIVE_PACK_RESUME)==FX_OK);
    for(uint32_t i=0;i<5;++i){FxNativePackProvider *p=(FxNativePackProvider *)&exports.providers[i];assert(op(p,FX_NATIVE_PACK_ATTACH,8,201+i,&cookies[i],0,0,0,&a)==FX_OK);}
    FxFramingSelection fs={1,sizeof(fs),FX_FRAMING_NRAW,FX_FRAMING_FINE};stop_during_set=1;
    assert(op(fr,FX_NATIVE_PACK_CALL,8,204,&cookies[3],FX_FRAMING_SELECT,&fs,sizeof(fs),&a)==FX_OK);
    assert(reentrant_stop==FX_BUSY&&exports.event(exports.context,FX_NATIVE_PACK_STOP)==FX_OK);
    for(uint32_t i=0;i<5;++i){FxNativePackProvider *p=(FxNativePackProvider *)&exports.providers[i];assert(op(p,FX_NATIVE_PACK_DETACH,8,201+i,&cookies[i],0,0,0,&a)==FX_OK);}
    assert(exports.event(exports.context,FX_NATIVE_PACK_RESUME)==FX_OK);
    assert(op(photo,FX_NATIVE_PACK_ATTACH,9,305,&cookies[4],0,0,0,&a)==FX_OK);
    assert(op(photo,FX_NATIVE_PACK_CALL,9,305,&cookies[4],FX_PHOTO_TOOLS_START,&merge,sizeof(merge),&a)==FX_OK);
    assert(creates==0&&*(uint32_t *)(runtime+4)==0&&exports.pending(exports.context));
    assert(exports.event(exports.context,FX_NATIVE_PACK_GUI_POLL)==FX_OK);
    assert(creates==1&&starts==1&&holds==1&&delay==8&&*(uint32_t *)(runtime+4)==1);
    assert(copied_parameters[0]==2&&copied_parameters[1]==40&&copied_parameters[2]==32768);
    assert(!memcmp((uint8_t *)copied_parameters+12,"FxPSMerge",10));
    *(uint32_t *)(runtime+20)=*(uint32_t *)(runtime+16); /* Synthetic worker claimed serial. */
    assert(exports.event(exports.context,FX_NATIVE_PACK_STOP)==FX_BUSY&&*(uint32_t *)(runtime+8)==1);
    assert(op(photo,FX_NATIVE_PACK_DETACH,9,305,&cookies[4],0,0,0,&a)==FX_BUSY);
    *(uint32_t *)(runtime+12)=7;*(uint32_t *)(runtime+4)=2;
    assert(exports.event(exports.context,FX_NATIVE_PACK_GUI_POLL)==FX_OK&&delay==2&&timer==17);
    assert(exports.event(exports.context,FX_NATIVE_PACK_STOP)==FX_OK);
    assert(op(photo,FX_NATIVE_PACK_DETACH,9,305,&cookies[4],0,0,0,&a)==FX_OK);
    assert(exports.event(exports.context,FX_NATIVE_PACK_RESUME)==FX_OK);
    assert(op(photo,FX_NATIVE_PACK_ATTACH,10,405,&cookies[4],0,0,0,&a)==FX_OK);
    assert(op(photo,FX_NATIVE_PACK_CALL,10,405,&cookies[4],FX_PHOTO_TOOLS_START,&merge,sizeof(merge),&a)==FX_OK);
    assert(exports.event(exports.context,FX_NATIVE_PACK_GUI_POLL)==FX_OK&&creates==1&&starts==1);
    assert(*(uint32_t *)(runtime+16)==2);now+=5001;
    assert(exports.event(exports.context,FX_NATIVE_PACK_GUI_POLL)==FX_OK&&*(uint32_t *)(runtime+20)==2);
    assert(!exports.pending(exports.context)&&*(uint32_t *)(runtime+12)==17&&delay==2);
    assert(exports.event(exports.context,FX_NATIVE_PACK_ABORT)==FX_BUSY&&releases==1);
    puts("PASS: five provider wire protocols, GUI-only native control, owner/token fencing, stop reentrancy, warm resume, permanent worker reuse, direct cancel, and late-claim revocation");
}
