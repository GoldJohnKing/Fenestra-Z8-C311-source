/* Actual native manager IO + manager + v4 inspector. All Nikon IO is synthetic. */
#define _CRT_SECURE_NO_WARNINGS
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "fenestra_wlm_bundle.h"
#include "../src/native_modules.c"
static uint32_t checks,opens,reads,closes,renames,position,at,eof_reads,max_room;
static uint32_t short_limit,read_error,close_error,oversized_done,resident,revision;
static int handle,eof_handle;
static char disk_name[32],module_id[16]="prores";
static uint8_t *disk_data;static uint32_t disk_bytes;static uint8_t stock[32];
static FxUiControl row;
#define CHECK(x) do{++checks;assert(x);}while(0)
static void put32(uint8_t *p,uint32_t n){for(uint32_t i=0u;i<4u;++i)p[i]=(uint8_t)(n>>(8u*i));}
static void reset_io(void){opens=reads=closes=renames=position=at=eof_reads=max_room=0u;short_limit=read_error=close_error=oversized_done=0u;handle=0;}
static const char *file_part(const char *path){CHECK(!strncmp(path,"B:\\FENESTRA\\",12u));return path+12u;}
char fx_z8_card_drive(void){return 'B';}
static int32_t fs_open(const char *path,uint32_t mode,uint32_t flags){CHECK(mode==0u&&flags==0u);++opens;if(strcmp(file_part(path),disk_name))return (int32_t)UINT32_C(0x80000010);CHECK(!handle);handle=1;eof_handle=0;at=0u;return 7;}
static uint32_t fs_close(int32_t fd){CHECK(fd==7&&handle);++closes;if(!close_error)handle=0;return close_error;}
static uint32_t fs_read(int32_t fd,void *out,uint32_t n,uint32_t *done){CHECK(fd==7&&handle&&n&&n<=32768u);CHECK(!eof_handle);++reads;if(n>max_room)max_room=n;if(read_error){*done=0u;return read_error;}if(oversized_done){*done=n+1u;return 0u;}uint32_t take=disk_bytes-at;if(take>n)take=n;if(short_limit&&take>short_limit)take=short_limit;if(take){if(disk_data)memcpy(out,disk_data+at,take);else memset(out,0x5a,take);at+=take;}else {++eof_reads;eof_handle=1;}*done=take;return 0u;}
uint32_t fx_z8_file_read(int32_t fd,void *out,uint32_t n,uint32_t *done){return fs_read(fd,out,n,done);}
static uint32_t fs_rename(const char *from,const char *to){CHECK(!handle);CHECK(!strcmp(file_part(from),disk_name));const char *name=file_part(to);CHECK(strlen(name)<32u);memset(disk_name,0,sizeof(disk_name));memcpy(disk_name,name,strlen(name));++renames;return 0u;}
static uint32_t dir_open(const char *path,int32_t *fd){CHECK(!strcmp(path,"B:\\FENESTRA"));position=0u;*fd=99;return 0u;}
static uint32_t dir_next(int32_t fd,void *out){CHECK(fd==99);if(position++)return UINT32_C(0x80000030);uint8_t *p=out;memset(p,0,0x220u);for(uint32_t i=0u;disk_name[i];++i)p[14u+2u*i]=(uint8_t)disk_name[i];put32(p+0x218u,disk_bytes);return 0u;}
static uint32_t dir_close(int32_t fd){CHECK(fd==99);return 0u;}
typedef union {max_align_t alignment;uint32_t bytes;} TestAllocation;
static uint64_t allocation_live,allocation_origin,allocation_peak;
static uint32_t allocation_limit,allocation_budget,allocation_largest,allocation_denied;
static void *allocate_bytes(uint32_t n){
    if((allocation_limit && n>allocation_limit) ||
       (allocation_budget && allocation_live-allocation_origin+n>allocation_budget)){++allocation_denied;return 0;}
    TestAllocation *p=malloc(sizeof(*p)+n);if(!p)return 0;p->bytes=n;allocation_live+=n;
    if(n>allocation_largest)allocation_largest=n;
    uint64_t live=allocation_live-allocation_origin;if(live>allocation_peak)allocation_peak=live;
    return p+1;
}
static void release_bytes(void *memory){if(!memory)return;TestAllocation *p=(TestAllocation *)memory-1;CHECK(allocation_live>=p->bytes);allocation_live-=p->bytes;free(p);}
#ifdef FX_NATIVE_CAPSULES
static void allocation_guard(void){allocation_origin=allocation_live;allocation_peak=0u;allocation_largest=allocation_denied=0u;allocation_limit=65536u;allocation_budget=131072u;}
static void allocation_unguard(void){allocation_limit=allocation_budget=0u;allocation_origin=0u;}
#endif

