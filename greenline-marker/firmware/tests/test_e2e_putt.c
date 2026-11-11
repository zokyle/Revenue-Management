/*
 * test_e2e_putt.c - from the green to the pixels: the putt estimate on the
 * display, through the real read sequence (IMU average, cameras, vision,
 * hand-over, estimator, view, renderer, LCD driver) on the host simulator.
 *
 * For every scene the test
 *   1. lets the firmware read it (Quick Read, Precision Read, Survey with 2
 *      to 4 drops, flag-out fallback, a left-camera-only read, an ambiguous
 *      read, the estimator's fallbacks);
 *   2. MEASURES THE DRAWN LINE FROM THE PANEL MEMORY of the LCD model,
 *      blind: runs of black pixels of the line's width in every row, a
 *      robust straight-line fit through their centres.  Nothing the
 *      firmware computed is used to find the line;
 *   3. runs the reference on the very record the application built
 *      (the double-precision build of the solver with the tolerances of the
 *      reference vectors: tests/solver/gl_solver_ref.h; `make appdiff` runs
 *      the PYTHON reference itself on the same records, dumped to a file)
 *      and on the TRUE scene (true slope, bearing, range, elevations);
 *   4. compares: the drawn direction with the reference's aim, within the
 *      display's quantisation; the side of the break, uphill / downhill and
 *      the fall-line arrow with the scene, in numbers; the distance, the
 *      plays-like distance, the break in cups and the slope as SHOWN (the
 *      strings, and their glyphs on the panel) with the reference.
 *
 * Usage:  test_e2e_putt [dump-file]
 *         With a file name every estimator call is also written there, one
 *         JSON object per line, for tools/app_diff.py.
 */
#include "gl_e2e_world.h"

#include "gl_solver_ref.h"

static FILE *dump_;

static uint32_t now_ms_(void)
{
    return (uint32_t)(gl_sim_now_us() / 1000u);
}

/* ======================================================================= */
/* the drawn line, measured from the panel                                  */
/* ======================================================================= */

typedef struct {
    bool found;
    double k;        /* dx / dy of the line on the panel (x right, y down) */
    double c;        /* x at y = 0 */
    unsigned rows;   /* run centres on the line */
    double rms;      /* of those centres about the line, px */
} line_t;

#define LINE_MAX_RUNS 900

/* The aim line is 6 px wide (plus the edge dither).  Collect the centres of
 * all horizontal runs of black pixels 5 to 9 px long in the panel memory,
 * find the straight line that the most of them lie on (every pair of
 * centres at least 25 rows apart proposes one), refine it by least squares.
 * Text strokes are 1 px, the confidence boxes and the icons contribute a few
 * runs of that length: they are outvoted. */
static void measure_line_(line_t *out)
{
    static double cx[LINE_MAX_RUNS], cy[LINE_MAX_RUNS];
    unsigned n = 0, best = 0;
    double k = 0.0, c = 0.0;

    memset(out, 0, sizeof(*out));
    for (int y = 0; y < 128; y++) {
        int x = 0;
        while (x < 128) {
            int x0;
            if (!panel_black_(x, y)) {
                x++;
                continue;
            }
            x0 = x;
            while (x < 128 && panel_black_(x, y)) {
                x++;
            }
            if (x - x0 >= 5 && x - x0 <= 9 && n < LINE_MAX_RUNS) {
                cx[n] = 0.5 * (double)(x0 + x - 1);
                cy[n] = (double)y;
                n++;
            }
        }
    }
    for (unsigned i = 0; i < n; i++) {
        for (unsigned j = i + 1u; j < n; j++) {
            unsigned in = 0;
            double kk, cc;
            if (cy[j] - cy[i] < 25.0) {
                continue;
            }
            kk = (cx[j] - cx[i]) / (cy[j] - cy[i]);
            cc = cx[i] - kk * cy[i];
            for (unsigned m = 0; m < n; m++) {
                in += (fabs(cx[m] - (kk * cy[m] + cc)) <= 1.3) ? 1u : 0u;
            }
            if (in > best) {
                best = in;
                k = kk;
                c = cc;
            }
        }
    }
    if (best < 20u) {
        return;
    }
    for (int pass = 0; pass < 3; pass++) {
        const double gate = (pass == 0) ? 1.3 : 1.0;
        double sx = 0, sy = 0, sxy = 0, syy = 0, ss = 0;
        unsigned m_in = 0;
        for (unsigned m = 0; m < n; m++) {
            if (fabs(cx[m] - (k * cy[m] + c)) <= gate) {
                sx += cx[m];
                sy += cy[m];
                sxy += cx[m] * cy[m];
                syy += cy[m] * cy[m];
                m_in++;
            }
        }
        if (m_in < 20u) {
            return;
        }
        {
            const double my = sy / m_in, mx = sx / m_in;
            const double vyy = syy / m_in - my * my;
            if (!(vyy > 1.0)) {
                return;
            }
            k = (sxy / m_in - mx * my) / vyy;
            c = mx - k * my;
        }
        for (unsigned m = 0; m < n; m++) {
            const double r = cx[m] - (k * cy[m] + c);
            if (fabs(r) <= gate) {
                ss += r * r;
            }
        }
        out->rows = m_in;
        out->rms = sqrt(ss / m_in);
    }
    out->found = true;
    out->k = k;
    out->c = c;
}

/* Smallest difference between two line ORIENTATIONS (mod pi), radians. */
static double orient_diff_(double a, double b)
{
    double d = fmod(a - b, PI_D);
    if (d > 0.5 * PI_D) {
        d -= PI_D;
    } else if (d < -0.5 * PI_D) {
        d += PI_D;
    }
    return d;
}

/* Solid or dashed?  Take the pixels that a SOLID line of this aim inks and a
 * DASHED one (9 px on, 7 px off) leaves white - the gaps between the dashes -
 * and return the fraction of them that is black on the panel: near 1 for a
 * solid line (less where labels lie over it), near 0 for a dashed one. */
static double ink_in_the_dash_gaps_(float aim_rad, float ball_az_rad)
{
    static gl_gfx_t solid, dashed;
    gl_gfx_aim_info_t info;
    unsigned n = 0, black = 0;

    gl_gfx_init(&solid);
    gl_gfx_set_clip(&solid, true);
    gl_gfx_clear(&solid, GL_INK_WHITE);
    gl_gfx_aim_line_styled(&solid, aim_rad, ball_az_rad, 3.0f, false, &info);
    gl_gfx_init(&dashed);
    gl_gfx_set_clip(&dashed, true);
    gl_gfx_clear(&dashed, GL_INK_WHITE);
    gl_gfx_aim_line_styled(&dashed, aim_rad, ball_az_rad, 3.0f, true, &info);
    for (int y = 0; y < 128; y++) {
        for (int x = 0; x < 128; x++) {
            if (!gl_gfx_get(&solid, x, y) && gl_gfx_get(&dashed, x, y)) {
                n++;
                black += panel_black_(x, y) ? 1u : 0u;
            }
        }
    }
    return (n >= 100u) ? (double)black / (double)n : (double)NAN;
}

/* The glyphs of `text`, as gl_ui.c draws a label centred on (cx, y): every
 * pixel of the label's box on the panel must be what a white box with that
 * text gives.  Returns the number of pixels that differ. */
static unsigned label_mismatch_(int cx, int y, const char *text)
{
    static gl_gfx_t scratch;
    const int w = gl_gfx_text_width(text, 1);
    unsigned bad = 0;
    gl_gfx_init(&scratch);
    gl_gfx_set_clip(&scratch, true);
    gl_gfx_clear(&scratch, GL_INK_BLACK);
    gl_gfx_rect(&scratch, cx - w / 2 - 2, y - 2, w + 4, GL_FONT_H + 4, GL_INK_WHITE);
    gl_gfx_text_centred(&scratch, cx, y, text, 1, GL_INK_BLACK);
    for (int yy = y - 2; yy < y - 2 + GL_FONT_H + 4; yy++) {
        for (int xx = cx - w / 2 - 2; xx < cx - w / 2 - 2 + w + 4; xx++) {
            if (!gl_gfx_in_clip(&scratch, xx, yy)) {
                continue;
            }
            bad += (panel_black_(xx, yy) != !gl_gfx_get(&scratch, xx, yy)) ? 1u : 0u;
        }
    }
    return bad;
}

/* The fall-line arrow of the result screen: where its ink lies relative to
 * the centre of the rose.  Returns the direction (rad, CCW from up) from the
 * centre to the ink's centroid, or NAN. */
static double rose_direction_(int rose_x)
{
    double sx = 0, sy = 0;
    unsigned n = 0;
    for (int y = 46; y <= 70; y++) {
        for (int x = rose_x - 12; x <= rose_x + 12; x++) {
            const double dx = (double)x - rose_x, dy = (double)y - 58.0;
            if (dx * dx + dy * dy <= 11.0 * 11.0 && panel_black_(x, y)) {
                sx += dx;
                sy += dy;
                n++;
            }
        }
    }
    if (n < 10u || sx * sx + sy * sy < 0.04 * (double)n * (double)n) {
        return (double)NAN;
    }
    return atan2(-sx, -sy); /* screen vector (-sin t, -cos t) points along t */
}

/* Fraction of the points along the line through the screen centre in
 * direction `angle` (rad, CCW from up) that are black on the panel: about 1
 * for a solid line, about 0.6 for the dashed substitute of a line that
 * leaves the aperture, about 0 where nothing is drawn. */
static double coverage_through_centre_(double angle)
{
    unsigned black = 0, total = 0;
    for (int i = -100; i <= 100; i++) {
        const double t = 0.5 * (double)i;
        const int x = (int)floor(63.5 - t * sin(angle) + 0.5);
        const int y = (int)floor(63.5 - t * cos(angle) + 0.5);
        if (x < 0 || x > 127 || y < 0 || y > 127) {
            continue;
        }
        total++;
        black += panel_black_(x, y) ? 1u : 0u;
    }
    return (total > 0u) ? (double)black / (double)total : 0.0;
}

/* The leading number of a shown string ("19.6FT" -> 19.6, "<2.5 CUP" -> 2.5). */
static double shown_number_(const char *s)
{
    while (*s != '\0' && !((*s >= '0' && *s <= '9') || *s == '-')) {
        s++;
    }
    return (*s != '\0') ? atof(s) : (double)NAN;
}

/* ======================================================================= */
/* the reference                                                            */
/* ======================================================================= */

