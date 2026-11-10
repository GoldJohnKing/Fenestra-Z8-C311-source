/* SPDX-License-Identifier: GPL-3.0-only
 * Synthetic native memory/MMU/rendezvous callbacks only; no camera transport.
 */
#include "fenestra_capsule.h"
#include "fenestra_memory.h"
#ifndef FX_CAPSULE_ARM_TEST
#include <stdio.h>
#include <stdlib.h>
#endif
uint32_t fx_capsule_test_checks,fx_capsule_test_failure;
static void fail(uint32_t line) {
    fx_capsule_test_failure=line;
#ifdef FX_CAPSULE_ARM_TEST
    for(;;)__asm__ volatile("nop");
#else
    fprintf(stderr,"capsule assertion at line %u\n",line);exit(1);
#endif
}
#define CHECK(x) do{++fx_capsule_test_checks;if(!(x))fail(__LINE__);}while(0)
#define NATIVE_BASE UINT64_C(0x1000)
#define RECORDS 4u
static uint8_t package[4096],target[32],package_hash[32],native[8192];
static FxCapsuleControl control;
static uint32_t package_bytes,apply_count,rollback_count,enter_count,leave_count,entry_count,abort_count,publish_count;
static uint32_t in_native,leave_outcome,entry_staged,sealed,log_count,events[64],switching;
static int forward_fail,rollback_fail,corrupt_readback,enter_error,enter_has_lease,leave_error,abort_error,entry_error,mutate_enter,admit_error;
static FxCapsuleHeader *header(void){return (FxCapsuleHeader *)(void *)package;}
static FxCapsuleRecord *record(uint32_t i){return (FxCapsuleRecord *)(void *)(package+128u+i*112u);}
static void finish_hash(uint32_t body) {
    if(body)fx_sha256(package+128u,package_bytes-128u,header()->body_sha256);
    fx_sha256(package,package_bytes,package_hash);
}
static void make(void) {
    memset(package,0,sizeof(package));memset(native,0,sizeof(native));
    FxCapsuleHeader *h=header();memcpy(h->magic,"FXCAPS1",8u);h->abi=1u;h->header_bytes=128u;
    h->record_count=RECORDS;h->records_offset=128u;h->package_id=79u;h->entry=NATIVE_BASE+4u;
    for(uint32_t i=0u;i<32u;++i)target[i]=(uint8_t)(i+1u);memcpy(h->target_sha256,target,32u);
    uint32_t at=128u+RECORDS*112u;
    for(uint32_t i=0u;i<RECORDS;++i) {
        FxCapsuleRecord *r=record(i);r->kind=i<2u?FX_CAPSULE_IMAGE:FX_CAPSULE_HOOK;
        r->flags=i==0u?FX_CAPSULE_EXECUTE:i==1u?0u:i==2u?FX_CAPSULE_INSTRUCTION:FX_CAPSULE_POINTER;
        r->address=NATIVE_BASE+(i==0u?0u:i==1u?256u:i==2u?4096u:4112u);
        r->bytes=i<2u?16u:i==2u?4u:8u;r->depends_on=i<2u?UINT32_MAX:0u;
        r->old_offset=at;at+=r->bytes;r->new_offset=at;at+=r->bytes;
        memset(package+r->old_offset,(int)(i+1u),r->bytes);memset(package+r->new_offset,(int)(i+17u),r->bytes);
        memcpy(native+(uint32_t)(r->address-NATIVE_BASE),package+r->old_offset,r->bytes);
        fx_sha256(package+r->old_offset,r->bytes,r->old_sha256);fx_sha256(package+r->new_offset,r->bytes,r->new_sha256);
        h->total_write_bytes+=r->bytes;
    }
    package_bytes=at;h->package_bytes=at;finish_hash(1u);
}
static uint32_t index_of(const FxCapsuleRecord *r){for(uint32_t i=0u;i<RECORDS;++i)if(r->address==record(i)->address)return i;return UINT32_MAX;}
static FxResult io_read(void *context,uint64_t address,void *out,uint32_t bytes) {
    CHECK(context==&control);if(address<NATIVE_BASE || address-NATIVE_BASE>sizeof(native) || bytes>sizeof(native)-(address-NATIVE_BASE))return FX_BOUNDS;
    memcpy(out,native+(uint32_t)(address-NATIVE_BASE),bytes);return FX_OK;
}
static FxResult io_admit(void *context,const FxCapsuleHeader *h,uint32_t i,const FxCapsuleRecord *r) {
    CHECK(context==&control && h->package_id==79u && i<RECORDS);
    if((int)i==admit_error)return FX_CAPABILITY;
    return r->address>=NATIVE_BASE && r->address-NATIVE_BASE<=sizeof(native)-r->bytes?FX_OK:FX_BOUNDS;
}
static FxResult io_enter(void *context,const FxCapsuleHeader *h,const uint8_t *bytes,uint64_t *lease) {
    CHECK(context==&control && h->package_id==79u && bytes==package);++enter_count;
    CHECK(!in_native);
    if(switching)CHECK(control.status.phase==FX_CAPSULE_ROLLING_BACK || control.status.phase==FX_CAPSULE_COMMITTING);
    else CHECK(!publish_count && control.status.phase==FX_CAPSULE_COMMITTING);
    if(enter_error){if(enter_has_lease){*lease=91u;in_native=1u;}return FX_BUSY;}
    in_native=1u;*lease=91u;
    if(mutate_enter==1)native[0]^=1u;
    if(mutate_enter==2)package[package_bytes-1u]^=1u;
    return FX_OK;
}
static FxResult io_apply(void *context,uint64_t lease,const FxCapsuleRecord *r,const uint8_t *data,uint32_t undo) {
    CHECK(context==&control && lease==91u && in_native);uint32_t i=index_of(r);CHECK(i<RECORDS);
    events[log_count++]=(undo?100u:0u)+i;CHECK(log_count<64u && (!switching || r->kind==FX_CAPSULE_HOOK));
    if(undo)++rollback_count;else ++apply_count;
    uint8_t *p=native+(uint32_t)(r->address-NATIVE_BASE);
    if(!undo && r->kind==FX_CAPSULE_HOOK)CHECK(sealed==3u && entry_staged);
    if((!undo && (int)i==forward_fail) || (undo && (int)i==rollback_fail)) {
        memcpy(p,data,r->bytes/2u);return FX_IO; /* Deliberately partial write. */
    }
    memcpy(p,data,r->bytes);
    if(!undo && r->kind==FX_CAPSULE_IMAGE)sealed|=1u<<i;
    if(undo && r->kind==FX_CAPSULE_IMAGE)sealed&=~(1u<<i);
    if(!undo && (int)i==corrupt_readback)p[0]^=1u;
    return FX_OK;
}
static FxResult io_leave(void *context,uint64_t lease,uint32_t outcome) {
    CHECK(context==&control && lease==91u && in_native);++leave_count;leave_outcome=outcome;
    CHECK(control.status.phase!=FX_CAPSULE_READY && control.status.phase!=FX_CAPSULE_DISARMED);
    CHECK(switching || !publish_count);
    if((int)outcome==leave_error)return FX_IO;
    in_native=0u;return FX_OK;
}
static FxResult io_stage(void *context,uint64_t lease,uint64_t entry) {
    CHECK(context==&control && lease==91u && in_native && entry==NATIVE_BASE+4u && sealed==3u);
    CHECK(apply_count==2u && !publish_count);++entry_count;entry_staged=1u;events[log_count++]=50u;
    return entry_error?FX_IO:FX_OK;
}
static FxResult io_abort(void *context,uint64_t lease,uint64_t entry) {
    CHECK(context==&control && lease==91u && in_native && entry==NATIVE_BASE+4u);++abort_count;
    if(abort_error)return FX_IO;
    entry_staged=0u;return FX_OK;
}
static void io_publish(void *context,uint64_t entry) {
    CHECK(context==&control && entry==NATIVE_BASE+4u && !in_native && entry_staged && leave_outcome==FX_CAPSULE_LEAVE_COMMIT);
    CHECK(control.status.phase!=FX_CAPSULE_READY && apply_count==4u);++publish_count;
}
static uint32_t io_survives(void *context,const FxCapsuleRecord *r) {
    CHECK(context==&control && r->kind==FX_CAPSULE_HOOK);return r->address!=record(3)->address;
}
static FxCapsuleIO io(void){return (FxCapsuleIO){&control,io_read,io_admit,io_enter,io_apply,io_leave,io_stage,io_abort,io_publish,0};}
static void reset(void) {
    memset(&control,0,sizeof(control));make();apply_count=rollback_count=enter_count=leave_count=entry_count=abort_count=publish_count=0u;
    in_native=leave_outcome=entry_staged=sealed=log_count=switching=0u;memset(events,0,sizeof(events));
    forward_fail=rollback_fail=corrupt_readback=leave_error=admit_error=-1;enter_error=enter_has_lease=abort_error=entry_error=mutate_enter=0;
    CHECK(fx_capsule_init(&control,target,0u,io())==FX_OK);
}
static FxCapsuleStatus status(void){FxCapsuleStatus s;CHECK(fx_capsule_query(&control,&s)==FX_OK);return s;}
static FxResult prepare(void){return fx_capsule_prepare(&control,package,package_bytes,package_hash);}
static int is_old(uint32_t i){FxCapsuleRecord *r=record(i);return !memcmp(native+(uint32_t)(r->address-NATIVE_BASE),package+r->old_offset,r->bytes);}
static int is_new(uint32_t i){FxCapsuleRecord *r=record(i);return !memcmp(native+(uint32_t)(r->address-NATIVE_BASE),package+r->new_offset,r->bytes);}
static void no_write_failure(FxResult expected) {
    finish_hash(1u);CHECK(prepare()==expected);CHECK(!apply_count && !enter_count && !publish_count && status().phase==FX_CAPSULE_FAILED);
}
int main(void) {
    reset();CHECK(prepare()==FX_OK && status().phase==FX_CAPSULE_PREPARED && !apply_count);
    CHECK(fx_capsule_commit(&control)==FX_OK);FxCapsuleStatus s=status();
    CHECK(s.phase==FX_CAPSULE_READY && s.applied_records==4u && s.validated_records==4u && s.image_records==2u && !s.error);
    CHECK(publish_count==1u && entry_count==1u && !rollback_count && !abort_count);
    CHECK(log_count==5u && events[0]==0u && events[1]==1u && events[2]==50u && events[3]==2u && events[4]==3u);
    for(uint32_t i=0u;i<RECORDS;++i)CHECK(is_new(i));
    CHECK(fx_capsule_commit(&control)==FX_STATE && prepare()==FX_STATE && fx_capsule_init(&control,target,0u,io())==FX_STATE);
    reset();package[package_bytes-1u]^=1u;CHECK(prepare()==FX_INTEGRITY && !enter_count);
    reset();package[package_bytes-1u]^=1u;finish_hash(0u);CHECK(prepare()==FX_INTEGRITY && !apply_count);
    reset();header()->target_sha256[0]^=1u;no_write_failure(FX_CAPABILITY);
    reset();header()->requires_id=88u;no_write_failure(FX_STATE);
    reset();record(0)->flags=3u;no_write_failure(FX_ARGUMENT);
    reset();record(1)->address=record(0)->address+4u;no_write_failure(FX_BOUNDS);
    reset();record(0)->new_offset=record(0)->old_offset;no_write_failure(FX_BOUNDS);
    reset();record(1)->old_offset=record(0)->new_offset;no_write_failure(FX_BOUNDS);
    reset();record(0)->new_offset=package_bytes;no_write_failure(FX_BOUNDS);
    reset();record(0)->address=UINT64_MAX-4u;no_write_failure(FX_BOUNDS);
    reset();record(0)->bytes=0u;no_write_failure(FX_BOUNDS);
    reset();record(2)->depends_on=2u;no_write_failure(FX_ARGUMENT);
    reset();record(0)->depends_on=1u;no_write_failure(FX_ARGUMENT);
    reset();record(0)->kind=FX_CAPSULE_HOOK;record(0)->flags=FX_CAPSULE_DATA;no_write_failure(FX_ARGUMENT);
    reset();record(0)->old_sha256[0]^=1u;no_write_failure(FX_INTEGRITY);
    reset();record(0)->reserved[1]=1u;no_write_failure(FX_ARGUMENT);
    reset();header()->total_write_bytes++;no_write_failure(FX_ARGUMENT);
    reset();header()->entry=record(1)->address;no_write_failure(FX_ARGUMENT);
    reset();header()->entry++;no_write_failure(FX_ARGUMENT);
    reset();header()->flags=1u;no_write_failure(FX_ARGUMENT);
    reset();header()->record_count=0u;no_write_failure(FX_ARGUMENT);
    reset();CHECK(fx_capsule_prepare(&control,package,FX_CAPSULE_MAX_PACKAGE+1u,package_hash)==FX_BOUNDS);
    reset();admit_error=3;CHECK(prepare()==FX_CAPABILITY && !apply_count && !enter_count);
    reset();native[0]^=1u;CHECK(prepare()==FX_STALE && !apply_count);
    reset();CHECK(prepare()==FX_OK);mutate_enter=1;CHECK(fx_capsule_commit(&control)==FX_STALE);
    CHECK(!apply_count && leave_count==1u && status().phase==FX_CAPSULE_FAILED && !publish_count);
    reset();CHECK(prepare()==FX_OK);mutate_enter=2;CHECK(fx_capsule_commit(&control)==FX_INTEGRITY && !apply_count && !publish_count);
    reset();CHECK(prepare()==FX_OK);package[package_bytes-1u]^=1u;CHECK(fx_capsule_commit(&control)==FX_INTEGRITY && !enter_count);
    reset();CHECK(prepare()==FX_OK);control.io.enter=0;CHECK(fx_capsule_commit(&control)==FX_CAPABILITY && !apply_count);
    reset();CHECK(prepare()==FX_OK);enter_error=1;CHECK(fx_capsule_commit(&control)==FX_BUSY && !apply_count && !leave_count);
    reset();CHECK(prepare()==FX_OK);enter_error=enter_has_lease=1;
    CHECK(fx_capsule_commit(&control)==FX_BUSY && leave_count==1u && status().phase==FX_CAPSULE_FAILED);
    for(int i=0;i<4;++i) {
        reset();CHECK(prepare()==FX_OK);forward_fail=i;CHECK(fx_capsule_commit(&control)==FX_IO);
        CHECK(status().phase==FX_CAPSULE_FAILED && !status().retained_records && !publish_count);
        for(uint32_t j=0u;j<RECORDS;++j)CHECK(is_old(j));
        CHECK(rollback_count==(uint32_t)i+1u && leave_outcome==FX_CAPSULE_LEAVE_ROLLBACK);
    }
    reset();CHECK(prepare()==FX_OK);corrupt_readback=2;CHECK(fx_capsule_commit(&control)==FX_INTEGRITY && status().phase==FX_CAPSULE_FAILED);
    for(uint32_t i=0u;i<RECORDS;++i)CHECK(is_old(i));
    reset();CHECK(prepare()==FX_OK);forward_fail=3;rollback_fail=3;
    CHECK(fx_capsule_commit(&control)==FX_IO && status().phase==FX_CAPSULE_RETAINED);
    CHECK(is_new(0u) && is_new(1u) && !abort_count && entry_staged && !publish_count);
    CHECK(leave_outcome==FX_CAPSULE_LEAVE_RETAINED && prepare()==FX_STATE);
    reset();CHECK(prepare()==FX_OK);forward_fail=3;abort_error=1;
    CHECK(fx_capsule_commit(&control)==FX_IO && status().phase==FX_CAPSULE_RETAINED && abort_count==1u);
    CHECK(is_old(2u) && is_old(3u) && is_new(0u) && is_new(1u) && !publish_count);
    reset();CHECK(prepare()==FX_OK);forward_fail=1;rollback_fail=1;
    CHECK(fx_capsule_commit(&control)==FX_IO && status().phase==FX_CAPSULE_RETAINED && !publish_count);
    reset();CHECK(prepare()==FX_OK);entry_error=1;
    CHECK(fx_capsule_commit(&control)==FX_IO && abort_count==1u && status().phase==FX_CAPSULE_FAILED);
    CHECK(!publish_count && is_old(0u) && is_old(1u));
    reset();CHECK(prepare()==FX_OK);leave_error=FX_CAPSULE_LEAVE_COMMIT;
    CHECK(fx_capsule_commit(&control)==FX_IO && status().phase==FX_CAPSULE_RETAINED && !publish_count && entry_staged);
    CHECK(!rollback_count && prepare()==FX_STATE);
    reset();CHECK(prepare()==FX_OK);forward_fail=2;leave_error=FX_CAPSULE_LEAVE_ROLLBACK;
    CHECK(fx_capsule_commit(&control)==FX_IO && status().phase==FX_CAPSULE_RETAINED && !publish_count);
    reset();atomic_store(&control.gate,1u);CHECK(fx_capsule_commit(&control)==FX_BUSY && fx_capsule_query(&control,&s)==FX_BUSY);
    CHECK(fx_capsule_disarm(&control)==FX_BUSY && fx_capsule_rearm(&control)==FX_BUSY);
    atomic_store(&control.gate,0u);
    /* Ingress revocation changes HOOKs only; IMAGE, entry and publication stay. */
    reset();CHECK(fx_capsule_disarm(&control)==FX_STATE && fx_capsule_rearm(&control)==FX_STATE);
    CHECK(prepare()==FX_OK && fx_capsule_disarm(&control)==FX_STATE && !enter_count);
    CHECK(fx_capsule_commit(&control)==FX_OK);switching=1u;uint32_t forward=apply_count;
    CHECK(fx_capsule_rearm(&control)==FX_STATE && enter_count==1u);
    CHECK(fx_capsule_disarm(&control)==FX_OK && status().phase==FX_CAPSULE_DISARMED && !status().error);
    CHECK(is_new(0u) && is_new(1u) && is_old(2u) && is_old(3u) && rollback_count==2u && apply_count==forward);
    CHECK(events[log_count-2u]==103u && events[log_count-1u]==102u && leave_outcome==FX_CAPSULE_LEAVE_COMMIT);
    CHECK(!in_native && publish_count==1u && entry_count==1u && entry_staged && !abort_count);
    CHECK(fx_capsule_disarm(&control)==FX_OK && enter_count==3u && rollback_count==2u && status().phase==FX_CAPSULE_DISARMED);
    CHECK(prepare()==FX_STATE && fx_capsule_commit(&control)==FX_STATE);
    CHECK(fx_capsule_rearm(&control)==FX_OK && status().phase==FX_CAPSULE_READY && apply_count==forward+2u);
    CHECK(events[log_count-2u]==2u && events[log_count-1u]==3u && publish_count==1u && entry_count==1u);
    for(uint32_t i=0u;i<RECORDS;++i)CHECK(is_new(i));
    /* Unexpected current bytes on either side are rejected before any write. */
    reset();CHECK(prepare()==FX_OK && fx_capsule_commit(&control)==FX_OK);switching=1u;
    native[4112u]^=1u;uint32_t undone=rollback_count;
    CHECK(fx_capsule_disarm(&control)==FX_STALE && status().phase==FX_CAPSULE_READY && status().failed_record==3u);
    CHECK(rollback_count==undone && leave_outcome==FX_CAPSULE_LEAVE_ROLLBACK);
    native[4112u]^=1u;native[0]^=1u;
    CHECK(fx_capsule_disarm(&control)==FX_STALE && status().phase==FX_CAPSULE_READY && status().failed_record==0u);
    native[0]^=1u;CHECK(fx_capsule_disarm(&control)==FX_OK);
    native[4096u]^=1u;CHECK(fx_capsule_rearm(&control)==FX_STALE && status().phase==FX_CAPSULE_DISARMED && status().failed_record==2u);
    CHECK(fx_capsule_disarm(&control)==FX_STALE && status().phase==FX_CAPSULE_DISARMED);
    native[4096u]^=1u;CHECK(fx_capsule_rearm(&control)==FX_OK);
    package[package_bytes-1u]^=1u;uint32_t entered=enter_count;
    CHECK(fx_capsule_disarm(&control)==FX_INTEGRITY && enter_count==entered && status().phase==FX_CAPSULE_READY);
    package[package_bytes-1u]^=1u;
    /* Runtime bytes inside a WRITE image are never compared. */
    reset();record(1)->flags=FX_CAPSULE_WRITE;finish_hash(1u);
    CHECK(prepare()==FX_OK && fx_capsule_commit(&control)==FX_OK);switching=1u;native[256u]^=0x5au;
    CHECK(fx_capsule_disarm(&control)==FX_OK && fx_capsule_rearm(&control)==FX_OK && native[256u]==(uint8_t)(18u^0x5au));
    /* Boot-rebuilt HOOK targets (runtime-owned by stock code) are neither
     * compared nor switched; surviving HOOKs still are. */
    reset();control.io.survives=io_survives;CHECK(prepare()==FX_OK && fx_capsule_commit(&control)==FX_OK);switching=1u;
    native[4112u]^=0x33u;undone=rollback_count;
    CHECK(fx_capsule_disarm(&control)==FX_OK && rollback_count==undone+1u && is_old(2u) && native[4112u]==(uint8_t)(20u^0x33u));
    CHECK(events[log_count-1u]==102u && fx_capsule_disarm(&control)==FX_OK && rollback_count==undone+1u);
    native[4112u]^=0x33u;forward=apply_count;
    CHECK(fx_capsule_rearm(&control)==FX_OK && apply_count==forward+1u && is_new(2u) && is_new(3u));
    native[4096u]^=1u;CHECK(fx_capsule_disarm(&control)==FX_STALE && status().failed_record==2u);
    native[4096u]^=1u;
    /* A failed switch restores the complete previous side, newest first. */
    reset();CHECK(prepare()==FX_OK && fx_capsule_commit(&control)==FX_OK);switching=1u;rollback_fail=2;
    CHECK(fx_capsule_disarm(&control)==FX_IO && status().phase==FX_CAPSULE_READY && !status().retained_records);
    for(uint32_t i=0u;i<RECORDS;++i)CHECK(is_new(i));
    CHECK(events[log_count-2u]==2u && events[log_count-1u]==3u && leave_outcome==FX_CAPSULE_LEAVE_ROLLBACK);
    reset();CHECK(prepare()==FX_OK && fx_capsule_commit(&control)==FX_OK);switching=1u;rollback_fail=2;forward_fail=3;
    CHECK(fx_capsule_disarm(&control)==FX_IO && status().phase==FX_CAPSULE_RETAINED && status().retained_records==1u);
    CHECK(leave_outcome==FX_CAPSULE_LEAVE_RETAINED && fx_capsule_disarm(&control)==FX_STATE && fx_capsule_rearm(&control)==FX_STATE);
    reset();CHECK(prepare()==FX_OK && fx_capsule_commit(&control)==FX_OK);switching=1u;
    CHECK(fx_capsule_disarm(&control)==FX_OK);forward_fail=3;
    CHECK(fx_capsule_rearm(&control)==FX_IO && status().phase==FX_CAPSULE_DISARMED && is_old(2u) && is_old(3u));
    CHECK(is_new(0u) && is_new(1u) && leave_outcome==FX_CAPSULE_LEAVE_ROLLBACK);
    forward_fail=-1;CHECK(fx_capsule_rearm(&control)==FX_OK && is_new(2u) && is_new(3u));
    reset();CHECK(prepare()==FX_OK && fx_capsule_commit(&control)==FX_OK);switching=1u;enter_error=1;
    CHECK(fx_capsule_disarm(&control)==FX_BUSY && status().phase==FX_CAPSULE_READY);
    enter_has_lease=1;CHECK(fx_capsule_disarm(&control)==FX_BUSY && status().phase==FX_CAPSULE_READY);
    CHECK(leave_outcome==FX_CAPSULE_LEAVE_ROLLBACK && !in_native);
    enter_error=enter_has_lease=0;leave_error=FX_CAPSULE_LEAVE_COMMIT;
    CHECK(fx_capsule_disarm(&control)==FX_IO && status().phase==FX_CAPSULE_RETAINED);
    /* Retained-RAM boot after verified revocation: earlier IMAGE bytes are
     * unreachable and overwritten; every HOOK must still be its preimage. */
    reset();
    for(uint32_t i=0u;i<2u;++i)memcpy(native+(uint32_t)(record(i)->address-NATIVE_BASE),package+record(i)->new_offset,record(i)->bytes);
    native[256u]=0xa5u;
    CHECK(prepare()==FX_STALE && status().failed_record==0u && !control.images_unreachable && !enter_count);
    CHECK(fx_capsule_prepare_unreachable(&control,package,package_bytes,package_hash)==FX_OK && control.images_unreachable);
    CHECK(fx_capsule_commit(&control)==FX_OK && status().phase==FX_CAPSULE_READY && publish_count==1u);
    for(uint32_t i=0u;i<RECORDS;++i)CHECK(is_new(i));
    reset();memcpy(native+4096u,package+record(2)->new_offset,4u);
    CHECK(fx_capsule_prepare_unreachable(&control,package,package_bytes,package_hash)==FX_STALE && status().failed_record==2u);
    reset();memcpy(native,package+record(0)->new_offset,16u);
    CHECK(fx_capsule_prepare_unreachable(&control,package,package_bytes,package_hash)==FX_OK);
    forward_fail=3;CHECK(fx_capsule_commit(&control)==FX_IO && status().phase==FX_CAPSULE_FAILED);
    for(uint32_t i=0u;i<RECORDS;++i)CHECK(is_old(i));
    CHECK(prepare()==FX_OK && !control.images_unreachable);
#ifndef FX_CAPSULE_ARM_TEST
    printf("PASS: capsule manager %u checks; synthetic native exclusion/W^X callbacks, double prevalidation, IMAGE-before-HOOK, full undo or retained, HOOK-only disarm/rearm, unreachable-IMAGE prepare, no hot unload\n",fx_capsule_test_checks);
#endif
    return 0;
}
