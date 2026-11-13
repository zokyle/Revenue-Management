/*
 * gl_sim_cost.h - what the firmware's computation costs: the table behind
 * the simulator's compute-time model.  HOST ONLY.
 *
 * The simulator runs the firmware's code natively and for nothing; on the
 * target the vision of one read is tens of millions of instructions.  At
 * every gl_hal_trace(point, work) the simulator therefore charges simulated
 * time for the stage that has just ended:
 *
 *     time = instructions(point, work) x cycles per instruction / core clock
 *
 * instructions(point, work) comes from this table.  The unit is ONE HOST
 * INSTRUCTION of the -O2 x86-64 build as valgrind's callgrind counts them
 * (Ir): that is what can be measured here.  Every figure below was measured
 * with tools/vision_cost.sh (`make profile`), which also re-measures them
 * and reports the difference from this table; the scenes are those of
 * tools/vision_bench.c.  A stage's cost depends on the scene (how many rows
 * carry a line, how many columns the coarse search covers); the table holds
 * the figures of the nominal scenes and `make profile` shows by how much a
 * whole read of each scene differs from the sum the table gives (within
 * about 10 % for reads that find the stick).
 *
 * The cycles-per-instruction factor is NOT measured (no board exists): see
 * GL_SIM_CPI_* in gl_sim.h for the low / nominal / high cases and the
 * README, "Run time", for what the factor stands for.
 */
#ifndef GL_SIM_COST_H
#define GL_SIM_COST_H

/** GL_TRACE_VISION_BAND: gl_vis_band_analyse() on the 640 x 96 band (work =
 *  its pixels; other sizes are scaled by the pixel count). */
#define GL_SIM_COST_BAND_IR 14270000u
#define GL_SIM_COST_BAND_PX (640u * 96u)

/** GL_TRACE_VISION_STRIP: one gl_vis_stick_refine() of a 96 x 480 strip per
 *  attempt, by the rows averaged (1, 4, 16) and by whether it found a line.
 *  FOUND: scenes A and B unbinned (1.38 and 1.39 million), scene A with 4
 *  and 16 rows.  NONE: the scene without a stick (an attempt that fails on a
 *  faint stick costs more: it gets further before it gives up).  A line
 *  wider than the narrowest window (GL_TRACE_STRIP_WIDE: 3 m and 1.5 m
 *  sticks measured 1.76 and 2.19 million) is charged the WIDE figure instead:
 *  its second pass measures every row again. */
#define GL_SIM_COST_REFINE_FOUND_IR { 1390000u, 960000u, 760000u }
#define GL_SIM_COST_REFINE_NONE_IR { 650000u, 300000u, 180000u }
#define GL_SIM_COST_REFINE_WIDE_IR 1970000u
/** ... plus gl_vis_strip_stats() where it was computed (GL_TRACE_STRIP_STATS) */
#define GL_SIM_COST_STRIP_STATS_IR 440000u

/** GL_TRACE_VISION_GROUP: segment fits, timing correction, disparity. */
#define GL_SIM_COST_GROUP_IR 40000u

/** GL_TRACE_SOLVE: gl_solver_estimate*(): the fit and the fixed part of the
 *  aim solve, plus the trial rolls per RK4 step (work = the steps). */
#define GL_SIM_COST_SOLVE_BASE_IR 40000u
#define GL_SIM_COST_SOLVE_STEP_IR 351u

/** GL_TRACE_RENDER: gl_ui_render() of the result screen (the transfer to the
 *  panel is bus time, which the simulator charges anyway). */
#define GL_SIM_COST_RENDER_IR 234000u

#endif /* GL_SIM_COST_H */
