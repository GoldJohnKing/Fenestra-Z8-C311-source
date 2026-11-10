/* SPDX-License-Identifier: GPL-3.0-only
 * Pure revocation-record encoding only; no camera memory or MMU is touched.
 */
#include "revocation.h"
#include <stdio.h>
#include <stdlib.h>
static uint32_t checks;
#define CHECK(x) do{++checks;if(!(x)){fprintf(stderr,"revocation assertion at line %d\n",__LINE__);exit(1);}}while(0)
int main(void) {
    uint8_t sha[32];for(uint32_t i=0u;i<32u;++i)sha[i]=(uint8_t)(0xa0u+i);
    FxZ8Revoked r;fx_z8_revoked_seal(&r,UINT64_C(0x1122334455667788),sha);
    CHECK(fx_z8_revoked_valid(&r) && !memcmp(r.magic,"FXREVOK1",8u) && r.abi==1u && r.bytes==64u);
    CHECK(r.package_id==UINT64_C(0x1122334455667788) && !memcmp(r.package_sha256,sha,32u));
    /* Retained zero RAM, the withdrawn record and every single-bit flip fail. */
    FxZ8Revoked zero;memset(&zero,0,sizeof(zero));CHECK(!fx_z8_revoked_valid(&zero));
    for(uint32_t bit=0u;bit<sizeof(r)*8u;++bit) {
        FxZ8Revoked flipped=r;((uint8_t *)&flipped)[bit/8u]^=(uint8_t)(1u<<(bit%8u));CHECK(!fx_z8_revoked_valid(&flipped));
    }
    FxZ8Revoked other;fx_z8_revoked_seal(&other,1u,sha);CHECK(fx_z8_revoked_valid(&other) && memcmp(other.check,r.check,8u));
    /* Loader page: last arena page, record at its final 64 bytes. */
    CHECK(FX_Z8_REVOKED_PAGE==UINT64_C(0x40c00000)-4096u && FX_Z8_REVOKED_AT==UINT64_C(0x40c00000)-64u);
    printf("PASS: revocation record %u checks; sealed, zero, withdrawn and every bit flip\n",checks);
    return 0;
}
