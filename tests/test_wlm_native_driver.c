#define _CRT_SECURE_NO_WARNINGS
/* SPDX-License-Identifier: GPL-3.0-only */
#include "fenestra_wlm_native.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static uint32_t calls,fail_at,live;static size_t current,peak;
static void *alloc(void *c,uint32_t n){(void)c;if(++calls==fail_at)return 0;size_t *p=malloc(sizeof(size_t)+n);if(!p)return 0;*p=n;current+=n;if(current>peak)peak=current;++live;return p+1;}
static void dealloc(void *c,void *v){(void)c;size_t *p=(size_t *)v-1;current-=*p;--live;free(p);}
int main(int argc,char **argv){
 if(argc<5||argc>37)return 2;fail_at=(uint32_t)strtoul(argv[1],0,0);
 uint8_t target[32];for(uint32_t i=0;i<32u;++i){char b[3]={argv[3][i*2u],argv[3][i*2u+1u],0};target[i]=(uint8_t)strtoul(b,0,16);}
 uint64_t required=strtoull(argv[4],0,16);FxWlmNativeView views[32];memset(views,0,sizeof(views));
 for(int i=5;i<argc;++i){FILE *f=fopen(argv[i],"rb");if(!f)return 3;fseek(f,0,SEEK_END);long n=ftell(f);rewind(f);uint8_t *p=malloc((size_t)n);if(!p||fread(p,1,(size_t)n,f)!=(size_t)n)return 4;fclose(f);views[i-5].data=p;views[i-5].bytes=(uint32_t)n;if(n>=36){memcpy(views[i-5].id,p+16,16);memcpy(&views[i-5].version,p+32,4);}}
 FxWlmNativePlan plan;FxResult result=fx_wlm_native_compose(views,(uint32_t)(argc-5),target,required,(FxWlmNativeMemory){0,alloc,dealloc},&plan);
 /* Input buffers may be released as soon as the private plan is returned. */
 for(int i=5;i<argc;++i){free((void *)views[i-5].data);views[i-5].data=0;}
 printf("{\"result\":%u,\"bytes\":%u,\"selection\":%u,\"entries\":[",(unsigned)result,plan.bytes,plan.selection);for(uint32_t i=0;i<plan.entry_count;++i)printf("%s%llu",i?",":"",(unsigned long long)plan.entries[i]);printf("],\"allocations\":%u,\"peak\":%llu,",calls,(unsigned long long)peak);
 if(result==FX_OK&&plan.package){FILE *f=fopen(argv[2],"wb");if(!f)return 5;fwrite(plan.package,1,plan.bytes,f);fclose(f);dealloc(0,plan.package);}
 printf("\"live\":%u}\n",live);for(int i=5;i<argc;++i)free((void *)views[i-5].data);return live?6:0;
}
