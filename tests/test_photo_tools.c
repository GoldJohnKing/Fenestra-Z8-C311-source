#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define FX_Z8_FEATURE_SUITE 1
#define FX_PHOTO_TOOLS_SYNTHETIC 1
#include "../src/platform/z8_c311_full/photo_tools.c"
static _Alignas(8) uint8_t memory[R_RESERVED],registry[16u*0x301u];
uint8_t *fx_photo_test_runtime=memory,*fx_photo_test_registry=registry;
static FxPhotoToolsControl state;
static FxPlatformOwner owner,other;
static uint64_t cookie;
static FxServiceRequest q;
static FxServiceReply a;
static uint32_t delay=3,held,restored,started,created;
static uint64_t clock_ticks;
FxPhotoToolsControl *fx_z8_photo_tools_control(void){return &state;}
void *fx_photo_test_allocate(uint32_t bytes,uint32_t zero){(void)zero;return calloc(1,bytes);}
void fx_photo_test_free(void *p){free(p);}
void fx_photo_test_task_create(void *p,void (*entry)(void *),uint32_t *parameters){
    assert(parameters[0]==2&&parameters[1]==40&&parameters[2]==32768);++created;
    *(int *)p=1;*(uintptr_t *)((uint8_t *)p+8)=(uintptr_t)entry;
    *(uint32_t *)(registry+16)=1;*(uintptr_t *)(registry+24)=(uintptr_t)p;
}
void fx_photo_test_task_start(void *p,void *arg){assert(p&&!arg);++started;}
uint32_t fx_photo_test_get(uint32_t id){return id==MENU_DELAY?delay:id==0x2126u?6u:id==0x06000604u?1u:3u;}
void fx_photo_test_set(uint32_t id,uint32_t value){assert(id==MENU_DELAY);delay=value;}
uint32_t fx_photo_test_timer_kind(void){return 7;}
void fx_photo_test_timer_hold(uint32_t value){assert(value==UINT32_MAX);++held;}
void fx_photo_test_timer_set(uint32_t value){assert(value==7);++restored;}
uint64_t fx_photo_test_ticks(void){return clock_ticks;}
uint64_t fx_photo_test_rate(void){return 1000;}
static FxResult call(uint32_t op){return fx_photo_tools_resource(&state,op,&owner,71,&cookie,&q,&a);}
static FxResult begin(uint32_t mode){
    FxPhotoToolsStart v={FX_PHOTO_TOOLS_ABI,sizeof(v),mode,FX_PHOTO_TOOLS_CONFIRM};
    q=(FxServiceRequest){.bytes=sizeof(v),.arg={0,0,FX_PHOTO_TOOLS_START,0}};memcpy(q.data,&v,sizeof(v));return call(FX_RESOURCE_CALL);
}
static void query(void){q=(FxServiceRequest){.arg={0,0,FX_PHOTO_TOOLS_QUERY,0}};assert(call(FX_RESOURCE_CALL)==FX_OK);}
int main(void){
    fx_z8_photo_tools_init(&state);assert(state.supported==(FX_PHOTO_PRECAPTURE|FX_PHOTO_MERGE));
    assert(call(FX_RESOURCE_ATTACH)==FX_OK);uint64_t foreign=0;
    assert(fx_photo_tools_resource(&state,FX_RESOURCE_ATTACH,&other,8,&foreign,0,0)==FX_BUSY);
    assert(begin(2)==FX_ARGUMENT&&!state.running);assert(begin(FX_PHOTO_NEWEST)==FX_OK);
    assert(state.running&&fx_z8_photo_tools_pending(&state)&&!started&&rd(R_STATE)==0); /* no I/O before GUI */
    assert(begin(FX_PHOTO_ALL)==FX_BUSY);fx_z8_photo_tools_poll(&state);
    assert(created==1&&started==1&&rd(R_STATE)==1&&rd(R_SERIAL)==1&&rd(R_CLAIMED)==0&&delay==8&&held==1);
    assert(alive()&&rd(R_JOB_MODE)==FX_PHOTO_NEWEST);
    uint32_t old=rd(R_CLAIMED);assert(__atomic_compare_exchange_n((uint32_t *)(memory+R_CLAIMED),&old,1,0,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE));
    old=rd(R_CLAIMED);assert(old==rd(R_SERIAL)); /* native worker sees already claimed, never duplicates */
    wr(R_ROWS,20);wr(R_TOTAL,100);wr(R_PHASE,3);fx_z8_photo_tools_poll(&state);query();
    FxPhotoToolsStatus status;memcpy(&status,a.data,sizeof(status));assert(status.rows==20&&status.total==100&&status.release_mode==6&&status.raw_recording==3);
    q=(FxServiceRequest){.arg={0,0,FX_PHOTO_TOOLS_CANCEL,0}};assert(call(FX_RESOURCE_CALL)==FX_OK);fx_z8_photo_tools_poll(&state);assert(rd(R_CANCEL)==1);
    wr(R_CANCEL,0u);assert(fx_z8_photo_tools_stop(&state)==FX_BUSY&&rd(R_CANCEL)==1); /* no GUI poll needed */
    assert(call(FX_RESOURCE_DETACH)==FX_BUSY&&cookie==71&&state.owner==(uintptr_t)&owner);
    wr(R_STATUS,7);wr(R_GROUP_COUNT,2);wr(R_TARGETS,1);wr(R_MERGED,0);wr(R_STATE,2);fx_z8_photo_tools_poll(&state);
    assert(!state.running&&state.status==7&&delay==3&&restored==1&&state.serial==1);
    assert(call(FX_RESOURCE_DETACH)==FX_OK&&!cookie);assert(call(FX_RESOURCE_ATTACH)==FX_OK);
    assert(begin(FX_PHOTO_ALL)==FX_OK);wr(R_STATE,1);wr(R_SERIAL,11); /* stock UI wins before queued GUI delivery */
    fx_z8_photo_tools_poll(&state);assert(!state.running&&state.status==17&&rd(R_SERIAL)==11&&rd(R_STATE)==1&&started==1);
    wr(R_STATE,0);wr(R_BROWSER_OPEN,1);assert(begin(FX_PHOTO_ALL)==FX_OK);fx_z8_photo_tools_poll(&state);assert(!state.running&&state.status==17);wr(R_BROWSER_OPEN,0);
    assert(begin(FX_PHOTO_ALL)==FX_OK);fx_z8_photo_tools_poll(&state);assert(rd(R_JOB_MODE)==FX_PHOTO_ALL&&rd(R_SERIAL)==12&&created==1);
    clock_ticks=6000;fx_z8_photo_tools_poll(&state);assert(!state.running&&state.status==17&&rd(R_CLAIMED)==12&&rd(R_STATE)==2);
    /* A late worker observes claimed==serial, so no file I/O occurs after revoke. */
    assert(rd(R_CLAIMED)==rd(R_SERIAL)&&delay==3&&restored==2);
    assert(begin(FX_PHOTO_NEWEST)==FX_OK);assert(fx_z8_photo_tools_stop(&state)==FX_OK);fx_z8_photo_tools_poll(&state);
    assert(!state.running&&state.status==7&&fx_z8_photo_tools_stop(&state)==FX_OK);uint32_t serial=state.serial;
    assert(fx_z8_photo_tools_resume(&state)==FX_OK&&!state.revoked&&state.serial==serial);
    assert(begin(FX_PHOTO_NEWEST)==FX_OK);fx_z8_photo_tools_poll(&state);assert(state.running);wr(R_SERIAL,99);fx_z8_photo_tools_poll(&state);
    assert(state.fault==FX_STALE&&state.running&&call(FX_RESOURCE_DETACH)==FX_BUSY&&fx_z8_photo_tools_resume(&state)==FX_BUSY);
    puts("PASS: GUI-only native claim, exclusive ownership, late-claim revocation, real progress ABI, cancellation, deferred detach, restart serial retention");
}
