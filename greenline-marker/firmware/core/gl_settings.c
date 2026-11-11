/* gl_settings.c - see gl_settings.h. */
#include "gl_settings.h"

#include <string.h>

#include "gl_fmt.h"

/* Dial step of the manual distance, in centimetres, per units setting. */
static float distance_step_cm(uint8_t units)
{
    switch (units) {
    case GL_UNITS_METRES: return 20.0f;                       /* 0.2 m */
    case GL_UNITS_PACES: return 50.0f * GL_PACE_LENGTH_M;     /* half a pace */
    default: return 15.24f;                                   /* half a foot */
    }
}

void gl_settings_defaults(gl_settings_t *s)
{
    s->stimp_x2 = (uint8_t)GL_STIMP_X2_DEFAULT;
    s->units = (uint8_t)GL_UNITS_FEET;
    s->pace = (uint8_t)GL_PACE_NORMAL;
    s->grass = (uint8_t)GL_GRASS_BENT;
    s->grain_enable = 0; /* grain ships DISABLED */
    s->raw_log_level = (uint8_t)GL_RAWLOG_OFF;
    s->manual_distance_cm = 0;
}

gl_status_t gl_settings_validate(const gl_settings_t *s)
{
    if (s->stimp_x2 < GL_STIMP_X2_MIN || s->stimp_x2 > GL_STIMP_X2_MAX ||
        s->units >= (uint8_t)GL_UNITS_COUNT || s->pace >= (uint8_t)GL_PACE_COUNT ||
        s->grass >= (uint8_t)GL_GRASS_COUNT || s->grain_enable > 1u ||
        s->raw_log_level >= (uint8_t)GL_RAWLOG_COUNT ||
        s->manual_distance_cm > GL_MANUAL_DISTANCE_MAX_CM) {
        return GL_ERR_RANGE;
    }
    return GL_OK;
}

void gl_settings_encode(const gl_settings_t *s, uint8_t out[GL_SETTINGS_BLOB_LEN])
{
    memset(out, 0, GL_SETTINGS_BLOB_LEN);
    out[0] = (uint8_t)GL_SETTINGS_VERSION;
    out[1] = s->stimp_x2;
    out[2] = s->units;
    out[3] = s->pace;
    out[4] = s->grass;
    out[5] = s->grain_enable;
    out[6] = s->raw_log_level;
    gl_put_u16(&out[8], s->manual_distance_cm);
}

gl_status_t gl_settings_decode(const uint8_t *blob, size_t len, gl_settings_t *s)
{
    gl_settings_t t;
    gl_status_t st;
    if (blob == NULL || len < GL_SETTINGS_BLOB_LEN) {
        return GL_ERR_PARAM;
    }
    if (blob[0] != GL_SETTINGS_VERSION) {
        return GL_ERR_UNSUPPORTED;
    }
    t.stimp_x2 = blob[1];
    t.units = blob[2];
    t.pace = blob[3];
    t.grass = blob[4];
    t.grain_enable = blob[5];
    t.raw_log_level = blob[6];
    t.manual_distance_cm = gl_get_u16(&blob[8]);
    st = gl_settings_validate(&t);
    if (st == GL_OK) {
        *s = t;
    }
    return st;
}

float gl_settings_stimp_ft(const gl_settings_t *s)
{
    return 0.5f * (float)s->stimp_x2;
}

float gl_settings_decel_mps2(const gl_settings_t *s)
{
    return (1.83f * 1.83f) / (2.0f * gl_settings_stimp_ft(s) * 0.3048f);
}

float gl_settings_past_m(const gl_settings_t *s)
{
    switch (s->pace) {
    case GL_PACE_DIE: return 0.0f;
    case GL_PACE_FIRM: return 0.45f;
    default: return 0.30f;
    }
}

float gl_settings_manual_distance_m(const gl_settings_t *s)
{
    return 0.01f * (float)s->manual_distance_cm;
}

const char *gl_settings_item_name(gl_item_t item)
{
    switch (item) {
    case GL_ITEM_STIMP: return "STIMP";
    case GL_ITEM_UNITS: return "UNITS";
    case GL_ITEM_PACE: return "PACE";
    case GL_ITEM_GRASS: return "GRASS";
    case GL_ITEM_GRAIN: return "GRAIN";
    case GL_ITEM_DISTANCE: return "DIST";
    case GL_ITEM_RAWLOG: return "RAW LOG";
    default: return "?";
    }
}

