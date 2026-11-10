/* SPDX-License-Identifier: GPL-3.0-only */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <malloc.h>
#include "module_stage.h"
#ifndef _WIN32
#define _aligned_malloc(n,a) aligned_alloc((a),(n))
#define _aligned_free(p) free(p)
#endif
static const uint8_t stock[32]=FX_Z8_APPLICATION_IDENTITY;
static void put(uint8_t *p,uint32_t n){for(uint32_t i=0;i<4u;++i)p[i]=(uint8_t)(n>>(8u*i));}
static uint8_t front[156],copy[156],scratch[157],sha[32];
static const char logical[48]="FENESTRA/framing.wlm";
static void package(void){memset(front,0,sizeof(front));memcpy(front,"FENESTRA",8);put(front+8,2);put(front+12,128);put(front+16,1);put(front+20,1);memcpy(front+24,stock,32);put(front+88,156);put(front+92,4096);put(front+100,1);put(front+116,1);put(front+132,152);put(front+136,4);put(front+140,4096);put(front+144,5);put(front+148,4096);put(front+152,0xd65f03c0);fx_sha256(front+128,28,front+56);fx_sha256(front,sizeof(front),sha);memcpy(copy,front,sizeof(front));}
int main(void){package();uint8_t *image=_aligned_malloc(4096,4096);assert(image);FxZ8ModuleStage s={0};
    memset(front,0,sizeof(front));assert(fx_z8_module_stage_frozen(&s,logical,copy,156,sha,0,scratch,156,image,4096,1)==FX_OK);assert(s.attempted&&s.loader.module.prepared&&s.loader.card.verified&&s.loader.runtime.phase==FX_PREPARED);assert(image[0]==0xc0&&image[1]==3&&image[2]==0x5f&&image[3]==0xd6);assert(!s.file.opened&&!s.file.buffer);assert(fx_z8_module_stage_frozen(&s,logical,copy,156,sha,0,scratch,156,image,4096,2)==FX_BUSY);
    FxZ8ModuleStage bad={0};copy[152]^=1;assert(fx_z8_module_stage_frozen(&bad,logical,copy,156,sha,0,scratch,156,image,4096,1)==FX_INTEGRITY);assert(!bad.loader.module.prepared&&!bad.loader.card.verified);_aligned_free(image);puts("PASS: actual frozen Z8 stage -> full digest/target -> loader prepare; replaced card irrelevant, no file IO, corruption refused");return 0;}

/* Frozen staging must not consult the physical-volume selector. */
char fx_z8_card_drive(void){assert(0 && "physical card path reached");return 0;}
uint32_t fx_z8_file_read(int32_t fd,void *out,uint32_t bytes,uint32_t *done){(void)fd;(void)out;(void)bytes;(void)done;assert(0 && "native card read reached");return 1u;}
FxResult fx_z8_card_files(FxTextFiles *files,FxZ8CardScope *scope){(void)files;(void)scope;assert(0 && "native card files reached");return FX_CAPABILITY;}