static void to_ref_(const gl_measurements_t *m, gl_ref_meas_t *r)
{
    memset(r, 0, sizeof(*r));
    r->f_px = (double)m->f_px;
    r->baseline = (double)m->baseline_m;
    r->h_cam = (double)m->h_cam_m;
    r->tilt[0] = (double)m->tilt_x;
    r->tilt[1] = (double)m->tilt_y;
    r->tilt_reads = m->tilt_reads;
    r->flag_found = m->flag_found;
    r->flag_base_visible = m->flag_base_visible;
    r->flag_top_visible = m->flag_top_visible;
    r->flag_bearing = (double)m->flag_bearing_rad;
    r->flag_disparity = (double)m->flag_disparity_px;
    r->flag_low_elev = (double)m->flag_low_elev_rad;
    r->flag_top_elev = (double)m->flag_top_elev_rad;
    r->stick_height_est = (double)m->stick_height_est_m;
    r->stick_height_rel_sigma = (double)m->stick_height_rel_sigma;
    r->n_horizon = m->n_horizon;
    for (unsigned i = 0; i < m->n_horizon; i++) {
        r->horizon_az[i] = (double)m->horizon_az_rad[i];
        r->horizon_elev[i] = (double)m->horizon_elev_rad[i];
    }
    r->grain_kappa = (double)m->grain_kappa;
    r->grain_azimuth = (double)m->grain_azimuth_rad;
    r->stimp_ft = (double)m->stimp_ft;
    r->user_distance = (double)m->user_distance_m;
}

/* The records of the estimator call the application has just made. */
static unsigned app_records_(gl_ref_meas_t rec[GL_REF_MAX_DROPS], unsigned *ball)
{
    if (app.solve_drops <= 1u) {
        to_ref_(&app.meas_cur, &rec[0]);
        *ball = 0;
        return 1;
    }
    for (unsigned i = 0; i < app.solve_drops; i++) {
        to_ref_(&app.meas[i], &rec[i]);
    }
    *ball = app.solve_ball;
    return app.solve_drops;
}

/* The TRUE scene as a placement record: the same fields, computed from the
 * world instead of measured.  What is available (disparity, stick top, the
 * base classification, the horizon samples of method B2) is taken over from
 * the application's record `like`: the truth of what was MEASURABLE, with
 * the true value of everything that was measured. */
static void truth_record_(const gl_ref_meas_t *like, gl_ref_meas_t *r)
{
    const gl_vec3_t u = up_of_(W.slope_x, W.slope_y);
    const double sx = -W.dist_m * sin(W.bearing_rad), sy = W.dist_m * cos(W.bearing_rad);
    const double by = (double)GL_CFG_BALL_CENTRE_Y_MM * 0.001;
    const double hy = (double)GL_CFG_CAM_LEFT_Y_MM * 0.001;
    const double cam[3] = { (double)W.cam[0].pos_m.x, (double)W.cam[0].pos_m.y,
                            (double)W.cam[0].pos_m.z };
    const double up[3] = { (double)u.x, (double)u.y, (double)u.z };

    *r = *like;
    /* device +x = marker +y (out of the visor), device +y = marker -x (left) */
    r->tilt[0] = W.slope_y;
    r->tilt[1] = -W.slope_x;
    if (!like->flag_found || !W.stick) {
        return;
    }
    r->flag_bearing = atan2(-sx, sy - by); /* from the ball */
    if (!isnan(like->flag_disparity)) {
        r->flag_disparity = like->f_px * like->baseline / sqrt(sx * sx + (sy - hy) * (sy - hy));
    }
    for (int end = 0; end < 2; end++) {
        /* base, then top: elevation above the gravity-level plane as the
         * left camera sees it */
        const double h = (end == 0) ? 0.0 : W.height_m;
        const double p[3] = { sx + h * up[0] - cam[0], sy + h * up[1] - cam[1], h * up[2] - cam[2] };
        const double rise = p[0] * up[0] + p[1] * up[1] + p[2] * up[2];
        const double run = sqrt(p[0] * p[0] + p[1] * p[1] + p[2] * p[2] - rise * rise);
        if (end == 0) {
            r->flag_low_elev = atan2(rise, run);
        } else if (like->flag_top_visible) {
            r->flag_top_elev = atan2(rise, run);
        }
    }
}

/* ======================================================================= */
/* one row of the comparison table                                          */
/* ======================================================================= */

typedef struct {
    char name[64];
    bool line;                 /* an aim line was expected and found */
    bool dashed;               /* ... and it is the dashed (tentative) one, by its pixels */
    double ref_aim;            /* reference on the application's record: aim in the read frame */
    double true_aim;           /* reference on the true scene */
    double fw_aim;             /* the firmware's (single precision) */
    double drawn_aim;          /* measured from the pixels, brought back to the read frame */
    int aim_source, solve_status;
    gl_ui_result_text_t text;
    int boxes;
} row_t;

#define MAX_ROWS 40
static row_t rows_[MAX_ROWS];
static unsigned n_rows_;
/* true-scene records of the drops of the Survey in progress */
static gl_ref_meas_t truth_[GL_REF_MAX_DROPS];

/* worst differences over all scenes, for the summary */
static double worst_draw_mrad_, worst_fw_mrad_, worst_true_mrad_;

static void dump_num_(const char *key, double v, bool last)
{
    if (isfinite(v)) {
        fprintf(dump_, "\"%s\": %.17g%s", key, v, last ? "" : ", ");
    } else {
        fprintf(dump_, "\"%s\": null%s", key, last ? "" : ", ");
    }
}

static void dump_meas_(const gl_ref_meas_t *r)
{
    fprintf(dump_, "{");
    dump_num_("f_px", r->f_px, false);
    dump_num_("baseline", r->baseline, false);
    dump_num_("h_cam", r->h_cam, false);
    fprintf(dump_, "\"tilt\": [%.17g, %.17g], \"tilt_reads\": %d, \"flag_found\": %s, ", r->tilt[0],
            r->tilt[1], r->tilt_reads, r->flag_found ? "true" : "false");
    dump_num_("flag_bearing", r->flag_bearing, false);
    dump_num_("flag_disparity", r->flag_disparity, false);
    dump_num_("flag_low_elev", r->flag_low_elev, false);
    fprintf(dump_, "\"flag_base_visible\": %s, \"flag_top_visible\": %s, ",
            r->flag_base_visible ? "true" : "false", r->flag_top_visible ? "true" : "false");
    dump_num_("flag_top_elev", r->flag_top_elev, false);
    dump_num_("stick_height_est", r->stick_height_est, false);
    dump_num_("stick_height_rel_sigma", r->stick_height_rel_sigma, false);
    for (int which = 0; which < 2; which++) {
        fprintf(dump_, "\"%s\": [", (which == 0) ? "horizon_az" : "horizon_elev");
        for (int i = 0; i < r->n_horizon; i++) {
            const double v = (which == 0) ? r->horizon_az[i] : r->horizon_elev[i];
            if (isfinite(v)) {
                fprintf(dump_, "%s%.17g", (i > 0) ? ", " : "", v);
            } else {
                fprintf(dump_, "%snull", (i > 0) ? ", " : "");
            }
        }
        fprintf(dump_, "], ");
    }
    dump_num_("grain_kappa", r->grain_kappa, false);
    dump_num_("grain_azimuth", r->grain_azimuth, false);
    dump_num_("stimp_ft", r->stimp_ft, false);
    dump_num_("user_distance", r->user_distance, true);
    fprintf(dump_, "}");
}

static void dump_est_(const char *key, const gl_ref_est_t *e)
{
    fprintf(dump_, "\"%s\": {\"status\": %d, ", key, e->status);
    dump_num_("phi", e->phi, false);
    dump_num_("aim_azimuth_device", e->aim_azimuth_device, false);
    dump_num_("v0", e->v0, false);
    dump_num_("plays_like", e->plays_like, false);
    dump_num_("break_cups", e->break_cups, false);
    dump_num_("distance", e->distance, false);
    dump_num_("distance_sigma", e->distance_sigma, false);
    dump_num_("bearing", e->bearing, false);
    dump_num_("slope_pct", e->slope_pct, false);
    dump_num_("fall_line_azimuth_device", e->fall_line_azimuth_device, false);
    dump_num_("dz_hole", e->dz_hole, false);
    dump_num_("confidence", e->confidence, false);
    fprintf(dump_, "\"base_hidden\": %d, \"flag_missing\": %d, \"range_missing\": %d, "
                   "\"poor_horizon\": %d, \"fit_converged\": %d, \"aim_source\": %d, "
                   "\"solve_status\": %d}",
            e->base_hidden, e->flag_missing, e->range_missing, e->poor_horizon, e->fit_converged,
            e->aim_source, e->solve_status);
}

/* The firmware's own estimate in the layout of the reference's. */
static void fw_est_(gl_ref_est_t *e)
{
    memset(e, 0, sizeof(*e));
    e->status = (int)app.solver_status;
    e->phi = (double)app.est.phi_rad;
    e->aim_azimuth_device = (double)app.est.aim_azimuth_device_rad;
    e->v0 = (double)app.est.v0_mps;
    e->plays_like = (double)app.est.plays_like_m;
    e->break_m = (double)app.est.break_m;
    e->break_cups = (double)app.est.break_cups;
    e->distance = (double)app.est.distance_m;
    e->distance_sigma = (double)app.est.distance_sigma_m;
    e->bearing = (double)app.est.bearing_rad;
    e->slope_pct = (double)app.est.slope_pct;
    e->fall_line_azimuth_device = (double)app.est.fall_line_azimuth_device_rad;
    e->dz_hole = (double)app.est.dz_hole_m;
    e->confidence = (double)app.est.confidence;
    e->base_hidden = app.est.base_hidden;
    e->flag_missing = app.est.flag_missing;
    e->range_missing = app.est.range_missing;
    e->poor_horizon = app.est.poor_horizon;
    e->fit_converged = app.est.fit_converged;
    e->aim_source = app.est.aim_source;
    e->solve_status = app.est.solve_status;
}

typedef struct {
    bool expect_line;       /* the marker lies at the ball: a line must be drawn */
    bool on_screen;         /* ... and inside the aperture */
    bool solved;            /* the aim is a solution (solid line, break quoted) */
    bool check_truth;       /* compare with the reference on the true scene */
    double truth_tol_mrad;
    double view_yaw;        /* true yaw of the marker since the read (Precision spin) */
} expect_t;

