"""Figures and numbers for the Gaussian process primer (entry 17A of docs/talk/study_guide_drone.html).

    python docs/talk/make_gp_primer.py

Every figure is an ILLUSTRATION on a made-up function, not a study result. The fits use the study's
own code (surrogate.gp.GP, surrogate.mf_gp.TwoLevelGP), so the pictures show what that code does.
Writes docs/talk/gp_primer/<name>.svg and values.json (every number the primer quotes), then
replaces each block <!-- gpfig:NAME --> ... <!-- /gpfig:NAME --> in the guide with the SVG inline.
Seeded: two runs give the same files.
"""
import json
import math
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from surrogate.gp import GP, Standardizer
from surrogate.mf_gp import TwoLevelGP

OUT = HERE / "gp_primer"
GUIDE = HERE / "study_guide_drone.html"
INK, ACC, MUTED, OK, BAND = "#1f3a5f", "#c8551a", "#5b6473", "#2e7d4f", "#c9d5e6"
plt.rcParams.update({"svg.fonttype": "none", "font.size": 10, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.edgecolor": MUTED, "font.family": "sans-serif",
                     "svg.hashsalt": "gp-primer"})
V = {}          # every number the primer quotes
FIGS = {}       # name -> svg text


def save(fig, name):
    path = OUT / f"{name}.svg"
    fig.savefig(path, format="svg", bbox_inches="tight", metadata={"Date": None}, dpi=110)
    plt.close(fig)
    text = path.read_text()
    FIGS[name] = text[text.index("<svg"):]


def matern(r, nu):
    """Correlation at scaled distance r. nu = 0.5, 1.5, 2.5, or inf (squared exponential)."""
    if nu == 0.5:
        return np.exp(-r)
    if nu == 1.5:
        return (1 + math.sqrt(3) * r) * np.exp(-math.sqrt(3) * r)
    if nu == 2.5:
        return (1 + math.sqrt(5) * r + 5 * r**2 / 3) * np.exp(-math.sqrt(5) * r)
    return np.exp(-0.5 * r**2)


def cov(a, b, ls, nu=2.5, sf2=1.0):
    return sf2 * matern(np.abs(a[:, None] - b[None, :]) / ls, nu)


def posterior(x, y, xs, ls, sf2=1.0, sn2=1e-8, nu=2.5):
    """The two posterior relations of the primer, written out (constant mean 0)."""
    K = cov(x, x, ls, nu, sf2) + (sn2 + 1e-10) * np.eye(len(x))
    ks = cov(xs, x, ls, nu, sf2)
    L = np.linalg.cholesky(K)
    alpha = np.linalg.solve(L.T, np.linalg.solve(L, y))
    v = np.linalg.solve(L, ks.T)
    return ks @ alpha, np.maximum(sf2 - (v**2).sum(0), 1e-12)


def fit_gp(x, y, lo, hi):
    """The study's GP, as the study uses it: inputs scaled to [0, 1], outputs standardised."""
    st = Standardizer().fit(y)
    gp = GP().fit(((x - lo) / (hi - lo))[:, None], st.transform(y))
    def pred(xs, noise=False):
        m, v = gp.predict(((xs - lo) / (hi - lo))[:, None], noise=noise)
        return st.inverse(m).numpy(), st.inverse_var(v).numpy()
    return gp, st, pred


def road(x):
    """A made-up temperature along a 20-mile road, degrees F."""
    return 61 + 3.0 * np.sin(x / 2.6) + 0.12 * x


def phi(z):
    return np.exp(-0.5 * z**2) / math.sqrt(2 * math.pi)


def Phi(z):
    return 0.5 * (1 + np.vectorize(math.erf)(z / math.sqrt(2)))


def fig_bell():
    z = np.linspace(-4, 4, 400)
    fig, ax = plt.subplots(figsize=(6.4, 2.6))
    ax.fill_between(z, phi(z), where=np.abs(z) <= 2, color=BAND, label="within 2 sd: 95.4 %")
    ax.fill_between(z, phi(z), where=np.abs(z) <= 1, color="#8fa8cc", label="within 1 sd: 68.3 %")
    ax.plot(z, phi(z), color=INK, lw=2)
    ax.set_xticks(range(-3, 4), ["mean−3sd", "−2sd", "−1sd", "mean", "+1sd", "+2sd", "+3sd"])
    ax.set_yticks([]); ax.set_ylabel("how likely")
    ax.legend(frameon=False, loc="upper right")
    save(fig, "bell")
    V["p1"] = float(math.erf(1 / math.sqrt(2))); V["p2"] = float(math.erf(2 / math.sqrt(2)))
    V["p3"] = float(math.erf(3 / math.sqrt(2)))