uint32_t fx_native_module_loaded(const char *id){return resident&& !strcmp(id,module_id);}
FxResult fx_platform_init(FxPlatformOwner *o,const FxPlatform *p,uint32_t owner,uint32_t generation,uint32_t caps){(void)owner;(void)generation;(void)caps;memset(o,0,sizeof(*o));o->platform=p;return FX_OK;}
FxResult fx_platform_dispatch(FxPlatformOwner *o,const FxServiceRequest *q,FxServiceReply *reply){(void)o;memset(reply,0,sizeof(*reply));if(q->arg[0]==FX_UI_GET)return FX_EMPTY;if(q->arg[0]==FX_UI_PUT){const FxUiControl *c=(const void *)q->data;if(c->id==4u)row=*c;}reply->value[0]=++revision;return FX_OK;}
FxResult fx_ui_poll_message(FxPlatformOwner *o,void *out,uint32_t capacity,uint32_t *bytes){(void)o;(void)out;(void)capacity;*bytes=0u;return FX_EMPTY;}
const uintptr_t fx_native_ui_actions[16]={0},fx_native_ui_options[8]={0};
void fx_native_ui_refresh_owner(FxPlatformOwner *o){(void)o;assert(0 && "GUI refresh is outside this IO fixture");}
FxResult fx_native_ui_init(FxNativeUi *u,FxPlatformOwner *o,const FxNativeMenuProfile *p,void *(*a)(uint32_t),uint32_t page,uint32_t text,uint32_t rows,const uintptr_t actions[16],const uintptr_t options[8],const uintptr_t callbacks[5]){(void)u;(void)o;(void)p;(void)a;(void)page;(void)text;(void)rows;(void)actions;(void)options;(void)callbacks;assert(0 && "GUI init is outside this IO fixture");return FX_STATE;}
static FxNamedBinding bindings[7];static FxPlatform platform;
static void binding(uint32_t i,const char *name,uintptr_t address){bindings[i]=(FxNamedBinding){.name=name,.kind=FX_BIND_FUNCTION,.abi=FX_CALL_U64_8,.version=1u,.address=address};}
static FxNativeModules *manager(void){FxNativeModules *m=calloc(1u,sizeof(*m));CHECK(m);m->directory=-1;m->allocate_index=allocate_bytes;m->release_index=release_bytes;FxModuleManagerIO io={{m,open_directory,next_directory,close_directory,read_module},rename_module,m,current,{m,allocate_index,release_index},FX_MODULE_INDEX_BUDGET};memcpy(platform.module_identity,stock,32u);CHECK(fx_module_manager_init(&m->manager,&platform,&io,0)==FX_OK);
#ifdef FX_NATIVE_CAPSULES
    m->manager.inspect_package=inspect_package;
#endif
    return m;}
