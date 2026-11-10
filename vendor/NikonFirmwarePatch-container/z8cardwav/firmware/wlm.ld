/* SPDX-License-Identifier: GPL-3.0-or-later */
PHDRS {
    text PT_LOAD FLAGS(5);
    rodata PT_LOAD FLAGS(4);
    data PT_LOAD FLAGS(6);
}
ENTRY(fx_native_pack_entry)
SECTIONS {
    .text 0x40940000 : { *(.text*) } :text
    .rodata ALIGN(4096) : { *(.rodata*) } :rodata
    .data 0x4094d000 : { *(.data*) *(.bss*) } :data
    .state 0x4094e000 (NOLOAD) : {
        m2_audio_state = .;
        . += 1536;
        m2_picker_state = .;
        . += 6656;
    } :data
    /DISCARD/ : { *(.comment) *(.eh_frame*) *(.note*) }
}
