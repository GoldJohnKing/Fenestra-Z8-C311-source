/* SPDX-License-Identifier: GPL-3.0-only
 * Includes the exact extracted production Directory/module_read text. Native
 * filesystem/cancel boundaries are synthetic; all loop/close policy is real. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "fenestra_wlm_bundle.h"
#include "fenestra_capacity.h"
#include "fenestra_file_observer.h"
typedef struct{uint32_t cancel;} State;
static uint32_t source_bytes,position,reads,closes,max_request,short_chunk,close_error,read_error,cancel_after,open_error;
static State task;
int cold_capsule_cancelled(void *p){return ((State *)p)->cancel!=0u;}
static char fx_z8_card_drive(void){return 'A';}
static int32_t native_open(const char *path,uint32_t a,uint32_t b){assert(!strcmp(path,"A:\\FENESTRA\\framing.wlm")&&!a&&!b);return open_error?-1:7;}
static uint32_t native_close(int32_t fd){assert(fd==7);++closes;return close_error;}
static uint32_t fx_z8_file_read(int32_t fd,void *out,uint32_t n,uint32_t *done){assert(fd==7&&n>0&&n<=32768u);++reads;if(n>max_request)max_request=n;if(read_error&&reads==read_error)return 1u;uint32_t take=source_bytes-position;if(take>n)take=n;if(short_chunk&&take>short_chunk)take=short_chunk;memset(out,0x5a,take);position+=take;*done=take;if(cancel_after&&reads==cancel_after)task.cancel=1u;return 0;}
#define FN(a,t) ((t)(uintptr_t)(a))
#define FX_Z8_ADDR_402dc960 ((uintptr_t)native_open)
#define FX_Z8_ADDR_402dc9c0 ((uintptr_t)native_close)
/* Production typedef and function, copied byte-for-byte by the test driver. */
#include "production_module_read.inc"
static void reset(uint32_t n){source_bytes=n;position=reads=closes=max_request=short_chunk=close_error=read_error=cancel_after=open_error=0u;task.cancel=0;}
int main(void){uint8_t *raw=malloc(16u*1024u*1024u+3u);assert(raw);uint8_t *buffer=raw+1u;const char name[32]="framing.wlm";uint32_t bytes;Directory d={.fd=-1};
#ifdef FX_NATIVE_CAPSULES
 d.state=&task;uint32_t big=16u*1024u*1024u;reset(big);raw[0]=0xaa;raw[big+2u]=0xbb;assert(module_read(&d,name,buffer,big+1u,&bytes)==FX_OK&&bytes==big);assert(reads==513u&&closes==1u&&max_request==32768u&&raw[0]==0xaa&&raw[big+2u]==0xbb);reset(big+1u);assert(module_read(&d,name,buffer,big+1u,&bytes)==FX_OK&&bytes==big+1u&&reads==513u&&closes==1u);reset(big);cancel_after=5u;assert(module_read(&d,name,buffer,big+1u,&bytes)==FX_INTERRUPTED&&reads==5u&&closes==1u);reset(big);cancel_after=5u;close_error=1u;assert(module_read(&d,name,buffer,big+1u,&bytes)==FX_CLOSE&&closes==1u);
#endif
 reset(1024u*1024u);assert(module_read(&d,name,buffer,1024u*1024u+1u,&bytes)==FX_OK&&bytes==1024u*1024u&&reads==33u&&closes==1u);reset(1024u*1024u);short_chunk=1u;assert(module_read(&d,name,buffer,1024u*1024u+1u,&bytes)==FX_IO&&reads==FX_Z8_DISCOVERY_CALLS&&closes==1u);reset(1024u*1024u);read_error=2u;close_error=1u;assert(module_read(&d,name,buffer,1024u*1024u+1u,&bytes)==FX_CLOSE&&reads==2u&&closes==1u);reset(1024u*1024u);open_error=1u;assert(module_read(&d,name,buffer,1024u*1024u+1u,&bytes)==FX_IO&&!reads&&!closes);free(raw);puts("PASS: exact production module_read; 32KiB requests, full cap+tail probe, legacy budget, bounded short IO, cancel and close precedence");return 0;}
