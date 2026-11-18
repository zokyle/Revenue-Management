/* gl_boot.ld - link region of the boot stub: page 0 of the flash (8 kB),
 * write-protected at the factory; 4 kB of RAM for its stack (it has no
 * data).  The application is linked from 0x08002000 (GL_BOOT_APP_BASE) with
 * its image header at +0x400: boot/gl_boot.h. */
ENTRY(Reset_Handler)

MEMORY
{
    STUB (rx) : ORIGIN = 0x08000000, LENGTH = 0x2000
    RAM (rw)  : ORIGIN = 0x20000000, LENGTH = 0x1000
}

gl_boot_stack_top_ = ORIGIN(RAM) + LENGTH(RAM);

SECTIONS
{
    .text :
    {
        KEEP(*(.isr_vector))
        *(.text*)
        *(.rodata*)
        . = ALIGN(4);
    } > STUB

    /* the stub has no initialised data and needs no zeroed data: if either
     * section is not empty the link fails here */
    .data : { *(.data*) } > RAM AT > STUB
    .bss (NOLOAD) : { *(.bss*) *(COMMON) } > RAM
    ASSERT(SIZEOF(.data) == 0, "the boot stub must not have initialised data (nothing copies it)")
    ASSERT(SIZEOF(.bss) == 0, "the boot stub must not have static variables (nothing clears them)")

    /DISCARD/ : { *(.ARM.exidx*) *(.ARM.attributes) *(.comment) *(.note*) }
}
