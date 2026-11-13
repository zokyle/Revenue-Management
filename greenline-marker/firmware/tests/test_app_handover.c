/*
 * test_app_handover.c - the one place where firmware quantities become
 * solver inputs (app/gl_app.c, build_measurement_), driven directly.
 *
 * gl_app.c is INCLUDED here so that the static function can be called with
 * records no read sequence produces (the application's object in the test
 * library is then not linked: every symbol of it is defined here).
 */
#include "gl_test.h"

#include "gl_app.c" /* NOLINT: the unit under test, with its statics */

static gl_app_t app_;

static void prepare_(void)
{
    memset(&app_, 0, sizeof(app_));
    gl_settings_defaults(&app_.settings);
    gl_cal_grain_defaults(&app_.cal_grain);
    gl_stick_height_reset(&app_.stick_height);
    app_.cur.flag_found = true;
    app_.cur.tier = (uint8_t)GL_READ_TIER_STEREO;
    app_.cur.bearing_rad = 0.02f;
    app_.cur.disparity_px = 2.19f; /* 6 m */
    app_.cur.disparity_sigma_px = 0.05f;
    app_.cur.base_elev_rad = -0.0009f;
    app_.cur.base = (uint8_t)GL_VIS_BASE_VISIBLE;
    app_.cur.slope.x = 0.01f;
    app_.cur.slope.y = -0.02f;
    for (unsigned i = 0; i < GL_VIS_HORIZON_BINS; i++) {
        app_.read.result.horizon_az_rad[i] = -0.4f + 0.025f * (float)i;
        app_.read.result.horizon_elev_rad[i] = 100.0f + (float)i; /* a sentinel, not an elevation */
    }
}

/* Review finding: the horizon count was clamped to the SOLVER's 41 and the
 * samples then copied from arrays of 32 (index 32 out of bounds for type
 * 'float [32]' under the sanitizer; in a plain build the "azimuths" 32..40
 * were the first elevations).  Not reachable from gl_read.c, which never
 * reports more than 32 - but the hand-over must not depend on that. */
GL_TEST(test_horizon_count_is_limited_to_the_arrays)
{
    static const unsigned counts[8] = { 0u, 1u, 5u, 32u, 33u, 41u, 200u, 255u };
    gl_measurements_t m;
    unsigned worst = 0;

    for (unsigned k = 0; k < 8u; k++) {
        const unsigned want = (counts[k] < GL_VIS_HORIZON_BINS) ? counts[k] : GL_VIS_HORIZON_BINS;
        prepare_();
        app_.read.result.n_horizon = (uint8_t)counts[k];
        build_measurement_(&app_, &m);
        worst = (m.n_horizon > worst) ? m.n_horizon : worst;
        GL_CHECK(m.n_horizon <= GL_VIS_HORIZON_BINS);
        GL_CHECK(m.n_horizon <= GL_SOLVER_MAX_HORIZON);
        GL_CHECK_EQ(m.n_horizon, want);
        for (unsigned i = 0; i < m.n_horizon && i < GL_VIS_HORIZON_BINS; i++) {
            GL_CHECK(m.horizon_az_rad[i] == app_.read.result.horizon_az_rad[i]);
            GL_CHECK(m.horizon_elev_rad[i] == app_.read.result.horizon_elev_rad[i]);
        }
        for (unsigned i = m.n_horizon; i < GL_SOLVER_MAX_HORIZON; i++) {
            GL_CHECK(isnan(m.horizon_az_rad[i]) && isnan(m.horizon_elev_rad[i])); /* untouched */
        }
    }
    printf("    horizon counts 0..255 handed to build_measurement_(): at most %u samples reach the "
           "solver record (the read's arrays hold %u, the solver's %u)\n", worst,
           (unsigned)GL_VIS_HORIZON_BINS, (unsigned)GL_SOLVER_MAX_HORIZON);
}

/* The gating rule of the hand-over, on the same record: a disparity below
 * 3 sigma is "not available", never a number. */
GL_TEST(test_weak_disparity_is_not_available)
{
    gl_measurements_t m;
    prepare_();
    build_measurement_(&app_, &m);
    GL_CHECK(m.flag_found && isfinite(m.flag_disparity_px));
    GL_CHECK_NEAR(m.flag_disparity_px, 2.19 * cos(0.02), 1e-4);
    prepare_();
    app_.cur.disparity_px = 0.14f; /* 2.8 sigma */
    build_measurement_(&app_, &m);
    GL_CHECK(m.flag_found && isnan(m.flag_disparity_px));
    prepare_();
    app_.cur.tier = (uint8_t)GL_READ_TIER_LEFT;
    build_measurement_(&app_, &m);
    GL_CHECK(m.flag_found && isnan(m.flag_disparity_px));
}

int main(void)
{
    GL_RUN(test_horizon_count_is_limited_to_the_arrays);
    GL_RUN(test_weak_disparity_is_not_available);
    return gl_test_summary();
}
