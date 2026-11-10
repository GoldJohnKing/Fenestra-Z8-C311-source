/* SPDX-License-Identifier: GPL-3.0-only */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "internal.h"
#include "precapture_subscription_preimages.h"
#define STRIDE 0xf98u
_Alignas(16) static uint8_t bank[48u*STRIDE+4u],before[sizeof(bank)];
static uint32_t cleans;
void fx_controls_test_dcf_clean(uintptr_t a,uintptr_t b){assert(b-a==0xc4u);assert(*(uint32_t *)a==9u&&*(uint8_t *)b==0x73&&*(uint8_t *)(b+1)==1);++cleans;}
static void slot(uint32_t n,uint32_t count){
 static const uint32_t ids[]={0x601u,0x2000688u,0x6000689u,0x200172au,0x2000600u,0x6000604u,0x6000608u,0x6000605u,0x6000606u};
 uint8_t *s=bank+n*STRIDE;memset(s+4,0,STRIDE);*(uintptr_t *)(s+8)=0x408703b4u;*(uint32_t *)(s+0x14)=0x04320000u;*(uint32_t *)(s+0x18)=count;
 for(uint32_t i=0;i<count;++i){uint32_t id=ids[i];s[0x1cu+((id>>8)&255u)*32u+((id>>3)&31u)]|=(uint8_t)(1u<<(id&7u));}
}
static FxControlsProfile profile(void){return (FxControlsProfile){.dcf_bank=bank,.dcf_constructor=fx_dcf_constructor_original,.dcf_registration=fx_dcf_registration_original};}
static void rejected(FxControlsProfile p){
 FxControlsDcfSubscription s={0};memcpy(before,bank,sizeof(bank));assert(fx_controls_precapture_stage(&s,&p)==FX_INTEGRITY);assert(!s.staged&&!s.slot);assert(!memcmp(before,bank,sizeof(bank)));fx_controls_precapture_publish(&s);assert(!memcmp(before,bank,sizeof(bank)));
}
int main(void){
 const uint32_t positions[]={0,7,47};
 for(uint32_t k=0;k<3;++k){
  memset(bank,0,sizeof(bank));slot(positions[k],5);memcpy(before,bank,sizeof(bank));FxControlsDcfSubscription s={0};FxControlsProfile p=profile();
  assert(fx_controls_precapture_stage(&s,&p)==FX_OK&&s.slot==(uintptr_t)(bank+positions[k]*STRIDE)&&!s.already_new);assert(!memcmp(bank,before,sizeof(bank)));
  uint32_t old=cleans;fx_controls_precapture_publish(&s);assert(cleans==old+1);uint32_t differences=0;
  for(uint32_t i=0;i<sizeof(bank);++i)if(bank[i]!=before[i]){uint32_t relative=i-positions[k]*STRIDE;assert(relative==0x18u||relative==0xdcu||relative==0xddu);++differences;}
  assert(differences==3);memcpy(before,bank,sizeof(bank));fx_controls_precapture_publish(&s);assert(cleans==old+1&&!memcmp(bank,before,sizeof(bank)));
  FxControlsDcfSubscription already={0};assert(fx_controls_precapture_stage(&already,&p)==FX_OK&&already.already_new);fx_controls_precapture_publish(&already);assert(cleans==old+1&&!memcmp(bank,before,sizeof(bank)));
 }
 memset(bank,0,sizeof(bank));rejected(profile());
 slot(7,5);slot(12,5);rejected(profile());
 memset(bank,0,sizeof(bank));slot(7,5);bank[7u*STRIDE+0x1cu+800u]=1;rejected(profile());
 slot(7,5);*(uint32_t *)(bank+7u*STRIDE+0x18u)=9;rejected(profile());
 slot(7,5);*(uint32_t *)(bank+7u*STRIDE+0x18u)=0;rejected(profile());
 slot(7,5);*(uint32_t *)(bank+7u*STRIDE+0x14u)=0;rejected(profile());
 slot(7,5);bank[7u*STRIDE+4u]=1;rejected(profile());
 slot(7,5);uint8_t bad[sizeof(fx_dcf_constructor_original)];memcpy(bad,fx_dcf_constructor_original,sizeof(bad));bad[0]^=1u;FxControlsProfile p=profile();p.dcf_constructor=bad;rejected(p);
 puts("DCF exact old/new stage, readonly failures and once-only three-byte publication: passed");return 0;
}
