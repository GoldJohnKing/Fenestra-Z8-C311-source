/* SPDX-License-Identifier: GPL-3.0-only */
/* Host driver for modules/portrait_video/native.c: the gravity anchors are
 * redirected to local buffers by defining the macros before the include. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static uint32_t g_enable;
static uint32_t g_grav[3];
#define GRAVITY_ENABLE ((uintptr_t)&g_enable)
#define GRAVITY_VECTOR ((uintptr_t)&g_grav[0])
#include "../modules/portrait_video/native.c"

static void setgrav(uint32_t x, uint32_t y, uint32_t z) {
    g_grav[0] = x; g_grav[1] = y; g_grav[2] = z;
}

static FxResult stub_lookup(void *ctx, const char *name, uint32_t version, uintptr_t *address) {
    (void)ctx; (void)name; (void)version; (void)address;
    return FX_CAPABILITY;
}

static FxNativePackExports exports;

static void open_gate(void) {
    FxNativePackHost host = {.abi = FX_NATIVE_PACK_ABI, .bytes = (uint32_t)sizeof(FxNativePackHost),
        .context = (void *)1, .allocate = 0, .release = 0, .lookup = stub_lookup};
    assert(fx_native_pack_entry(&host, &exports) == FX_OK);
    assert(exports.event(exports.context, FX_NATIVE_PACK_PUBLISH) == FX_OK);
}

static uint32_t slot_pose(uintptr_t writer) {
    _Atomic uintptr_t *slot = find_writer(writer);
    assert(slot != 0);
    return (uint32_t)(atomic_load_explicit(slot, memory_order_relaxed) & 3u);
}

static void identity_matrix(uint8_t *m) {
    for (unsigned i = 0; i < 36u; ++i)
        m[i] = (uint8_t)((i == 1u || i == 17u) ? 1u : (i == 32u ? 64u : 0u));
}

static void check_matrix(uintptr_t writer, uint32_t code, const uint32_t words[8]) {
    static const uint32_t CODE_VEC[4][3] = {
        {0xbf800000u, 0u, 0u},      /* 0: level landscape (-X) */
        {0u, 0x3f800000u, 0u},      /* 1: +Y shutter-bottom */
        {0u, 0xbf800000u, 0u},      /* 2: -Y shutter-top */
        {0x3f800000u, 0u, 0u},      /* 3: +X upside-down */
    };
    uint8_t buf[36];
    setgrav(CODE_VEC[code][0], CODE_VEC[code][1], CODE_VEC[code][2]);
    identity_matrix(buf);
    fx_portrait_sample(writer, 0u);
    fx_portrait_matrix(writer, buf, 3840u, 2160u);
    for (unsigned i = 0; i < 8u; ++i) {
        assert((uint32_t)buf[4u * i] == ((words[i] >> 24) & 0xffu));
        assert((uint32_t)buf[4u * i + 1u] == ((words[i] >> 16) & 0xffu));
        assert((uint32_t)buf[4u * i + 2u] == ((words[i] >> 8) & 0xffu));
        assert((uint32_t)buf[4u * i + 3u] == (words[i] & 0xffu));
    }
    assert(buf[32] == 0x40 && buf[33] == 0 && buf[34] == 0 && buf[35] == 0);
}

