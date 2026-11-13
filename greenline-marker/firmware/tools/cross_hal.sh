#!/bin/sh
# cross_hal.sh <header-dir> <toolchain-prefix> <out-dir> <flags> <needed-headers> <sources...>
#
# `make cross-hal`: compile the STM32 backend against ST's and Arm's header
# files - COMPILE ONLY.  <header-dir> holds the headers as the three public
# repositories lay them out (see the Makefile).  The headers are data:
# nothing in <header-dir> is executed and nothing from it is copied anywhere.
#
# If <header-dir> is empty or the headers are not there, the step is SKIPPED
# with a message and exits 0: the backend has then NOT been compiled.
set -u
HDR=$1
PREFIX=$2
OUT=$3
FLAGS=$4
NEED=$5
shift 5

if [ -z "$HDR" ]; then
    echo "cross-hal SKIPPED: STM32_HEADERS is not set."
    echo "  Use: make cross-hal STM32_HEADERS=<dir>   (the Makefile says what <dir> must hold)."
    echo "  hal/stm32u5/gl_hal_stm32u5.c was NOT compiled in this run."
    exit 0
fi
for f in $NEED; do
    if [ ! -f "$HDR/$f" ]; then
        echo "cross-hal SKIPPED: $HDR/$f not found."
        echo "  hal/stm32u5/gl_hal_stm32u5.c was NOT compiled in this run."
        exit 0
    fi
done

mkdir -p "$OUT"
echo "${PREFIX}gcc $FLAGS -isystem <STM32_HEADERS>/cmsis_device_u5/Include" \
     "-isystem <STM32_HEADERS>/stm32u5xx_hal_driver/Inc -isystem <STM32_HEADERS>/CMSIS_5/CMSIS/Core/Include"
OBJS=""
for src in "$@"; do
    obj="$OUT/$(basename "$src" .c).o"
    echo "  XCC     $src"
    # shellcheck disable=SC2086
    "${PREFIX}gcc" $FLAGS \
        -isystem "$HDR/cmsis_device_u5/Include" \
        -isystem "$HDR/stm32u5xx_hal_driver/Inc" \
        -isystem "$HDR/CMSIS_5/CMSIS/Core/Include" \
        -c "$src" -o "$obj" || exit 1
    OBJS="$OBJS $obj"
done
# shellcheck disable=SC2086
sh tools/cross_hal_report.sh "$PREFIX" $OBJS
