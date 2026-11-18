/*
 * boot_check.c - the boot stub's own image check as a host program:
 *
 *     boot_check IMAGE.bin      prints the verdict; exit 0 = the stub starts it
 *
 * It runs boot/gl_boot_logic.c, the code that is in the stub, on a file.
 * `make tooltest` uses it against tools/stamp_image.py (the same rule,
 * written independently in Python): both must give the same verdict on
 * stamped, truncated and damaged images.
 */
#include <stdio.h>
#include <stdlib.h>

#include "gl_boot.h"

int main(int argc, char **argv)
{
    static const char *const name[] = { "OK", "NO_HEADER", "BAD_VERSION", "BAD_HW", "BAD_LENGTH",
                                        "BAD_VECTORS", "BAD_CRC" };
    static uint8_t image[4u * 1024u * 1024u];
    gl_boot_header_t h;
    gl_boot_img_t r;
    size_t n;
    FILE *f;

    if (argc != 2) {
        fprintf(stderr, "usage: boot_check IMAGE.bin\n");
        return 2;
    }
    f = fopen(argv[1], "rb");
    if (f == NULL) {
        fprintf(stderr, "boot_check: cannot open %s\n", argv[1]);
        return 2;
    }
    n = fread(image, 1, sizeof(image), f);
    fclose(f);
    /* the stub sees the whole application region; a file is as long as the
     * image that was written, and the flash behind it is not this image's */
    r = gl_boot_image_check(image, (n < GL_BOOT_APP_MAX_BYTES) ? n : GL_BOOT_APP_MAX_BYTES,
                            GL_BOOT_APP_BASE, &h);
    printf("%s: %s\n", argv[1], name[r]);
    return (r == GL_BOOT_IMG_OK) ? 0 : 1;
}
