/* SPDX-License-Identifier: GPL-3.0-only */
/* Synthetic transport/CPU fixture. This test does not operate a camera. */
#include "capsule_rendezvous.h"
#include "fenestra_capsule.h"
#include <stdio.h>
#include <stdlib.h>
#if defined(_WIN32)
#include <windows.h>
#else
#include <pthread.h>
#include <sched.h>
#endif
static unsigned checks;
#define CHECK(c) do {++checks;if(!(c)){fprintf(stderr,"check %u at line %u failed\n",checks,(unsigned)__LINE__);exit(1);}}while(0)
static _Thread_local uint32_t this_cpu;
static _Thread_local uint64_t this_daif;
static uint32_t current_el=4u,bad_kind,bad_index,dispatch_count,dispatch_error;
static _Atomic uint32_t synchronized[3],returned[3];
static const uint64_t addresses[4]={0x40174108u,0x40173f0cu,0x4016c8f4u,0x40173c54u};
static const uint8_t original[4][16]={
{0xff,0x83,0x02,0xd1,0xfc,0x23,0x00,0xf9,0xfb,0x6b,0x05,0xa9,0xf9,0x63,0x06,0xa9},
{0xff,0xc3,0x01,0xd1,0xf9,0x63,0x03,0xa9,0xf7,0x5b,0x04,0xa9,0xf5,0x53,0x05,0xa9},
{0x08,0x04,0x83,0xd2,0xa8,0x96,0xa0,0xf2,0x48,0x01,0xc0,0xf2,0x08,0x00,0xe0,0xf2},
{0xa8,0x00,0x38,0xd5,0x00,0x0d,0x00,0x12,0xc0,0x03,0x5f,0xd6,0xe0,0x01,0x00,0xb4}};
uint64_t fx_rendezvous_test_register(uint32_t n) {return n==0u?this_cpu:n==1u?this_daif:current_el;}
void fx_rendezvous_test_daif(uint64_t d) {this_daif=d;}
void fx_rendezvous_test_mask(void) {this_daif|=0xc0u;}
void fx_rendezvous_test_sync(void) {
    if((this_daif&0xc0u)!=0xc0u)abort();
    atomic_fetch_add_explicit(&synchronized[this_cpu],1u,memory_order_relaxed);
}
void fx_rendezvous_test_wait(void) {
#if defined(_WIN32)
    (void)SwitchToThread();
#else
    (void)sched_yield();
#endif
}
void fx_rendezvous_test_event(void) {}
uint64_t fx_rendezvous_test_read(uint64_t a,uint32_t bytes) {
    for(uint32_t i=0u;i<4u;++i)if(bytes==1u && a>=addresses[i] && a<addresses[i]+16u) {
        uint32_t j=(uint32_t)(a-addresses[i]);
        return (uint64_t)(original[i][j]^((bad_kind==1u && bad_index==i*16u+j)?1u:0u));
    }
    for(uint32_t i=0u;i<3u;++i) {
        uint64_t descriptor=UINT64_C(0xa04b6bfd8)+(uint64_t)i*32u;
        if(a==UINT64_C(0xa04b6c038)+(uint64_t)i*24u && bytes==4u)return bad_kind==2u && bad_index==i?4u:5u;
        if(a==UINT64_C(0xa04b51820)+0x2000u+(uint64_t)i*256u+120u && bytes==8u)
            return bad_kind==3u && bad_index==i?0u:descriptor;
        if(a==descriptor && bytes==4u)return bad_kind==4u && bad_index==i?14u:15u;
        if(a==descriptor+16u && bytes==8u)return bad_kind==5u && bad_index==i?0u:0x40173f0cu;
    }
    abort();
}
typedef struct {void (*fn)(void *,uintptr_t);void *arg;uint32_t cpu;} Thread;
#if defined(_WIN32)
#define THREAD_RESULT DWORD WINAPI
#define THREAD_RETURN 0u
#else
#define THREAD_RESULT void *
#define THREAD_RETURN NULL
#endif
static THREAD_RESULT remote(void *p) {
    Thread *t=p;this_cpu=t->cpu;this_daif=0x80u;
    t->fn(t->arg,0u);
    if(this_daif!=0x80u)abort();
    atomic_store_explicit(&returned[this_cpu],1u,memory_order_release);return THREAD_RETURN;
}
int64_t fx_rendezvous_test_dispatch(void (*fn)(void *,uintptr_t),void *arg,uintptr_t unused,uint32_t mask) {
    (void)unused;++dispatch_count;if(mask!=7u)abort();if(dispatch_error)return -1012;
    Thread threads[2];uint32_t n=0u;
#if defined(_WIN32)
    HANDLE handles[2];
#else
    pthread_t handles[2];
#endif
    for(uint32_t i=0u;i<3u;++i)if(i!=this_cpu) {
        threads[n]=(Thread){fn,arg,i};
#if defined(_WIN32)
        handles[n]=CreateThread(NULL,0u,remote,&threads[n],0u,NULL);if(!handles[n])abort();
#else
        if(pthread_create(&handles[n],NULL,remote,&threads[n]))abort();
#endif
        ++n;
    }
    fn(arg,0u);
    for(uint32_t i=0u;i<2u;++i) {
#if defined(_WIN32)
        if(WaitForSingleObject(handles[i],10000u)!=WAIT_OBJECT_0)abort();CloseHandle(handles[i]);
#else
        if(pthread_join(handles[i],NULL))abort();
#endif
    }
    return 0;
}
typedef struct {FxZ8CapsuleRendezvous *r;uint32_t no_leave,fail;uint32_t calls;} Work;
static FxResult work(void *p) {
    Work *w=p;FxZ8CapsuleRendezvous *r=w->r;uint64_t lease=0u,duplicate=9u;++w->calls;
    CHECK(atomic_load_explicit(&r->parked,memory_order_acquire)==(7u^(1u<<this_cpu)));
    CHECK(fx_z8_capsule_rendezvous_run(r,work,w)==FX_BUSY);
    CHECK(fx_z8_capsule_exclusion_enter(r,&lease)==FX_OK && lease!=0u);
    CHECK((this_daif&0xc0u)==0xc0u);
    CHECK(fx_z8_capsule_exclusion_enter(r,&duplicate)==FX_STATE && duplicate==0u);
    CHECK(fx_z8_capsule_exclusion_leave(r,lease+1u,1u)==FX_STATE);
    CHECK(fx_z8_capsule_exclusion_leave(r,lease,3u)==FX_ARGUMENT);
    CHECK(atomic_load_explicit(&r->parked,memory_order_acquire)==7u);
    if(w->no_leave)return FX_OK;
    for(uint32_t epoch=1u;epoch<=2u;++epoch) {
        CHECK(fx_z8_capsule_exclusion_leave(r,lease,epoch==1u?FX_CAPSULE_LEAVE_COMMIT:FX_CAPSULE_LEAVE_ROLLBACK)==FX_OK);
        for(uint32_t i=0u;i<3u;++i) {
            CHECK(atomic_load_explicit(&synchronized[i],memory_order_acquire)==epoch);
            CHECK(atomic_load_explicit(&r->acknowledged[i],memory_order_acquire)==epoch);
            CHECK(atomic_load_explicit(&returned[i],memory_order_acquire)==0u);
        }
        CHECK(atomic_load_explicit(&r->exit_requested,memory_order_acquire)==0u);
    }
    return w->fail?FX_IO:FX_OK;
}
static FxResult ignored(void *p) {(void)p;return FX_OK;}
int main(void) {
    FxZ8CapsuleRendezvous r={0};Work w={&r,0u,0u,0u};uint64_t lease=1u;
    CHECK(fx_z8_capsule_rendezvous_run(NULL,work,&w)==FX_ARGUMENT);
    CHECK(fx_z8_capsule_rendezvous_run(&r,NULL,&w)==FX_ARGUMENT);
    CHECK(fx_z8_capsule_exclusion_enter(&r,&lease)==FX_STATE && !lease);
    CHECK(fx_z8_capsule_exclusion_leave(&r,1u,0u)==FX_STATE);
    for(bad_index=0u;bad_index<64u;++bad_index) {bad_kind=1u;CHECK(fx_z8_capsule_rendezvous_run(&r,ignored,NULL)==FX_INTEGRITY);}
    for(bad_kind=2u;bad_kind<=5u;++bad_kind)for(bad_index=0u;bad_index<3u;++bad_index)
        CHECK(fx_z8_capsule_rendezvous_run(&r,ignored,NULL)==(bad_kind==2u?FX_BUSY:FX_INTEGRITY));
    bad_kind=0u;CHECK(dispatch_count==0u);
    current_el=0u;CHECK(fx_z8_capsule_rendezvous_run(&r,ignored,NULL)==FX_STATE);current_el=4u;
    this_cpu=3u;CHECK(fx_z8_capsule_rendezvous_run(&r,ignored,NULL)==FX_STATE);this_cpu=0u;
    this_daif=0x80u;CHECK(fx_z8_capsule_rendezvous_run(&r,ignored,NULL)==FX_BUSY);this_daif=0u;
    r.serial=UINT64_MAX;CHECK(fx_z8_capsule_rendezvous_run(&r,ignored,NULL)==FX_BOUNDS);r.serial=0u;
    dispatch_error=1u;CHECK(fx_z8_capsule_rendezvous_run(&r,ignored,NULL)==FX_IO);dispatch_error=0u;
    for(this_cpu=0u;this_cpu<3u;++this_cpu) {
        for(uint32_t i=0u;i<3u;++i) {atomic_store(&synchronized[i],0u);atomic_store(&returned[i],0u);}
        CHECK(fx_z8_capsule_rendezvous_run(&r,work,&w)==FX_OK);
        CHECK(!r.held && !r.lease && !r.work && !r.argument && this_daif==0u);
        for(uint32_t i=0u;i<3u;++i)CHECK(i==this_cpu || atomic_load(&returned[i])==1u);
    }
    this_cpu=0u;
    for(uint32_t i=0u;i<3u;++i){atomic_store(&synchronized[i],0u);atomic_store(&returned[i],0u);}
    w.no_leave=1u;CHECK(fx_z8_capsule_rendezvous_run(&r,work,&w)==FX_STATE);
    for(uint32_t i=0u;i<3u;++i)CHECK(atomic_load(&synchronized[i])==1u);
    for(uint32_t i=0u;i<3u;++i){atomic_store(&synchronized[i],0u);atomic_store(&returned[i],0u);}
    w.no_leave=0u;w.fail=1u;CHECK(fx_z8_capsule_rendezvous_run(&r,work,&w)==FX_IO);
    for(uint32_t i=0u;i<3u;++i){atomic_store(&synchronized[i],0u);atomic_store(&returned[i],0u);}
    w.fail=0u;this_daif=0x40u;CHECK(fx_z8_capsule_rendezvous_run(&r,work,&w)==FX_OK);
    CHECK(w.calls==6u && !atomic_load(&r.gate) && this_daif==0x40u);
    printf("capsule rendezvous: %u checks PASS (synthetic CPU/IRQ transport)\n",checks);return 0;
}
