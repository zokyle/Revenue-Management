"""Frozen inputs of the ``near_miss_estimator_cases`` of the reference vectors.

Plain numbers (7 significant digits), independent of any seed.  They were found by a
random search of the firmware review (phase 2) for reads whose aim solve on the
fitted patch ends NO_CONVERGENCE (with the tolerances of the reference vectors, 1e-9 m)
although its best iterate passes within millimetres
of the hole centre; see ``EstimatorConfig.near_miss_keep``.  Each entry: what it is,
the pace (``past`` [m]) and the placements (``Measurements.to_dict()`` form, the one
at the ball first).  The last four are controls whose best miss is outside 5 mm.
"""

NEAR_MISS_CASES = [
    {
        "tag": '2.6 m dying putt at the critical slope; the best effort shown without the rule is 159 mrad away',
        "past": 0.0,
        "drops": [
            {
                'f_px': 659.2329, 'baseline': 0.02, 'h_cam': 0.0056, 'tilt': [-0.02790798, -0.07873974],
                'tilt_reads': 2, 'flag_found': True, 'flag_bearing': -0.3022965, 'flag_disparity': 5.058996,
                'flag_low_elev': -0.001788236, 'flag_base_visible': True, 'flag_top_visible': False,
                'flag_top_elev': None, 'stick_height_est': 2.09418, 'stick_height_rel_sigma': 0.15,
                'horizon_az': [], 'horizon_elev': [], 'grain_kappa': 0.0, 'grain_azimuth': 1.519895,
                'stimp_ft': 9.914974, 'user_distance': 2.370377,
            },
        ],
    },
    {
        "tag": 'Survey of 2 drops, 3.7 m dying putt, slope at 0.91 of critical (best miss 3.3 mm); 106 mrad away without the rule',
        "past": 0.0,
        "drops": [
            {
                'f_px': 671.2563, 'baseline': 0.02, 'h_cam': 0.00561, 'tilt': [-0.0005933794, -0.05123081],
                'tilt_reads': 1, 'flag_found': True, 'flag_bearing': 0.0976625, 'flag_disparity': 3.633067,
                'flag_low_elev': -0.00276247, 'flag_base_visible': True, 'flag_top_visible': False,
                'flag_top_elev': None, 'stick_height_est': 1.903607, 'stick_height_rel_sigma': 0.15,
                'horizon_az': [], 'horizon_elev': [], 'grain_kappa': 0.0, 'grain_azimuth': 1.051431,
                'stimp_ft': 13.82762, 'user_distance': None,
            },
            {
                'f_px': 671.2563, 'baseline': 0.02, 'h_cam': 0.00561, 'tilt': [-0.0003383062, -0.05146199],
                'tilt_reads': 1, 'flag_found': True, 'flag_bearing': 0.04554189, 'flag_disparity': 5.694376,
                'flag_low_elev': None, 'flag_base_visible': False, 'flag_top_visible': False, 'flag_top_elev': None,
                'stick_height_est': 1.980347, 'stick_height_rel_sigma': 0.15, 'horizon_az': [], 'horizon_elev': [],
                'grain_kappa': 0.0, 'grain_azimuth': 1.051431, 'stimp_ft': 13.82762, 'user_distance': None,
            },
        ],
    },
    {
        "tag": '5.8 m dying putt, slope at 0.90 of critical; 86 mrad away without the rule',
        "past": 0.0,
        "drops": [
            {
                'f_px': 644.8692, 'baseline': 0.02, 'h_cam': 0.00561, 'tilt': [-0.01983588, -0.04745301],
                'tilt_reads': 2, 'flag_found': True, 'flag_bearing': -0.3027235, 'flag_disparity': 2.219912,
                'flag_low_elev': -0.001087331, 'flag_base_visible': True, 'flag_top_visible': False,
                'flag_top_elev': None, 'stick_height_est': 2.009097, 'stick_height_rel_sigma': 0.02,
                'horizon_az': [], 'horizon_elev': [], 'grain_kappa': 0.0, 'grain_azimuth': 2.864519,
                'stimp_ft': 13.29375, 'user_distance': 5.150526,
            },
        ],
    },
    {
        "tag": '6.0 m, 30 cm past, above the critical slope; without the rule the secant plane is UNREACHABLE, best effort 80 mrad away',
        "past": 0.3,
        "drops": [
            {
                'f_px': 665.4628, 'baseline': 0.02, 'h_cam': 0.00561, 'tilt': [-0.02408974, 0.04895172],
                'tilt_reads': 1, 'flag_found': True, 'flag_bearing': 0.3750457, 'flag_disparity': 2.226699,
                'flag_low_elev': -0.0002529965, 'flag_base_visible': True, 'flag_top_visible': False,
                'flag_top_elev': None, 'stick_height_est': 2.212798, 'stick_height_rel_sigma': 0.07,
                'horizon_az': [], 'horizon_elev': [], 'grain_kappa': 0.0, 'grain_azimuth': 0.5684042,
                'stimp_ft': 16.87711, 'user_distance': 6.017764,
            },
        ],
    },
    {
        "tag": '4.3 m dying putt, slope at 0.86 of critical; without the rule the secant plane is solved, 76 mrad away',
        "past": 0.0,
        "drops": [
            {
                'f_px': 645.031, 'baseline': 0.02, 'h_cam': 0.0052, 'tilt': [-0.01149327, 0.05202464],
                'tilt_reads': 1, 'flag_found': True, 'flag_bearing': 0.1154655, 'flag_disparity': 3.01046,
                'flag_low_elev': -0.002668291, 'flag_base_visible': True, 'flag_top_visible': False,
                'flag_top_elev': None, 'stick_height_est': 1.745454, 'stick_height_rel_sigma': 0.07,
                'horizon_az': [], 'horizon_elev': [], 'grain_kappa': 0.0, 'grain_azimuth': -0.5936434,
                'stimp_ft': 13.03683, 'user_distance': None,
            },
        ],
    },
    {
        "tag": '8.1 m, 2 cm past, slope at 0.94 of critical; 65 mrad away without the rule',
        "past": 0.02,
        "drops": [
            {
                'f_px': 656.5987, 'baseline': 0.02, 'h_cam': 0.0056, 'tilt': [-0.003998653, -0.0569569],
                'tilt_reads': 1, 'flag_found': True, 'flag_bearing': 0.01405457, 'flag_disparity': 1.621962,
                'flag_low_elev': 0.0008543132, 'flag_base_visible': True, 'flag_top_visible': False,
                'flag_top_elev': None, 'stick_height_est': 1.855908, 'stick_height_rel_sigma': 0.07,
                'horizon_az': [], 'horizon_elev': [], 'grain_kappa': 0.1562364, 'grain_azimuth': 1.824868,
                'stimp_ft': 12.86795, 'user_distance': 8.072689,
            },
        ],
    },
    {
        "tag": 'Survey of 3 drops, 5.7 m, 10 cm past (best miss 2.2 mm); 52 mrad away without the rule',
        "past": 0.1,
        "drops": [
            {
                'f_px': 669.5251, 'baseline': 0.02, 'h_cam': 0.00561, 'tilt': [-0.01528486, -0.07765037],
                'tilt_reads': 1, 'flag_found': True, 'flag_bearing': -0.3227122, 'flag_disparity': 2.353977,
                'flag_low_elev': 0.004702764, 'flag_base_visible': True, 'flag_top_visible': False,
                'flag_top_elev': None, 'stick_height_est': 2.144171, 'stick_height_rel_sigma': 0.02,
                'horizon_az': [], 'horizon_elev': [], 'grain_kappa': 0.0, 'grain_azimuth': 2.870099,
                'stimp_ft': 10.02804, 'user_distance': None,
            },
            {
                'f_px': 669.5251, 'baseline': 0.02, 'h_cam': 0.00561, 'tilt': [-0.01768711, -0.07409724],
                'tilt_reads': 1, 'flag_found': True, 'flag_bearing': -0.3395447, 'flag_disparity': 5.746807,
                'flag_low_elev': 0.007735892, 'flag_base_visible': False, 'flag_top_visible': False,
                'flag_top_elev': None, 'stick_height_est': 2.168693, 'stick_height_rel_sigma': 0.02,
                'horizon_az': [], 'horizon_elev': [], 'grain_kappa': 0.0, 'grain_azimuth': 2.870099,
                'stimp_ft': 10.02804, 'user_distance': None,
            },
            {
                'f_px': 669.5251, 'baseline': 0.02, 'h_cam': 0.00561, 'tilt': [-0.01462532, -0.0765374],
                'tilt_reads': 1, 'flag_found': False, 'flag_bearing': None, 'flag_disparity': None,
                'flag_low_elev': None, 'flag_base_visible': False, 'flag_top_visible': False, 'flag_top_elev': None,
                'stick_height_est': 2.037466, 'stick_height_rel_sigma': 0.02, 'horizon_az': [], 'horizon_elev': [],
                'grain_kappa': 0.0, 'grain_azimuth': 2.870099, 'stimp_ft': 10.02804, 'user_distance': None,
            },
        ],
    },
    {
        "tag": 'Survey of 3 drops, 14.3 m, 30 cm past (best miss 3.4 mm); without the rule the secant plane is solved, 52 mrad away',
        "past": 0.3,
        "drops": [
            {
                'f_px': 638.3207, 'baseline': 0.02, 'h_cam': 0.00561, 'tilt': [0.006756436, -0.06348936],
                'tilt_reads': 1, 'flag_found': True, 'flag_bearing': 0.3904441, 'flag_disparity': 0.8941093,
                'flag_low_elev': -0.02082692, 'flag_base_visible': False, 'flag_top_visible': True,
                'flag_top_elev': 0.1209746, 'stick_height_est': 2.084387, 'stick_height_rel_sigma': 0.07,
                'horizon_az': [], 'horizon_elev': [], 'grain_kappa': 0.3420712, 'grain_azimuth': -1.655862,
                'stimp_ft': 11.3704, 'user_distance': 14.7825,
            },
            {
                'f_px': 638.3207, 'baseline': 0.02, 'h_cam': 0.00561, 'tilt': [0.002915383, -0.06503925],
                'tilt_reads': 1, 'flag_found': True, 'flag_bearing': 0.3762096, 'flag_disparity': 1.282293,
                'flag_low_elev': -0.0235316, 'flag_base_visible': True, 'flag_top_visible': True,
                'flag_top_elev': 0.1861461, 'stick_height_est': 2.034271, 'stick_height_rel_sigma': 0.07,
                'horizon_az': [], 'horizon_elev': [], 'grain_kappa': 0.3420712, 'grain_azimuth': -1.655862,
                'stimp_ft': 11.3704, 'user_distance': None,
            },
            {
                'f_px': 638.3207, 'baseline': 0.02, 'h_cam': 0.00561, 'tilt': [0.002495498, -0.06611307],
                'tilt_reads': 1, 'flag_found': True, 'flag_bearing': 0.3957974, 'flag_disparity': 2.897667,
                'flag_low_elev': -0.02559748, 'flag_base_visible': False, 'flag_top_visible': False,
                'flag_top_elev': None, 'stick_height_est': 2.124974, 'stick_height_rel_sigma': 0.07,
                'horizon_az': [], 'horizon_elev': [], 'grain_kappa': 0.3420712, 'grain_azimuth': -1.655862,
                'stimp_ft': 11.3704, 'user_distance': None,
            },
        ],
    },
    {
        "tag": '15 m, 10 cm past, slope at 0.89 of critical; without the rule the secant plane is solved, 48 mrad away',
        "past": 0.1,
        "drops": [
            {
                'f_px': 662.5319, 'baseline': 0.02, 'h_cam': 0.00561, 'tilt': [-0.007857151, -0.04961724],
                'tilt_reads': 1, 'flag_found': True, 'flag_bearing': -0.08808127, 'flag_disparity': 0.8589769,
                'flag_low_elev': -0.001018177, 'flag_base_visible': True, 'flag_top_visible': True,
                'flag_top_elev': 0.1291206, 'stick_height_est': 1.818399, 'stick_height_rel_sigma': 0.15,
                'horizon_az': [], 'horizon_elev': [], 'grain_kappa': -0.04358493, 'grain_azimuth': -0.6382148,
                'stimp_ft': 13.68779, 'user_distance': 13.56333,
            },
        ],
    },
    {
        "tag": '11 m, 30 cm past, above the critical slope; 47 mrad away without the rule',
        "past": 0.3,
        "drops": [
            {
                'f_px': 644.2681, 'baseline': 0.02, 'h_cam': 0.0052, 'tilt': [0.0009999138, 0.07473249],
                'tilt_reads': 2, 'flag_found': True, 'flag_bearing': 0.1169984, 'flag_disparity': 1.169145,
                'flag_low_elev': 0.005858581, 'flag_base_visible': False, 'flag_top_visible': True,
                'flag_top_elev': 0.1969697, 'stick_height_est': 2.099006, 'stick_height_rel_sigma': 0.07,
                'horizon_az': [], 'horizon_elev': [], 'grain_kappa': 0.0, 'grain_azimuth': -1.25349,
                'stimp_ft': 11.30146, 'user_distance': 10.33897,
            },
        ],
    },
    {
        "tag": 'Survey of 4 drops, 5.3 m, 10 cm past; 35 mrad away without the rule',
        "past": 0.1,
        "drops": [
            {
                'f_px': 675.0108, 'baseline': 0.02, 'h_cam': 0.0052, 'tilt': [0.0103308, 0.08737396],
                'tilt_reads': 1, 'flag_found': True, 'flag_bearing': -0.1204878, 'flag_disparity': 2.571214,
                'flag_low_elev': None, 'flag_base_visible': False, 'flag_top_visible': False, 'flag_top_elev': None,
                'stick_height_est': 1.794084, 'stick_height_rel_sigma': 0.15, 'horizon_az': [], 'horizon_elev': [],
                'grain_kappa': 0.05940923, 'grain_azimuth': 2.24027, 'stimp_ft': 8.9898, 'user_distance': None,
            },
            {
                'f_px': 675.0108, 'baseline': 0.02, 'h_cam': 0.0052, 'tilt': [0.01617258, 0.09047373],
                'tilt_reads': 1, 'flag_found': True, 'flag_bearing': -0.1613804, 'flag_disparity': 2.836669,
                'flag_low_elev': 0.003246002, 'flag_base_visible': True, 'flag_top_visible': False,
                'flag_top_elev': None, 'stick_height_est': 1.837454, 'stick_height_rel_sigma': 0.15,
                'horizon_az': [], 'horizon_elev': [], 'grain_kappa': 0.05940923, 'grain_azimuth': 2.24027,
                'stimp_ft': 8.9898, 'user_distance': None,
            },
            {
                'f_px': 675.0108, 'baseline': 0.02, 'h_cam': 0.0052, 'tilt': [0.01190054, 0.09043309],
                'tilt_reads': 1, 'flag_found': True, 'flag_bearing': -0.06544413, 'flag_disparity': 12.95531,
                'flag_low_elev': 0.001248365, 'flag_base_visible': True, 'flag_top_visible': False,
                'flag_top_elev': None, 'stick_height_est': 1.826355, 'stick_height_rel_sigma': 0.15,
                'horizon_az': [], 'horizon_elev': [], 'grain_kappa': 0.05940923, 'grain_azimuth': 2.24027,
                'stimp_ft': 8.9898, 'user_distance': 5.642499,
            },
            {
                'f_px': 675.0108, 'baseline': 0.02, 'h_cam': 0.0052, 'tilt': [0.02186807, 0.09058723],
                'tilt_reads': 1, 'flag_found': True, 'flag_bearing': -0.1746178, 'flag_disparity': 14.82661,
                'flag_low_elev': 0.0003167918, 'flag_base_visible': True, 'flag_top_visible': False,
                'flag_top_elev': None, 'stick_height_est': 1.844384, 'stick_height_rel_sigma': 0.15,
                'horizon_az': [], 'horizon_elev': [], 'grain_kappa': 0.05940923, 'grain_azimuth': 2.24027,
                'stimp_ft': 8.9898, 'user_distance': None,
            },
        ],
    },
    {
        "tag": 'Survey of 3 drops, 6.9 m, 2 cm past: best miss 4.4 mm, just inside the 5 mm',
        "past": 0.02,
        "drops": [
            {
                'f_px': 655.6235, 'baseline': 0.02, 'h_cam': 0.0056, 'tilt': [0.03753603, 0.05768046],
                'tilt_reads': 2, 'flag_found': True, 'flag_bearing': -0.2047439, 'flag_disparity': 1.913527,
                'flag_low_elev': 0.01557257, 'flag_base_visible': True, 'flag_top_visible': False,
                'flag_top_elev': None, 'stick_height_est': 1.97296, 'stick_height_rel_sigma': 0.07,
                'horizon_az': [], 'horizon_elev': [], 'grain_kappa': 0.0, 'grain_azimuth': 1.969082,
                'stimp_ft': 9.709456, 'user_distance': 7.222321,
            },
            {
                'f_px': 655.6235, 'baseline': 0.02, 'h_cam': 0.0056, 'tilt': [0.02806599, 0.06495578],
                'tilt_reads': 2, 'flag_found': True, 'flag_bearing': -0.1834613, 'flag_disparity': 9.641777,
                'flag_low_elev': None, 'flag_base_visible': False, 'flag_top_visible': False, 'flag_top_elev': None,
                'stick_height_est': 2.071226, 'stick_height_rel_sigma': 0.07, 'horizon_az': [], 'horizon_elev': [],
                'grain_kappa': 0.0, 'grain_azimuth': 1.969082, 'stimp_ft': 9.709456, 'user_distance': 7.248801,
            },
            {
                'f_px': 655.6235, 'baseline': 0.02, 'h_cam': 0.0056, 'tilt': [0.03116302, 0.06381817],
                'tilt_reads': 2, 'flag_found': True, 'flag_bearing': -0.2352132, 'flag_disparity': 10.80466,
                'flag_low_elev': 0.008393946, 'flag_base_visible': True, 'flag_top_visible': False,
                'flag_top_elev': None, 'stick_height_est': 1.955064, 'stick_height_rel_sigma': 0.07,
                'horizon_az': [], 'horizon_elev': [], 'grain_kappa': 0.0, 'grain_azimuth': 1.969082,
                'stimp_ft': 9.709456, 'user_distance': None,
            },
        ],
    },
    {
        "tag": 'long Survey of 4 drops, 18.6 m dying putt on a gentle slope (0.13 of critical; best miss 2.4 mm)',
        "past": 0.0,
        "drops": [
            {
                'f_px': 646.0809, 'baseline': 0.02, 'h_cam': 0.0056, 'tilt': [0.001443331, -0.002246916],
                'tilt_reads': 1, 'flag_found': True, 'flag_bearing': 0.1279902, 'flag_disparity': 0.6934207,
                'flag_low_elev': 0.01294423, 'flag_base_visible': False, 'flag_top_visible': True,
                'flag_top_elev': 0.1336368, 'stick_height_est': 2.098586, 'stick_height_rel_sigma': 0.07,
                'horizon_az': [], 'horizon_elev': [], 'grain_kappa': 0.0, 'grain_azimuth': -2.29155,
                'stimp_ft': 19.95401, 'user_distance': 16.8395,
            },
            {
                'f_px': 646.0809, 'baseline': 0.02, 'h_cam': 0.0056, 'tilt': [0.01341883, -0.007446385],
                'tilt_reads': 1, 'flag_found': True, 'flag_bearing': 0.1679252, 'flag_disparity': 1.032985,
                'flag_low_elev': 0.01282072, 'flag_base_visible': True, 'flag_top_visible': False,
                'flag_top_elev': None, 'stick_height_est': 2.172761, 'stick_height_rel_sigma': 0.07,
                'horizon_az': [], 'horizon_elev': [], 'grain_kappa': 0.0, 'grain_azimuth': -2.29155,
                'stimp_ft': 19.95401, 'user_distance': None,
            },
            {
                'f_px': 646.0809, 'baseline': 0.02, 'h_cam': 0.0056, 'tilt': [0.01447437, -0.01350914],
                'tilt_reads': 1, 'flag_found': True, 'flag_bearing': 0.2016604, 'flag_disparity': 2.271281,
                'flag_low_elev': 0.01443758, 'flag_base_visible': True, 'flag_top_visible': False,
                'flag_top_elev': None, 'stick_height_est': 2.165689, 'stick_height_rel_sigma': 0.07,
                'horizon_az': [], 'horizon_elev': [], 'grain_kappa': 0.0, 'grain_azimuth': -2.29155,
                'stimp_ft': 19.95401, 'user_distance': None,
            },
            {
                'f_px': 646.0809, 'baseline': 0.02, 'h_cam': 0.0056, 'tilt': [0.01690477, -0.0197155],
                'tilt_reads': 1, 'flag_found': True, 'flag_bearing': 0.1261851, 'flag_disparity': None,
                'flag_low_elev': 0.01212925, 'flag_base_visible': False, 'flag_top_visible': False,
                'flag_top_elev': None, 'stick_height_est': 2.180696, 'stick_height_rel_sigma': 0.07,
                'horizon_az': [], 'horizon_elev': [], 'grain_kappa': 0.0, 'grain_azimuth': -2.29155,
                'stimp_ft': 19.95401, 'user_distance': None,
            },
        ],
    },
    {
        "tag": 'NOMINAL green: 8.7 m dying putt, slope at 0.17 of critical - the roll budget ends the search at 1e-9 m; without the rule the secant plane is solved',
        "past": 0.0,
        "drops": [
            {
                'f_px': 665.8501, 'baseline': 0.02, 'h_cam': 0.0056, 'tilt': [-0.0007325192, 0.01494364],
                'tilt_reads': 1, 'flag_found': True, 'flag_bearing': 0.3943257, 'flag_disparity': 1.409656,
                'flag_low_elev': 0.01115747, 'flag_base_visible': True, 'flag_top_visible': True,
                'flag_top_elev': 0.24715, 'stick_height_est': 2.06183, 'stick_height_rel_sigma': 0.02,
                'horizon_az': [], 'horizon_elev': [], 'grain_kappa': 0.0, 'grain_azimuth': -1.174487,
                'stimp_ft': 7.052719, 'user_distance': 8.113426,
            },
        ],
    },
    {
        "tag": 'CONTROL, not kept: 15 m dying putt, best miss 5.05 mm (just outside 5 mm): the estimate without the rule',
        "past": 0.0,
        "drops": [
            {
                'f_px': 665.154, 'baseline': 0.02, 'h_cam': 0.0052, 'tilt': [0.01971647, -0.07603277],
                'tilt_reads': 2, 'flag_found': True, 'flag_bearing': 0.339832, 'flag_disparity': 0.8833814,
                'flag_low_elev': -0.002379102, 'flag_base_visible': True, 'flag_top_visible': False,
                'flag_top_elev': None, 'stick_height_est': 1.813778, 'stick_height_rel_sigma': 0.07,
                'horizon_az': [], 'horizon_elev': [], 'grain_kappa': 0.0, 'grain_azimuth': 0.5602637,
                'stimp_ft': 8.438372, 'user_distance': 14.76966,
            },
        ],
    },
    {
        "tag": 'CONTROL, not kept: Survey of 3 drops, best miss 5.9 mm: the estimate without the rule',
        "past": 0.1,
        "drops": [
            {
                'f_px': 658.1238, 'baseline': 0.02, 'h_cam': 0.00561, 'tilt': [-0.004746539, 0.0815502],
                'tilt_reads': 1, 'flag_found': True, 'flag_bearing': 0.09574621, 'flag_disparity': 2.508161,
                'flag_low_elev': 0.001835888, 'flag_base_visible': True, 'flag_top_visible': False,
                'flag_top_elev': None, 'stick_height_est': 1.651067, 'stick_height_rel_sigma': 0.07,
                'horizon_az': [], 'horizon_elev': [], 'grain_kappa': 0.3486415, 'grain_azimuth': 0.09071612,
                'stimp_ft': 8.634654, 'user_distance': None,
            },
            {
                'f_px': 658.1238, 'baseline': 0.02, 'h_cam': 0.00561, 'tilt': [0.0001624042, 0.08059229],
                'tilt_reads': 1, 'flag_found': True, 'flag_bearing': 0.05822247, 'flag_disparity': 3.083149,
                'flag_low_elev': 0.001404558, 'flag_base_visible': True, 'flag_top_visible': False,
                'flag_top_elev': None, 'stick_height_est': 1.674578, 'stick_height_rel_sigma': 0.07,
                'horizon_az': [], 'horizon_elev': [], 'grain_kappa': 0.3486415, 'grain_azimuth': 0.09071612,
                'stimp_ft': 8.634654, 'user_distance': 4.940501,
            },
            {
                'f_px': 658.1238, 'baseline': 0.02, 'h_cam': 0.00561, 'tilt': [-0.005505291, 0.08292585],
                'tilt_reads': 1, 'flag_found': True, 'flag_bearing': 0.1451239, 'flag_disparity': 25.94077,
                'flag_low_elev': -0.006732226, 'flag_base_visible': True, 'flag_top_visible': False,
                'flag_top_elev': None, 'stick_height_est': 1.641385, 'stick_height_rel_sigma': 0.07,
                'horizon_az': [], 'horizon_elev': [], 'grain_kappa': 0.3486415, 'grain_azimuth': 0.09071612,
                'stimp_ft': 8.634654, 'user_distance': None,
            },
        ],
    },
    {
        "tag": 'CONTROL, not kept: 11.7 m dying putt, best miss 8.0 mm: the secant plane, PACE_LIMITED, as without the rule',
        "past": 0.0,
        "drops": [
            {
                'f_px': 639.0243, 'baseline': 0.02, 'h_cam': 0.00561, 'tilt': [0.02135467, 0.0600392],
                'tilt_reads': 1, 'flag_found': True, 'flag_bearing': -0.1216966, 'flag_disparity': 1.056479,
                'flag_low_elev': 0.01226498, 'flag_base_visible': True, 'flag_top_visible': True,
                'flag_top_elev': 0.153668, 'stick_height_est': 1.608615, 'stick_height_rel_sigma': 0.07,
                'horizon_az': [], 'horizon_elev': [], 'grain_kappa': 0.1612972, 'grain_azimuth': -2.132073,
                'stimp_ft': 10.85672, 'user_distance': None,
            },
        ],
    },
    {
        "tag": 'CONTROL, not kept: long Survey of 3 drops, 39.9 m, best miss 22 mm: the secant plane, as without the rule',
        "past": 0.3,
        "drops": [
            {
                'f_px': 646.0576, 'baseline': 0.02, 'h_cam': 0.0056, 'tilt': [-0.008769243, -0.005845523],
                'tilt_reads': 2, 'flag_found': True, 'flag_bearing': -0.1516989, 'flag_disparity': 0.3218727,
                'flag_low_elev': -0.01297055, 'flag_base_visible': True, 'flag_top_visible': True,
                'flag_top_elev': 0.03718478, 'stick_height_est': 1.998873, 'stick_height_rel_sigma': 0.07,
                'horizon_az': [], 'horizon_elev': [], 'grain_kappa': 0.1129363, 'grain_azimuth': 0.7909581,
                'stimp_ft': 14.56156, 'user_distance': None,
            },
            {
                'f_px': 646.0576, 'baseline': 0.02, 'h_cam': 0.0056, 'tilt': [-0.009856232, 0.002698597],
                'tilt_reads': 2, 'flag_found': True, 'flag_bearing': -0.1691512, 'flag_disparity': 0.3844719,
                'flag_low_elev': -0.01413421, 'flag_base_visible': True, 'flag_top_visible': True,
                'flag_top_elev': 0.04340987, 'stick_height_est': 2.014209, 'stick_height_rel_sigma': 0.07,
                'horizon_az': [], 'horizon_elev': [], 'grain_kappa': 0.1129363, 'grain_azimuth': 0.7909581,
                'stimp_ft': 14.56156, 'user_distance': None,
            },
            {
                'f_px': 646.0576, 'baseline': 0.02, 'h_cam': 0.0056, 'tilt': [-0.01299213, 0.011555],
                'tilt_reads': 2, 'flag_found': False, 'flag_bearing': -0.09599301, 'flag_disparity': 1.274379,
                'flag_low_elev': -0.007459097, 'flag_base_visible': False, 'flag_top_visible': True,
                'flag_top_elev': 0.1626551, 'stick_height_est': 1.955937, 'stick_height_rel_sigma': 0.07,
                'horizon_az': [], 'horizon_elev': [], 'grain_kappa': 0.1129363, 'grain_azimuth': 0.7909581,
                'stimp_ft': 14.56156, 'user_distance': None,
            },
        ],
    },
]
