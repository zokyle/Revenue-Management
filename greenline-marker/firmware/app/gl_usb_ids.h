/*
 * gl_usb_ids.h - the USB vendor and product ids of the GL-1.
 *
 * NONE IS ASSIGNED (DESIGN_SPEC E34: a release gate).  The two values below
 * are NAMED PLACEHOLDERS: 0xFFFF is "no vendor" in the USB-IF's own lists
 * and is never a valid vendor id, so a unit built with them cannot be
 * mistaken for a product, and 0x0000 is no product.  They are the ONLY place
 * the ids are written; hal/stm32u5/gl_hal_stm32u5_usb.c takes them from
 * here.
 *
 * A RELEASE BUILD FAILS WHILE THEY ARE PLACEHOLDERS: `make release-check`,
 * and every build made with RELEASE=1 (which defines GL_RELEASE_BUILD),
 * stops at the #error below.  To release: obtain a vendor id (or a
 * sub-licensed product id), write both numbers here and set
 * GL_USB_IDS_ARE_PLACEHOLDERS to 0.
 */
#ifndef GL_USB_IDS_H
#define GL_USB_IDS_H

#define GL_USB_VID_PLACEHOLDER 0xFFFFu
#define GL_USB_PID_PLACEHOLDER 0x0000u

#define GL_USB_VID GL_USB_VID_PLACEHOLDER
#define GL_USB_PID GL_USB_PID_PLACEHOLDER
/** 1 while GL_USB_VID / GL_USB_PID are the placeholders above. */
#define GL_USB_IDS_ARE_PLACEHOLDERS 1

#if defined(GL_RELEASE_BUILD) && (GL_USB_IDS_ARE_PLACEHOLDERS != 0)
#error "release build with placeholder USB ids: assign GL_USB_VID / GL_USB_PID (app/gl_usb_ids.h, DESIGN_SPEC E34)"
#endif
#if defined(GL_RELEASE_BUILD) && ((GL_USB_VID == 0xFFFFu) || (GL_USB_VID == 0x0000u))
#error "release build with an invalid USB vendor id"
#endif

#endif /* GL_USB_IDS_H */
