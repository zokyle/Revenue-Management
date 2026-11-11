/*
 * test_gesture.c - posture, roll-to-set dial, double tap, half-turn spin.
 */
#include "gl_gesture.h"
#include "gl_test.h"

static gl_vec3_t v3(float x, float y, float z)
{
    gl_vec3_t v = { x, y, z };
    return v;
}

/* Up vector in body axes after rolling the upright puck clockwise by t
 * (seen from the display side): (-sin t, cos t, 0). */
static gl_vec3_t rolled(float t_deg)
{
    float t = t_deg * GL_DEG2RAD_F;
    return v3(-sinf(t), cosf(t), 0.02f);
}

GL_TEST(test_posture)
{
    gl_posture_det_t p;
    GL_CHECK_EQ(gl_posture_classify(v3(0.02f, -0.01f, 1.0f)), GL_POSTURE_FLAT);
    GL_CHECK_EQ(gl_posture_classify(v3(0.3f, 0.2f, 0.93f)), GL_POSTURE_FLAT);
    GL_CHECK_EQ(gl_posture_classify(v3(0.7f, 0.7f, 0.1f)), GL_POSTURE_UPRIGHT);
    GL_CHECK_EQ(gl_posture_classify(v3(0.0f, -1.0f, -0.2f)), GL_POSTURE_UPRIGHT);
    GL_CHECK_EQ(gl_posture_classify(v3(0.0f, 0.0f, -1.0f)), GL_POSTURE_OTHER);   /* face down */
    GL_CHECK_EQ(gl_posture_classify(v3(0.6f, 0.0f, 0.6f)), GL_POSTURE_OTHER);    /* 45 degrees */
    GL_CHECK_EQ(gl_posture_classify(v3(0.0f, 2.5f, 0.0f)), GL_POSTURE_OTHER);    /* shaken */

    gl_posture_init(&p, 400);
    GL_CHECK_EQ(p.stable, GL_POSTURE_UNKNOWN);
    /* flat for 390 ms: not yet; at 400 ms: reported once */
    for (int i = 0; i < 39; i++) {
        GL_CHECK(!gl_posture_update(&p, v3(0, 0, 1), 10));
    }
    GL_CHECK_EQ(p.stable, GL_POSTURE_UNKNOWN);
    {
        int changes = 0;
        for (int i = 0; i < 10; i++) {
            changes += gl_posture_update(&p, v3(0, 0, 1), 10) ? 1 : 0;
        }
        GL_CHECK_EQ(changes, 1);
    }
    GL_CHECK_EQ(p.stable, GL_POSTURE_FLAT);
    /* a short excursion does not change the stable posture */
    for (int i = 0; i < 20; i++) {
        gl_posture_update(&p, v3(1, 0, 0), 10);
    }
    GL_CHECK_EQ(p.stable, GL_POSTURE_FLAT);
    for (int i = 0; i < 10; i++) {
        gl_posture_update(&p, v3(0, 0, 1), 10);
    }
    GL_CHECK_EQ(p.stable, GL_POSTURE_FLAT);
    /* held upright long enough */
    {
        int changes = 0;
        for (int i = 0; i < 60; i++) {
            changes += gl_posture_update(&p, v3(0, 1, 0.05f), 10) ? 1 : 0;
        }
        GL_CHECK_EQ(changes, 1);
        GL_CHECK_EQ(p.stable, GL_POSTURE_UPRIGHT);
    }
}

GL_TEST(test_dial)
{
    gl_dial_t d;
    int changes = 0;

    /* Stimp dial: 12..28 (half feet), start at 20 */
    gl_dial_begin(&d, 20, 12, 28);
    GL_CHECK(!gl_dial_update(&d, rolled(0.0f)));
    /* roll clockwise 45 degrees in 1-degree steps: +3 detents of 15 degrees */
    for (int a = 1; a <= 45; a++) {
        changes += gl_dial_update(&d, rolled((float)a)) ? 1 : 0;
    }
    GL_CHECK_EQ(d.value, 23);
    GL_CHECK_EQ(changes, 3);
    /* back 30 degrees: -2 (the first reverse step needs a full detent) */
    for (int a = 44; a >= 15; a--) {
        gl_dial_update(&d, rolled((float)a));
    }
    GL_CHECK_EQ(d.value, 21);
    /* jitter of +-6 degrees around the current position never changes it */
    changes = 0;
    for (int i = 0; i < 200; i++) {
        float j = (i & 1) ? 6.0f : -6.0f;
        changes += gl_dial_update(&d, rolled(15.0f + j)) ? 1 : 0;
    }
    GL_CHECK_EQ(changes, 0);
    GL_CHECK_EQ(d.value, 21);
    /* more than a full turn clockwise: saturates at the maximum, no wrap */
    for (int a = 15; a <= 15 + 400; a += 2) {
        gl_dial_update(&d, rolled((float)a));
    }
    GL_CHECK_EQ(d.value, 28);
    /* and all the way back down to the minimum */
    for (int a = 415; a >= -400; a -= 3) {
        gl_dial_update(&d, rolled((float)a));
    }
    GL_CHECK_EQ(d.value, 12);
    /* lying flat: samples are ignored (in-plane gravity too small) */
    changes = 0;
    for (int i = 0; i < 50; i++) {
        changes += gl_dial_update(&d, v3(0.1f * (float)(i % 3), -0.2f, 0.97f)) ? 1 : 0;
    }
    GL_CHECK_EQ(changes, 0);
    /* start value is clamped */
    gl_dial_begin(&d, 99, 0, 2);
    GL_CHECK_EQ(d.value, 2);
    /* a two-state item toggles with one detent each way */
    gl_dial_begin(&d, 0, 0, 1);
    gl_dial_update(&d, rolled(90.0f));
    for (int a = 90; a <= 106; a++) {
        gl_dial_update(&d, rolled((float)a));
    }
    GL_CHECK_EQ(d.value, 1);
    for (int a = 106; a >= 88; a--) {
        gl_dial_update(&d, rolled((float)a));
    }
    GL_CHECK_EQ(d.value, 0);
}