static void fixture_init(void){binding(0u,"camera.card.open",(uintptr_t)fs_open);binding(1u,"camera.card.read",(uintptr_t)fs_read);binding(2u,"camera.card.close",(uintptr_t)fs_close);binding(3u,"camera.card.rename",(uintptr_t)fs_rename);binding(4u,"camera.card.directory.open",(uintptr_t)dir_open);binding(5u,"camera.card.directory.next",(uintptr_t)dir_next);binding(6u,"camera.card.directory.close",(uintptr_t)dir_close);platform=(FxPlatform){.abi=1u,.count=7u,.bindings=bindings};memset(stock,0xa5,32u);strcpy(disk_name,"prores.wlm.disabled");}
static void reader_case(uint32_t n,FxResult expected,uint32_t expected_reads){reset_io();disk_data=0;disk_bytes=n;strcpy(disk_name,"prores.wlm.disabled");FxNativeModules *m=manager();uint8_t *out=malloc((size_t)n+2u);CHECK(out);memset(out,0xa7,(size_t)n+2u);uint32_t bytes=123u;CHECK(read_module(m,disk_name,out,n+1u,&bytes)==expected);CHECK(reads==expected_reads);CHECK(out[n+1u]==0xa7u);if(expected==FX_OK){CHECK(bytes==n&&at==n&&eof_reads==1u&&closes==1u&&!handle);CHECK(out[0u]==0x5au&&out[n-1u]==0x5au&&out[n]==0xa7u);CHECK(max_room<=32768u);}else CHECK(!opens&&!closes&&bytes==0u);free(out);fx_module_index_destroy(&m->manager.index);free(m);}
static void reader_boundaries(void){reader_case(1024u*1024u,FX_OK,33u);
#ifdef FX_NATIVE_CAPSULES
    reader_case(2u*1024u*1024u,FX_OK,65u);reader_case(2u*1024u*1024u+1u,FX_OK,66u);reader_case(FX_WLM_BUNDLE_LIMIT,FX_OK,513u);reader_case(FX_WLM_BUNDLE_LIMIT+1u,FX_ARGUMENT,0u);
#else
    reader_case(1024u*1024u+1u,FX_ARGUMENT,0u);reader_case(2u*1024u*1024u,FX_ARGUMENT,0u);
#endif
    reset_io();disk_bytes=1024u;disk_data=0;FxNativeModules *m=manager();uint8_t out[1025];uint32_t bytes=0u;short_limit=1u;CHECK(read_module(m,disk_name,out,sizeof(out),&bytes)==FX_IO);
#ifdef FX_NATIVE_CAPSULES
    CHECK(reads==576u&&bytes==576u);
#else
    CHECK(reads==64u&&bytes==64u);
#endif
    CHECK(closes==1u&&!m->poisoned&&!handle);reset_io();oversized_done=1u;CHECK(read_module(m,disk_name,out,sizeof(out),&bytes)==FX_IO&&closes==1u);reset_io();read_error=1u;close_error=1u;CHECK(read_module(m,disk_name,out,sizeof(out),&bytes)==FX_CLOSE&&m->poisoned);uint32_t old_reads=reads,old_closes=closes;CHECK(read_module(m,disk_name,out,sizeof(out),&bytes)==FX_CLOSE&&reads==old_reads&&closes==old_closes);fx_module_index_destroy(&m->manager.index);free(m);handle=0;}
