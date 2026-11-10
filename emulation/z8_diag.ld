/* All addresses are supplied by the separately validated binding profile. */
ENTRY(fx_z8_system_dispatch)
SECTIONS {
    . = FX_Z8_CODE_BEGIN;
    __fx_z8_code_begin = .;
    .text : { *(.text*) }
    .rodata : { *(.rodata*) }
    .data : { *(.data*) }
    .bss : { *(.bss*) *(COMMON) }
    __fx_z8_code_end = .;
    ASSERT(. <= FX_Z8_CODE_END, "Z8 validated RX reservation exhausted")
    ASSERT(SIZEOF(.data) == 0, "Z8 diagnostic core must not contain writable static data")
    ASSERT(SIZEOF(.bss) == 0, "Z8 diagnostic core must use owned heap RAM")
    /DISCARD/ : { *(.comment) *(.eh_frame*) *(.note*) }
}