def fig_joint():
    rng = np.random.default_rng(1)
    fig, axs = plt.subplots(1, 3, figsize=(9.6, 3.0))
    x1 = 1.5
    for ax, rho in zip(axs[:2], (0.0, 0.8)):
        z = rng.multivariate_normal([0, 0], [[1, rho], [rho, 1]], 1500)
        ax.scatter(z[:, 0], z[:, 1], s=3, color=INK, alpha=0.35, rasterized=True)
        ax.axvline(x1, color=ACC, lw=1.5)
        ax.set_title(f"correlation {rho:g}", fontsize=10)
        ax.set_xlabel("older sibling (sd from mean)"); ax.set_ylabel("younger sibling")
        ax.set_xlim(-3.5, 3.5); ax.set_ylim(-3.5, 3.5); ax.set_aspect("equal")
    y = np.linspace(-3.5, 3.5, 300)
    axs[2].plot(y, phi(y), color=MUTED, lw=1.5, ls="--", label="before: mean 0, sd 1")
    m, s = 0.8 * x1, math.sqrt(1 - 0.8**2)
    axs[2].plot(y, phi((y - m) / s) / s, color=ACC, lw=2, label=f"after: mean {m:.1f}, sd {s:.1f}")
    axs[2].set_title("younger sibling, after we measure\nthe older one at +1.5 sd (corr. 0.8)",
                     fontsize=10)
    axs[2].set_yticks([]); axs[2].legend(frameon=False, fontsize=8, loc="upper left")
    fig.tight_layout()
    save(fig, "joint")
    V["sib"] = {"rho": 0.8, "x1": x1, "mean": m, "sd": s}


def fig_kernel():
    r = np.linspace(0, 3, 300)
    fig, ax = plt.subplots(figsize=(6.4, 2.8))
    for nu, lab, c in ((0.5, "Matérn 1/2", MUTED), (1.5, "Matérn 3/2", OK),
                       (2.5, "Matérn 5/2 (this repository)", ACC), (math.inf, "squared exponential", INK)):
        ax.plot(r, matern(r, nu), color=c, lw=2.4 if nu == 2.5 else 1.5, label=lab)
    ax.set_xlabel("distance between two inputs, in lengthscales  r = |x − x′| / ℓ")
    ax.set_ylabel("correlation of the outputs")
    ax.legend(frameon=False)
    save(fig, "kernel")
    V["rho_r1_m52"] = float(matern(np.array(1.0), 2.5)); V["rho_r2_m52"] = float(matern(np.array(2.0), 2.5))


def draws(x, ls, nu, z):
    K = cov(x, x, ls, nu) + 1e-8 * np.eye(len(x))
    return np.linalg.cholesky(K) @ z


def fig_prior():
    x = np.linspace(0, 1, 300)
    z = np.random.default_rng(7).standard_normal((300, 3))
    fig, axs = plt.subplots(1, 3, figsize=(9.6, 2.6), sharey=True)
    for ax, ls in zip(axs, (0.05, 0.15, 0.5)):
        ax.plot(x, draws(x, ls, 2.5, z), lw=1.4, color=INK, alpha=0.8)
        ax.set_title(f"lengthscale ℓ = {ls:g}", fontsize=10); ax.set_xlabel("input x")
        ax.axhspan(-2, 2, color=BAND, alpha=0.4, lw=0)
    axs[0].set_ylabel("f(x), three random draws")
    fig.tight_layout()
    save(fig, "prior")
    fig, axs = plt.subplots(1, 4, figsize=(10.4, 2.4), sharey=True)
    z = np.random.default_rng(3).standard_normal(300)
    for ax, (nu, lab) in zip(axs, ((0.5, "Matérn 1/2"), (1.5, "Matérn 3/2"), (2.5, "Matérn 5/2"),
                                   (math.inf, "squared exp."))):
        ax.plot(x, draws(x, 0.2, nu, z), color=ACC if nu == 2.5 else INK, lw=1.4)
        ax.set_title(lab, fontsize=10); ax.set_xlabel("x")
    fig.tight_layout()
    save(fig, "smooth")


