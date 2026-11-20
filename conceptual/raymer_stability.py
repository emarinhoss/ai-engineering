"""Longitudinal static stability (Raymer 16.3). Distances non-dimensional by the wing MAC
(written X-bar), measured from the same datum."""
import math


def fuselage_cm_alpha_per_deg(K_f, W_f, L_f, c, S_w):
    """C_m_alpha_fus = K_f W_f^2 L_f/(c S_w) per degree (16.22), p. 427 (consistent units)."""
    return K_f * W_f ** 2 * L_f / (c * S_w)


def neutral_point(CLa_w, X_acw, Cma_fus, eta_h, Sh_Sw, CLa_h, dah_da, X_ach):
    """Power-off stick-fixed neutral point (16.9), p. 417, without the propeller terms."""
    tail = eta_h * Sh_Sw * CLa_h * dah_da
    return (CLa_w * X_acw - Cma_fus + tail * X_ach) / (CLa_w + tail)


def cm_alpha(CLa_w, X_np, X_cg):
    """C_m_alpha = -CL_alpha (X_np - X_cg) (16.10), p. 417."""
    return -CLa_w * (X_np - X_cg)


def static_margin(X_np, X_cg):
    """Static margin (X_np - X_cg) in MAC (DR-1, p. 580)."""
    return X_np - X_cg


def downwash_gradient_lifting_line(CLa_w, aspect_ratio):
    """d(eps)/d(alpha) = 2 CL_alpha/(pi A): the far-wake value of an elliptic wing.

    NOT from the library. Raymer's subsonic method is a chart (Fig. 16.12, p. 425), which the notes
    describe but cannot be read numerically. For DR-1 it gives 0.51 against the chart's 0.38, i.e.
    conservative there. It is not conservative in general: for the Task 12 pusher the vortex
    lattice gives 0.38 at the tail against this formula's 0.35
    (docs/validation/2026-11-20_task12_stage3_aero.md)."""
    return 2.0 * CLa_w / (math.pi * aspect_ratio)
