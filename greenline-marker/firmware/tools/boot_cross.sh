#!/bin/sh
# boot_cross.sh <header-dir> <toolchain-prefix> <out-dir> <flags>
#
# `make boot-cross`: the boot stub (boot/, DESIGN_SPEC E34).
#   1. always: compile boot/gl_boot_logic.c with the flags of the cross build
#      and print its size and its forbidden-symbol check (it may call
#      nothing: no library exists in the stub);
#   2. with the vendor's DEVICE header in <header-dir> (laid out as for
#      `make cross-hal`): compile boot/gl_boot_stm32u5.c against it and LINK
#      the stub with boot/gl_boot.ld - no C library, no start-up file, no
#      HAL - and check that it fits its page.
# The headers are data: nothing in <header-dir> is executed or copied.
# Linked is NOT run: no hardware exists.
set -u
HDR=$1
PREFIX=$2
OUT=$3
FLAGS=$4
mkdir -p "$OUT"

echo "== boot stub: ${PREFIX}gcc $FLAGS"
echo "  XCC     boot/gl_boot_logic.c"
# shellcheck disable=SC2086
"${PREFIX}gcc" $FLAGS -c boot/gl_boot_logic.c -o "$OUT/gl_boot_logic.o" || exit 1
UNDEF=$("${PREFIX}nm" -u "$OUT/gl_boot_logic.o" | awk '{print $2}' | tr '\n' ' ')
if [ -n "$UNDEF" ]; then
    echo "  FAIL: the portable part of the stub needs external symbols: $UNDEF"
    exit 1
fi
echo "  OK: boot/gl_boot_logic.c references no external symbol (no library, no helper call)"
"${PREFIX}size" "$OUT/gl_boot_logic.o" | sed 's/^/  /'

DEV="$HDR/cmsis_device_u5/Include/stm32u585xx.h"
CORE="$HDR/CMSIS_5/CMSIS/Core/Include/core_cm33.h"
if [ -z "$HDR" ] || [ ! -f "$DEV" ] || [ ! -f "$CORE" ]; then
    echo "  boot stub link SKIPPED: STM32_HEADERS is not set or the device header is not there."
    echo "  boot/gl_boot_stm32u5.c was NOT compiled and the stub was NOT linked in this run."
    exit 0
fi
echo "  XCC     boot/gl_boot_stm32u5.c   (-isystem <STM32_HEADERS>/cmsis_device_u5/Include, .../CMSIS/Core/Include)"
# shellcheck disable=SC2086
"${PREFIX}gcc" $FLAGS -isystem "$HDR/cmsis_device_u5/Include" \
    -isystem "$HDR/CMSIS_5/CMSIS/Core/Include" \
    -c boot/gl_boot_stm32u5.c -o "$OUT/gl_boot_stm32u5.o" || exit 1
echo "  LINK    $OUT/gl_boot.elf   (-nostdlib -nostartfiles -T boot/gl_boot.ld)"
"${PREFIX}gcc" -mcpu=cortex-m33 -mthumb -mfpu=fpv5-sp-d16 -mfloat-abi=hard -nostdlib -nostartfiles \
    -Wl,--gc-sections -Wl,-T,boot/gl_boot.ld -Wl,-Map,"$OUT/gl_boot.map" \
    "$OUT/gl_boot_stm32u5.o" "$OUT/gl_boot_logic.o" -o "$OUT/gl_boot.elf" || {
    echo "  FAIL: the boot stub does not link"
    exit 1
}
"${PREFIX}objcopy" -O binary "$OUT/gl_boot.elf" "$OUT/gl_boot.bin" || exit 1
BYTES=$(wc -c < "$OUT/gl_boot.bin" | tr -d ' ')
"${PREFIX}size" "$OUT/gl_boot.elf" | sed 's/^/  /'
ENTRY=$("${PREFIX}nm" "$OUT/gl_boot.elf" | awk '$3 == "Reset_Handler" {print $1}')
VEC=$(od -A n -t x4 -N 8 "$OUT/gl_boot.bin" | tr -s ' ')
echo "  image: $BYTES bytes of 8192 (page 0); vector table:$VEC; Reset_Handler at 0x$ENTRY"
if [ "$BYTES" -gt 8192 ]; then
    echo "  FAIL: the boot stub does not fit its page"
    exit 1
fi
STACK=$(cat "$OUT"/gl_boot_logic.su "$OUT"/gl_boot_stm32u5.su 2>/dev/null | awk '{ if ($(NF-1) > m) m = $(NF-1) } END { print m + 0 }')
echo "  largest stack frame of the stub: $STACK bytes (its stack: 4096)"
echo "  OK: the boot stub links without any library and fits its page.  LINKED IS NOT RUN: no hardware."
