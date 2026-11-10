/* SPDX-License-Identifier: GPL-3.0-only */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "fenestra_wlm_bundle.h"
static uint8_t stock[32];static uint32_t checks;
#define CHECK(v) do{++checks;assert(v);}while(0)
static void put(uint8_t *p,uint32_t n){for(uint32_t i=0u;i<4u;++i)p[i]=(uint8_t)(n>>(8u*i));}
static void hash_body(uint8_t *p,uint32_t n){fx_sha256(p+192u,n-192u,p+56u);}
static uint32_t inner(uint8_t *p){memset(p,0,512u);memcpy(p,"FENESTRA",8u);put(p+8u,2u);put(p+12u,128u);put(p+16u,1u);put(p+20u,1u);memcpy(p+24u,stock,32u);put(p+88u,156u);put(p+92u,4096u);put(p+100u,1u);put(p+116u,1u);put(p+128u+4u,152u);put(p+128u+8u,4u);put(p+128u+12u,4096u);put(p+128u+16u,5u);put(p+128u+20u,4096u);put(p+152u,0xd65f03c0u);fx_sha256(p+128u,28u,p+56u);return 156u;}
static uint32_t bundle(uint8_t *p,const char *id,uint8_t code){uint8_t f[512];uint32_t n=inner(f);memset(p,0,2048u);memcpy(p,"FENESTRA",8u);put(p+8u,4u);put(p+12u,192u);put(p+16u,1u);put(p+20u,1u);memcpy(p+24u,stock,32u);put(p+88u,256u+n+160u);put(p+96u,256u);put(p+100u,n);fx_sha256(f,n,p+104u);put(p+136u,192u);put(p+140u,1u);put(p+144u,64u);put(p+148u,1u);memcpy(p+152u,id,strlen(id));memcpy(p+192u,"shared",6u);put(p+208u,1u);put(p+216u,256u+n);put(p+220u,160u);memcpy(p+256u,f,n);uint8_t *native=p+256u+n;memcpy(native,"WLMNAT1\0",8u);put(native+8u,1u);put(native+12u,160u);memcpy(native+16u,"shared",6u);put(native+32u,1u);put(native+36u,1u);put(native+56u,160u);native[100u]=code;fx_sha256(native,160u,p+224u);hash_body(p,256u+n+160u);return 256u+n+160u;}
static uint8_t a[2048],b[2048],legacy[512],bad[2048];static FxWlmBundle parsed;
static char id[16]="framing";
static void parser(void){uint32_t n=bundle(a,"framing",0x55);CHECK(fx_wlm_bundle_inspect(a,n,id,stock,FX_SDK_CAPS,&parsed)==FX_OK);CHECK(parsed.frontend.bytes==4096u&&parsed.component_count==1u&&parsed.frontend_bytes==156u);CHECK(fx_module_header_entry(a,n)==UINT32_MAX);
    memcpy(bad,a,n);bad[92]=1u;CHECK(fx_wlm_bundle_inspect(bad,n,id,stock,FX_SDK_CAPS,&parsed)==FX_BOUNDS);memcpy(bad,a,n);bad[24]^=1u;CHECK(fx_wlm_bundle_inspect(bad,n,id,stock,FX_SDK_CAPS,&parsed)==FX_CAPABILITY);
    memcpy(bad,a,n);bad[n-1u]^=1u;CHECK(fx_wlm_bundle_inspect(bad,n,id,stock,FX_SDK_CAPS,&parsed)==FX_INTEGRITY);memcpy(bad,a,n);put(bad+96u,n-4u);CHECK(fx_wlm_bundle_inspect(bad,n,id,stock,FX_SDK_CAPS,&parsed)==FX_BOUNDS);
    memcpy(bad,a,n);put(bad+216u,256u);hash_body(bad,n);CHECK(fx_wlm_bundle_inspect(bad,n,id,stock,FX_SDK_CAPS,&parsed)==FX_BOUNDS);memcpy(bad,a,n);put(bad+136u,256u);CHECK(fx_wlm_bundle_inspect(bad,n,id,stock,FX_SDK_CAPS,&parsed)==FX_BOUNDS);
    memcpy(bad,a,n);bad[224]^=1u;hash_body(bad,n);CHECK(fx_wlm_bundle_inspect(bad,n,id,stock,FX_SDK_CAPS,&parsed)==FX_INTEGRITY);memcpy(bad,a,n);bad[104]^=1u;CHECK(fx_wlm_bundle_inspect(bad,n,id,stock,FX_SDK_CAPS,&parsed)==FX_INTEGRITY);
    memcpy(bad,a,n);put(bad+256u+8u,4u);fx_sha256(bad+256u,156u,bad+104u);hash_body(bad,n);CHECK(fx_wlm_bundle_inspect(bad,n,id,stock,FX_SDK_CAPS,&parsed)==FX_CAPABILITY);memcpy(bad,a,n);bad[168]=1u;CHECK(fx_wlm_bundle_inspect(bad,n,id,stock,FX_SDK_CAPS,&parsed)==FX_BOUNDS);}

