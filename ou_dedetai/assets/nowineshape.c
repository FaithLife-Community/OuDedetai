/*
 * nowineshape.c -- LD_PRELOAD shim for Wine on wlroots-style Wayland compositors.
 *
 * Wine >= 9.12 (commit 0931c2a4, "win32u: Update the window surface shape with
 * color key and alpha") puts an XShape bounding mask on every per-pixel-alpha
 * layered window, derived from the window's alpha channel.  Compositors such as
 * Hyprland do not apply XShape to XWayland surfaces, and XWayland leaves the
 * pixels outside the shape stale, so every tooltip / menu / popup drop shadow
 * renders as an opaque black frame.  Mutter and KWin apply the shape as a mask,
 * which is why the same Wine install looks fine on GNOME and KDE.
 *
 * Under a compositor the mask serves no purpose (it only exists so that
 * non-compositing X setups can click through transparent areas), so this shim
 * swallows exactly that call: XShapeCombineMask() on ShapeBounding with a real
 * mask pixmap.  Everything else passes through unchanged: shape resets
 * (src == None), and XShapeCombineRectangles()/XShapeCombineRegion(), which Wine
 * uses for SetWindowRgn() and to hide zero-sized windows.
 *
 * Built at runtime by ou_dedetai/xshape_shim.py.  No X11 headers are required;
 * the two constants below are stable parts of the Xlib/XShape ABI.
 *
 *   cc -O2 -shared -fPIC -o nowineshape.so nowineshape.c -ldl
 *
 * Diagnosis and code by Claude (Anthropic), working with a Logos user on
 * Omarchy/Hyprland; see the pull request for the full analysis and the
 * reproduction program.
 */
#define _GNU_SOURCE
#include <dlfcn.h>

#define ShapeBounding 0
#define None 0L

typedef void *Display;
typedef unsigned long Window;
typedef unsigned long Pixmap;

void XShapeCombineMask(Display *dpy, Window dest, int dest_kind, int x_off, int y_off, Pixmap src, int op)
{
    static void (*real)(Display *, Window, int, int, int, Pixmap, int);

    if (dest_kind == ShapeBounding && src != None)
        return; /* the alpha-derived mask: drop it */

    if (!real)
        real = dlsym(RTLD_NEXT, "XShapeCombineMask");
    if (real)
        real(dpy, dest, dest_kind, x_off, y_off, src, op);
}
