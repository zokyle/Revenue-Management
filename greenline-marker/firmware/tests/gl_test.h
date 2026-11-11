/*
 * gl_test.h - tiny self-contained unit-test runner (no third-party code).
 *
 * Usage, one executable per tests/test_*.c file:
 *
 *     #include "gl_test.h"
 *     GL_TEST(test_something) { GL_CHECK(1 + 1 == 2); }
 *     int main(void) { GL_RUN(test_something); return gl_test_summary(); }
 *
 * A failed check prints file:line and the expression, marks the current
 * test as failed and CONTINUES (so one run reports every failure).
 * gl_test_summary() prints "PASS"/"FAIL" totals and returns the process
 * exit code (0 = all passed).  Host only: uses stdio and double printf.
 */
#ifndef GL_TEST_H
#define GL_TEST_H

#include <math.h>
#include <stdio.h>
#include <string.h>

static int gl_test_checks_ = 0;
static int gl_test_failures_ = 0;
static int gl_test_tests_ = 0;
static int gl_test_tests_failed_ = 0;
static int gl_test_current_failed_ = 0;

static inline void gl_test_fail_(const char *file, int line, const char *msg)
{
    gl_test_failures_++;
    gl_test_current_failed_ = 1;
    if (gl_test_failures_ <= 50) {
        printf("    FAIL %s:%d: %s\n", file, line, msg);
    }
}

static inline void gl_test_run_(const char *name, void (*fn)(void))
{
    gl_test_current_failed_ = 0;
    gl_test_tests_++;
    fn();
    if (gl_test_current_failed_) {
        gl_test_tests_failed_++;
        printf("  [FAIL] %s\n", name);
    } else {
        printf("  [ ok ] %s\n", name);
    }
    fflush(stdout);
}

static inline int gl_test_summary_(const char *file)
{
    printf("%s: %d tests, %d checks, %d failed checks -> %s\n", file, gl_test_tests_,
           gl_test_checks_, gl_test_failures_, (gl_test_tests_failed_ == 0) ? "PASS" : "FAIL");
    return (gl_test_tests_failed_ == 0) ? 0 : 1;
}

#define GL_TEST(name) static void name(void)
#define GL_RUN(name) gl_test_run_(#name, name)
#define gl_test_summary() gl_test_summary_(__FILE__)

#define GL_CHECK(cond)                                           \
    do {                                                         \
        gl_test_checks_++;                                       \
        if (!(cond)) {                                           \
            gl_test_fail_(__FILE__, __LINE__, #cond);            \
        }                                                        \
    } while (0)

/** Integer equality with both values printed on failure. */
#define GL_CHECK_EQ(a, b)                                                        \
    do {                                                                         \
        long long gl_a_ = (long long)(a);                                        \
        long long gl_b_ = (long long)(b);                                        \
        gl_test_checks_++;                                                       \
        if (gl_a_ != gl_b_) {                                                    \
            char gl_m_[200];                                                     \
            snprintf(gl_m_, sizeof(gl_m_), "%s == %s (got %lld, expected %lld)", \
                     #a, #b, gl_a_, gl_b_);                                      \
            gl_test_fail_(__FILE__, __LINE__, gl_m_);                            \
        }                                                                        \
    } while (0)

/** |a - b| <= tol, values printed on failure.  NaN fails. */
#define GL_CHECK_NEAR(a, b, tol)                                                   \
    do {                                                                           \
        double gl_a_ = (double)(a);                                                \
        double gl_b_ = (double)(b);                                                \
        double gl_t_ = (double)(tol);                                              \
        gl_test_checks_++;                                                         \
        if (!(fabs(gl_a_ - gl_b_) <= gl_t_)) {                                     \
            char gl_m_[240];                                                       \
            snprintf(gl_m_, sizeof(gl_m_), "|%s - %s| <= %s (got %.6g vs %.6g)",   \
                     #a, #b, #tol, gl_a_, gl_b_);                                  \
            gl_test_fail_(__FILE__, __LINE__, gl_m_);                              \
        }                                                                          \
    } while (0)

/** Byte-wise equality of two buffers; prints the first differing offset. */
#define GL_CHECK_MEM(a, b, n)                                                        \
    do {                                                                             \
        const unsigned char *gl_pa_ = (const unsigned char *)(a);                    \
        const unsigned char *gl_pb_ = (const unsigned char *)(b);                    \
        size_t gl_n_ = (size_t)(n);                                                  \
        size_t gl_i_ = 0;                                                            \
        gl_test_checks_++;                                                           \
        while (gl_i_ < gl_n_ && gl_pa_[gl_i_] == gl_pb_[gl_i_]) {                    \
            gl_i_++;                                                                 \
        }                                                                            \
        if (gl_i_ != gl_n_) {                                                        \
            char gl_m_[240];                                                         \
            snprintf(gl_m_, sizeof(gl_m_),                                           \
                     "%s == %s for %lu bytes (offset %lu: 0x%02X vs 0x%02X)", #a,    \
                     #b, (unsigned long)gl_n_, (unsigned long)gl_i_, gl_pa_[gl_i_],  \
                     gl_pb_[gl_i_]);                                                 \
            gl_test_fail_(__FILE__, __LINE__, gl_m_);                                \
        }                                                                            \
    } while (0)

#endif /* GL_TEST_H */