static void canonical(void){uint32_t n=bundle(a,"framing",0x55);uint32_t native=412u;
    memcpy(bad,a,n);bad[n]=0;put(bad+88u,n+1u);hash_body(bad,n+1u);CHECK(fx_wlm_bundle_inspect(bad,n+1u,id,stock,FX_SDK_CAPS,&parsed)==FX_BOUNDS);
    memcpy(bad,a,n);put(bad+212u,2u);hash_body(bad,n);CHECK(fx_wlm_bundle_inspect(bad,n,id,stock,FX_SDK_CAPS,&parsed)==FX_BOUNDS);
    memcpy(bad,a,n);put(bad+212u,1u);hash_body(bad,n);CHECK(fx_wlm_bundle_inspect(bad,n,id,stock,FX_SDK_CAPS,&parsed)==FX_INTEGRITY);
    memcpy(bad,a,n);bad[native+16u]='X';fx_sha256(bad+native,160u,bad+224u);hash_body(bad,n);CHECK(fx_wlm_bundle_inspect(bad,n,id,stock,FX_SDK_CAPS,&parsed)==FX_INTEGRITY);
    memcpy(bad,a,n);memset(bad+192u,0,16u);memset(bad+native+16u,0,16u);memcpy(bad+192u,"shared.locale",13u);memcpy(bad+native+16u,"shared.locale",13u);put(bad+212u,1u);put(bad+native+36u,0u);put(bad+native+60u,1u);fx_sha256(bad+native,160u,bad+224u);hash_body(bad,n);CHECK(fx_wlm_bundle_inspect(bad,n,id,stock,FX_SDK_CAPS,&parsed)==FX_OK);
}
typedef struct{const char *name;uint8_t *data;uint32_t bytes;} File;
static File files[5];static uint32_t file_count,position,opens,reads,closes,close_fail,cancelled_flag,cancel_after_read,cancel_at_read,io_fail_at_read,io_fail_cancels;
static FxResult op(void *p){(void)p;++opens;position=0;return FX_OK;}
static FxResult next(void *p,FxModuleDirectoryEntry *out){(void)p;if(position==file_count)return FX_EMPTY;File *f=&files[position++];memset(out,0,sizeof(*out));memcpy(out->name,f->name,strlen(f->name));out->bytes=f->bytes;return FX_OK;}
static FxResult close_dir(void *p){(void)p;++closes;return close_fail?FX_CLOSE:FX_OK;}
static FxResult read_file(void *p,const char *name,uint8_t *out,uint32_t cap,uint32_t *n){(void)p;++reads;if(reads==io_fail_at_read){if(io_fail_cancels)cancelled_flag=1u;return FX_IO;}for(uint32_t i=0u;i<file_count;++i)if(!strcmp(name,files[i].name)){if(files[i].bytes>cap)return FX_BOUNDS;memcpy(out,files[i].data,files[i].bytes);*n=files[i].bytes;if(cancel_after_read || reads==cancel_at_read)cancelled_flag=1u;return FX_OK;}return FX_IO;}
static int cancel(void *p){(void)p;return cancelled_flag!=0u;}
static void *allocate(void *p,uint32_t n){(void)p;return malloc(n);}
static void release(void *p,void *v){(void)p;free(v);}
static FxModuleDirectory io={0,op,next,close_dir,read_file};static FxIndexMemory mem={0,allocate,release};
static FxFrozenModules *fresh(void){opens=reads=closes=close_fail=cancelled_flag=cancel_after_read=cancel_at_read=io_fail_at_read=io_fail_cancels=0u;FxFrozenModules *s=calloc(1,sizeof(*s));assert(s);s->cancelled=cancel;return s;}
static void snapshot(void){uint32_t an=bundle(a,"framing",0x55),bn=bundle(b,"log",0x55),ln=inner(legacy);files[0]=(File){"framing.wlm",a,an};files[1]=(File){"log.wlm",b,bn};files[2]=(File){"legacy.wlm",legacy,ln};files[3]=(File){"parked.wlm.disabled",0,0};file_count=4u;FxFrozenModules *s=fresh();CHECK(fx_wlm_frozen_scan(s,&io,stock,FX_SDK_CAPS,mem)==FX_OK);CHECK(reads==3u&&opens==1u&&closes==1u&&s->inventory.count==3u&&s->native_count==1u);CHECK(!fx_wlm_frozen_inventory(s));const uint8_t *front=s->inventory.entries[0].frozen_frontend;uint8_t hash[32];fx_sha256(front,156u,hash);CHECK(!memcmp(hash,s->inventory.entries[0].digest,32u));memset(a,0,an);memset(b,0,bn);CHECK(front[152u]==0xc0u);CHECK(fx_wlm_frozen_seal(s)==FX_OK);CHECK(fx_wlm_frozen_inventory(s)->count==3u&&s->native_views[0].data==0);CHECK(front[152u]==0xc0u);CHECK(fx_wlm_frozen_scan(s,&io,stock,FX_SDK_CAPS,mem)==FX_STATE);CHECK(reads==3u);CHECK(fx_wlm_frozen_seal(s)==FX_STATE);
    an=bundle(a,"framing",0x55);bn=bundle(b,"log",0x66);files[0]=(File){"framing.wlm",a,an};files[1]=(File){"log.wlm",b,bn};file_count=2u;s=fresh();CHECK(fx_wlm_frozen_scan(s,&io,stock,FX_SDK_CAPS,mem)==FX_INTEGRITY);CHECK(!fx_wlm_frozen_inventory(s)&&fx_wlm_frozen_seal(s)==FX_STATE);
    files[1]=(File){"framing.wlm.disabled",0,0};s=fresh();CHECK(fx_wlm_frozen_scan(s,&io,stock,FX_SDK_CAPS,mem)==FX_INTEGRITY);CHECK(reads==1u&&closes==1u);
    file_count=1u;s=fresh();close_fail=1u;cancel_after_read=1u;CHECK(fx_wlm_frozen_scan(s,&io,stock,FX_SDK_CAPS,mem)==FX_CLOSE);CHECK(!s->prepared&&!s->sealed&&s->retained);CHECK(fx_wlm_frozen_scan(s,&io,stock,FX_SDK_CAPS,mem)==FX_STATE);
    s=fresh();CHECK(fx_wlm_frozen_scan(s,&io,stock,FX_SDK_CAPS,mem)==FX_OK);((uint8_t *)s->inventory.entries[0].frozen_frontend)[152u]^=1u;CHECK(fx_wlm_frozen_seal(s)==FX_INTEGRITY);CHECK(!fx_wlm_frozen_inventory(s));}

