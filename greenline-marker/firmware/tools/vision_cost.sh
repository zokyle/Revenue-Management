#!/bin/sh
# vision_cost.sh BUILD OUT - `make profile`: instruction counts of the stages
# of a read, MEASURED with valgrind's callgrind on the host build, against
# the cost table of the simulator (hal/host/gl_sim_cost.h).
#
#   BUILD  directory with vision_bench, solver_bench and tests/test_read
#   OUT    directory for the callgrind output files
#
# Counts are "Ir" of the -O2 x86-64 build: instructions executed inside the
# named function and everything it calls.  Prints what to put into
# gl_sim_cost.h; nothing is written anywhere but OUT.
set -u
B=$1
OUT=$2
mkdir -p "$OUT"
command -v valgrind >/dev/null 2>&1 || { echo "profile SKIPPED: valgrind is not installed"; exit 0; }

# ir FUNCTION PROGRAM ARGS... -> instructions inside FUNCTION (inclusive; the
# name is matched as a prefix, for the clones the compiler makes)
logof() { echo "$OUT/cg_$(echo "$*" | tr ' /' '__').log"; }
ir() {
    log=$(logof "$@")
    fn=$1; shift
    valgrind --tool=callgrind --collect-atstart=no "--toggle-collect=$fn*" \
        "--callgrind-out-file=${log%.log}.out" "$@" > "$log" 2>&1
    sed -n 's/^==[0-9]*== Collected : \([0-9]*\).*/\1/p' "$log" | tail -1
}
table() { sed -n "s/^#define $1 \(.*\)\$/\1/p" hal/host/gl_sim_cost.h | head -1; }
per() { awk "BEGIN { printf \"%d\", $1 / $2 }"; }
pct() { awk "BEGIN { if ($2 > 0) printf \"%+.0f %%\", 100.0 * ($1 - $2) / $2; else printf \"-\" }"; }

echo "== stage costs, host instructions (callgrind Ir, -O2 x86-64)"
echo "   stage                                    measured   per call | cost table"

n=4
v=$(ir bench_band_ "$B/vision_bench" band A $n)
echo "   band 640 x 96, scene A                 $(printf %10s "$v") $(printf %10s "$(per "$v" $n)") | GL_SIM_COST_BAND_IR $(table GL_SIM_COST_BAND_IR)"
v=$(ir bench_band_ "$B/vision_bench" band none $n)
echo "   band 640 x 96, no stick                $(printf %10s "$v") $(printf %10s "$(per "$v" $n)") |"

n=32
for row in "A 1 FOUND[0]" "B 1 FOUND[0]" "near3 1 WIDE" "near1 1 WIDE" "A 4 FOUND[1]" \
           "faint 4 FOUND[1]" "A 16 FOUND[2]" "none 1 NONE[0]" "none 4 NONE[1]" "none 16 NONE[2]" \
           "faint 1 -" "faint2 1 -"; do
    set -- $row
    v=$(ir bench_refine_ "$B/vision_bench" refine "$1" "$2" $n)
    what=$(sed -n 's/^refine [^:]*: \(.*\)$/\1/p' "$(logof bench_refine_ "$B/vision_bench" refine "$1" "$2" $n)" | head -1)
    echo "   refine $(printf %-7s "$1") rows averaged $(printf %-2s "$2")        $(printf %10s "$v") $(printf %10s "$(per "$v" $n)") | $3   ($what)"
done
echo "   cost table: GL_SIM_COST_REFINE_FOUND_IR $(table GL_SIM_COST_REFINE_FOUND_IR)   GL_SIM_COST_REFINE_NONE_IR $(table GL_SIM_COST_REFINE_NONE_IR)   GL_SIM_COST_REFINE_WIDE_IR $(table GL_SIM_COST_REFINE_WIDE_IR)"

v=$(ir bench_stats_ "$B/vision_bench" stats A $n)
echo "   strip statistics 96 x 480              $(printf %10s "$v") $(printf %10s "$(per "$v" $n)") | GL_SIM_COST_STRIP_STATS_IR $(table GL_SIM_COST_STRIP_STATS_IR)"
n=16
v=$(ir bench_render_ "$B/vision_bench" render $n)
echo "   result screen (gl_ui_render)           $(printf %10s "$v") $(printf %10s "$(per "$v" $n)") | GL_SIM_COST_RENDER_IR $(table GL_SIM_COST_RENDER_IR)"
v=$(ir bench_estimate_ "$B/solver_bench" typical)
echo "   putt estimate, typical Quick Read      $(printf %10s "$v")            | $(table GL_SIM_COST_SOLVE_BASE_IR) + $(table GL_SIM_COST_SOLVE_STEP_IR) per RK4 step ($(grep -h -o '[0-9]* RK4 steps' "$(logof bench_estimate_ "$B/solver_bench" typical)" | head -1))"

echo "== whole reads: measured (gl_read_step and below) against the sum the cost table gives"
echo "   scene      measured    cost table   table - measured"
for sc in A B near3 near1 faint faint2 person none; do
    v=$(ir gl_read_step "$B/vision_bench" read $sc)
    m=$(sed -n 's/.*total \([0-9.]*\) M instructions.*/\1/p' "$(logof gl_read_step "$B/vision_bench" read $sc)" | head -1)
    mi=$(awk "BEGIN { printf \"%d\", $m * 1000000 }")
    echo "   $(printf %-7s $sc) $(printf %11s "$v") $(printf %11s "$mi")   $(pct "$mi" "$v")"
done
echo "== the nominal read of tests/test_read.c (the figure of the README): A_nominal, one read"
v=$(ir gl_read_step "$B/tests/test_read" A_nominal 1)
echo "   gl_read_step and below: $v instructions"
