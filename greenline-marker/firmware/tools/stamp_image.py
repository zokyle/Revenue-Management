#!/usr/bin/env python3
"""Stamp the image header of a GL-1 application image (firmware/boot/gl_boot.h).

    stamp_image.py stamp IN.bin OUT.bin --fw-version 0x0003 --fw-build 20261113 [--hw-rev 5]
    stamp_image.py check IMAGE.bin        exit 0 if the boot stub would start it
    stamp_image.py info IMAGE.bin         print the header as JSON

IN.bin is the application as linked for 0x08002000, with 32 bytes reserved
for the header at offset 0x400 (they must be 0x00 or 0xFF: anything else is
code the header would overwrite, and the tool refuses).  The image is padded
with 0xFF to a multiple of 4 bytes, the header is written and the CRC-32
(zlib) of the whole image - with the header's two CRC fields taken as zero -
goes into it.  The check is the stub's rule, written here a second time on
purpose: `make tooltest` runs both on the same files (tools/boot_check.c is
the stub's own C code) and they must agree.

Python 3, standard library only.  Nothing is executed or downloaded.
"""
import json
import struct
import sys
import zlib

APP_BASE = 0x08002000
APP_MAX = 0x200000 - 0x2000
HDR_OFFSET = 0x400
HDR_LEN = 32
MAGIC = 0x4D494C47
HDR_VERSION = 1
RAM_BASE = 0x20000000
RAM_BYTES = 0x000C0000
HW_REV = 5

REASONS = ["OK", "NO_HEADER", "BAD_VERSION", "BAD_HW", "BAD_LENGTH", "BAD_VECTORS", "BAD_CRC"]


def parse(image):
    f = struct.unpack_from("<IHHIIIIII", image, HDR_OFFSET)
    keys = ("magic", "hdr_version", "hw_rev", "length", "crc32", "fw_version", "fw_build", "reserved", "hdr_crc")
    return dict(zip(keys, f))


def image_crc(image, length):
    body = bytearray(image[:length])
    body[HDR_OFFSET + 12:HDR_OFFSET + 16] = b"\0\0\0\0"
    body[HDR_OFFSET + 28:HDR_OFFSET + 32] = b"\0\0\0\0"
    return zlib.crc32(bytes(body)) & 0xFFFFFFFF


def check(image, region_len=APP_MAX, load_addr=APP_BASE):
    """The stub's rule (gl_boot_image_check).  Returns (reason index, header or None)."""
    if len(image) < HDR_OFFSET + HDR_LEN or region_len < HDR_OFFSET + HDR_LEN:
        return 1, None
    h = parse(image)
    if h["magic"] != MAGIC or zlib.crc32(image[HDR_OFFSET:HDR_OFFSET + HDR_LEN - 4]) & 0xFFFFFFFF != h["hdr_crc"]:
        return 1, None
    if h["hdr_version"] != HDR_VERSION:
        return 2, h
    if h["hw_rev"] != HW_REV:
        return 3, h
    n = h["length"]
    if n < HDR_OFFSET + HDR_LEN or n > region_len or n > len(image) or n % 4:
        return 4, h
    sp, pc = struct.unpack_from("<II", image, 0)
    if (sp < RAM_BASE + 0x100 or sp > RAM_BASE + RAM_BYTES or sp % 8 or pc % 2 == 0
            or pc < load_addr + HDR_OFFSET + HDR_LEN or pc >= load_addr + n):
        return 5, h
    if image_crc(image, n) != h["crc32"]:
        return 6, h
    return 0, h


def stamp(image, fw_version, fw_build, hw_rev=HW_REV):
    image = bytearray(image)
    if len(image) < HDR_OFFSET + HDR_LEN:
        raise ValueError("image shorter than the header slot at 0x%X" % HDR_OFFSET)
    slot = bytes(image[HDR_OFFSET:HDR_OFFSET + HDR_LEN])
    if slot.strip(b"\x00") and slot.strip(b"\xff"):
        raise ValueError("the 32 bytes at 0x%X are not a blank header slot (the image was not linked with one)"
                         % HDR_OFFSET)
    while len(image) % 4:
        image.append(0xFF)
    if len(image) > APP_MAX:
        raise ValueError("image larger than the application region")
    struct.pack_into("<IHHIIIII", image, HDR_OFFSET, MAGIC, HDR_VERSION, hw_rev, len(image), 0,
                     fw_version, fw_build, 0)
    crc = image_crc(image, len(image))
    struct.pack_into("<I", image, HDR_OFFSET + 12, crc)
    struct.pack_into("<I", image, HDR_OFFSET + 28, zlib.crc32(bytes(image[HDR_OFFSET:HDR_OFFSET + 28])) & 0xFFFFFFFF)
    return bytes(image)


def main(argv):
    if len(argv) < 3 or argv[1] not in ("stamp", "check", "info"):
        sys.stderr.write(__doc__)
        return 2
    if argv[1] == "stamp":
        if len(argv) < 4:
            sys.stderr.write(__doc__)
            return 2
        opts = dict(zip(argv[4::2], argv[5::2]))
        try:
            fw_version = int(opts["--fw-version"], 0)
            fw_build = int(opts["--fw-build"], 0)
            hw_rev = int(opts.get("--hw-rev", str(HW_REV)), 0)
            out = stamp(open(argv[2], "rb").read(), fw_version, fw_build, hw_rev)
        except (KeyError, ValueError) as exc:
            sys.stderr.write("stamp_image: %s\n" % exc)
            return 2
        open(argv[3], "wb").write(out)
        h = parse(out)
        print("stamped %s: %d bytes, CRC-32 0x%08X, firmware 0x%04X build %d, board revision %d"
              % (argv[3], h["length"], h["crc32"], h["fw_version"], h["fw_build"], h["hw_rev"]))
        return 0
    image = open(argv[2], "rb").read()
    reason, h = check(image)
    if argv[1] == "info":
        print(json.dumps({"verdict": REASONS[reason], "header": h}, indent=2))
        return 0
    print("%s: %s" % (argv[2], REASONS[reason]))
    return 0 if reason == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
