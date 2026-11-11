/*
 * gl_cam.h - camera model: pixels <-> rays <-> bearing / elevation.
 *
 * Pinhole model with one radial distortion term, per camera, plus the
 * rotation and position of the camera in the marker (= IMU) frame, all
 * from the factory calibration record (gl_cal_cam_t).
 *
 *   normalised distorted   xd = (u - cx) / fx,  yd = (v - cy) / fy
 *   distortion             (xd, yd) = (xu, yu) * (1 + k1 * (xu^2 + yu^2))
 *   camera-frame ray       (xu, yu, 1), +x right, +y DOWN, +z forward
 *   marker-frame ray       R_cm * ray,  R_cm from gl_cal_cam_t (see there)
 *
 * Angles relative to GRAVITY need the tilt estimate: `up` is the unit up
 * vector in the marker frame (the calibrated, normalised accelerometer
 * reading).  Bearing is counter-clockwise positive from the marker's
 * forward axis projected on the level plane; elevation is positive upward
 * from the level plane.
 *
 * "Rectified" coordinates (for stereo) are the marker-frame ray divided by
 * its forward component: xr = ray.x / ray.y (right positive), yr = -ray.z /
 * ray.y (down positive).  They are what an ideal camera with unit focal
 * length, perfectly aligned with the marker axes, would measure; the two
 * cameras' xr differ only by baseline / depth.
 *
 * RAM: gl_cam_model_t 68 bytes.  Stack: under 150 bytes.
 */
#ifndef GL_CAM_H
#define GL_CAM_H

#include "gl_cal.h"
#include "gl_types.h"

typedef struct {
    float fx, fy, cx, cy, k1;
    gl_mat3_t r_cm;      /**< camera -> marker rotation */
    gl_vec3_t pos_m;     /**< optical centre in the marker frame, metres */
} gl_cam_model_t;

/** Build the model from a calibration record. */
void gl_cam_model_init(gl_cam_model_t *m, const gl_cal_cam_t *cal);

/** Pixel -> undistorted normalised camera coordinates (xu, yu). */
void gl_cam_undistort(const gl_cam_model_t *m, float u, float v, float *xu, float *yu);

/** Pixel -> unit ray in the marker frame. */
gl_vec3_t gl_cam_pixel_to_ray(const gl_cam_model_t *m, float u, float v);

/** Marker-frame direction -> pixel.  Returns false if the direction is not
 *  in front of the camera (then *u, *v are untouched). */
bool gl_cam_ray_to_pixel(const gl_cam_model_t *m, gl_vec3_t ray_marker, float *u, float *v);

/** Marker-frame POINT (metres) -> pixel, including the camera position
 *  (parallax).  Returns false if the point is behind the camera. */
bool gl_cam_point_to_pixel(const gl_cam_model_t *m, gl_vec3_t point_marker_m, float *u, float *v);

/** Bearing and elevation (rad, relative to gravity) of a marker-frame ray. */
void gl_cam_ray_to_bearing_elev(gl_vec3_t ray_marker, gl_vec3_t up_marker, float *bearing_rad,
                                float *elev_rad);

/** Pixel -> bearing and elevation relative to gravity. */
void gl_cam_pixel_to_bearing_elev(const gl_cam_model_t *m, float u, float v, gl_vec3_t up_marker,
                                  float *bearing_rad, float *elev_rad);

/** Bearing / elevation relative to gravity -> unit ray in the marker frame. */
gl_vec3_t gl_cam_bearing_elev_to_ray(float bearing_rad, float elev_rad, gl_vec3_t up_marker);

/** Pixel -> rectified coordinates (see the file comment). */
void gl_cam_pixel_to_rectified(const gl_cam_model_t *m, float u, float v, float *xr, float *yr);

/**
 * The CALIBRATED HORIZON ROW: the image row, at column u, of directions
 * parallel to the marker's base plane (elevation zero in the MARKER frame).
 * On a planar green the puck lies in the plane of the green, so the far
 * turf appears at this row whatever the slope; the horizon band is centred
 * on it.
 */
float gl_cam_base_plane_row(const gl_cam_model_t *m, float u);

#endif /* GL_CAM_H */