/*
 * Everything that is checked for a result on the screen; adds one row to
 * the table.  `truth` = the true-scene records in the order of the
 * application's (NULL: no comparison with the true scene).
 */
static double least_solid_ink_ = 2.0, most_dashed_ink_ = -1.0;

static void check_result_(const char *name, const expect_t *x, const gl_ref_meas_t *truth)
{
    gl_ref_meas_t rec[GL_REF_MAX_DROPS];
    gl_ref_est_t ref, tru, fw;
    gl_ref_opt_t opt;
    unsigned ball = 0;
    const unsigned n = app_records_(rec, &ball);
    row_t *row = &rows_[(n_rows_ < MAX_ROWS) ? n_rows_ : MAX_ROWS - 1u];
    line_t ln;
    const double yaw = (double)app.cur.view_yaw_rad;

    memset(row, 0, sizeof(*row));
    snprintf(row->name, sizeof(row->name), "%s", name);
    n_rows_++;
    GL_CHECK_EQ(app.ui.state, GL_UI_SHOW_RESULT);
    GL_CHECK_EQ(app.solver_status, GL_OK);
    GL_CHECK(app.view.have_result);

    /* ---- the reference on the application's record ---- */
    opt.method = app.solve_opt.method;
    opt.past = (double)app.solve_opt.past_m;
    opt.tight = 1;
    gl_ref_estimate(rec, n, ball, &opt, &ref);
    fw_est_(&fw);
    GL_CHECK_EQ(ref.status, GL_OK);
    memset(&tru, 0, sizeof(tru));
    if (truth != NULL) {
        gl_ref_estimate(truth, n, ball, &opt, &tru);
        GL_CHECK_EQ(tru.status, GL_OK);
    }
    if (dump_ != NULL) {
        fprintf(dump_, "{\"name\": \"%s\", \"method\": %d, \"past\": %.9g, \"ball_index\": %u, "
                       "\"drops\": [", name, opt.method, opt.past, ball);
        for (unsigned i = 0; i < n; i++) {
            fprintf(dump_, "%s", (i > 0) ? ", " : "");
            dump_meas_(&rec[i]);
        }
        fprintf(dump_, "], \"truth\": [");
        for (unsigned i = 0; truth != NULL && i < n; i++) {
            fprintf(dump_, "%s", (i > 0) ? ", " : "");
            dump_meas_(&truth[i]);
        }
        fprintf(dump_, "], ");
        dump_est_("firmware", &fw);
        fprintf(dump_, ", ");
        dump_est_("c_double", &ref);
        fprintf(dump_, ", ");
    }
    /* flags and codes: the firmware's single-precision estimate against the
     * reference at its tight tolerances */
    GL_CHECK_EQ(fw.flag_missing, ref.flag_missing);
    GL_CHECK_EQ(fw.range_missing, ref.range_missing);
    GL_CHECK_EQ(fw.base_hidden, ref.base_hidden);
    GL_CHECK_EQ(fw.poor_horizon, ref.poor_horizon);
    GL_CHECK_EQ(fw.fit_converged, ref.fit_converged);
    GL_CHECK_EQ(fw.aim_source, ref.aim_source);
    GL_CHECK_EQ(fw.solve_status, ref.solve_status);
    GL_CHECK_NEAR(fw.distance, ref.distance, 1e-5 * ref.distance + 1e-6);
    GL_CHECK_NEAR(fw.slope_pct, ref.slope_pct, 1e-4);
    GL_CHECK_NEAR(fw.confidence, ref.confidence, 1e-4);
    row->aim_source = fw.aim_source;
    row->solve_status = fw.solve_status;
    row->ref_aim = ref.aim_azimuth_device;
    row->true_aim = (truth != NULL) ? tru.aim_azimuth_device : (double)NAN;
    row->fw_aim = fw.aim_azimuth_device;
    row->drawn_aim = (double)NAN;
    GL_CHECK_EQ(app.view.solved, x->solved);
    GL_CHECK_EQ(x->solved, fw.aim_source == GL_AIM_FROM_PATCH || fw.aim_source == GL_AIM_FROM_PLANE);
    if (x->solved) {
        /* a solution: single precision against the reference */
        const double d = 1000.0 * fabs(gl_wrap_pi((float)(fw.aim_azimuth_device - ref.aim_azimuth_device)));
        GL_CHECK(d < 0.5);
        GL_CHECK_NEAR(fw.v0, ref.v0, 1e-3 * ref.v0);
        GL_CHECK_NEAR(fw.break_cups, ref.break_cups, 0.01 + 1e-3 * fabs(ref.break_cups));
        if (d > worst_fw_mrad_) {
            worst_fw_mrad_ = d;
        }
    }

    /* ---- the screen ---- */
    GL_CHECK_EQ(panel_differs_from_framebuffer_(), 0u);
    {
        /* the panel shows gl_ui_render() of the view, nothing else */
        static gl_gfx_t again;
        unsigned bad = 0;
        gl_gfx_init(&again);
        gl_ui_render(&app.ui, &app.view, &again);
        for (unsigned i = 0; i < GL_GFX_BYTES; i++) {
            bad += (again.px[i] != gl_sim_lcd()->mem[i]) ? 1u : 0u;
        }
        GL_CHECK_EQ(bad, 0u);
    }
    gl_ui_result_text(&app.ui, &app.view, &row->text);
    row->boxes = gl_ui_conf_boxes(app.view.confidence);
    GL_CHECK_EQ(app.view.line_here, x->expect_line);
    measure_line_(&ln);
    if (x->expect_line) {
        /* the view's aim is the estimate's, turned into the marker's present frame */
        GL_CHECK_NEAR(gl_wrap_pi(app.view.aim_rad + app.cur.view_yaw_rad - app.est.aim_azimuth_device_rad),
                      0.0, 1e-5);
        GL_CHECK_NEAR(yaw, x->view_yaw, 0.02);
        if (!x->on_screen) {
            /* The true line leaves the aperture (more than about 13.5 degrees
             * off the visor axis): a DASHED parallel through the screen
             * centre shows the direction, an arrow the side.  Whatever else
             * it is, it is not a solid line. */
            const double cov = coverage_through_centre_((double)app.view.aim_rad);
            const double cov_off = coverage_through_centre_((double)app.view.aim_rad + 0.5);
            GL_CHECK(cov > 0.35 && cov < 0.80);
            GL_CHECK(cov_off < 0.25);
            GL_CHECK(!(ln.found && ln.rows >= 40u));
            row->drawn_aim = (double)NAN;
        } else {
            GL_CHECK(ln.found);
        }
        if (ln.found && x->on_screen) {
            /* a line through the ball position in direction a has dx/dy = tan(a) */
            const double drawn = atan(ln.k);
            const double d_view = orient_diff_(drawn, (double)app.view.aim_rad);
            const double bx = 63.5 - (double)GL_CFG_BALL_CENTRE_Y_PX * sin((double)app.view.ball_az_rad);
            const double byp = 63.5 - (double)GL_CFG_BALL_CENTRE_Y_PX * cos((double)app.view.ball_az_rad);
            const double miss = fabs(ln.k * byp + ln.c - bx) * cos(drawn);
            /* back to the read frame, on the branch of the firmware's aim */
            row->drawn_aim = fw.aim_azimuth_device + d_view;
            row->line = true;
            {
                const double d_ref = 1000.0 * fabs(orient_diff_(row->drawn_aim, ref.aim_azimuth_device));
                /* the display: 0.05 degree rms, 0.3 degree worst, for a free
                 * line; labels cover parts of this one.  0.35 degree = 6.1 mrad */
                GL_CHECK(fabs(d_view) < 0.0061);
                GL_CHECK(d_ref < 6.5);
                /* through the ball position, 246 px beyond the screen centre */
                GL_CHECK(miss < 3.0);
                GL_CHECK(ln.rows >= 30u);
                /* SOLID only for a solution of a putt whose distance is known
                 * (measured or dialled); long dashes for anything else, told
                 * from the panel's pixels in the gaps of the dashes. */
                {
                    const double ink = ink_in_the_dash_gaps_(app.view.aim_rad, app.view.ball_az_rad);
                    GL_CHECK(!isnan(ink));
                    row->dashed = ink < 0.3;
                    GL_CHECK_EQ(row->dashed, !app.view.solved || !(app.view.distance_m > 0.0f));
                    if (row->dashed) {
                        most_dashed_ink_ = (ink > most_dashed_ink_) ? ink : most_dashed_ink_;
                    } else {
                        least_solid_ink_ = (ink < least_solid_ink_) ? ink : least_solid_ink_;
                    }
                }
                if (d_ref > worst_draw_mrad_) {
                    worst_draw_mrad_ = d_ref;
                }
            }
        }
        if (x->check_truth && truth != NULL) {
            const double d = 1000.0 * fabs(gl_wrap_pi((float)(fw.aim_azimuth_device - tru.aim_azimuth_device)));
            GL_CHECK(d < x->truth_tol_mrad);
            if (d > worst_true_mrad_) {
                worst_true_mrad_ = d;
            }
        }
    } else {
        /* a Survey drop along the line: no aim line on the screen */
        GL_CHECK(!ln.found);
        GL_CHECK(strcmp(row->text.note, "PUT AT BALL") == 0);
    }

    /* ---- the numbers shown, against the reference ---- */
    {
        const bool dialled = app.settings.manual_distance_cm != 0u;
        const bool assumed = ref.flag_missing || ref.range_missing;
        const double unit = (app.settings.units == GL_UNITS_METRES)
                                ? 1.0 : ((app.settings.units == GL_UNITS_PACES) ? 0.9144 : 0.3048);
        if (assumed && !dialled) {
            GL_CHECK(strcmp(row->text.distance, "--") == 0);
            GL_CHECK(row->text.plays[0] == '\0');
        } else {
            GL_CHECK_NEAR(shown_number_(row->text.distance), ref.distance / unit, 0.051);
            GL_CHECK_EQ(strchr(row->text.distance, '?') != NULL, assumed);
            if (x->solved) {
                GL_CHECK(strncmp(row->text.plays, "PLAYS ", 6) == 0);
                GL_CHECK_NEAR(shown_number_(row->text.plays), ref.plays_like / unit, 0.052);
            } else {
                GL_CHECK(row->text.plays[0] == '\0');
            }
        }
        GL_CHECK_NEAR(shown_number_(row->text.slope), ref.slope_pct, 0.051);
        if (!x->solved || (assumed && !dialled)) {
            GL_CHECK(strcmp(row->text.brk, "BREAK ?") == 0);
        } else if (fabs(ref.break_cups) < 0.045) {
            GL_CHECK(strcmp(row->text.brk, "STRAIGHT") == 0);
        } else if (fabs(ref.break_cups) > 0.055) {
            GL_CHECK_NEAR(shown_number_(row->text.brk), fabs(ref.break_cups), 0.06);
            /* "<n CUP": aim left of the hole; "n CUP>": aim right */
            GL_CHECK_EQ(row->text.brk[0] == '<', ref.break_cups > 0.0);
            GL_CHECK_EQ(row->text.brk[strlen(row->text.brk) - 1u] == '>', ref.break_cups < 0.0);
        }
        /* and they are on the panel, glyph for glyph */
        GL_CHECK_EQ(label_mismatch_(64, 12, row->text.distance), 0u);
        if (row->text.plays[0] != '\0') {
            GL_CHECK_EQ(label_mismatch_(64, 24, row->text.plays), 0u);
        }
        if (row->text.note[0] != '\0' && app.view.flag_found) {
            GL_CHECK_EQ(label_mismatch_(64, 36, row->text.note), 0u);
        }
        GL_CHECK_EQ(label_mismatch_(64, 92, row->text.brk), 0u);
    }
    if (dump_ != NULL) {
        fprintf(dump_, "\"view\": {");
        dump_num_("aim_rad", (double)app.view.aim_rad, false);
        dump_num_("drawn_aim_read_frame", row->drawn_aim, false);
        dump_num_("yaw", yaw, false);
        dump_num_("confidence_shown", (double)app.view.confidence, false);
        fprintf(dump_, "\"dashed\": %s, ", row->dashed ? "true" : "false");
        fprintf(dump_, "\"line_here\": %s, \"solved\": %s, \"boxes\": %d}, \"shown\": {\"distance\": "
                       "\"%s\", \"plays\": \"%s\", \"note\": \"%s\", \"slope\": \"%s\", \"break\": "
                       "\"%s\", \"mode\": \"%s\"}}\n",
                app.view.line_here ? "true" : "false", app.view.solved ? "true" : "false", row->boxes,
                row->text.distance, row->text.plays, row->text.note, row->text.slope, row->text.brk,
                row->text.mode);
    }
    /* ---- the board: nothing objected, the fast clock is off again ---- */
    if (gl_sim_violation_total() != 0u) {
        printf("    first violation: %s\n", gl_sim_violations()->first);
    }
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
    GL_CHECK_EQ(gl_sim_clock(), GL_CLOCK_SLOW);
    GL_CHECK_EQ(gl_sim_stats()->clock_to_fast, gl_sim_stats()->clock_to_slow);
    GL_CHECK_EQ(gl_sim_stats()->heavy_while_slow, 0u);
}