def fig_road():
    posts = np.array([2.0, 5.0, 9.0, 10.5, 12.0])
    temps = road(posts)
    _, _, pred = fit_gp(posts, temps, 0.0, 20.0)
    xs = np.linspace(0, 20, 401)
    m, v = pred(xs)
    s = np.sqrt(v)
    fig, ax = plt.subplots(figsize=(7.6, 3.2))
    ax.fill_between(xs, m - 2 * s, m + 2 * s, color=BAND, lw=0, label="95 % band (mean ± 2 sd)")
    ax.plot(xs, road(xs), color=MUTED, ls="--", lw=1.2, label="the true temperature (unknown to the model)")
    ax.plot(xs, m, color=INK, lw=2, label="GP mean (best guess)")
    ax.plot(posts, temps, "o", color=ACC, ms=7, label="thermometers")
    out = {}
    for mile in (7.0, 19.0):
        mm, vv = pred(np.array([mile]))
        out[mile] = (float(mm[0]), float(math.sqrt(vv[0])), float(road(np.array(mile))))
        ax.annotate(f"mile {mile:g}: {mm[0]:.1f} ± {2 * math.sqrt(vv[0]):.1f} °F", (mile, mm[0]),
                    xytext=(mile - 6 if mile > 15 else mile - 1, mm[0] + 6.5), fontsize=9, color=INK,
                    arrowprops={"arrowstyle": "->", "color": INK, "lw": 0.8})
    ax.set_xlabel("mile marker"); ax.set_ylabel("temperature (°F)")
    ax.legend(frameon=False, fontsize=8, loc="lower left", ncol=2)
    ax.set_ylim(48, 76)
    save(fig, "road")
    V["road"] = {"posts": posts.tolist(), "temps": [round(t, 3) for t in temps],
                 "mile7": out[7.0], "mile19": out[19.0]}


def fig_grow():
    order = np.array([10.0, 3.0, 17.0, 6.5, 13.5, 1.0, 19.5, 8.5])
    xs = np.linspace(0, 20, 401)
    fig, axs = plt.subplots(1, 3, figsize=(10.4, 2.8), sharey=True)
    V["grow_max_sd"] = {}
    for ax, n in zip(axs, (2, 4, 8)):
        x = order[:n]
        m, v = posterior((x - 10) / 10, road(x) - 62, (xs - 10) / 10, ls=0.35, sf2=4.0)
        s = np.sqrt(v)
        ax.fill_between(xs, m + 62 - 2 * s, m + 62 + 2 * s, color=BAND, lw=0)
        ax.plot(xs, road(xs), color=MUTED, ls="--", lw=1)
        ax.plot(xs, m + 62, color=INK, lw=2)
        ax.plot(x, road(x), "o", color=ACC, ms=6)
        ax.set_title(f"{n} runs: largest sd {s.max():.2f} °F", fontsize=10); ax.set_xlabel("mile")
        V["grow_max_sd"][n] = float(s.max())
    axs[0].set_ylabel("°F")
    fig.tight_layout()
    save(fig, "grow")


def fig_noise():
    rng = np.random.default_rng(11)
    x = np.sort(rng.uniform(0, 20, 14))
    y = road(x) + rng.normal(0, 0.8, x.size)
    xs = np.linspace(0, 20, 401)
    fig, axs = plt.subplots(1, 2, figsize=(9.6, 2.9), sharey=True)
    for ax, sn2, title in ((axs[0], 1e-8, "noise fixed at almost zero: interpolation"),
                           (axs[1], 0.8**2 / 4.0, "noise in the model: regression")):
        m, v = posterior((x - 10) / 10, (y - 62) / 2, (xs - 10) / 10, ls=0.12 if sn2 < 1e-6 else 0.35,
                         sf2=1.0, sn2=sn2)
        s = 2 * np.sqrt(v)
        ax.fill_between(xs, 62 + 2 * (m - 2 * s / 2), 62 + 2 * (m + 2 * s / 2), color=BAND, lw=0)
        ax.plot(xs, road(xs), color=MUTED, ls="--", lw=1)
        ax.plot(xs, 62 + 2 * m, color=INK, lw=2)
        ax.plot(x, y, "o", color=ACC, ms=5)
        ax.set_title(title, fontsize=10); ax.set_xlabel("mile")
    axs[0].set_ylabel("°F")
    fig.tight_layout()
    save(fig, "noise")