#ifdef FX_NATIVE_CAPSULES
static uint8_t *make_bundle(uint32_t size){uint8_t *p=calloc(1u,size);CHECK(p&&size>572u);memcpy(p,"FENESTRA",8u);put32(p+8u,4u);put32(p+12u,192u);put32(p+16u,1u);put32(p+20u,1u);memcpy(p+24u,stock,32u);put32(p+88u,size);put32(p+96u,256u);put32(p+100u,156u);put32(p+136u,192u);put32(p+140u,1u);put32(p+144u,64u);put32(p+148u,1u);memcpy(p+152u,"prores",6u);memcpy(p+192u,"prores",6u);put32(p+208u,1u);put32(p+216u,412u);put32(p+220u,size-412u);uint8_t *f=p+256u;memcpy(f,"FENESTRA",8u);put32(f+8u,2u);put32(f+12u,128u);put32(f+16u,1u);put32(f+20u,1u);memcpy(f+24u,stock,32u);put32(f+88u,156u);put32(f+92u,4096u);put32(f+100u,1u);put32(f+108u,FX_SDK_QUERY);put32(f+116u,1u);put32(f+132u,152u);put32(f+136u,4u);put32(f+140u,4096u);put32(f+144u,5u);put32(f+148u,4096u);put32(f+152u,0xd65f03c0u);fx_sha256(f+128u,28u,f+56u);fx_sha256(f,156u,p+104u);uint8_t *native=p+412u;memcpy(native,"WLMNAT1\0",8u);put32(native+8u,1u);put32(native+12u,160u);memcpy(native+16u,"prores",6u);put32(native+32u,1u);put32(native+36u,2u);put32(native+56u,size-412u);fx_sha256(native,size-412u,p+224u);fx_sha256(p+192u,size-192u,p+56u);return p;}
static void disk_setup(uint8_t *data,uint32_t n,int enabled){reset_io();disk_data=data;disk_bytes=n;memset(disk_name,0,sizeof(disk_name));memcpy(disk_name,module_id,strlen(module_id));strcat(disk_name,enabled?".wlm":".wlm.disabled");}
static void stream_reject(FxNativeModules *m,uint8_t *data,uint32_t n){
    FxWlmBundle whole;CHECK(fx_wlm_bundle_inspect(data,n,module_id,stock,FX_SDK_CAPS,&whole)!=FX_OK);
    disk_setup(data,n,1);FxModule out;uint8_t digest[32];
    CHECK(inspect_package(m,disk_name,n,stock,FX_SDK_CAPS,&out,digest)!=FX_OK);CHECK(!handle&&!renames&&closes==1u);
}
static void stream_equivalence(uint8_t *data,uint32_t n){
    memcpy(stock,data+24u,32u);memcpy(module_id,data+152u,16u);uint8_t *mut=malloc((size_t)n+1u);CHECK(mut);
    allocation_guard();FxNativeModules *m=manager();FxWlmBundle original;CHECK(fx_wlm_bundle_inspect(data,n,module_id,stock,FX_SDK_CAPS,&original)==FX_OK);
    disk_setup(data,n,1);FxModule out;uint8_t digest[32],full[32];fx_sha256(data,n,full);
    CHECK(inspect_package(m,disk_name,n,stock,FX_SDK_CAPS,&out,digest)==FX_OK);
    CHECK(!memcmp(&out,&original.frontend,sizeof(out))&&!memcmp(digest,full,32u)&&eof_reads==1u&&!handle);
    const uint32_t header_fields[]={12u,16u,20u,24u,56u,88u,92u,96u,100u,104u,136u,140u,144u,148u,152u,168u};
    for(uint32_t i=0u;i<sizeof(header_fields)/sizeof(header_fields[0]);++i){memcpy(mut,data,n);mut[header_fields[i]]^=1u;stream_reject(m,mut,n);}
    const uint32_t record_fields[]={0u,16u,20u,24u,28u,32u};
    for(uint32_t i=0u;i<sizeof(record_fields)/sizeof(record_fields[0]);++i){memcpy(mut,data,n);uint32_t record_at=FX_WLM_BUNDLE_HEADER+record_fields[i];
        if(record_fields[i]==0u)mut[record_at]='!';else if(record_fields[i]==16u)put32(mut+record_at,0u);else if(record_fields[i]==20u)put32(mut+record_at,2u);else mut[record_at]^=1u;
        fx_sha256(mut+FX_WLM_BUNDLE_HEADER,n-FX_WLM_BUNDLE_HEADER,mut+56u);stream_reject(m,mut,n);}
    if(original.component_count>1u){memcpy(mut,data,n);memcpy(mut+FX_WLM_BUNDLE_HEADER+FX_WLM_COMPONENT_BYTES,mut+FX_WLM_BUNDLE_HEADER,16u);
        fx_sha256(mut+FX_WLM_BUNDLE_HEADER,n-FX_WLM_BUNDLE_HEADER,mut+56u);stream_reject(m,mut,n);}
    const uint32_t native_fields[]={8u,12u,16u,32u,36u,56u,60u};
    for(uint32_t i=0u;i<sizeof(native_fields)/sizeof(native_fields[0]);++i){memcpy(mut,data,n);const FxWlmComponent *v=&original.components[0];
        if(native_fields[i]==36u)put32(mut+v->offset+36u,data[v->offset+36u]?0u:1u);else mut[v->offset+native_fields[i]]^=1u;fx_sha256(mut+v->offset,v->bytes,mut+FX_WLM_BUNDLE_HEADER+32u);
        fx_sha256(mut+FX_WLM_BUNDLE_HEADER,n-FX_WLM_BUNDLE_HEADER,mut+56u);stream_reject(m,mut,n);}
    memcpy(mut,data,n);mut[n-1u]^=1u;fx_sha256(mut+FX_WLM_BUNDLE_HEADER,n-FX_WLM_BUNDLE_HEADER,mut+56u);stream_reject(m,mut,n);
    memcpy(mut,data,n);uint32_t f=original.frontend_offset;put32(mut+f+16u,0u);fx_sha256(mut+f,original.frontend_bytes,mut+104u);
    fx_sha256(mut+FX_WLM_BUNDLE_HEADER,n-FX_WLM_BUNDLE_HEADER,mut+56u);stream_reject(m,mut,n);
    /* EOF is mandatory even when every declared byte and checksum is valid. */
    disk_setup(data,n-1u,1);CHECK(inspect_package(m,disk_name,n,stock,FX_SDK_CAPS,&out,digest)==FX_INTEGRITY&&!handle);
    memcpy(mut,data,n);mut[n]=0xa7u;disk_setup(mut,n+1u,1);CHECK(inspect_package(m,disk_name,n,stock,FX_SDK_CAPS,&out,digest)==FX_INTEGRITY&&!handle&&eof_reads==0u);
    disk_setup(data,n,1);oversized_done=1u;CHECK(inspect_package(m,disk_name,n,stock,FX_SDK_CAPS,&out,digest)==FX_IO&&!handle);
    disk_setup(data,n,1);short_limit=1u;CHECK(inspect_package(m,disk_name,n,stock,FX_SDK_CAPS,&out,digest)==FX_IO&&!handle);
    /* The same stream adapter keeps ordinary service frontend semantics. */
    const uint8_t *front=data+original.frontend_offset;uint32_t front_bytes=original.frontend_bytes;
    disk_setup((uint8_t *)front,front_bytes,1);CHECK(inspect_package(m,disk_name,front_bytes,stock,FX_SDK_CAPS,&out,digest)==FX_OK);
    fx_sha256(front,front_bytes,full);CHECK(!memcmp(&out,&original.frontend,sizeof(out))&&!memcmp(digest,full,32u)&&eof_reads==1u&&!handle);
    CHECK(allocation_peak<=131072u&&allocation_largest<=65536u&&!allocation_denied);
    printf("stream equivalence %s bytes=%u mutations/EOF/shortIO/legacy max_alloc=%u peak=%llu checks=%u\n",module_id,n,allocation_largest,(unsigned long long)allocation_peak,checks);
    allocation_unguard();fx_module_index_destroy(&m->manager.index);free(m);free(mut);reset_io();
}
static void bounded_manager_preflight(uint8_t *data,uint32_t n){
    memcpy(stock,data+24u,32u);memcpy(module_id,data+152u,16u);resident=1u;disk_setup(data,n,1);
    allocation_guard();FxNativeModules *m=manager();m->manager.inspect_package=0;
    CHECK(fx_module_manager_scan(&m->manager)==FX_OK);FxManagedModule *e=&m->manager.entries[0];
    CHECK(e->present&&e->enabled&&e->current&&!e->valid&&e->error==FX_BUDGET);
    CHECK(allocation_denied==1u&&!reads&&!handle&&!renames&&!strstr(row.label,"invalid")&&!strcmp(row.text,"Not enough memory"));
    m->manager.inspect_package=inspect_package;reset_io();
    CHECK(fx_module_manager_scan(&m->manager)==FX_OK);e=&m->manager.entries[0];
    CHECK(e->enabled&&e->current&&e->valid&&!e->error&&eof_reads==1u&&!handle);
    uint8_t digest[32];fx_sha256(data,n,digest);CHECK(!memcmp(digest,e->digest,32u));
    data[n-1u]^=1u;reset_io();CHECK(fx_module_manager_scan(&m->manager)==FX_OK);e=&m->manager.entries[0];
    CHECK(e->enabled&&e->current&&!e->valid&&e->error==FX_INTEGRITY&&strstr(row.label,"invalid"));
    data[n-1u]^=1u;reset_io();CHECK(fx_module_manager_scan(&m->manager)==FX_OK);
    CHECK(fx_module_manager_enable(&m->manager,0u,0u)==FX_OK&&m->manager.entries[0].current);
    reset_io();CHECK(fx_module_manager_scan(&m->manager)==FX_OK);data[n-1u]^=1u;
    CHECK(fx_module_manager_enable(&m->manager,0u,1u)==FX_INTEGRITY&&!renames&&!m->manager.entries[0].enabled);
    data[n-1u]^=1u;reset_io();CHECK(fx_module_manager_scan(&m->manager)==FX_OK);
    CHECK(fx_module_manager_enable(&m->manager,0u,1u)==FX_OK&&m->manager.entries[0].enabled);
    reset_io();read_error=1u;CHECK(fx_module_manager_scan(&m->manager)==FX_OK);e=&m->manager.entries[0];
    CHECK(e->enabled&&e->current&&e->error==FX_IO&&!strstr(row.label,"invalid")&&!strcmp(row.text,"Read error")&&!handle);
    reset_io();short_limit=4093u;CHECK(fx_module_manager_scan(&m->manager)==FX_OK);e=&m->manager.entries[0];
    CHECK(e->valid&&!e->error&&eof_reads==1u&&!handle&&!memcmp(digest,e->digest,32u));
    CHECK(allocation_peak<=131072u&&allocation_largest<=65536u&&allocation_denied==1u);
    printf("bounded manager %s bytes=%u max_alloc=%u peak=%llu old_outer_denied=%u checks=%u\n",module_id,n,allocation_largest,(unsigned long long)allocation_peak,allocation_denied,checks);
    allocation_unguard();fx_module_index_destroy(&m->manager.index);free(m);reset_io();
}
static void bundle_roundtrip(uint8_t *data,uint32_t n){memcpy(stock,data+24u,32u);memcpy(module_id,data+152u,16u);resident=0u;disk_setup(data,n,0);FxNativeModules *m=manager();CHECK(fx_module_manager_scan(&m->manager)==FX_OK);CHECK(m->manager.count==1u&&reads==0u);FxManagedModule *e=&m->manager.entries[0];CHECK(!e->enabled&&!e->current&&!e->valid&&!e->error&&e->bytes==n);CHECK(fx_module_manager_enable(&m->manager,0u,1u)==FX_OK);CHECK(e->enabled&&e->valid&&!e->current&&!e->error&&renames==1u);CHECK(e->bytes==n&&e->image_bytes&&e->image_bytes<=FX_NATIVE_MODULE_IMAGE_LIMIT);uint8_t sha[32];fx_sha256(data,n,sha);CHECK(!memcmp(sha,e->digest,32u));CHECK(!strstr(row.label,"invalid")&&!strcmp(row.text,"After restart"));CHECK(reads>0u&&reads<=(n+4095u)/4096u+128u&&eof_reads==1u&&!handle);fx_module_manager_shutdown(&m->manager);CHECK(fx_module_manager_resume(&m->manager)==FX_OK);reset_io();CHECK(fx_module_manager_scan(&m->manager)==FX_OK);e=&m->manager.entries[0];CHECK(e->enabled&&!e->current&&e->valid);uint32_t old_renames=renames;CHECK(fx_module_manager_freeze(&m->manager)==FX_OK);CHECK(fx_module_manager_enable(&m->manager,0u,0u)==FX_BUSY&&renames==old_renames);fx_module_manager_ready(&m->manager);CHECK(!m->manager.loading&&!e->current);
    /* A new cold snapshot owns its frontend. Later manager renames cannot
     * rebuild or alter that frozen selection in the current boot. */
    FxFrozenModules *frozen=calloc(1u,sizeof(*frozen));CHECK(frozen);FxModuleDirectory io={m,open_directory,next_directory,close_directory,read_module};CHECK(fx_wlm_frozen_scan(frozen,&io,stock,FX_SDK_CAPS,(FxIndexMemory){m,allocate_index,release_index})==FX_OK);CHECK(fx_wlm_frozen_seal(frozen)==FX_OK&&fx_wlm_frozen_inventory(frozen)->count==1u);const uint8_t *front=frozen->inventory.entries[0].frozen_frontend;uint8_t front_hash[32];fx_sha256(front,frozen->inventory.entries[0].bytes,front_hash);resident=1u;CHECK(fx_module_manager_freeze(&m->manager)==FX_OK);fx_module_manager_ready(&m->manager);CHECK(e->current==1u);reset_io();CHECK(fx_module_manager_enable(&m->manager,0u,0u)==FX_OK&&e->current==1u&&!e->enabled&&reads==0u);CHECK(fx_wlm_frozen_inventory(frozen)->count==1u&&frozen->inventory.entries[0].frozen_frontend==front);fx_sha256(front,frozen->inventory.entries[0].bytes,sha);CHECK(!memcmp(sha,front_hash,32u));printf("manager v4 bytes=%u image=%u checks=%u\n",n,e->image_bytes,checks);}