/* The confidence shown, from the estimator's and the rule of app/gl_app.c
 * written out again here. */
static double expected_confidence_(void)
{
    double c = (double)app.est.confidence;
    if (app.cur.flag_found) {
        if (app.cur.tier == GL_READ_TIER_LEFT) {
            c *= 0.6;
        }
        if (app.cur.ambiguous) {
            c *= 0.6;
        }
        if (app.cur.tier >= GL_READ_TIER_STEREO && app.cur.disparity_sigma_px > 0.08f) {
            double s = 0.08 / (double)app.cur.disparity_sigma_px;
            c *= (s < 0.5) ? 0.5 : s;
        }
    }
    if (!app.est.fit_converged) {
        c *= 0.7;
    }
    if (app.est.aim_source == GL_AIM_STRAIGHT) {
        c = 0.0;
    } else if (app.est.aim_source == GL_AIM_BEST_EFFORT && c > 0.2) {
        c = 0.2;
    }
    return c;
}

/* ======================================================================= */
/* driving the marker                                                       */
/* ======================================================================= */

static void scene_(double dist, double bearing, double sx, double sy)
{
    W.dist_m = dist;
    W.bearing_rad = bearing;
    W.slope_x = sx;
    W.slope_y = sy;
    project_scene_();
}

static void power_on_(void)
{
    board_up_(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    watch_reset_();
}

/* The golfer picks the marker up and puts it down in a new place. */
static void replace_marker_(double dist, double bearing, double sx, double sy)
{
    const double t = (double)gl_sim_now_us() * 1e-6;
    W.t_pick_s = t + 0.5;
    W.t_place_s = t + 2.0;
    run_until_ms_((uint32_t)((t + 1.0) * 1000.0));
    scene_(dist, bearing, sx, sy);
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, (uint32_t)(t * 1000.0) + 12000u));
}

static void double_tap_(void)
{
    gl_app_post(&app, GL_EV_DOUBLE_TAP, 0);
    run_until_ms_(now_ms_() + 150u);
}

/* ======================================================================= */
/* 1. Quick Read: left and right breaks, uphill and downhill, 1.5 to 12 m   */
/* ======================================================================= */

typedef struct {
    const char *name;
    double dist, bearing, sx, sy; /* slope: uphill gradient, marker frame (x right, y forward) */
} scene_t;

GL_TEST(test_quick_read_scenes_line_and_numbers)
{
    static const scene_t scenes[] = {
        { "Quick 3 m, rises LEFT 2 %, level", 3.0, 0.030, -0.020, 0.000 },
        { "Quick 3 m, rises RIGHT 2 %, uphill 1.5 %", 3.0, -0.020, 0.020, 0.015 },
        { "Quick 6 m, rises RIGHT 1.2 %, downhill 2 %", 6.0, 0.050, 0.012, -0.020 },
        { "Quick 6 m, rises LEFT 1 %, uphill 1.5 %", 6.0, -0.040, -0.010, 0.015 },
        { "Quick 9 m, rises LEFT 0.8 %, downhill 1 %", 9.0, 0.020, -0.008, -0.010 },
        { "Quick 1.5 m, rises RIGHT 1.5 %, uphill 0.5 %", 1.5, 0.000, 0.015, 0.005 },
        { "Quick 12 m, rises RIGHT 0.6 %, uphill 1 %", 12.0, -0.030, 0.006, 0.010 },
        { "Quick 4.5 m, level green", 4.5, 0.010, 0.000, 0.000 },
    };
    for (size_t i = 0; i < GL_ARRAY_LEN(scenes); i++) {
        const scene_t *s = &scenes[i];
        gl_ref_meas_t rec, tru;
        expect_t x;
        double cross, along, ball_bearing;

        world_defaults_();
        scene_(s->dist, s->bearing, s->sx, s->sy);
        power_on_();
        GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 12000));
        if (app.ui.state != (uint8_t)GL_UI_SHOW_RESULT) {
            print_seen_();
            continue;
        }
        GL_CHECK_EQ(app.cur.tier, GL_READ_TIER_STEREO);
        to_ref_(&app.meas_cur, &rec);
        truth_record_(&rec, &tru);
        memset(&x, 0, sizeof(x));
        x.expect_line = true;
        x.on_screen = true;
        x.solved = true;
        x.check_truth = true;
        /* against the TRUE scene the firmware also carries its measurement
         * errors: 0.3 mrad of tilt is 1 to 4 mrad of aim (the aim moves by
         * about 0.7 rad per unit of cross slope at Stimp 10, more downhill) */
        x.truth_tol_mrad = 6.0;
        check_result_(s->name, &x, &tru);

        /* ---- the sign conventions, end to end, in numbers ---- */
        /* slope across and along the line to the hole, from the scene: the
         * putt frame is the marker frame turned by the hole's bearing */
        ball_bearing = atan2(W.dist_m * sin(W.bearing_rad),
                             W.dist_m * cos(W.bearing_rad) - (double)GL_CFG_BALL_CENTRE_Y_MM * 0.001);
        /* unit vector to the hole (marker x right, y forward): (-sin b, cos b);
         * unit vector to its LEFT: (-cos b, -sin b) */
        along = -s->sx * sin(ball_bearing) + s->sy * cos(ball_bearing);
        cross = -s->sx * cos(ball_bearing) - s->sy * sin(ball_bearing); /* > 0: rises to the left */
        /* device frame of the reference: +x out of the visor, +y LEFT */
        GL_CHECK_NEAR(app.meas_cur.tilt_x, s->sy, 0.0005);
        GL_CHECK_NEAR(app.meas_cur.tilt_y, -s->sx, 0.0005);
        GL_CHECK_NEAR(app.est.bearing_rad, ball_bearing, 0.001);
        if (fabs(cross) > 0.002) {
            /* ground rises to the LEFT of the line <=> the ball falls to the
             * right <=> aim LEFT of the hole <=> phi > 0 <=> break "<" */
            GL_CHECK_EQ(app.est.phi_rad > 0.0f, cross > 0.0);
            GL_CHECK_EQ(app.est.break_cups > 0.0f, cross > 0.0);
            GL_CHECK_EQ(app.view.break_cups > 0.0f, cross > 0.0);
            GL_CHECK_EQ(rows_[n_rows_ - 1u].text.brk[0] == '<', cross > 0.0);
            /* the DRAWN line is turned from the true direction of the hole
             * towards the high side: counter-clockwise (left) for phi > 0 */
            GL_CHECK_EQ(rows_[n_rows_ - 1u].drawn_aim - ball_bearing > 0.0, cross > 0.0);
            /* and its backward extension crosses the screen on the other
             * side of where a line straight at the hole would: further
             * RIGHT for an aim to the left */
            {
                line_t ln;
                measure_line_(&ln);
                GL_CHECK_EQ(ln.k * 63.5 + ln.c > 63.5 + (double)GL_CFG_BALL_CENTRE_Y_PX * sin(ball_bearing),
                            cross > 0.0);
            }
        } else {
            GL_CHECK(fabs((double)app.est.break_cups) < 0.3);
        }
        /* uphill: the putt plays longer than its length plus the 30 cm it is
         * hit past the hole; downhill shorter */
        if (fabs(along) > 0.002) {
            GL_CHECK_EQ(app.est.plays_like_m > app.est.distance_m + 0.30f, along > 0.0);
            GL_CHECK_EQ(app.est.dz_hole_m > 0.0f, along > 0.0);
            GL_CHECK_EQ(app.view.plays_like_m > app.view.distance_m + 0.30f, along > 0.0);
        }
        /* slope and fall line at the ball: the tilt reading */
        GL_CHECK_NEAR(app.view.slope_pct, 100.0 * sqrt(s->sx * s->sx + s->sy * s->sy), 0.06);
        if (s->sx * s->sx + s->sy * s->sy > 1e-6) {
            /* downhill is -slope: (-sx, -sy) in the marker frame, which is the
             * angle atan2(sx, -sy) counter-clockwise from forward */
            const double fall = atan2(s->sx, -s->sy);
            const int rose_x = (rows_[n_rows_ - 1u].drawn_aim > 0.0) ? 28 : 100;
            double arrow;
            GL_CHECK_NEAR(gl_wrap_pi((float)((double)app.view.fall_line_rad - fall)), 0.0, 0.03);
            /* the arrow on the panel points that way */
            arrow = rose_direction_(rose_x);
            if (isnan(arrow)) {
                arrow = rose_direction_((rose_x == 28) ? 100 : 28);
            }
            GL_CHECK(!isnan(arrow));
            GL_CHECK(fabs((double)gl_wrap_pi((float)(arrow - fall))) < 0.45);
        }
        /* the estimator's confidence is shown as it is: a clean stereo read */
        GL_CHECK_NEAR(app.view.confidence, expected_confidence_(), 1e-6);
        GL_CHECK_NEAR(app.view.confidence, app.est.confidence, 1e-6);
        GL_CHECK_EQ(app.view.note, GL_UI_NOTE_NONE);
        /* one capture and one solve: the clock went up once and came down */
        GL_CHECK_EQ(gl_sim_stats()->clock_to_fast, 1u);
        GL_CHECK(gl_sim_stats()->trace_points[GL_TRACE_SOLVE] == 1u);
    }
}

