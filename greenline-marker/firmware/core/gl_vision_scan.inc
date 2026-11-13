/*
 * gl_vision_scan.inc - the coarse column search of one row, as a template.
 *
 * NOT a translation unit: core/gl_vision.c includes this file twice, once
 * for a row of 8-bit pixels (the unbinned refinement reads the strip
 * directly) and once for a row of 16-bit sums of 4 or 16 rows, with
 *     GL_VIS_SCAN_FN   the name of the function to define
 *     GL_VIS_SCAN_PIX  the element type of the row
 * Everything it uses (FLANK_W, row_scan_t, scan_response_) is defined in
 * gl_vision.c before the first inclusion.
 */

/* 1. coarse position: the column c_lo..c_hi with the strongest centre-minus-
 *    flanks response |rr|, the first one if several are equal.  `row` holds
 *    the SUM of nb image rows (nb = 1, 4 or 16; for nb = 1 the pixels themselves).
 *
 * The three pixel sums slide along the row, and the comparison is made on
 * the INTEGER
 *     N = 2 FLANK_W core - (2 h + 1) (l + r),
 * which is rr times 2 FLANK_W (2 h + 1) nb exactly.  The first version
 * compared the rounded values rr; this gives the same column:
 *   - the flank means and their sum are exact in single precision (sums below
 *     2^24, divided by powers of two), so the only rounding in rr is in the
 *     division by (2 h + 1) and in the final subtraction: |rr - exact| <= 2 x
 *     255 x 2^-24 = 3.1e-5 grey;
 *   - two columns with different |N| differ in |exact| by at least 1 / (8 x 13
 *     x 16) = 6.0e-4 grey (h <= 6, nb <= 16), twenty times that error, so the
 *     rounded comparison agrees with the integer one;
 *   - with EQUAL |N| (also N = 0 against "nothing yet") the rounded values
 *     decide, as before: they are worked out for that case.
 * The response and the flank means of the winner are computed at the end
 * with the very expressions of the first version (scan_response_). */
static bool GL_VIS_SCAN_FN(const GL_VIS_SCAN_PIX *row, int nb, int c_lo, int c_hi, int h, int g,
                           row_scan_t *out)
{
    const float inv = 1.0f / (float)nb;
    const int kc = 2 * FLANK_W, kf = 2 * h + 1;
    int core = 0, l = 0, r = 0;
    int best_c = -1, best_core = 0, best_l = 0, best_r = 0, best_an = 0;

    if (c_lo > c_hi) {
        return false;
    }
    for (int k = -h; k <= h; k++) {
        core += row[c_lo + k];
    }
    for (int k = 0; k < FLANK_W; k++) {
        l += row[c_lo - g - k];
        r += row[c_lo + g + k];
    }
    for (int c = c_lo;; c++) {
        const int nn = kc * core - kf * (l + r);
        const int an = (nn < 0) ? -nn : nn;
        bool take = (an > best_an);
        if (an == best_an) {
            float lm, rm, lb, rb;
            const float rr = scan_response_(core, l, r, h, inv, &lm, &rm);
            const float rr_best = (best_c < 0) ? 0.0f
                                               : scan_response_(best_core, best_l, best_r, h, inv,
                                                                &lb, &rb);
            take = (fabsf(rr) > fabsf(rr_best));
        }
        if (take) {
            best_an = an;
            best_c = c;
            best_core = core;
            best_l = l;
            best_r = r;
        }
        if (c == c_hi) {
            break;
        }
        core += (int)row[c + 1 + h] - (int)row[c - h];
        l += (int)row[c + 1 - g] - (int)row[c - g - FLANK_W + 1];
        r += (int)row[c + g + FLANK_W] - (int)row[c + g];
    }
    if (best_c < 0) {
        return false;
    }
    out->c = best_c;
    out->rr = scan_response_(best_core, best_l, best_r, h, inv, &out->lm, &out->rm);
    return true;
}

