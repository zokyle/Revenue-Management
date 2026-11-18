/* gl_fieldlog.c - encoders of the replay records.  See gl_fieldlog.h.
 *
 * tools/glctl/logdec.py mirrors these functions field by field: a change
 * here is a change there, and of GL_FIELDLOG_LAYOUT. */
#include "gl_fieldlog.h"

#include "gl_buf.h"

static void wr_v2_(gl_wr_t *w, gl_vec2_t v)
{
    gl_wr_f32(w, v.x);
    gl_wr_f32(w, v.y);
}

static void wr_v3_(gl_wr_t *w, gl_vec3_t v)
{
    gl_wr_f32(w, v.x);
    gl_wr_f32(w, v.y);
    gl_wr_f32(w, v.z);
}

size_t gl_fieldlog_meas_encode(uint16_t read_id, uint8_t drop, uint8_t n_drops, bool is_ball,
                               const gl_measurements_t *m, uint8_t *out, size_t cap)
{
    gl_wr_t w;
    const unsigned n = (m->n_horizon <= GL_SOLVER_MAX_HORIZON) ? m->n_horizon
                                                               : GL_SOLVER_MAX_HORIZON;
    const size_t len = GL_FIELDLOG_MEAS_FIXED + 8u * n;
    if (out == NULL || cap < len) {
        return 0;
    }
    gl_wr_init(&w, out, cap);
    gl_wr_u16(&w, read_id);                       /*  0 */
    gl_wr_u8(&w, drop);                           /*  2 */
    gl_wr_u8(&w, n_drops);                        /*  3 */
    gl_wr_u8(&w, (uint8_t)((is_ball ? GL_FIELDLOG_MEAS_F_BALL : 0u) |
                           (m->flag_found ? GL_FIELDLOG_MEAS_F_FLAG_FOUND : 0u) |
                           (m->flag_base_visible ? GL_FIELDLOG_MEAS_F_BASE_VISIBLE : 0u) |
                           (m->flag_top_visible ? GL_FIELDLOG_MEAS_F_TOP_VISIBLE : 0u))); /* 4 */
    gl_wr_u8(&w, m->tilt_reads);                  /*  5 */
    gl_wr_u8(&w, (uint8_t)n);                     /*  6 */
    gl_wr_u8(&w, (uint8_t)GL_FIELDLOG_LAYOUT);    /*  7 */
    gl_wr_f32(&w, m->f_px);                       /*  8 */
    gl_wr_f32(&w, m->baseline_m);                 /* 12 */
    gl_wr_f32(&w, m->h_cam_m);                    /* 16 */
    gl_wr_f32(&w, m->tilt_x);                     /* 20 */
    gl_wr_f32(&w, m->tilt_y);                     /* 24 */
    gl_wr_f32(&w, m->flag_bearing_rad);           /* 28 */
    gl_wr_f32(&w, m->flag_disparity_px);          /* 32 */
    gl_wr_f32(&w, m->flag_low_elev_rad);          /* 36 */
    gl_wr_f32(&w, m->flag_top_elev_rad);          /* 40 */
    gl_wr_f32(&w, m->stick_height_est_m);         /* 44 */
    gl_wr_f32(&w, m->stick_height_rel_sigma);     /* 48 */
    gl_wr_f32(&w, m->grain_kappa);                /* 52 */
    gl_wr_f32(&w, m->grain_azimuth_rad);          /* 56 */
    gl_wr_f32(&w, m->stimp_ft);                   /* 60 */
    gl_wr_f32(&w, m->user_distance_m);            /* 64 */
    for (unsigned i = 0; i < n; i++) {            /* 68 */
        gl_wr_f32(&w, m->horizon_az_rad[i]);
        gl_wr_f32(&w, m->horizon_elev_rad[i]);
    }
    return w.ok ? len : 0u;
}