/* The fast clock is on from the start of the capture to the end of the
 * solve and at no other time; Stop mode is never entered with it. */
GL_TEST(test_core_clock_is_fast_for_capture_and_solve_only)
{
    uint64_t t_up = 0, t_down = 0;
    unsigned ups = 0, downs = 0;
    const gl_sim_stats_t *st;

    world_defaults_();
    power_on_();
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 12000));
    for (size_t i = 0; i < gl_sim_trace_count(); i++) {
        const gl_sim_trace_t *t = gl_sim_trace_at(i);
        if (t->type != (uint8_t)GL_SIM_TR_CLOCK || t->a == t->b) {
            continue;
        }
        if (t->a == (uint8_t)GL_CLOCK_FAST) {
            ups++;
            t_up = t->t_us;
        } else {
            downs++;
            t_down = t->t_us;
        }
    }
    st = gl_sim_stats();
    GL_CHECK_EQ(ups, 1u);
    GL_CHECK_EQ(downs, 1u);
    GL_CHECK_EQ(st->clock_to_fast, 1u);
    GL_CHECK_EQ(st->clock_to_slow, 1u);
    /* up when the CAPTURE state was entered, down when the result was ready */
    GL_CHECK(seen.n >= 6u);
    if (seen.n >= 6u) {
        GL_CHECK_EQ(seen.state[4], GL_UI_CAPTURE);
        GL_CHECK_NEAR((double)t_up / 1000.0, (double)seen.t_ms[4], 2.0);
        GL_CHECK_NEAR((double)t_down / 1000.0, (double)seen.t_ms[5], 2.0);
    }
    /* every piece of heavy computation ran at the fast clock */
    GL_CHECK_EQ(st->heavy_while_slow, 0u);
    GL_CHECK_EQ(st->trace_points[GL_TRACE_VISION_BAND], 1u);
    GL_CHECK_EQ(st->trace_points[GL_TRACE_VISION_STRIP], 4u * GL_APP_LRRL_REPEATS);
    GL_CHECK_EQ(st->trace_points[GL_TRACE_SOLVE], 1u);
    printf("    fast clock: on for %.0f ms of a Quick Read (capture %.0f ms .. result %.0f ms), "
           "%u vision trace points and 1 solve inside it, 0 outside; Stop-mode time so far %.2f s\n",
           (double)st->clock_fast_us / 1000.0, (double)t_up / 1000.0, (double)t_down / 1000.0,
           (unsigned)(st->trace_points[GL_TRACE_VISION_BAND] + st->trace_points[GL_TRACE_VISION_STRIP]),
           (double)st->stop_us / 1e6);
    /* while the result is shown the MCU is in Stop mode again, slow */
    run_until_ms_(now_ms_() + 5000u);
    GL_CHECK_EQ(gl_sim_clock(), GL_CLOCK_SLOW);
    GL_CHECK_EQ(gl_sim_violations()->clock, 0u);

    /* a read that ends without a solve (no flagstick, nothing dialled: the
     * distance prompt) does not leave the clock up either */
    world_defaults_();
    W.stick = false;
    power_on_();
    GL_CHECK(run_until_state_(GL_UI_SETTINGS_DIAL, 12000));
    run_until_ms_(now_ms_() + 200u);
    GL_CHECK_EQ(gl_sim_clock(), GL_CLOCK_SLOW);
    GL_CHECK_EQ(gl_sim_stats()->clock_to_fast, 1u);
    GL_CHECK_EQ(gl_sim_stats()->clock_to_slow, 1u);
    /* a read that is bumped in the middle of the capture: down at the abort,
     * up again for the re-read */
    world_defaults_();
    power_on_();
    W.jolt_at_s = 3.9;
    W.jolt_len_s = 0.25;
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 15000));
    GL_CHECK_EQ(gl_sim_stats()->clock_to_fast, 2u);
    GL_CHECK_EQ(gl_sim_stats()->clock_to_slow, 2u);
    GL_CHECK_EQ(gl_sim_clock(), GL_CLOCK_SLOW);
    /* a PLL that does not lock: the read still completes, at the slow clock */
    world_defaults_();
    board_up_(true);
    gl_sim_clock_fail(8);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    watch_reset_();
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 12000));
    GL_CHECK_EQ(app.solver_status, GL_OK);
    GL_CHECK_EQ(gl_sim_stats()->clock_to_fast, 0u);
    GL_CHECK(app.clock_fails >= 1u);
    GL_CHECK(gl_sim_stats()->heavy_while_slow > 30u); /* counted, not hidden */
    GL_CHECK_EQ(gl_sim_violation_total(), 0);
}

/* ======================================================================= */
/* 2. Precision Read: the line after the 180-degree spin                    */
/* ======================================================================= */

GL_TEST(test_precision_read_line_and_numbers)
{
    static const float acc_bias[3] = { 0.004f, -0.003f, 0.0f }; /* a device bias of 4 / 3 mrad */
    static const float gyro_bias[3] = { 0.004f, -0.002f, 0.001f };
    gl_ref_meas_t rec, tru;
    expect_t x;
    double t_now, single_err;

    world_defaults_();
    scene_(6.0, 0.05, -0.012, 0.016);
    board_up_(true);
    gl_sim_imu_set_errors(0.0008f, 0.002f, acc_bias, gyro_bias);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    watch_reset_();
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 12000));
    /* the single read carries the device bias, and its aim with it */
    to_ref_(&app.meas_cur, &rec);
    truth_record_(&rec, &tru);
    {
        gl_ref_est_t t;
        gl_ref_opt_t opt = { GL_SOLVER_METHOD_B1, 0.30, 1 };
        gl_ref_estimate(&tru, 1, 0, &opt, &t);
        single_err = 1000.0 * fabs((double)app.est.aim_azimuth_device_rad - t.aim_azimuth_device);
    }
    double_tap_();
    GL_CHECK_EQ(app.ui.state, GL_UI_PRECISION_WAIT_SPIN);
    t_now = (double)gl_sim_now_us() * 1e-6;
    W.turn_at_s = t_now + 0.5;
    W.turn_len_s = 1.2;
    W.turn_rad = 176.0 * PI_D / 180.0;
    GL_CHECK(run_until_state_(GL_UI_READ_TILT, (uint32_t)(t_now * 1000.0) + 5000u));
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, (uint32_t)(t_now * 1000.0) + 9000u));
    GL_CHECK(app.cur.precision && app.view.precision);
    GL_CHECK_EQ(app.meas_cur.tilt_reads, 2);

    to_ref_(&app.meas_cur, &rec);
    truth_record_(&rec, &tru);
    memset(&x, 0, sizeof(x));
    x.expect_line = true;
    x.on_screen = true;
    x.solved = true;
    x.check_truth = true;
    x.truth_tol_mrad = 3.0; /* the bias has cancelled */
    x.view_yaw = W.turn_rad;
    check_result_("Precision 6 m, rises LEFT 1.2 %, uphill 1.6 %, spun 176 deg", &x, &tru);
    /* the marker faces away from the hole: the ball position is behind it,
     * and the line is drawn through that point */
    GL_CHECK_NEAR(fabs((double)app.view.ball_az_rad), 176.0 * PI_D / 180.0, 0.02);
    GL_CHECK(strcmp(rows_[n_rows_ - 1u].text.mode, "2X") == 0);
    GL_CHECK(app.est.phi_rad > 0.0f); /* rises to the left: aim left */
    GL_CHECK(rows_[n_rows_ - 1u].text.brk[0] == '<');
    printf("    Precision Read with a device bias of (0.4, -0.3) %%: aim error against the true "
           "scene %.2f mrad single, %.2f mrad combined\n", single_err,
           1000.0 * fabs(rows_[n_rows_ - 1u].fw_aim - rows_[n_rows_ - 1u].true_aim));
    GL_CHECK(single_err > 3.0); /* the bias is worth several mrad of aim */
    /* the re-read needed no camera: the clock went up for its solve only */
    GL_CHECK_EQ(gl_sim_stats()->cam_rail_cycles, 1u);
    GL_CHECK_EQ(gl_sim_stats()->clock_to_fast, 2u);
    GL_CHECK_EQ(gl_sim_stats()->trace_points[GL_TRACE_SOLVE], 2u);
}

/* ======================================================================= */
/* 3. Survey with 2, 3 and 4 drops                                          */
/* ======================================================================= */

/* The true-scene record of the drop just read, into the Survey's list. */
static void survey_truth_(void)
{
    gl_ref_meas_t rec;
    const unsigned k = app.survey.count - 1u;
    to_ref_(&app.meas[k], &rec);
    truth_record_(&rec, &truth_[k]);
}

