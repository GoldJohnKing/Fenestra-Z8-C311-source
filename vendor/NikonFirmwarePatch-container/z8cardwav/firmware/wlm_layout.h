/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef Z8_CARD_WAV_WLM_LAYOUT_H
#define Z8_CARD_WAV_WLM_LAYOUT_H
#define M2_LABEL_SCAN 0x1f00
#define M2_LABEL_FIRST 0x1f01
#define M2_LABEL_END 0x1f15
#ifndef __ASSEMBLER__
_Alignas(8) extern unsigned char m2_audio_state[], m2_picker_state[];
int m2_wlm_begin(void);
void m2_wlm_end(void);
int m2_wlm_accepting(void);
int m2_audio_pending(void);
#endif
#endif
