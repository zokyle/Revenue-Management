#!/bin/sh
# cross_hal_report.sh <toolchain-prefix> <object files...>
#
# For the STM32 backend compiled by `make cross-hal`: size, the largest stack
# frames, the forbidden-symbol check of `make cross` (no double-precision
# helper, no double libm, no heap, no stdio), and the symbols a link would
# have to find in ST's HAL, in CMSIS / start-up code and in the firmware.
set -eu
PREFIX="$1"
shift
echo "== size (arm-none-eabi, -Os, bytes; COMPILE ONLY: no HAL code, nothing linked)"
"${PREFIX}size" -B "$@" | awk 'NR == 1 { printf "  %7s %7s %7s  %s\n", "text", "data", "bss", "object"; next }
                                { printf "  %7d %7d %7d  %s\n", $1, $2, $3, $6 }'
echo "== largest stack frames (bytes, from -fstack-usage; the HAL's own frames below them are unknown)"
for o in "$@"; do
    su="${o%.o}.su"
    if [ -f "$su" ]; then
        awk -F'\t' '{ n = split($1, p, ":"); printf "  %6d  %-34s %s\n", $2, p[n], $3 }' "$su"
    fi
done | sort -rn | head -8
echo "== forbidden symbol check"
BAD=0
for o in "$@"; do
    syms=$("${PREFIX}nm" -u "$o" | awk '{ print $2 }' | grep -E \
        '^(__aeabi_d[a-z0-9]*|__aeabi_f2d|__aeabi_i2d|__aeabi_ui2d|__aeabi_l2d|__aeabi_ul2d|__aeabi_d2f|__aeabi_d2iz|__aeabi_d2uiz|sqrt|sin|cos|tan|atan|atan2|asin|acos|exp|log|pow|floor|ceil|fabs|fmod|erf|round|malloc|calloc|realloc|free|printf|sprintf|snprintf|puts|fopen|fwrite)$' || true)
    if [ -n "$syms" ]; then
        echo "  $o references: $(echo "$syms" | tr '\n' ' ')"
        BAD=1
    fi
done
if [ "$BAD" -ne 0 ]; then
    echo "  FAIL: double-precision, heap or stdio symbols referenced"
    exit 1
fi
echo "  OK: no double-precision helpers, no double libm calls, no heap, no stdio"
U=$("${PREFIX}nm" -u "$@" | awk 'NF == 2 { print $2 }' | sort -u)
echo "== undefined symbols a link must provide"
echo "  from ST's HAL sources ($(echo "$U" | grep -c '^HAL_') functions):"
echo "$U" | grep '^HAL_' | tr '\n' ' ' | fold -s -w 100 | sed 's/^/    /'
echo
echo "  from CMSIS / start-up code, libc, the compiler runtime and the firmware:"
echo "$U" | grep -v '^HAL_' | tr '\n' ' ' | fold -s -w 100 | sed 's/^/    /'
echo
echo "== interrupt handlers and HAL callbacks this object defines (the vector table of the"
echo "   start-up file must name the handlers exactly like this)"
"${PREFIX}nm" --defined-only "$@" | awk '$2 == "T" { print $3 }' |
    grep -E 'IRQHandler$|_Handler$|^HAL_.*Callback$' | sort | tr '\n' ' ' | fold -s -w 100 | sed 's/^/    /'
echo