/* Feed a 1 kHz acceleration trace: flat, with tap spikes starting at the
 * given times (ms).  Returns how many double-taps fired. */
static int run_taps(const int *tap_ms, int n_taps, int total_ms, int spike_ms, float amp)
{
    gl_tap_det_t t;
    int fired = 0;
    gl_tap_init(&t, 0.6f);
    for (int ms = 0; ms < total_ms; ms++) {
        gl_vec3_t a = v3(0.0f, 0.0f, 1.0f);
        for (int k = 0; k < n_taps; k++) {
            int dt = ms - tap_ms[k];
            if (dt >= 0 && dt < spike_ms) {
                a.z += (dt & 1) ? -amp : amp; /* ringing */
            }
        }
        fired += gl_tap_update(&t, a, 1) ? 1 : 0;
    }
    return fired;
}

GL_TEST(test_double_tap)
{
    {
        const int taps[2] = { 100, 350 };
        GL_CHECK_EQ(run_taps(taps, 2, 1000, 8, 1.5f), 1);
    }
    {
        const int one[1] = { 100 };
        GL_CHECK_EQ(run_taps(one, 1, 1500, 8, 1.5f), 0);
    }
    {
        const int slow[2] = { 100, 900 }; /* 800 ms apart: two single taps */
        GL_CHECK_EQ(run_taps(slow, 2, 2000, 8, 1.5f), 0);
    }
    {
        const int fast[2] = { 100, 140 }; /* 40 ms apart: one bounce, not two taps */
        GL_CHECK_EQ(run_taps(fast, 2, 1000, 8, 1.5f), 0);
    }
    {
        const int weak[2] = { 100, 350 }; /* below the threshold */
        GL_CHECK_EQ(run_taps(weak, 2, 1000, 8, 0.2f), 0);
    }
    {
        const int four[4] = { 100, 350, 1500, 1750 }; /* two separate double taps */
        GL_CHECK_EQ(run_taps(four, 4, 2500, 8, 1.5f), 2);
    }
    {
        const int limits[2] = { 100, 100 + 480 }; /* just inside the 500 ms window */
        GL_CHECK_EQ(run_taps(limits, 2, 1500, 8, 1.5f), 1);
    }
    /* continuous shaking for a second never fires */
    {
        gl_tap_det_t t;
        int fired = 0;
        gl_tap_init(&t, 0.6f);
        for (int ms = 0; ms < 2000; ms++) {
            gl_vec3_t a = v3(0.0f, 0.0f, 1.0f);
            if (ms > 200 && ms < 1400) {
                a.x = ((ms / 3) & 1) ? 1.2f : -1.2f;
            }
            fired += gl_tap_update(&t, a, 1) ? 1 : 0;
        }
        GL_CHECK_EQ(fired, 0);
    }
    /* being picked up (a long burst) and then tapped twice still works */
    {
        gl_tap_det_t t;
        int fired = 0;
        gl_tap_init(&t, 0.6f);
        for (int ms = 0; ms < 3000; ms++) {
            gl_vec3_t a = v3(0.0f, 0.0f, 1.0f);
            if (ms > 100 && ms < 700) {
                a.y = ((ms / 2) & 1) ? 0.9f : -0.9f;
            }
            if ((ms >= 1500 && ms < 1506) || (ms >= 1750 && ms < 1756)) {
                a.z += (ms & 1) ? 1.5f : -1.5f;
            }
            fired += gl_tap_update(&t, a, 1) ? 1 : 0;
        }
        GL_CHECK_EQ(fired, 1);
    }
}

static float spin_by(float deg, float rate_rad_s)
{
    gl_spin_det_t s;
    const float dt = 1.0f / 240.0f;
    const float target = deg * GL_DEG2RAD_F;
    float done = 0.0f;
    gl_spin_begin(&s, v3(0.01f, -0.02f, 1.0f), v3(0.0f, 0.0f, 0.01f));
    while (fabsf(done) < fabsf(target)) {
        float w = (target > 0.0f) ? rate_rad_s : -rate_rad_s;
        gl_spin_update(&s, v3(0.0f, 0.0f, w + 0.01f), dt);
        done += w * dt;
    }
    return gl_spin_is_half_turn(&s) ? gl_spin_yaw(&s) : 0.0f;
}

GL_TEST(test_spin)
{
    GL_CHECK_NEAR(fabs((double)spin_by(180.0f, 3.0f)), 3.14159, 0.03);
    GL_CHECK(spin_by(-175.0f, 4.0f) < -2.9f);
    GL_CHECK(spin_by(150.0f, 2.0f) > 2.5f);     /* inside the 35-degree tolerance */
    GL_CHECK_NEAR(spin_by(90.0f, 3.0f), 0.0, 1e-9);  /* a quarter turn is not a spin */
    GL_CHECK_NEAR(spin_by(120.0f, 3.0f), 0.0, 1e-9);
    GL_CHECK_NEAR(spin_by(5.0f, 3.0f), 0.0, 1e-9);
    {
        gl_spin_det_t s;
        memset(&s, 0, sizeof(s));
        GL_CHECK(!gl_spin_is_half_turn(&s)); /* never armed */
    }
}

int main(void)
{
    GL_RUN(test_posture);
    GL_RUN(test_dial);
    GL_RUN(test_double_tap);
    GL_RUN(test_spin);
    return gl_test_summary();
}