int main(void) {
    /* Enable byte: anything but exactly 1 classifies as no mark. */
    g_enable = 0u; setgrav(0x3f800000u, 0u, 0u);
    assert(classify_pose() == 0u);
    g_enable = 2u; setgrav(0x3f800000u, 0u, 0u);
    assert(classify_pose() == 0u);

    g_enable = 1u;
    /* Six axis directions: +X upside-down, -X level, +Y/-Y the portrait
     * grips, +/-Z the lens axis without a roll code. */
    setgrav(0x3f800000u, 0u, 0u); assert(classify_pose() == 3u);
    setgrav(0xbf800000u, 0u, 0u); assert(classify_pose() == 0u);
    setgrav(0u, 0x3f800000u, 0u); assert(classify_pose() == 1u);
    setgrav(0u, 0xbf800000u, 0u); assert(classify_pose() == 2u);
    setgrav(0u, 0u, 0x3f800000u); assert(classify_pose() == 0u);
    setgrav(0u, 0u, 0xbf800000u); assert(classify_pose() == 0u);
    /* Ties: x beats y on equality; z must be strictly larger to win. */
    setgrav(0x3f800000u, 0x3f800000u, 0u); assert(classify_pose() == 3u);
    setgrav(0xbf800000u, 0xbf800000u, 0u); assert(classify_pose() == 0u);
    setgrav(0x3f800000u, 0u, 0x3f800000u); assert(classify_pose() == 3u);
    /* Threshold boundary on the sign-stripped magnitude bits. */
    setgrav(0x3f333332u, 0u, 0u); assert(classify_pose() == 0u);
    setgrav(0x3f333333u, 0u, 0u); assert(classify_pose() == 3u);
    /* Zero vector: no dominant axis. */
    setgrav(0u, 0u, 0u); assert(classify_pose() == 0u);
    /* NaN payload bits order above every finite magnitude in the unsigned
     * comparison and classify like their axis. */
    setgrav(0x7fc00000u, 0u, 0u); assert(classify_pose() == 3u);

    /* Writer lifecycle: the first sample of a writer captures the pose,
       later samples do not, upside-down stores code 3, forget clears the
       slot, a reused writer address is re-captured, and a stopped pack
       leaves every hook inert. */
    open_gate();
    setgrav(0u, 0x3f800000u, 0u);
    fx_portrait_sample(0x5000u, 0u);
    assert(slot_pose(0x5000u) == 1u);
    setgrav(0u, 0u, 0x3f800000u);
    fx_portrait_sample(0x5000u, 5u);
    assert(slot_pose(0x5000u) == 1u);
    fx_portrait_sample(0x7000u, 5u);
    assert(find_writer(0x7000u) == 0);
    setgrav(0x3f800000u, 0u, 0u);
    fx_portrait_sample(0x6000u, 0u);
    assert(slot_pose(0x6000u) == 3u);
    fx_portrait_forget(0x5000u);
    assert(find_writer(0x5000u) == 0);
    setgrav(0u, 0xbf800000u, 0u);
    fx_portrait_sample(0x6000u, 0u);
    assert(slot_pose(0x6000u) == 2u);
    assert(exports.event(exports.context, FX_NATIVE_PACK_STOP) == FX_OK);
    fx_portrait_sample(0x8000u, 0u);
    assert(find_writer(0x8000u) == 0);
    /* A stopped pack leaves every hook inert, matrix and forget included. */
    {
        uint8_t buf[36], want[36];
        identity_matrix(buf); identity_matrix(want);
        fx_portrait_matrix(0xa300u, buf, 3840u, 2160u);
        assert(memcmp(buf, want, sizeof(buf)) == 0);
        fx_portrait_forget(0xa300u);
        assert(find_writer(0xa300u) == 0);
    }

    /* Matrix writing at 3840x2160.  Swap guard: code 1 (90 deg CW,
     * b=+1/c=-1) must equal byte-for-byte the group the stock module
     * wrote for its pose 2 (tx=height, ty=0 -- the canonical Apple EXIF-6
     * pairing), and code 2 the group it wrote for its pose 1 (tx=0,
     * ty=width). Code 3 is the new 180-degree group. */
    open_gate();
    {
        const uint32_t cw[8] = {0u, 0x10000u, 0u, 0xffff0000u, 0u, 0u, 0x08700000u, 0u};
        const uint32_t ccw[8] = {0u, 0xffff0000u, 0u, 0x10000u, 0u, 0u, 0u, 0x0f000000u};
        const uint32_t half[8] = {0xffff0000u, 0u, 0u, 0u, 0xffff0000u, 0u, 0x0f000000u, 0x08700000u};
        check_matrix(0xa100u, 1u, cw);
        check_matrix(0xa200u, 2u, ccw);
        check_matrix(0xa300u, 3u, half);
    }
    /* Landscape (code 0), a non-identity stock matrix and an unknown
     * writer all leave the buffer untouched. */
    {
        uint8_t buf[36], want[36];
        identity_matrix(buf); identity_matrix(want);
        setgrav(0xbf800000u, 0u, 0u);
        fx_portrait_sample(0xa400u, 0u);
        fx_portrait_matrix(0xa400u, buf, 3840u, 2160u);
        assert(memcmp(buf, want, sizeof(buf)) == 0);
        memset(buf, 0xaa, sizeof(buf));
        fx_portrait_matrix(0xa100u, buf, 3840u, 2160u);
        for (unsigned i = 0; i < 36u; ++i) assert(buf[i] == 0xaa);
        identity_matrix(buf);
        fx_portrait_matrix(0xb000u, buf, 3840u, 2160u);
        assert(memcmp(buf, want, sizeof(buf)) == 0);
    }

    puts("PASS: portrait_video");
    return 0;
}