GL_TEST(test_survey_two_three_and_four_drops)
{
    expect_t x;
    memset(&x, 0, sizeof(x));
    x.solved = true;
    x.check_truth = true;
    x.truth_tol_mrad = 6.0;

    /* ---- 2 drops, walking back from the hole: 3 m short of the hole
     *      first, then the ball at 6 m.  The newest drop is the farthest:
     *      the marker lies at the ball and the line is drawn there. ---- */
    world_defaults_();
    scene_(3.0, -0.02, -0.006, -0.014);
    power_on_();
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 12000));
    double_tap_();
    double_tap_(); /* Precision prompt, then Survey: the shown read is drop 1 */
    GL_CHECK_EQ(app.ui.state, GL_UI_SURVEY_NEXT_DROP);
    GL_CHECK_EQ(app.survey.count, 1);
    survey_truth_();
    replace_marker_(6.0, 0.03, 0.010, -0.020);
    GL_CHECK_EQ(app.survey.count, 2);
    survey_truth_();
    GL_CHECK_EQ(app.solve_drops, 2);
    GL_CHECK_EQ(app.solve_ball, 1); /* the newest drop is the ball */
    GL_CHECK(app.line_here);
    GL_CHECK_EQ(app.solver_work.fit.n_drops, 2);
    GL_CHECK_NEAR(app.solver_work.fit.stations_m[1], 3.0, 0.15);
    x.expect_line = true;
    x.on_screen = true;
    check_result_("Survey 2 drops (3 m, then the ball at 6 m)", &x, truth_);
    GL_CHECK(strcmp(rows_[n_rows_ - 1u].text.mode, "D2") == 0);
    GL_CHECK_NEAR(app.est.distance_m, 6.0, 0.15);
    /* the slope shown is the tilt AT THE BALL, drop 2 */
    GL_CHECK_NEAR(app.view.slope_pct, 100.0 * sqrt(0.010 * 0.010 + 0.020 * 0.020), 0.06);

    /* ---- 3 drops, the usual way round: ball (6 m), half way (3 m), back
     *      to the ball.  At the second drop the marker is NOT at the ball:
     *      numbers, no line. ---- */
    world_defaults_();
    scene_(6.0, 0.04, 0.012, -0.020);
    power_on_();
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 12000));
    double_tap_();
    double_tap_();
    survey_truth_();
    replace_marker_(3.0, -0.02, -0.004, -0.015);
    GL_CHECK_EQ(app.survey.count, 2);
    survey_truth_();
    GL_CHECK_EQ(app.solve_ball, 0); /* the putt starts at drop 1 */
    GL_CHECK(!app.line_here);
    x.expect_line = false;
    x.check_truth = false;
    check_result_("Survey 3 drops: at drop 2 (3 m), not at the ball", &x, truth_);
    GL_CHECK(strcmp(rows_[n_rows_ - 1u].text.mode, "D2") == 0);
    GL_CHECK_NEAR(app.est.distance_m, 6.0, 0.15); /* from the ball, not from where it lies */
    replace_marker_(6.0, 0.03, 0.012, -0.020); /* back at the ball, a little differently placed */
    GL_CHECK_EQ(app.survey.count, 3);
    survey_truth_();
    GL_CHECK_EQ(app.solve_drops, 3);
    GL_CHECK_EQ(app.solve_ball, 2);
    GL_CHECK(app.line_here);
    GL_CHECK_EQ(app.solver_work.fit.n_drops, 3);
    x.expect_line = true;
    x.check_truth = true;
    check_result_("Survey 3 drops (ball 6 m, 3 m, ball again)", &x, truth_);
    GL_CHECK(strcmp(rows_[n_rows_ - 1u].text.mode, "D3") == 0);

    /* ---- 4 drops: ball (9 m), 6 m, 2 m, ball again ---- */
    world_defaults_();
    scene_(9.0, 0.02, -0.010, 0.012);
    power_on_();
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 12000));
    double_tap_();
    double_tap_();
    survey_truth_();
    replace_marker_(6.0, 0.00, -0.008, 0.016);
    survey_truth_();
    GL_CHECK(!app.line_here);
    replace_marker_(2.0, 0.05, -0.004, 0.020);
    survey_truth_();
    GL_CHECK_EQ(app.survey.count, 3);
    GL_CHECK_EQ(app.solve_ball, 0);
    GL_CHECK(!app.line_here);
    x.expect_line = false;
    x.check_truth = false;
    check_result_("Survey 4 drops: at drop 3 (2 m), not at the ball", &x, truth_);
    replace_marker_(9.0, -0.01, -0.010, 0.012);
    survey_truth_();
    GL_CHECK_EQ(app.survey.count, 4);
    GL_CHECK_EQ(app.solve_drops, 4);
    GL_CHECK_EQ(app.solve_ball, 3);
    GL_CHECK_EQ(app.solver_work.fit.n_drops, 4);
    x.expect_line = true;
    x.check_truth = true;
    check_result_("Survey 4 drops (ball 9 m, 6 m, 2 m, ball again)", &x, truth_);
    GL_CHECK(strcmp(rows_[n_rows_ - 1u].text.mode, "D4") == 0);
    GL_CHECK(app.est.phi_rad > 0.0f); /* rises to the left along the whole line */
    GL_CHECK(app.est.plays_like_m > app.est.distance_m + 0.30f); /* uphill */
    /* a fifth placement is a new read, not a fifth drop */
    replace_marker_(9.0, 0.00, -0.010, 0.012);
    GL_CHECK_EQ(app.ui.survey_count, 0);
    GL_CHECK_EQ(app.solve_drops, 1);
    GL_CHECK(app.line_here && app.view.drop == 0u);
}

/* ======================================================================= */
/* 4. flag-out fallback, a left-camera-only read, an ambiguous read         */
/* ======================================================================= */

GL_TEST(test_flag_out_fallback_on_the_display)
{
    gl_ref_meas_t rec, tru;
    expect_t x;

    world_defaults_();
    scene_(6.0, 0.05, -0.015, 0.010); /* the stick is gone; the green is what it is */
    W.stick = false;
    board_up_(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    {
        gl_settings_t s = app.settings;
        s.manual_distance_cm = 450;
        GL_CHECK_EQ(gl_app_set_settings(&app, &s), GL_OK);
    }
    watch_reset_();
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 12000));
    GL_CHECK(app.est.flag_missing && !app.est.range_missing);
    to_ref_(&app.meas_cur, &rec);
    truth_record_(&rec, &tru);
    memset(&x, 0, sizeof(x));
    x.expect_line = true;
    x.on_screen = true;
    x.solved = true; /* a tilt-only plane along the visor axis IS solved */
    x.check_truth = true;
    x.truth_tol_mrad = 6.0;
    check_result_("Flag out, dialled 4.5 m, rises LEFT 1.5 %, uphill 1 %", &x, &tru);
    /* shown for what it is: the message, the no-flag icon, "?" after the
     * dialled distance, the estimator's reduced confidence */
    GL_CHECK_EQ(app.view.note, GL_UI_NOTE_NO_FLAG);
    GL_CHECK(strcmp(rows_[n_rows_ - 1u].text.note, "NO FLAG") == 0);
    GL_CHECK(!app.view.flag_found && app.view.distance_assumed);
    GL_CHECK(strcmp(rows_[n_rows_ - 1u].text.distance, "14.8FT?") == 0);
    GL_CHECK_NEAR(app.view.confidence, app.est.confidence, 1e-6);
    /* the same placement read WITH the flag scores higher */
    {
        const float without = app.view.confidence;
        world_defaults_();
        scene_(4.5, 0.0, -0.015, 0.010);
        power_on_();
        GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 12000));
        printf("    confidence shown: %.2f with the flagstick at 4.5 m, %.2f flag-out with 4.5 m "
               "dialled\n", (double)app.view.confidence, (double)without);
        GL_CHECK(app.view.confidence > without);
    }
}

GL_TEST(test_left_camera_only_read_keeps_the_bearing)
{
    gl_ref_meas_t rec, tru;
    expect_t x;
    float conf_stereo;
    line_t ln_dialled, ln_assumed;

    /* the reference point: the same scene with both cameras */
    world_defaults_();
    scene_(5.0, 0.06, 0.014, 0.006);
    power_on_();
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 12000));
    conf_stereo = app.view.confidence;

    /* the right window is covered: the left camera measures the stick, there
     * is no disparity.  5 m dialled. */
    world_defaults_();
    scene_(5.0, 0.06, 0.014, 0.006);
    W.right_blind = true;
    board_up_(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    {
        gl_settings_t s = app.settings;
        s.manual_distance_cm = 500;
        s.units = GL_UNITS_METRES;
        GL_CHECK_EQ(gl_app_set_settings(&app, &s), GL_OK);
    }
    watch_reset_();
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 15000));
    print_seen_();
    GL_CHECK_EQ(app.cur.tier, GL_READ_TIER_LEFT);
    GL_CHECK(app.cur.flag_found && !app.read.result.stick_found);
    /* handed over as "flag found, range not available": the bearing is the
     * camera's, the disparity is not a number (NOT a synthesised one), the
     * dialled distance goes in */
    GL_CHECK(app.meas_cur.flag_found);
    GL_CHECK(isnan(app.meas_cur.flag_disparity_px));
    GL_CHECK(!isnan(app.meas_cur.flag_bearing_rad));
    GL_CHECK_NEAR(app.meas_cur.user_distance_m, 5.0, 1e-5);
    GL_CHECK(app.est.range_missing && !app.est.flag_missing);
    to_ref_(&app.meas_cur, &rec);
    truth_record_(&rec, &tru);
    memset(&x, 0, sizeof(x));
    x.expect_line = true;
    x.on_screen = true;
    x.solved = true;
    x.check_truth = true;
    x.truth_tol_mrad = 6.0;
    check_result_("Left camera only, 5 m dialled, rises RIGHT 1.4 %", &x, &tru);
    /* the bearing was kept: the line points at the hole the camera saw, not
     * along the visor axis (0.06 rad apart) */
    GL_CHECK_NEAR(app.est.bearing_rad, 0.06, 0.004);
    GL_CHECK_EQ(app.view.note, GL_UI_NOTE_NO_RANGE);
    GL_CHECK(strcmp(rows_[n_rows_ - 1u].text.distance, "5.0M?") == 0);
    GL_CHECK(app.view.flag_found && app.view.distance_assumed);
    /* confidence: the estimator halves it for the missing range, the
     * application takes 0.6 for the single camera */
    GL_CHECK_NEAR(app.view.confidence, expected_confidence_(), 1e-6);
    GL_CHECK_NEAR(app.view.confidence, 0.6 * (double)app.est.confidence, 1e-6);
    printf("    confidence shown: %.3f stereo, %.3f left camera only with 5 m dialled (estimator "
           "%.3f x 0.6)\n", (double)conf_stereo, (double)app.view.confidence,
           (double)app.est.confidence);
    GL_CHECK(app.view.confidence < 0.5f * conf_stereo);
    measure_line_(&ln_dialled);
    GL_CHECK(ln_dialled.found);

    /* the same with NOTHING dialled: the estimator falls back to its 3 m
     * default.  The aim was solved for a distance nobody measured or
     * dialled: the line is drawn DASHED, and the distance, the plays-like
     * distance and the break in cups are not shown as if anybody knew them. */
    world_defaults_();
    scene_(5.0, 0.06, 0.014, 0.006);
    W.right_blind = true;
    power_on_();
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 15000));
    GL_CHECK(app.est.range_missing);
    GL_CHECK_NEAR(app.est.distance_m, 3.0, 1e-6);
    to_ref_(&app.meas_cur, &rec);
    truth_record_(&rec, &tru);
    x.check_truth = false;
    check_result_("Left camera only, nothing dialled (3 m assumed)", &x, &tru);
    GL_CHECK(strcmp(rows_[n_rows_ - 1u].text.distance, "--") == 0);
    GL_CHECK(strcmp(rows_[n_rows_ - 1u].text.brk, "BREAK ?") == 0);
    GL_CHECK_EQ(app.view.note, GL_UI_NOTE_NO_RANGE);
    GL_CHECK(app.view.solved); /* the estimator did solve: for its 3 m */
    measure_line_(&ln_assumed);
    GL_CHECK(ln_assumed.found);
    GL_CHECK(ln_assumed.rows + 15u < ln_dialled.rows);
    printf("    aim line: solid on %u rows with 5 m dialled, dashed on %u rows with nothing dialled\n",
           ln_dialled.rows, ln_assumed.rows);
}

