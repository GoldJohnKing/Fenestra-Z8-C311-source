/* SPDX-License-Identifier: GPL-3.0-only */
/* Cross-language FNC parser/transaction integration, sparse synthetic RAM.
 * This never executes a package entry or implements a hardware MMU. */
#define _CRT_SECURE_NO_WARNINGS 1
#include "fenestra_capsule.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef struct {FxCapsuleRecord record;uint8_t *data;} Window;
typedef struct {Window *windows;uint32_t count,applied,stage,published,leave;uint64_t entry;} Fixture;
static FxResult read_memory(void *p,uint64_t address,void *out,uint32_t bytes) {
 Fixture *f=p;
 for(uint32_t i=0u;i<f->count;++i){Window *w=&f->windows[i];uint64_t off=address-w->record.address;
  if(address>=w->record.address && off<=w->record.bytes && bytes<=w->record.bytes-off){memcpy(out,w->data+(size_t)off,bytes);return FX_OK;}}
 return FX_BOUNDS;
}
static FxResult admit(void *p,const FxCapsuleHeader *h,uint32_t i,const FxCapsuleRecord *r){Fixture *f=p;(void)h;return i<f->count && !memcmp(r,&f->windows[i].record,sizeof(*r))?FX_OK:FX_INTEGRITY;}
static FxResult enter(void *p,const FxCapsuleHeader *h,const uint8_t *packet,uint64_t *lease){(void)p;(void)h;(void)packet;*lease=7u;return FX_OK;}
static FxResult apply(void *p,uint64_t lease,const FxCapsuleRecord *r,const uint8_t *data,uint32_t rollback){Fixture *f=p;if(lease!=7u || rollback)return FX_STATE;
 for(uint32_t i=0u;i<f->count;++i)if(!memcmp(r,&f->windows[i].record,sizeof(*r))){memcpy(f->windows[i].data,data,r->bytes);++f->applied;return FX_OK;}return FX_BOUNDS;}
static FxResult leave(void *p,uint64_t lease,uint32_t outcome){Fixture *f=p;if(lease!=7u || outcome!=FX_CAPSULE_LEAVE_COMMIT || f->applied!=f->count)return FX_STATE;++f->leave;return FX_OK;}
static FxResult stage(void *p,uint64_t lease,uint64_t entry){Fixture *f=p;if(lease!=7u || !entry)return FX_STATE;
 for(uint32_t i=0u;i<f->count;++i)if(f->windows[i].record.kind==FX_CAPSULE_IMAGE && i>=f->applied)return FX_STATE;
 ++f->stage;f->entry=entry;return FX_OK;}
static FxResult abort_entry(void *p,uint64_t lease,uint64_t entry){(void)p;(void)lease;(void)entry;return FX_STATE;}
static void publish(void *p,uint64_t entry){Fixture *f=p;if(f->leave!=1u || f->stage!=1u || entry!=f->entry)abort();++f->published;}
int main(int argc,char **argv){if(argc!=2)return 2;FILE *file=fopen(argv[1],"rb");if(!file)return 3;
 if(fseek(file,0,SEEK_END))return 4;long length=ftell(file);if(length<=0 || (unsigned long)length>FX_CAPSULE_MAX_PACKAGE)return 5;rewind(file);
 uint32_t bytes=(uint32_t)length;uint8_t *packet=malloc(bytes);if(!packet)return 6;if(fread(packet,1u,bytes,file)!=bytes)return 7;fclose(file);
 if(bytes<sizeof(FxCapsuleHeader))return 8;FxCapsuleHeader h;memcpy(&h,packet,sizeof(h));if(h.record_count>FX_CAPSULE_MAX_RECORDS || h.records_offset>bytes || h.record_count>(bytes-h.records_offset)/sizeof(FxCapsuleRecord))return 9;
 Fixture f={0};f.count=h.record_count;f.windows=calloc(f.count,sizeof(*f.windows));if(!f.windows)return 10;
 for(uint32_t i=0u;i<f.count;++i){Window *w=&f.windows[i];memcpy(&w->record,packet+h.records_offset+(size_t)i*sizeof(FxCapsuleRecord),sizeof(FxCapsuleRecord));
  if(w->record.old_offset>bytes || w->record.bytes>bytes-w->record.old_offset)return 11;w->data=malloc(w->record.bytes);if(!w->data)return 12;memcpy(w->data,packet+w->record.old_offset,w->record.bytes);}
 uint8_t hash[32];fx_sha256(packet,bytes,hash);FxCapsuleControl control={0};FxCapsuleIO io={&f,read_memory,admit,enter,apply,leave,stage,abort_entry,publish,0};
 FxResult result=fx_capsule_init(&control,h.target_sha256,h.requires_id,io);if(result==FX_OK)result=fx_capsule_prepare(&control,packet,bytes,hash);if(result==FX_OK)result=fx_capsule_commit(&control);
 FxCapsuleStatus status;FxResult queried=fx_capsule_query(&control,&status);
 if(result!=FX_OK || queried!=FX_OK || status.phase!=FX_CAPSULE_READY || f.applied!=f.count || f.published!=(h.entry?1u:0u)){fprintf(stderr,"failure result=%u phase=%u error=%u record=%u applied=%u/%u\n",(unsigned)result,status.phase,status.error,status.failed_record,f.applied,f.count);return 13;}
 for(uint32_t i=0u;i<f.count;++i)if(memcmp(f.windows[i].data,packet+f.windows[i].record.new_offset,f.windows[i].record.bytes))return 14;
 printf("FNC cross-language sparse fixture PASS: %u records, %u bytes, %u images, staged=%u, published=%u\n",f.count,bytes,status.image_records,f.stage,f.published);
 for(uint32_t i=0u;i<f.count;++i)free(f.windows[i].data);free(f.windows);free(packet);return 0;}
