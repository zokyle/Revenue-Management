/*
 * cross_sizes.c - NOT FIRMWARE (it is in tools/, which no firmware target
 * compiles): the sizes of the application object and of its large parts AS
 * THE CROSS COMPILER LAYS THEM OUT, for the RAM table of the README.
 *
 * `make cross` compiles this file with the firmware's own cross flags and
 * reads the sizes of the arrays below from the object's symbol table
 * (arm-none-eabi-nm -S): sizeof(part) = size of glsz_<part>.  Nothing is
 * linked or run.  The parts of gl_app_t listed here do not overlap, so
 * "gl_app_t less the listed parts" is what is left for everything else,
 * and the table adds up by construction (tools/readme_check.py).
 */
#include "gl_app.h"

#define APP ((gl_app_t *)0)
#define PART(name, expr) char glsz_##name[sizeof(expr)]

PART(app, gl_app_t);
/* the camera pipeline, gl_read_t, and inside it */
PART(read, APP->read);
PART(read_img, APP->read.img);
PART(read_band_work, APP->read.band_work);
PART(read_stick_work, APP->read.stick_work);
PART(read_band, APP->read.band);
/* display */
PART(gfx, APP->gfx);
PART(lcd, APP->lcd);
/* USB protocol */
PART(proto, APP->proto);
/* solver: inputs, work area */
PART(meas_cur, APP->meas_cur);
PART(meas, APP->meas);
PART(solve_meas, APP->solve_meas);
PART(solver_work, APP->solver_work);
PART(est, APP->est);
/* storage, log, factory commands */
PART(store, APP->store);
PART(log, APP->log);
PART(fac, APP->fac);
/* small ones the README names */
PART(ui, APP->ui);
PART(view, APP->view);
PART(motion, APP->motion);
PART(one_meas, gl_measurements_t);
PART(one_stick_work, gl_vis_stick_work_t);
PART(patch_fit, gl_patch_fit_t);