GL_TEST(test_ambiguous_read_lowers_the_confidence)
{
    gl_ref_meas_t rec, tru;
    expect_t x;
    float conf_clean;

    world_defaults_();
    scene_(6.0, 0.05, 0.012, -0.020);
    power_on_();
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 12000));
    conf_clean = app.view.confidence;
    GL_CHECK(!app.cur.ambiguous);

    /* a second flagstick in view, about as strong and about as central:
     * 7.5 m away, 6 degrees to the right (a clearly weaker one further off
     * to the side is NOT ambiguous: the read ranks the candidates) */
    world_defaults_();
    scene_(6.0, 0.05, 0.012, -0.020);
    W.pole2 = true;
    W.pole2_dist_m = 7.5;
    W.pole2_bearing_rad = -0.10;
    W.pole2_height_m = 1.96;
    project_scene_();
    power_on_();
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 15000));
    print_seen_();
    printf("    two flagsticks in view: %u band candidates, %u probed, ambiguous %d, bearing "
           "%.1f mrad, range %.2f m\n", (unsigned)app.read.result.n_candidates,
           (unsigned)app.read.result.n_probed, (int)app.read.result.ambiguous,
           1000.0 * (double)app.cur.bearing_rad, (double)app.est.distance_m);
    GL_CHECK(app.read.result.ambiguous && app.cur.ambiguous);
    /* the nearer, more central one was taken */
    GL_CHECK_NEAR(app.est.distance_m, 6.0, 0.2);
    to_ref_(&app.meas_cur, &rec);
    truth_record_(&rec, &tru);
    memset(&x, 0, sizeof(x));
    x.expect_line = true;
    x.on_screen = true;
    x.solved = true;
    x.check_truth = true;
    x.truth_tol_mrad = 6.0;
    check_result_("Ambiguous: a second flagstick in view", &x, &tru);
    GL_CHECK_EQ(app.view.note, GL_UI_NOTE_AMBIGUOUS);
    GL_CHECK(strcmp(rows_[n_rows_ - 1u].text.note, "2 LINES SEEN") == 0);
    GL_CHECK_NEAR(app.view.confidence, expected_confidence_(), 1e-6);
    printf("    confidence shown: %.3f clean, %.3f with the second flagstick (x 0.6, and the read's "
           "own disparity sigma %.3f px against the 0.08 px the estimator assumes)\n",
           (double)conf_clean, (double)app.view.confidence, (double)app.cur.disparity_sigma_px);
    GL_CHECK(app.view.confidence <= 0.6f * conf_clean + 0.002f); /* (two reads of one scene) */
}

/* ======================================================================= */
/* 5. the estimator's fallbacks, through the read sequence                  */
/* ======================================================================= */

GL_TEST(test_estimator_fallbacks_reached_by_real_reads)
{
    gl_ref_meas_t rec, tru;
    expect_t x;

    /* ---- base of the stick at the turf horizon: the hole height is only
     *      bounded (base_hidden), the estimator's score is lowered.  On the
     *      flat synthetic green that is EVERY read; shown here once. ---- */
    world_defaults_();
    power_on_();
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 12000));
    GL_CHECK(app.est.base_hidden && !app.meas_cur.flag_base_visible);
    GL_CHECK_EQ(app.view.note, GL_UI_NOTE_NONE); /* no message: the confidence carries it */

    /* ---- a cross slope the green cannot hold at this speed: 7 % at Stimp
     *      14.  The ball cannot be made to reach the hole: the estimator
     *      returns its best effort (aim_source 2).  NOT a normal line. ---- */
    world_defaults_();
    scene_(4.0, 0.0, -0.070, 0.0);
    board_up_(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    {
        gl_settings_t s = app.settings;
        s.stimp_x2 = 28;
        GL_CHECK_EQ(gl_app_set_settings(&app, &s), GL_OK);
    }
    watch_reset_();
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 12000));
    printf("    7 %% cross slope at Stimp 14: aim source %u, status %u, best-effort aim %.0f mrad, "
           "%u trial rolls, %lu RK4 steps\n", (unsigned)app.est.aim_source,
           (unsigned)app.est.solve_status, 1000.0 * (double)app.est.phi_rad,
           (unsigned)app.est.n_rolls, (unsigned long)app.est.n_steps);
    GL_CHECK_EQ(app.est.aim_source, GL_AIM_BEST_EFFORT);
    GL_CHECK(app.est.solve_status == GL_SOLVE_UNREACHABLE || app.est.solve_status == GL_SOLVE_NO_BRACKET ||
             app.est.solve_status == GL_SOLVE_NO_CONVERGENCE);
    to_ref_(&app.meas_cur, &rec);
    truth_record_(&rec, &tru);
    memset(&x, 0, sizeof(x));
    x.expect_line = true;
    x.on_screen = false; /* the best iterate points far off the screen */
    x.solved = false;
    check_result_("Best effort: 7 % cross slope at Stimp 14 (not solvable)", &x, &tru);
    GL_CHECK_EQ(app.view.note, GL_UI_NOTE_NOT_SOLVED);
    GL_CHECK(strcmp(rows_[n_rows_ - 1u].text.note, "NOT SOLVED") == 0);
    GL_CHECK(strcmp(rows_[n_rows_ - 1u].text.brk, "BREAK ?") == 0);
    GL_CHECK(rows_[n_rows_ - 1u].text.plays[0] == '\0');
    GL_CHECK(app.view.confidence <= 0.2f + 1e-6f);
    GL_CHECK(rows_[n_rows_ - 1u].boxes <= 1);
    GL_CHECK_NEAR(app.view.confidence, expected_confidence_(), 1e-6);

    /* ---- downhill and across, steeper than the green holds: 6.5 % down
     *      with 0.5 % across at Stimp 14: no aim angle brackets the hole ---- */
    world_defaults_();
    scene_(3.0, 0.0, -0.005, -0.065);
    board_up_(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    {
        gl_settings_t s = app.settings;
        s.stimp_x2 = 28;
        GL_CHECK_EQ(gl_app_set_settings(&app, &s), GL_OK);
    }
    watch_reset_();
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 12000));
    printf("    6.5 %% downhill, 0.5 %% across at Stimp 14: aim source %u, status %u\n",
           (unsigned)app.est.aim_source, (unsigned)app.est.solve_status);
    GL_CHECK_EQ(app.est.aim_source, GL_AIM_BEST_EFFORT);
    to_ref_(&app.meas_cur, &rec);
    truth_record_(&rec, &tru);
    check_result_("Best effort: 6.5 % downhill at Stimp 14 (no bracket)", &x, &tru);
    GL_CHECK_EQ(app.view.note, GL_UI_NOTE_NOT_SOLVED);
    GL_CHECK(rows_[n_rows_ - 1u].boxes <= 1);

    /* ---- a twisted green, surveyed: the cross slope grows from 6.2 % at the
     *      ball to 9.7 % near the hole (Stimp 8).  The fitted patch cannot be
     *      solved; its secant plane can (aim_source 1). ---- */
    world_defaults_();
    scene_(1.0, 0.0, 0.0972, 0.0004);
    board_up_(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    {
        gl_settings_t s = app.settings;
        s.stimp_x2 = 16;
        GL_CHECK_EQ(gl_app_set_settings(&app, &s), GL_OK);
    }
    watch_reset_();
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 12000));
    double_tap_();
    double_tap_();
    survey_truth_();
    replace_marker_(2.5, 0.0, 0.084, 0.00175);
    survey_truth_();
    replace_marker_(5.0, 0.0, 0.062, 0.004);
    survey_truth_();
    printf("    twisted green, Survey of 3 drops at Stimp 8: aim source %u, status %u, aim %.0f "
           "mrad, patch d %.4f /m, %u trial rolls\n", (unsigned)app.est.aim_source,
           (unsigned)app.est.solve_status, 1000.0 * (double)app.est.phi_rad,
           (double)app.est.patch[3], (unsigned)app.est.n_rolls);
    GL_CHECK_EQ(app.solve_drops, 3);
    GL_CHECK(app.line_here);
    GL_CHECK_EQ(app.est.aim_source, GL_AIM_FROM_PLANE);
    memset(&x, 0, sizeof(x));
    x.expect_line = true;
    x.on_screen = false; /* 24 degrees off the visor axis: the dashed substitute */
    x.solved = true;     /* a solution - of the secant plane */
    check_result_("Secant plane: twisted green, Survey of 3 drops, Stimp 8", &x, truth_);
    GL_CHECK_EQ(app.view.note, GL_UI_NOTE_APPROX);
    GL_CHECK(strcmp(rows_[n_rows_ - 1u].text.note, "APPROX") == 0);
    GL_CHECK_NEAR(app.view.confidence, expected_confidence_(), 1e-6);
    memset(&x, 0, sizeof(x));
    x.expect_line = true;
    x.on_screen = false;
    x.solved = false;

    /* ---- method B2 from the settings: the turf horizon enters the fit ---- */
    world_defaults_();
    board_up_(true);
    GL_CHECK_EQ(gl_app_init(&app), GL_OK);
    {
        gl_settings_t s = app.settings;
        s.method = GL_METHOD_B2;
        s.past_cm = 45;
        s.units = GL_UNITS_PACES;
        GL_CHECK_EQ(gl_app_set_settings(&app, &s), GL_OK);
    }
    watch_reset_();
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 12000));
    GL_CHECK_EQ(app.solve_opt.method, GL_SOLVER_METHOD_B2);
    GL_CHECK_NEAR(app.solve_opt.past_m, 0.45, 1e-6);
    GL_CHECK(app.solver_work.fit.used_horizon);
    GL_CHECK_EQ(app.solver_work.fit.n_starts, 5);
    printf("    method B2 (setting): horizon used, %u starts, horizon rms %.2f sigma, poor %d, aim "
           "%.2f mrad, %u fit iterations\n", (unsigned)app.solver_work.fit.n_starts,
           (double)app.solver_work.fit.horizon_rms, (int)app.est.poor_horizon,
           1000.0 * (double)app.est.phi_rad, (unsigned)app.solver_work.fit.n_iter);
    to_ref_(&app.meas_cur, &rec);
    truth_record_(&rec, &tru);
    memset(&x, 0, sizeof(x));
    x.expect_line = true;
    x.on_screen = true;
    x.solved = true;
    check_result_("Method B2 (setting), 45 cm past, paces", &x, &tru);
    GL_CHECK(strchr(rows_[n_rows_ - 1u].text.distance, 'P') != NULL);
}