/* A bounded allocator exercises the actual cold scanner's ownership, with
 * five independent outers carrying the same large common component. Its
 * requested-byte peak is evidence about this fixture, not the camera heap. */
typedef union {max_align_t alignment;size_t bytes;} Allocation;
static size_t live_bytes,peak_bytes;static uint32_t frees;
static void *bounded_allocate(void *context,uint32_t n){(void)context;if((size_t)n+live_bytes>7u*1024u*1024u)return 0;Allocation *p=malloc(sizeof(*p)+n);if(!p)return 0;p->bytes=n;live_bytes+=n;if(live_bytes>peak_bytes)peak_bytes=live_bytes;return p+1;}
static void bounded_release(void *context,void *v){(void)context;assert(v);Allocation *p=(Allocation *)v-1;assert(live_bytes>=p->bytes);live_bytes-=p->bytes;memset(v,0xdd,p->bytes);++frees;free(p);}
static void shared_ownership(void){
    static const char *names[5]={"framing.wlm","prores.wlm","h265.wlm","log.wlm","photo.wlm"};
    static const char *ids[5]={"framing","prores","h265","log","photo"};
    const uint32_t component_bytes=3u*1024u*1024u,total=412u+component_bytes;uint8_t *outers[5];
    for(uint32_t i=0u;i<5u;++i){outers[i]=calloc(1,total);assert(outers[i]);bundle(outers[i],ids[i],0x55u);put(outers[i]+88u,total);put(outers[i]+220u,component_bytes);put(outers[i]+412u+56u,component_bytes);fx_sha256(outers[i]+412u,component_bytes,outers[i]+224u);hash_body(outers[i],total);files[i]=(File){names[i],outers[i],total};}
    file_count=5u;FxFrozenModules *s=fresh();FxIndexMemory bounded={0,bounded_allocate,bounded_release};
    CHECK(fx_wlm_frozen_scan(s,&io,stock,FX_SDK_CAPS,bounded)==FX_OK);
    CHECK(s->prepared&&s->inventory.count==5u&&s->native_count==1u&&reads==5u&&closes==1u);
    CHECK(peak_bytes<7u*1024u*1024u&&live_bytes<4u*1024u*1024u);
    CHECK(s->native_views[0].data&&s->native_views[0].bytes==component_bytes&&s->native_views[0].data[100u]==0x55u);
    for(uint32_t i=0u;i<5u;++i){const FxFrozenPackage *f=&((const FxFrozenPackage *)s->packages.records)[i];CHECK(!f->package&&!f->bundle&&f->package_bytes==total&&f->frontend_bytes==156u);memset(outers[i],0,total);free(outers[i]);}
    CHECK(s->native_views[0].data[100u]==0x55u);
    uint32_t before=s->bytes,old_frees=frees;uint8_t digest[32];memcpy(digest,s->native_sha256[0],32u);
    fx_wlm_frozen_release_native(s);
    CHECK(!s->native_views[0].data&&s->bytes==before-component_bytes&&frees==old_frees+1u);
    CHECK(s->native_count==1u&&!memcmp(digest,s->native_sha256[0],32u)&&s->native_views[0].bytes==component_bytes);
    fx_wlm_frozen_release_native(s);CHECK(frees==old_frees+1u);
    CHECK(fx_wlm_frozen_seal(s)==FX_OK&&frees==old_frees+1u);
    CHECK(fx_wlm_frozen_inventory(s)->count==5u&&s->inventory.entries[4].frozen_frontend[152u]==0xc0u&&reads==5u);
    printf("requested allocator peak=%zu bytes; five 3MiB-component outers; remaining=%zu bytes\n",peak_bytes,live_bytes);
}
/* A cancelled scan continues with the same memory: completed packages are
 * kept and skipped, the interrupted outer was returned, and the result holds
 * exactly what one uninterrupted scan holds. IO lost to the cancelling
 * shutdown is an interruption; a real error, a close failure or another
 * allocator stays terminal. Seal no longer observes cancellation. */