void gl_settings_item_range(gl_item_t item, int *min, int *max)
{
    *min = 0;
    switch (item) {
    case GL_ITEM_STIMP:
        *min = (int)GL_STIMP_X2_MIN;
        *max = (int)GL_STIMP_X2_MAX;
        break;
    case GL_ITEM_UNITS: *max = (int)GL_UNITS_COUNT - 1; break;
    case GL_ITEM_PACE: *max = (int)GL_PACE_COUNT - 1; break;
    case GL_ITEM_GRASS: *max = (int)GL_GRASS_COUNT - 1; break;
    case GL_ITEM_GRAIN: *max = 1; break;
    case GL_ITEM_DISTANCE: *max = 196; break; /* 196 half feet = 29.9 m; clamped in cm */
    case GL_ITEM_RAWLOG: *max = (int)GL_RAWLOG_COUNT - 1; break;
    default: *max = 0; break;
    }
}

int gl_settings_item_get(const gl_settings_t *s, gl_item_t item)
{
    switch (item) {
    case GL_ITEM_STIMP: return (int)s->stimp_x2;
    case GL_ITEM_UNITS: return (int)s->units;
    case GL_ITEM_PACE: return (int)s->pace;
    case GL_ITEM_GRASS: return (int)s->grass;
    case GL_ITEM_GRAIN: return (int)s->grain_enable;
    case GL_ITEM_DISTANCE:
        return gl_roundi((float)s->manual_distance_cm / distance_step_cm(s->units));
    case GL_ITEM_RAWLOG: return (int)s->raw_log_level;
    default: return 0;
    }
}

void gl_settings_item_set(gl_settings_t *s, gl_item_t item, int value)
{
    int lo, hi;
    gl_settings_item_range(item, &lo, &hi);
    value = gl_clampi(value, lo, hi);
    switch (item) {
    case GL_ITEM_STIMP: s->stimp_x2 = (uint8_t)value; break;
    case GL_ITEM_UNITS: s->units = (uint8_t)value; break;
    case GL_ITEM_PACE: s->pace = (uint8_t)value; break;
    case GL_ITEM_GRASS: s->grass = (uint8_t)value; break;
    case GL_ITEM_GRAIN: s->grain_enable = (uint8_t)value; break;
    case GL_ITEM_DISTANCE: {
        int cm = gl_roundi((float)value * distance_step_cm(s->units));
        s->manual_distance_cm = (uint16_t)gl_clampi(cm, 0, (int)GL_MANUAL_DISTANCE_MAX_CM);
        break;
    }
    case GL_ITEM_RAWLOG: s->raw_log_level = (uint8_t)value; break;
    default: break;
    }
}

void gl_settings_format_distance(const gl_settings_t *s, float metres, char *out, size_t cap)
{
    if (cap == 0u) {
        return;
    }
    out[0] = '\0';
    switch (s->units) {
    case GL_UNITS_METRES:
        gl_fmt_fixed(out, cap, metres, 1);
        gl_fmt_append(out, cap, "M");
        break;
    case GL_UNITS_PACES:
        gl_fmt_fixed(out, cap, metres / GL_PACE_LENGTH_M, 1);
        gl_fmt_append(out, cap, "P");
        break;
    default:
        gl_fmt_fixed(out, cap, metres / 0.3048f, 1);
        gl_fmt_append(out, cap, "FT");
        break;
    }
}

void gl_settings_item_format(const gl_settings_t *s, gl_item_t item, char *out, size_t cap)
{
    static const char *const units_name[GL_UNITS_COUNT] = { "FEET", "METRES", "PACES" };
    static const char *const pace_name[GL_PACE_COUNT] = { "DIE", "NORMAL", "FIRM" };
    static const char *const grass_name[GL_GRASS_COUNT] = { "BENT", "POA", "BERMUDA" };
    static const char *const raw_name[GL_RAWLOG_COUNT] = { "OFF", "FIRST", "ALL" };
    const char *txt = NULL;

    if (cap == 0u) {
        return;
    }
    out[0] = '\0';
    switch (item) {
    case GL_ITEM_STIMP:
        gl_fmt_fixed(out, cap, gl_settings_stimp_ft(s), 1);
        return;
    case GL_ITEM_UNITS: txt = units_name[s->units % GL_UNITS_COUNT]; break;
    case GL_ITEM_PACE: txt = pace_name[s->pace % GL_PACE_COUNT]; break;
    case GL_ITEM_GRASS: txt = grass_name[s->grass % GL_GRASS_COUNT]; break;
    case GL_ITEM_GRAIN: txt = (s->grain_enable != 0u) ? "ON" : "OFF"; break;
    case GL_ITEM_RAWLOG: txt = raw_name[s->raw_log_level % GL_RAWLOG_COUNT]; break;
    case GL_ITEM_DISTANCE:
        if (s->manual_distance_cm == 0u) {
            txt = "--";
        } else {
            gl_settings_format_distance(s, gl_settings_manual_distance_m(s), out, cap);
            return;
        }
        break;
    default: txt = "?"; break;
    }
    gl_fmt_append(out, cap, txt);
}