size_t gl_fieldlog_read_encode(const gl_fieldlog_ctx_t *c, const gl_solver_options_t *opt,
                               const gl_estimate_t *e, const gl_patch_fit_t *f, uint8_t *out,
                               size_t cap)
{
    gl_wr_t w;
    if (out == NULL || cap < GL_FIELDLOG_READ_LEN) {
        return 0;
    }
    gl_wr_init(&w, out, GL_FIELDLOG_READ_LEN);
    /* ---- context: 0 .. 263 ---- */
    gl_wr_u8(&w, (uint8_t)GL_FIELDLOG_LAYOUT);    /*   0 */
    gl_wr_u8(&w, c->hw_rev);                      /*   1 */
    gl_wr_u16(&w, c->read_id);                    /*   2 */
    gl_wr_u32(&w, c->rtc_s);                      /*   4 */
    gl_wr_u32(&w, c->tick_ms);                    /*   8 */
    gl_wr_u16(&w, c->fw_version);                 /*  12 */
    gl_wr_u16(&w, c->flags);                      /*  14 */
    gl_wr_u32(&w, c->fw_build);                   /*  16 */
    gl_wr_u32(&w, c->solver_version);             /*  20 */
    gl_wr_u8(&w, c->cal_version);                 /*  24 */
    gl_wr_bytes(&w, c->cal_flags, 5);             /*  25 */
    for (int i = 0; i < 5; i++) {
        gl_wr_u16(&w, c->cal_crc[i]);             /*  30 */
    }
    gl_wr_bytes(&w, c->settings, GL_SETTINGS_BLOB_LEN); /* 40 */
    gl_wr_u8(&w, c->n_drops);                     /*  52 */
    gl_wr_u8(&w, c->ball_index);                  /*  53 */
    gl_wr_u8(&w, c->solver_ret);                  /*  54 */
    gl_wr_u8(&w, c->tier);                        /*  55 */
    gl_wr_u8(&w, c->base);                        /*  56 */
    gl_wr_u8(&w, c->seat);                        /*  57 */
    gl_wr_u8(&w, c->note);                        /*  58 */
    gl_wr_u8(&w, c->groups_ok);                   /*  59 */
    wr_v2_(&w, c->slope_raw);                     /*  60 */
    wr_v2_(&w, c->slope);                         /*  68 */
    wr_v2_(&w, c->zero);                          /*  76 */
    wr_v2_(&w, c->spin_slope_raw);                /*  84 */
    wr_v2_(&w, c->reread_slope_raw);              /*  92 */
    gl_wr_f32(&w, c->view_yaw_rad);               /* 100 */
    wr_v3_(&w, c->up);                            /* 104 */
    wr_v3_(&w, c->gyro_bias);                     /* 116 */
    gl_wr_f32(&w, c->tilt_scatter);               /* 128 */
    gl_wr_f32(&w, c->accel_noise_g);              /* 132 */
    gl_wr_i16(&w, c->imu_temp_c_x100);            /* 136 */
    gl_wr_i16(&w, c->cell_temp_c_x10);            /* 138 */
    gl_wr_i16(&w, c->mcu_temp_c_x10);             /* 140 */
    gl_wr_u16(&w, c->batt_mv);                    /* 142 */
    gl_wr_f32(&w, c->grain_red_mod);              /* 144 */
    gl_wr_f32(&w, c->grain_red_az);               /* 148 */
    gl_wr_f32(&w, c->grain_nir_mod);              /* 152 */
    gl_wr_f32(&w, c->grain_nir_az);               /* 156 */
    for (int i = 0; i < 16; i++) {
        gl_wr_u16(&w, c->grain_signal[i]);        /* 160 */
    }
    gl_wr_f32(&w, c->bearing_rad);                /* 192 */
    gl_wr_f32(&w, c->disparity_px);               /* 196 */
    gl_wr_f32(&w, c->disparity_sigma_px);         /* 200 */
    gl_wr_f32(&w, c->base_elev_rad);              /* 204 */
    gl_wr_f32(&w, c->top_elev_rad);               /* 208 */
    gl_wr_f32(&w, c->diag_range_m);               /* 212 */
    gl_wr_f32(&w, c->diag_range_sigma_m);         /* 216 */
    gl_wr_f32(&w, c->stick_height_m);             /* 220 */
    gl_wr_f32(&w, c->stick_height_sigma_m);       /* 224 */
    gl_wr_bytes(&w, c->quality, 5);               /* 228 */
    gl_wr_u8(&w, c->grain_reject);                /* 233 */
    gl_wr_u8(&w, c->tilt_blocks);                 /* 234 */
    gl_wr_u8(&w, 0);                              /* 235 reserved */
    for (int i = 0; i < (int)GL_FIELDLOG_T_COUNT; i++) {
        gl_wr_u16(&w, c->stage_ms[i]);            /* 236 */
    }
    gl_wr_u16(&w, c->cam_on_ms);                  /* 246 */
    gl_wr_f32(&w, c->shown_aim_rad);              /* 248 */
    gl_wr_f32(&w, c->shown_confidence);           /* 252 */
    gl_wr_f32(&w, c->display_rot_rad);            /* 256 */
    gl_wr_u32(&w, 0);                             /* 260 reserved */
    /* ---- options of the call: 264 .. 295 ---- */
    gl_wr_f32(&w, opt->past_m);                   /* 264 */
    gl_wr_f32(&w, opt->tol_miss_m);               /* 268 */
    gl_wr_f32(&w, opt->tol_pace_m);               /* 272 */
    gl_wr_f32(&w, opt->lm_tol);                   /* 276 */
    gl_wr_f32(&w, opt->near_miss_m);              /* 280 */
    gl_wr_u32(&w, opt->max_steps);                /* 284 */
    gl_wr_u16(&w, opt->max_rolls);                /* 288 */
    gl_wr_u16(&w, opt->lm_max_iter);              /* 290 */
    gl_wr_u8(&w, opt->method);                    /* 292 */
    gl_wr_u8(&w, opt->use_grain ? 1u : 0u);       /* 293 */
    gl_wr_u16(&w, 0);                             /* 294 reserved */
    /* ---- the estimate: 296 .. 411 ---- */
    gl_wr_f32(&w, e->phi_rad);                    /* 296 */
    gl_wr_f32(&w, e->aim_azimuth_device_rad);     /* 300 */
    gl_wr_f32(&w, e->v0_mps);                     /* 304 */
    gl_wr_f32(&w, e->plays_like_m);               /* 308 */
    gl_wr_f32(&w, e->break_m);                    /* 312 */
    gl_wr_f32(&w, e->break_cups);                 /* 316 */
    gl_wr_f32(&w, e->distance_m);                 /* 320 */
    gl_wr_f32(&w, e->distance_sigma_m);           /* 324 */
    gl_wr_f32(&w, e->bearing_rad);                /* 328 */
    gl_wr_f32(&w, e->slope_pct);                  /* 332 */
    gl_wr_f32(&w, e->fall_line_azimuth_rad);      /* 336 */
    gl_wr_f32(&w, e->fall_line_azimuth_device_rad); /* 340 */
    gl_wr_f32(&w, e->dz_hole_m);                  /* 344 */
    for (int i = 0; i < 5; i++) {
        gl_wr_f32(&w, e->patch[i]);               /* 348 */
    }
    gl_wr_f32(&w, e->cross_slope_sigma);          /* 368 */
    gl_wr_f32(&w, e->confidence);                 /* 372 */
    gl_wr_f32(&w, e->a_r_mps2);                   /* 376 */
    gl_wr_f32(&w, e->stimp_ft);                   /* 380 */
    gl_wr_f32(&w, e->grain_x);                    /* 384 */
    gl_wr_f32(&w, e->grain_y);                    /* 388 */
    gl_wr_u32(&w, e->n_steps);                    /* 392 */
    gl_wr_u16(&w, e->n_rolls);                    /* 396 */
    gl_wr_u8(&w, e->aim_source);                  /* 398 */
    gl_wr_u8(&w, e->solve_status);                /* 399 */
    gl_wr_u8(&w, e->base_hidden ? 1u : 0u);       /* 400 */
    gl_wr_u8(&w, e->flag_missing ? 1u : 0u);      /* 401 */
    gl_wr_u8(&w, e->range_missing ? 1u : 0u);     /* 402 */
    gl_wr_u8(&w, e->poor_horizon ? 1u : 0u);      /* 403 */
    gl_wr_u8(&w, e->fit_converged ? 1u : 0u);     /* 404 */
    gl_wr_u8(&w, 0);                              /* 405 reserved */
    gl_wr_u16(&w, 0);                             /* 406 reserved */
    gl_wr_u32(&w, 0);                             /* 408 reserved */
    /* ---- the fit record: 412 .. 683 ---- */
    for (int i = 0; i < 5; i++) {
        gl_wr_f32(&w, f->coeffs[i]);              /* 412 */
    }
    for (int i = 0; i < 5; i++) {
        for (int j = 0; j < 5; j++) {
            gl_wr_f32(&w, f->cov[i][j]);          /* 432 */
        }
    }
    gl_wr_f32(&w, f->level_offsets[0]);           /* 532 */
    gl_wr_f32(&w, f->level_offsets[1]);           /* 536 */
    gl_wr_f32(&w, f->distance_m);                 /* 540 */
    gl_wr_f32(&w, f->distance_sigma_m);           /* 544 */
    gl_wr_f32(&w, f->bearing_rad);                /* 548 */
    gl_wr_f32(&w, f->range.distance_m);           /* 552 */
    gl_wr_f32(&w, f->range.sigma_m);              /* 556 */
    gl_wr_f32(&w, f->range.stereo_m);             /* 560 */
    gl_wr_f32(&w, f->range.sigma_stereo_m);       /* 564 */
    gl_wr_f32(&w, f->range.mono_m);               /* 568 */
    gl_wr_f32(&w, f->range.sigma_mono_m);         /* 572 */
    gl_wr_f32(&w, f->tilt_slopes[0]);             /* 576 */
    gl_wr_f32(&w, f->tilt_slopes[1]);             /* 580 */
    gl_wr_f32(&w, f->cross_sigma_read);           /* 584 */
    for (unsigned i = 0; i < GL_SOLVER_MAX_DROPS; i++) {
        gl_wr_f32(&w, f->stations_m[i]);          /* 588 */
    }
    gl_wr_f32(&w, f->horizon_rms);                /* 604 */
    gl_wr_f32(&w, f->cost);                       /* 608 */
    gl_wr_f32(&w, f->cost_first_start);           /* 612 */
    gl_wr_u16(&w, f->n_iter);                     /* 616 */
    gl_wr_u8(&w, f->n_drops);                     /* 618 */
    gl_wr_u8(&w, f->n_starts);                    /* 619 */
    gl_wr_u8(&w, f->base_hidden ? 1u : 0u);       /* 620 */
    gl_wr_u8(&w, f->flag_missing ? 1u : 0u);      /* 621 */
    gl_wr_u8(&w, f->range_missing ? 1u : 0u);     /* 622 */
    gl_wr_u8(&w, f->used_horizon ? 1u : 0u);      /* 623 */
    gl_wr_u8(&w, f->poor_horizon ? 1u : 0u);      /* 624 */
    gl_wr_u8(&w, f->converged ? 1u : 0u);         /* 625 */
    gl_wr_u16(&w, 0);                             /* 626 reserved */
    while (w.ok && w.len < GL_FIELDLOG_READ_LEN) {
        gl_wr_u8(&w, 0);                          /* 628 .. 683 reserved (room for 14 floats) */
    }
    return w.ok ? GL_FIELDLOG_READ_LEN : 0u;
}