/* The mappings no read sequence produces: an estimate is put into app.est
 * and the application composes its view of it (gl_app_recompose_view).
 * Stated as such: these are tests of the MAPPING, not of a read. */
GL_TEST(test_fallback_mappings_that_no_read_produces)
{
    static const struct {
        const char *name;
        uint8_t source, status;
        bool fit_converged, poor_horizon;
        uint8_t note;
        bool solved;
    } cases[] = {
        { "Mapping only: secant plane (aim_source 1)", GL_AIM_FROM_PLANE, GL_SOLVE_OK, true, false,
          GL_UI_NOTE_APPROX, true },
        { "Mapping only: pace limited on the patch", GL_AIM_FROM_PATCH, GL_SOLVE_PACE_LIMITED, true,
          false, GL_UI_NOTE_PACE, true },
        { "Mapping only: best effort, aim on the screen", GL_AIM_BEST_EFFORT, GL_SOLVE_NO_CONVERGENCE,
          true, false, GL_UI_NOTE_NOT_SOLVED, false },
        { "Mapping only: straight (aim_source 3)", GL_AIM_STRAIGHT, GL_SOLVE_INVALID, true, false,
          GL_UI_NOTE_NO_SOLUTION, false },
        { "Mapping only: fit stopped on its limit", GL_AIM_FROM_PATCH, GL_SOLVE_OK, false, false,
          GL_UI_NOTE_FIT, true },
        { "Mapping only: poor horizon (B2)", GL_AIM_FROM_PATCH, GL_SOLVE_OK, true, true,
          GL_UI_NOTE_NONE, true },
    };
    gl_estimate_t base;
    unsigned black_solid = 0;

    world_defaults_();
    power_on_();
    GL_CHECK(run_until_state_(GL_UI_SHOW_RESULT, 12000));
    base = app.est;
    {
        line_t ln;
        measure_line_(&ln);
        GL_CHECK(ln.found);
        black_solid = ln.rows;
    }
    for (size_t i = 0; i < GL_ARRAY_LEN(cases); i++) {
        gl_ui_result_text_t t;
        line_t ln;
        double conf;
        app.est = base;
        app.est.aim_source = cases[i].source;
        app.est.solve_status = cases[i].status;
        app.est.fit_converged = cases[i].fit_converged;
        app.est.poor_horizon = cases[i].poor_horizon;
        if (cases[i].poor_horizon) {
            app.est.confidence = 0.8f * base.confidence; /* what the estimator does */
        }
        if (cases[i].source == GL_AIM_STRAIGHT) {
            app.est.phi_rad = 0.0f; /* straight at the hole */
            app.est.aim_azimuth_device_rad = base.bearing_rad;
            app.est.break_cups = 0.0f;
        }
        gl_app_recompose_view(&app);
        gl_app_run_once(&app); /* redraw */
        GL_CHECK_EQ(panel_differs_from_framebuffer_(), 0u);
        gl_ui_result_text(&app.ui, &app.view, &t);
        GL_CHECK_EQ(app.view.note, cases[i].note);
        GL_CHECK(strcmp(t.note, gl_ui_note_text((gl_ui_note_t)cases[i].note)) == 0);
        GL_CHECK_EQ(app.view.solved, cases[i].solved);
        conf = expected_confidence_();
        GL_CHECK_NEAR(app.view.confidence, conf, 1e-6);
        measure_line_(&ln);
        GL_CHECK(ln.found);
        if (ln.found) {
            GL_CHECK(fabs(orient_diff_(atan(ln.k), (double)app.view.aim_rad)) < 0.0061);
        }
        if (cases[i].solved) {
            /* a solution: the solid line, the break quoted */
            GL_CHECK(ln.rows + 14u >= black_solid); /* (a message label covers 11 rows) */
            GL_CHECK(strcmp(t.brk, "BREAK ?") != 0);
            GL_CHECK(t.plays[0] != '\0');
        } else {
            /* not a solution: long dashes (fewer rows carry the line), no
             * break, no plays-like distance, at most one confidence box */
            GL_CHECK(ln.rows + 20u < black_solid);
            GL_CHECK(strcmp(t.brk, "BREAK ?") == 0);
            GL_CHECK(t.plays[0] == '\0');
            GL_CHECK(gl_ui_conf_boxes(app.view.confidence) <= 1);
        }
        if (cases[i].source == GL_AIM_STRAIGHT) {
            GL_CHECK_EQ(gl_ui_conf_boxes(app.view.confidence), 0);
        }
        if (!cases[i].fit_converged) {
            GL_CHECK_NEAR(app.view.confidence, 0.7 * (double)base.confidence, 1e-6);
        }
        printf("    %-46s note \"%s\", %s line on %u rows (solid: %u), break \"%s\", confidence "
               "%.3f -> %d of 5 boxes\n", cases[i].name, t.note, cases[i].solved ? "solid" : "dashed",
               ln.rows, black_solid, t.brk, (double)app.view.confidence,
               gl_ui_conf_boxes(app.view.confidence));
    }
    app.est = base;
}

/* ======================================================================= */
/* the table                                                                */
/* ======================================================================= */

GL_TEST(test_print_the_comparison_table)
{
    printf("    scene | reference aim [mrad] (on the app's record; on the true scene) | drawn aim "
           "[mrad] | drawn - reference [mrad] | shown\n");
    for (unsigned i = 0; i < n_rows_ && i < MAX_ROWS; i++) {
        const row_t *r = &rows_[i];
        char drawn[40], diff[24], tru[24];
        if (r->line) {
            snprintf(drawn, sizeof(drawn), "%+8.2f%s", 1000.0 * r->drawn_aim, r->dashed ? " dashed" : "");
            snprintf(diff, sizeof(diff), "%+6.2f", 1000.0 * orient_diff_(r->drawn_aim, r->ref_aim));
        } else {
            snprintf(drawn, sizeof(drawn), " no line");
            snprintf(diff, sizeof(diff), "     -");
        }
        if (isnan(r->true_aim)) {
            snprintf(tru, sizeof(tru), "       -");
        } else {
            snprintf(tru, sizeof(tru), "%+8.2f", 1000.0 * r->true_aim);
        }
        printf("    %-58s | %+8.2f %s | %s | %s | %s, %s, %s, %s%s%s, %d/5%s%s (src %d, st %d)\n",
               r->name, 1000.0 * r->ref_aim, tru, drawn, diff, r->text.distance,
               (r->text.plays[0] != '\0') ? r->text.plays : "no plays-like", r->text.brk, r->text.slope,
               (r->text.note[0] != '\0') ? ", " : "", r->text.note, r->boxes,
               (r->text.mode[0] != '\0') ? ", " : "", r->text.mode, r->aim_source, r->solve_status);
    }
    printf("    %u results; largest |drawn - reference| of a line on the screen %.2f mrad (%.2f deg); "
           "largest |firmware - reference| of a solved aim %.3f mrad; largest |firmware - true "
           "scene| %.2f mrad\n", n_rows_, worst_draw_mrad_, worst_draw_mrad_ * 0.0572958,
           worst_fw_mrad_, worst_true_mrad_);
    printf("    ink on the panel where only a solid line has ink (the gaps of the dashes): at least "
           "%.2f of those pixels for the solid lines, at most %.2f for the dashed ones (the test "
           "separates them at 0.3)\n", least_solid_ink_, most_dashed_ink_);
    GL_CHECK(least_solid_ink_ > 0.45 && most_dashed_ink_ < 0.15);
    GL_CHECK(n_rows_ >= 20u && n_rows_ <= MAX_ROWS);
    GL_CHECK(worst_draw_mrad_ < 6.5);
}

int main(int argc, char **argv)
{
    int rc;
    if (argc > 1) {
        dump_ = fopen(argv[1], "w");
        if (dump_ == NULL) {
            printf("cannot write %s\n", argv[1]);
            return 2;
        }
    }
    GL_RUN(test_quick_read_scenes_line_and_numbers);
    GL_RUN(test_core_clock_is_fast_for_capture_and_solve_only);
    GL_RUN(test_precision_read_line_and_numbers);
    GL_RUN(test_survey_two_three_and_four_drops);
    GL_RUN(test_flag_out_fallback_on_the_display);
    GL_RUN(test_left_camera_only_read_keeps_the_bearing);
    GL_RUN(test_ambiguous_read_lowers_the_confidence);
    GL_RUN(test_estimator_fallbacks_reached_by_real_reads);
    GL_RUN(test_fallback_mappings_that_no_read_produces);
    GL_RUN(test_print_the_comparison_table);
    rc = gl_test_summary();
    if (dump_ != NULL) {
        fclose(dump_);
    }
    return rc;
}
