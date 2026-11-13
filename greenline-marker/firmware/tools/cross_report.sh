#!/bin/sh
# cross_report.sh <toolchain-prefix> <object files...>
#
# Prints, for the cross-compiled objects:
#   1. a size table (text / data / bss per module, with group totals),
#   2. the largest stack frames (from gcc -fstack-usage .su files),
#   3. a check that no object references a forbidden library symbol:
#      double-precision soft-float helpers (the Cortex-M33 FPU is single
#      precision: any double arithmetic would be a slow library call),
#      double-precision libm functions, the heap, or stdio,
#   4. a check that the objects hold no fused multiply-add instruction,
#   5. the same forbidden-symbol rule on a link probe against the
#      toolchain's own libm and libc (tools/cross_link_check.py).
# Exits non-zero if a forbidden symbol is referenced or reachable, or a
# fused instruction is found.
set -eu
PREFIX="$1"
shift

if [ "$#" -eq 0 ]; then
    echo "cross_report: no objects"
    exit 1
fi

echo "== size per module (arm-none-eabi, -Os, bytes)"
"${PREFIX}size" -B "$@" | awk '
    NR == 1 { next }
    {
        path = $6
        n = split(path, parts, "/")
        group = parts[n - 1]
        name = parts[n]
        sub(/\.o$/, "", name)
        printf "  %-8s %-18s %7d %7d %7d\n", group, name, $1, $2, $3
        gt[group] += $1; gd[group] += $2; gb[group] += $3
        tt += $1; td += $2; tb += $3
    }
    END {
        print "  ----------------------------------------------------"
        for (g in gt) printf "  %-8s %-18s %7d %7d %7d\n", g, "(total)", gt[g], gd[g], gb[g]
        printf "  %-8s %-18s %7d %7d %7d\n", "all", "(total)", tt, td, tb
    }' | awk 'BEGIN { printf "  %-8s %-18s %7s %7s %7s\n", "group", "module", "text", "data", "bss" } { print }'

echo "== largest stack frames (bytes, from -fstack-usage)"
SU=""
for o in "$@"; do
    su="${o%.o}.su"
    [ -f "$su" ] && SU="$SU $su"
done
if [ -n "$SU" ]; then
    # shellcheck disable=SC2086
    cat $SU | awk -F'\t' '{ n = split($1, p, ":"); printf "  %6d  %-34s %s\n", $2, p[n], $3 }' |
        sort -rn | head -12
fi

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

# The solver's results are those of IEEE single-precision operations rounded
# one at a time (what the host tests compare with the reference).  A fused
# multiply-add rounds once where the source has two operations: the compiler
# must not contract (CROSS_FLAGS has -ffp-contract=off; -std=c99 happens to
# imply it, -std=gnu99 - the default of most IDE projects - does not).
echo "== fused multiply-add check (floating-point contraction must be off)"
FUSED=$("${PREFIX}objdump" -d "$@" | grep -cE '[[:space:]]vfn?m[as]\.f(32|64)' || true)
if [ "$FUSED" -ne 0 ]; then
    echo "  FAIL: $FUSED fused multiply-add instructions (vfma / vfms / vfnma / vfnms) in the objects"
    exit 1
fi
MULADD=$("${PREFIX}objdump" -d "$@" | grep -cE '[[:space:]]vml[as]\.f32' || true)
echo "  OK: no fused instruction; $MULADD vmla / vmls (multiply, round, add, round - as written)"
echo "== undefined symbols the final link must provide (libm single precision, libc, compiler runtime)"
"${PREFIX}nm" -u "$@" | awk 'NF == 2 { print $2 }' | sort -u | grep -v '^gl_' | tr '\n' ' ' | fold -s -w 100 | sed 's/^/  /'
echo

# The same rule on a linked image: what the C library brings in.
echo "== link probe: the forbidden-symbol rule on a linked image (tools/cross_link_check.py)"
if command -v "${PYTHON:-python3}" >/dev/null 2>&1; then
    "${PYTHON:-python3}" tools/cross_link_check.py "$PREFIX" "$(dirname "$(dirname "$1")")/link" "$@"
else
    echo "  SKIPPED: python3 not available (the rule was checked on the objects only)"
fi