def fig_lml():
    rng = np.random.default_rng(5)
    x = np.sort(rng.uniform(0, 1, 12))
    y = np.sin(9 * x) + rng.normal(0, 0.1, x.size)
    y = (y - y.mean()) / y.std()
    lss = np.exp(np.linspace(np.log(0.01), np.log(3), 200))
    fitp, comp = [], []
    for ls in lss:
        K = cov(x, x, ls) + 0.01 * np.eye(x.size)
        L = np.linalg.cholesky(K)
        a = np.linalg.solve(L, y)
        fitp.append(-0.5 * a @ a); comp.append(-np.log(np.diag(L)).sum())
    fitp, comp = np.array(fitp), np.array(comp)
    tot = fitp + comp - 0.5 * x.size * math.log(2 * math.pi)
    best = lss[tot.argmax()]
    fig, axs = plt.subplots(1, 2, figsize=(10, 3.0))
    axs[0].semilogx(lss, fitp, color=OK, lw=1.6, label="data fit  −½ yᵀK⁻¹y")
    axs[0].semilogx(lss, comp, color=MUTED, lw=1.6, label="complexity  −½ log|K|")
    axs[0].semilogx(lss, tot, color=INK, lw=2.4, label="log marginal likelihood (sum)")
    axs[0].axvline(best, color=ACC, lw=1.2)
    axs[0].set_ylim(-60, 25); axs[0].set_xlabel("lengthscale ℓ (log axis)"); axs[0].legend(frameon=False, fontsize=8)
    xs = np.linspace(0, 1, 300)
    for ls, c, lab in ((0.02, MUTED, "ℓ = 0.02 (too short)"), (best, ACC, f"ℓ = {best:.3f} (best)"),
                       (2.0, OK, "ℓ = 2 (too long)")):
        m, _ = posterior(x, y, xs, ls, sn2=0.01)
        axs[1].plot(xs, m, color=c, lw=1.8, label=lab)
    axs[1].plot(x, y, "o", color=INK, ms=5); axs[1].legend(frameon=False, fontsize=8)
    axs[1].set_xlabel("x"); axs[1].set_title("posterior mean for three lengthscales", fontsize=10)
    fig.tight_layout()
    save(fig, "lml")
    V["lml_best_ls"] = float(best)


def fig_acq():
    f = lambda x: np.sin(3 * x) + 0.3 * x**2 - 0.6 * x
    x = np.array([-1.6, -0.4, 0.9, 1.7, 2.0])
    y = f(x)
    xs = np.linspace(-2, 2, 401)
    m, v = posterior(x / 2, y, xs / 2, ls=0.3, sf2=1.0)
    s = np.sqrt(v)
    best = y.min()
    gap = best - m
    z = gap / s
    ei = gap * Phi(z) + s * phi(z)
    fig, axs = plt.subplots(2, 1, figsize=(7.4, 4.4), sharex=True, gridspec_kw={"height_ratios": [2, 1.3]})
    axs[0].fill_between(xs, m - 2 * s, m + 2 * s, color=BAND, lw=0)
    axs[0].plot(xs, f(xs), color=MUTED, ls="--", lw=1); axs[0].plot(xs, m, color=INK, lw=2)
    axs[0].plot(x, y, "o", color=ACC, ms=6); axs[0].axhline(best, color=OK, lw=1, ls=":")
    axs[0].set_ylabel("cost (lower is better)")
    axs[0].text(-2, best - 0.35, "best run so far", color=OK, fontsize=8)
    axs[1].plot(xs, ei / ei.max(), color=ACC, lw=2, label="expected improvement")
    axs[1].plot(xs, v / v.max(), color=INK, lw=1.4, ls="--", label="variance (max-variance rule)")
    i, j = int(ei.argmax()), int(v.argmax())
    axs[1].plot(xs[i], 1, "v", color=ACC, ms=8); axs[1].plot(xs[j], 1, "v", color=INK, ms=8)
    axs[1].set_ylabel("score (scaled to 1)"); axs[1].set_xlabel("design input x")
    axs[1].legend(frameon=False, fontsize=8, loc="center left")
    fig.tight_layout()
    save(fig, "acq")
    V["acq"] = {"next_ei": float(xs[i]), "next_var": float(xs[j]), "best": float(best),
                "true_min_x": float(xs[f(xs).argmin()]), "n_runs": int(x.size)}


