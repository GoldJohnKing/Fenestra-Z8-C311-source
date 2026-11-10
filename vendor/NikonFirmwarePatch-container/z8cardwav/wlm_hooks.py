# SPDX-License-Identifier: GPL-3.0-or-later
# Hook shims derived from the Z8 card WAV v0.1.1 builder.
"""Generate the native hooks, reading displaced instructions from stock MAIN."""
import struct

ENTRY_HOOKS = {
    'api': 0x40e3133c, 'pcm': 0x40d23c4c,
    'flags': 0x40f9c5cc, 'terminal': 0x40f9cda0, 'fast_timer': 0x40f9cc64,
    'composite': 0x40f9cfa4, 'cxx_stop': 0x40f9d00c,
    'notice_sync_end': 0x40e35420, 'notice_async_end': 0x40e35590,
}
CLASSIFIER_HOOKS = (0x4032e244, 0x4032e350, 0x4032e414, 0x4032e4a0,
                    0x4032e504, 0x4032e604, 0x4032e6c8)


def generate(read_stock):
    asm = ['#include "wlm_layout.h"', '.section .text.hooks,"ax"']

    def label(name):
        asm.extend((f'.global {name}', f'{name}:'))

    def replay(name):
        site = ENTRY_HOOKS[name]
        word, = struct.unpack('<I', read_stock(site, 4))
        asm.extend((f'.inst {word}', f'b continue_{name}'))

    def save_args(frame):
        asm.extend((f'sub sp,sp,#{frame}', 'stp x0,x1,[sp]', 'stp x2,x3,[sp,#16]',
                    'stp x4,x5,[sp,#32]', 'stp x6,x7,[sp,#48]', 'str x30,[sp,#64]'))

    def restore_args():
        asm.extend(('ldp x0,x1,[sp]', 'ldp x2,x3,[sp,#16]',
                    'ldp x4,x5,[sp,#32]', 'ldp x6,x7,[sp,#48]'))

    for name in ('api', 'pcm', 'composite', 'cxx_stop'):
        label('hook_' + name)
        frame = 96 if name in ('api', 'pcm') else 80
        save_args(frame)
        if name in ('api', 'pcm'):
            asm.append('mov x0,sp')
        asm.append('bl m2_' + name)
        if name == 'api':
            asm.append('cbnz w0,api_rejected')
        restore_args()
        if name == 'api':
            asm.extend(('bl original_api', 'str x0,[sp,#72]', 'mov x0,sp',
                        'bl m2_api_result', 'ldr x0,[sp,#72]'))
        asm.extend(('ldr x30,[sp,#64]', f'add sp,sp,#{frame}'))
        if name == 'api':
            asm.append('ret')
        else:
            replay(name)

    for name in ('flags', 'terminal', 'fast_timer'):
        label('hook_' + name)
        asm.append('stp x0,x30,[sp,#-16]!')
        if name == 'terminal':
            asm.append('mov x0,x30')
        asm.extend(('bl m2_' + name, 'mov w9,w0', 'ldp x0,x30,[sp],#16', 'cbnz w9,1f'))
        replay(name)
        asm.append('1: ret')

    asm.extend(('api_rejected:', 'ldr x30,[sp,#64]', 'add sp,sp,#96', 'mov w0,wzr', 'ret'))
    label('original_api')
    replay('api')
    for name in ('notice_sync_end', 'notice_async_end'):
        label('hook_' + name)
        asm.extend(('stp x0,x30,[sp,#-16]!', 'bl m2_notice_retired', 'ldp x0,x30,[sp],#16'))
        replay(name)

    label('mark2_discovery_label')
    asm.extend(('mov w9,#M2_LABEL_SCAN', 'cmp w1,w9', 'b.lo 2f',
                'mov w9,#M2_LABEL_END', 'cmp w1,w9', 'b.lo mark2_picker_label', '2: b foundation_text'))
    wav_class = read_stock(0x4320a3cc + 0x925, 1)[0]
    for index, site in enumerate(CLASSIFIER_HOOKS):
        label(f'hook_class_{index}')
        word, = struct.unpack('<I', read_stock(site, 4))
        # x12 and NZCV are dead after each original classifier load. For a
        # non-WAV label replay the load against the original classifier root.
        asm.extend(('mov w12,#M2_LABEL_SCAN', 'sub w12,w8,w12',
                    'cmp w12,#(M2_LABEL_END-M2_LABEL_SCAN)', 'b.hs 3f',
                    f'mov w8,#{wav_class}', 'b 4f', f'3: .inst {word}',
                    f'4: b continue_class_{index}'))
    for slot in range(64):
        label(f'notice_slot_{slot}')
        asm.extend(('mov x2,x1', 'mov w1,w0', f'mov w0,#{slot}', 'b m2_notice_slot'))
    asm.extend(('.section .rodata.callbacks,"a"', '.balign 8'))
    label('callback_slots')
    asm.extend(f'.quad notice_slot_{slot}' for slot in range(64))
    return '\n'.join(asm) + '\n'