static void bad_bundle(void){uint32_t n=2u*1024u*1024u;memset(stock,0xa5,32u);strcpy(module_id,"prores");uint8_t *data=make_bundle(n);resident=0u;disk_setup(data,n,0);data[n-1u]^=1u;FxNativeModules *m=manager();CHECK(fx_module_manager_scan(&m->manager)==FX_OK&&reads==0u);CHECK(fx_module_manager_enable(&m->manager,0u,1u)==FX_INTEGRITY);CHECK(!renames&&!m->manager.entries[0].enabled&&m->manager.entries[0].error==FX_INTEGRITY&&strstr(row.label,"invalid"));data[n-1u]^=1u;CHECK(fx_module_manager_scan(&m->manager)==FX_OK);data[152u]='x';CHECK(fx_module_manager_enable(&m->manager,0u,1u)==FX_INTEGRITY&&!renames);data[152u]='p';CHECK(fx_module_manager_scan(&m->manager)==FX_OK);data[24u]^=1u;CHECK(fx_module_manager_enable(&m->manager,0u,1u)==FX_CAPABILITY&&!renames);data[24u]^=1u;CHECK(fx_module_manager_scan(&m->manager)==FX_OK);close_error=1u;CHECK(fx_module_manager_enable(&m->manager,0u,1u)==FX_CLOSE&&m->manager.uncertain&&m->poisoned&&!renames);CHECK(fx_module_manager_enable(&m->manager,0u,0u)==FX_CLOSE&&!renames);free(data);handle=0;
    data=make_bundle(n);disk_setup(data,n,1);m=manager();data[n-1u]^=1u;CHECK(fx_module_manager_scan(&m->manager)==FX_OK);CHECK(m->manager.entries[0].enabled&&m->manager.entries[0].error==FX_INTEGRITY);reset_io();CHECK(fx_module_manager_enable(&m->manager,0u,0u)==FX_OK&&renames==1u&&reads==0u);free(data);}
#endif
int main(int argc,char **argv){fixture_init();reader_boundaries();
#ifdef FX_NATIVE_CAPSULES
    uint8_t *data=make_bundle(2u*1024u*1024u);stream_equivalence(data,2u*1024u*1024u);bounded_manager_preflight(data,2u*1024u*1024u);bundle_roundtrip(data,2u*1024u*1024u);free(data);bad_bundle();
    for(int i=1;i<argc;++i){FILE *file=fopen(argv[i],"rb");CHECK(file);CHECK(!fseek(file,0,SEEK_END));long length=ftell(file);CHECK(length>128&&length<=(long)FX_WLM_BUNDLE_LIMIT);rewind(file);data=malloc((size_t)length);CHECK(data);CHECK(fread(data,1u,(size_t)length,file)==(size_t)length);CHECK(!fclose(file));stream_equivalence(data,(uint32_t)length);bounded_manager_preflight(data,(uint32_t)length);bundle_roundtrip(data,(uint32_t)length);free(data);}
#else
    (void)argc;(void)argv;
#endif
    printf("PASS: %u checks; real native manager reader bounds/EOF/shortIO/close and v4 preflight, rename, current/freeze/resume\n",checks);return 0;}
