/*
 * gl_regulatory.h - the text block of the regulatory and information screen
 * (the INFO item of the settings dial, core/gl_ui.c).
 *
 * THE TEXT BELOW IS A PLACEHOLDER.  The statements a GL-1 must show - which
 * ones, and their exact words - are the business of docs/COMPLIANCE.md (its
 * rows 5 and 33: the FCC part 15 statement if the screen is to serve as the
 * label, the Canadian ICES-003 line, the practice-device statement, the
 * responsible party).  None of them is frozen there, so none is written
 * here: a regulatory sentence copied from memory into firmware would look
 * official and might be wrong.  Whoever freezes the wording replaces
 * GL_REGULATORY_TEXT and sets GL_REGULATORY_TEXT_IS_PLACEHOLDER to 0.
 *
 * WHAT FITS (asserted by tests/test_ui.c): a text page has 10 lines of
 * 12, 15, 17, 19, 19, 20, 19, 18, 17 and 15 characters (the display is
 * round) = 171 character cells; the screen shows up to 4 text pages = 684
 * cells.  Words are not broken, so a real text needs a little less: check
 * it with gl_ui_info_fit().  The font has capitals, digits and the ASCII
 * punctuation from space to underscore only (lower case is drawn as upper
 * case); '\n' starts a new line.  Page 1 of the screen is not text: model,
 * "PRACTICE DEVICE", hardware and firmware version, serial number.
 *
 * A RELEASE BUILD FAILS WHILE THE TEXT IS THE PLACEHOLDER (RELEASE=1, `make
 * release-gate`), like the USB ids of app/gl_usb_ids.h.
 */
#ifndef GL_REGULATORY_H
#define GL_REGULATORY_H

#define GL_REGULATORY_TEXT_PLACEHOLDER \
    "REGULATORY TEXT\nNOT SUPPLIED\n\nPLACEHOLDER. THE\nSTATEMENTS FOR THIS\nSCREEN COME FROM\nDOCS/COMPLIANCE.MD\n(ROWS 5 AND 33)."

#define GL_REGULATORY_TEXT GL_REGULATORY_TEXT_PLACEHOLDER
/** 1 while GL_REGULATORY_TEXT is the placeholder above. */
#define GL_REGULATORY_TEXT_IS_PLACEHOLDER 1

#if defined(GL_RELEASE_BUILD) && (GL_REGULATORY_TEXT_IS_PLACEHOLDER != 0)
#error "release build with the placeholder regulatory text: supply GL_REGULATORY_TEXT (app/gl_regulatory.h, docs/COMPLIANCE.md)"
#endif

#endif /* GL_REGULATORY_H */