void gl_fieldlog_tilt_encode(const gl_fieldlog_tilt_t *t, uint8_t out[GL_FIELDLOG_TILT_LEN])
{
    gl_wr_t w;
    gl_wr_init(&w, out, GL_FIELDLOG_TILT_LEN);
    gl_wr_u8(&w, (uint8_t)GL_FIELDLOG_LAYOUT);    /*  0 */
    gl_wr_u8(&w, t->kind);                        /*  1 */
    gl_wr_u16(&w, t->read_id);                    /*  2 */
    gl_wr_u32(&w, t->rtc_s);                      /*  4 */
    gl_wr_u32(&w, t->tick_ms);                    /*  8 */
    wr_v2_(&w, t->slope_raw);                     /* 12 */
    wr_v2_(&w, t->slope);                         /* 20 */
    wr_v3_(&w, t->accel_g);                       /* 28 */
    wr_v3_(&w, t->gyro_bias);                     /* 40 */
    gl_wr_f32(&w, t->tilt_scatter);               /* 52 */
    gl_wr_f32(&w, t->accel_noise_g);              /* 56 */
    gl_wr_f32(&w, t->yaw_rad);                    /* 60 */
    gl_wr_i16(&w, t->imu_temp_c_x100);            /* 64 */
    gl_wr_i16(&w, t->cell_temp_c_x10);            /* 66 */
    gl_wr_i16(&w, t->mcu_temp_c_x10);             /* 68 */
    gl_wr_u16(&w, t->batt_mv);                    /* 70 */
    gl_wr_u16(&w, t->cal_tilt_crc);               /* 72 */
    gl_wr_u8(&w, t->cal_tilt_flags);              /* 74 */
    gl_wr_u8(&w, t->tilt_blocks);                 /* 75 */
    gl_wr_u8(&w, t->seat);                        /* 76 */
    gl_wr_u8(&w, 0);                              /* 77 reserved */
    gl_wr_u16(&w, 0);                             /* 78 reserved */
}