def fig_two_level():
    hi = lambda x: np.sin(8 * x) * x + 0.5 * x
    lo = lambda x: 0.8 * hi(x) - 0.3 * x + 0.2
    XL = np.linspace(0, 1, 25)
    XH = np.array([0.05, 0.3, 0.55, 0.8, 0.98])
    xs = np.linspace(0, 1, 300)
    t = lambda a: torch.as_tensor(a, dtype=torch.float64)
    mf = TwoLevelGP().fit(t(XL[:, None]), t(lo(XL)), t(XH[:, None]), t(hi(XH)), t(lo(XH)))
    m2, v2 = (a.numpy() for a in mf.predict(t(xs[:, None])))
    _, _, pred1 = fit_gp(XH, hi(XH), 0.0, 1.0)
    m1, v1 = pred1(xs)
    fig, axs = plt.subplots(1, 2, figsize=(10, 3.0), sharey=True)
    for ax, m, v, title in ((axs[0], m1, v1, "one GP on the 5 expensive runs"),
                            (axs[1], m2, v2, f"two-level GP (fitted ρ = {mf.rho:.2f})")):
        s = np.sqrt(v)
        ax.fill_between(xs, m - 2 * s, m + 2 * s, color=BAND, lw=0)
        ax.plot(xs, hi(xs), color=MUTED, ls="--", lw=1, label="expensive truth")
        ax.plot(xs, m, color=INK, lw=2, label="prediction")
        ax.plot(XH, hi(XH), "o", color=ACC, ms=6, label="5 expensive runs")
        ax.set_title(title, fontsize=10); ax.set_xlabel("x")
    axs[1].plot(XL, lo(XL), ".", color=OK, ms=5, label="25 cheap runs")
    axs[1].legend(frameon=False, fontsize=8, loc="lower right")
    fig.tight_layout()
    save(fig, "twolevel")
    rmse = lambda m: float(np.sqrt(np.mean((m - hi(xs)) ** 2)))
    V["twolevel"] = {"rho": float(mf.rho), "rmse_one": rmse(m1), "rmse_two": rmse(m2)}


def fig_calibration():
    """Coverage of held-out noisy runs by the study's fitted GP, at two training sizes."""
    xt_rng = np.random.default_rng(40)
    xt = xt_rng.uniform(0, 20, 400); yt = road(xt) + xt_rng.normal(0, 0.5, xt.size)
    levels = np.linspace(0.05, 0.95, 19)
    fig, ax = plt.subplots(figsize=(4.6, 4.0))
    ax.plot([0, 1], [0, 1], color=MUTED, ls=":", lw=1, label="perfect calibration")
    V["calib"] = {}
    for n, c in ((12, INK), (30, ACC)):
        rng = np.random.default_rng(4)
        x = rng.uniform(0, 20, n); y = road(x) + rng.normal(0, 0.5, n)
        gp, st, pred = fit_gp(x, y, 0.0, 20.0)
        m, v = pred(xt, noise=True)
        z = np.abs(yt - m) / np.sqrt(v)
        cover = [float(np.mean(z <= math.sqrt(2) * _erfinv(p))) for p in levels]
        ax.plot(levels, cover, "o-", color=c, ms=3, lw=1.6, label=f"{n} training runs")
        V["calib"][n] = {"cov80": float(np.mean(z <= math.sqrt(2) * _erfinv(0.8))),
                         "lengthscale_box": float(math.exp(gp.theta[0])),
                         "noise_sd_F": float(math.sqrt(gp.noise_var().item()) * float(st.std)),
                         "true_noise_sd_F": 0.5}
    ax.set_xlabel("stated probability of the interval"); ax.set_ylabel("fraction of held-out runs inside")
    ax.legend(frameon=False, fontsize=8, loc="upper left"); ax.set_aspect("equal")
    save(fig, "calib")


def _erfinv(p):
    lo, hi = 0.0, 6.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if math.erf(mid) < p else (lo, mid)
    return 0.5 * (lo + hi)


def hand_example():
    """Two observations, one prediction, done with numbers small enough for a pencil."""
    x, y, xs, ls = np.array([0.0, 1.0]), np.array([1.0, 2.0]), np.array([0.5]), 1.0
    K = cov(x, x, ls)
    ks = cov(xs, x, ls)[0]
    Kinv = np.linalg.inv(K)
    V["hand"] = {"k01": float(K[0, 1]), "ks": ks.tolist(), "Kinv": Kinv.tolist(),
                 "w": (ks @ Kinv).tolist(), "mean": float(ks @ Kinv @ y),
                 "var": float(1 - ks @ Kinv @ ks), "rho_half": float(ks[0])}


def splice():
    html = GUIDE.read_text()
    for name, svg in FIGS.items():
        pat = re.compile(rf"(<!-- gpfig:{name} -->).*?(<!-- /gpfig:{name} -->)", re.DOTALL)
        if not pat.search(html):
            continue
        html = pat.sub(lambda m, svg=svg: m.group(1) + svg + m.group(2), html)
    GUIDE.write_text(html)


def main():
    OUT.mkdir(exist_ok=True)
    torch.manual_seed(0)
    for f in (fig_bell, fig_joint, fig_kernel, fig_prior, fig_road, fig_grow, fig_noise, fig_lml,
              fig_acq, fig_two_level, fig_calibration, hand_example):
        f()
    (OUT / "values.json").write_text(json.dumps(V, indent=1, default=float) + "\n")
    splice()
    print(json.dumps(V, indent=1, default=float))


if __name__ == "__main__":
    main()