static void continuation(void){
    uint32_t an=bundle(a,"framing",0x55),bn=bundle(b,"log",0x55),ln=inner(legacy);
    files[0]=(File){"framing.wlm",a,an};files[1]=(File){"log.wlm",b,bn};files[2]=(File){"legacy.wlm",legacy,ln};file_count=3u;
    FxIndexMemory bounded={0,bounded_allocate,bounded_release};size_t base=live_bytes;
    FxFrozenModules *whole=fresh();CHECK(fx_wlm_frozen_scan(whole,&io,stock,FX_SDK_CAPS,bounded)==FX_OK&&reads==3u);
    size_t complete=live_bytes-base;uint32_t whole_bytes=whole->bytes;
    FxFrozenModules *s=fresh();cancel_at_read=2u;base=live_bytes;
    CHECK(fx_wlm_frozen_scan(s,&io,stock,FX_SDK_CAPS,bounded)==FX_INTERRUPTED);
    CHECK(reads==2u&&closes==1u&&s->error==FX_INTERRUPTED&&!s->prepared&&s->inventory.count==1u&&s->native_count==1u&&s->bytes==156u+160u);
    const uint8_t *kept=s->inventory.entries[0].frozen_frontend;cancelled_flag=0u;cancel_at_read=0u;
    CHECK(fx_wlm_frozen_scan(s,&io,stock,FX_SDK_CAPS,mem)==FX_STATE&&s->error==FX_INTERRUPTED);
    CHECK(fx_wlm_frozen_scan(s,&io,stock,FX_SDK_CAPS,bounded)==FX_OK);
    CHECK(reads==4u&&opens==2u&&closes==2u&&s->prepared&&!s->error&&!s->retained&&s->inventory.count==3u&&s->native_count==1u);
    CHECK(s->inventory.entries[0].frozen_frontend==kept&&live_bytes-base==complete&&s->bytes==whole_bytes);
    CHECK(fx_wlm_frozen_scan(s,&io,stock,FX_SDK_CAPS,bounded)==FX_STATE&&reads==4u);
    cancelled_flag=1u;CHECK(fx_wlm_frozen_seal(s)==FX_OK&&fx_wlm_frozen_inventory(s)->count==3u);cancelled_flag=0u;
    s=fresh();io_fail_at_read=2u;io_fail_cancels=1u;CHECK(fx_wlm_frozen_scan(s,&io,stock,FX_SDK_CAPS,mem)==FX_INTERRUPTED);
    io_fail_at_read=0u;cancelled_flag=0u;CHECK(fx_wlm_frozen_scan(s,&io,stock,FX_SDK_CAPS,mem)==FX_OK&&s->inventory.count==3u&&reads==4u);
    s=fresh();io_fail_at_read=2u;CHECK(fx_wlm_frozen_scan(s,&io,stock,FX_SDK_CAPS,mem)==FX_IO);
    io_fail_at_read=0u;CHECK(fx_wlm_frozen_scan(s,&io,stock,FX_SDK_CAPS,mem)==FX_STATE);
    s=fresh();close_fail=1u;cancel_at_read=1u;CHECK(fx_wlm_frozen_scan(s,&io,stock,FX_SDK_CAPS,mem)==FX_CLOSE);
    close_fail=0u;cancelled_flag=0u;cancel_at_read=0u;CHECK(fx_wlm_frozen_scan(s,&io,stock,FX_SDK_CAPS,mem)==FX_STATE);
}
int main(void){memset(stock,0xa5,32u);parser();canonical();snapshot();continuation();shared_ownership();printf("PASS: %u checks; explicit v4 hashes/bounds, recursive reject, duplicate component consistency, copied cold frontend, close/cancel terminal and no rediscovery; cancelled-scan continuation without reallocation\n",checks);return 0;}
