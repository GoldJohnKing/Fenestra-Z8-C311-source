/* SPDX-License-Identifier: GPL-3.0-or-later */
#include <stdatomic.h>
#include "fenestra_native_locale.h"
#include "fenestra_native_pack.h"
#include "wlm_layout.h"

#define CLOSED (UINT32_C(1) << 31)
static _Atomic uint32_t admission = CLOSED;
static const FxNativeLocale stock_locale = {FX_NATIVE_LOCALE_ABI, sizeof(FxNativeLocale), 36u,
    3136u, UINT64_C(0x4327c5a0), UINT64_C(0x439daf58)};
static const FxNativePackSymbol locale_export = {
    FX_NATIVE_LOCALE_SYMBOL, 1u, FX_NATIVE_PACK_SYMBOL_DATA, (uintptr_t)&stock_locale};

int m2_wlm_begin(void) {
    uint32_t state = atomic_load(&admission);
    while (!(state & CLOSED)) {
        if (atomic_compare_exchange_weak(&admission, &state, state + 1u)) return 1;
    }
    return 0;
}

void m2_wlm_end(void) { atomic_fetch_sub(&admission, 1u); }
int m2_wlm_accepting(void) { return !(atomic_load(&admission) & CLOSED); }

static uint32_t pending(void *context) {
    (void)context;
    return (atomic_load(&admission) & ~CLOSED) != 0u || m2_audio_pending();
}

FxResult m2_wlm_event(void *context, uint32_t event) {
    switch (event) {
    case FX_NATIVE_PACK_STOP:
    case FX_NATIVE_PACK_FAULT:
    case FX_NATIVE_PACK_ABORT:
        atomic_fetch_or(&admission, CLOSED);
        return pending(context) ? FX_BUSY : FX_OK;
    case FX_NATIVE_PACK_RESUME:
        if (pending(context)) return FX_BUSY;
        /* No escaped PCM or original callback can outlive its backing. */
        atomic_fetch_and(&admission, ~CLOSED);
        return FX_OK;
    case FX_NATIVE_PACK_PUBLISH:
        atomic_fetch_and(&admission, ~CLOSED);
        return FX_OK;
    case FX_NATIVE_PACK_GUI_POLL:
        return FX_OK;
    default:
        return FX_ARGUMENT;
    }
}

FxResult fx_native_pack_entry(const FxNativePackHost *host, FxNativePackExports *out) {
    if (!host || !out || host->abi != FX_NATIVE_PACK_ABI || host->bytes < sizeof(*host) || !host->lookup) return FX_ARGUMENT;
    *out = (FxNativePackExports){.abi = FX_NATIVE_PACK_ABI, .bytes = sizeof(*out),
        .context = &admission, .event = m2_wlm_event, .pending = pending};
    /* shared.locale stages first when installed. Otherwise describe the
     * original tables so this WLM can be the only resident component. */
    uintptr_t locale = 0u;
    FxResult found = host->lookup(host->context, FX_NATIVE_LOCALE_SYMBOL, 1u, &locale);
    if (found == FX_CAPABILITY) {
        out->symbols = &locale_export;
        out->symbol_count = 1u;
    } else if (found != FX_OK || !locale) return FX_INTEGRITY;
    return FX_OK;
}
