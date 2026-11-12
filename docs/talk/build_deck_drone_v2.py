"""Build docs/talk/deck_drone_v2.pptx (version 2 of the drone talk) from docs/talk/outline_drone_v2.md.

Run from the repository root with:
    python -m docs.talk.build_deck_drone_v2

Version 2 is about the pipeline; the aircraft is its test problem. Version 1
(docs/talk/build_deck_drone.py and its outline) is imported, never modified: its values, drawings and
slide bodies are reused wherever the outline says "Reuse version-1 Dxx".

Rules (CLAUDE.md and the outline's conventions):
- Every number is computed from a record at build time; a missing record renders PENDING, no number.
- No source footers, no repository paths, module names or case ids, and no mention of an earlier
  study, on any slide, in any note or in any figure text. The build enforces this: a slide or a
  figure that breaks the rule fails the build rather than reaching the deck.
- Main body V1 to V25 without dividers, then one "Backup" divider and B1 onward.
"""
import contextlib
import functools
import json
import math
import re
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import itertools

import matplotlib.figure
import matplotlib.text
from matplotlib.patches import Circle
from matplotlib.ticker import MaxNLocator

from docs.talk import build_deck as bd
from docs.talk import build_deck_drone as v1
from docs.talk import equations as eq

plt = bd.plt
LM, CW, CT = bd.LM, bd.CW, bd.CT

OUTLINE = ROOT / "docs/talk/outline_drone_v2.md"
DEFAULT_OUT = ROOT / "docs/talk/deck_drone_v2.pptx"
FIG_V2 = "docs/talk/figures/drone_v2/"            # every picture of this deck is drawn here
FIG_V2_FD = FIG_V2 + "results/"                   # the four result figures, redrawn clean
FIG_V2_FLOW = FIG_V2 + "flow/"                    # the surface-flow figures, redrawn clean
CONFIRM_30 = "runs/drone_confirm/2026-11-09_30designs/confirm.json"
CONFIRM_32 = v1.CONFIRM                           # runs/drone_confirm/2026-11-09/confirm.json
GRID_RECORD = "runs/drone_grid/2026-11-08/record.json"
POOL_RESULTS = v1.POOL + "/results.csv"
POOL_TAGS = ("pool_af", "pool_af_bias")
TIMELINE_TAGS = ("pool_af", "pool_af_bias", "confirm", "viz")
VIZ_14 = "runs/viz/airfoil2d-0ae85f2779"           # the readable volume file (14 degrees)


# ---- what may not appear anywhere in the deck --------------------------------------------------
PATH_RE = re.compile(r"\b(runs|docs|analysis|drone|worker|mcp_server|designs|data|tests|postprocess"
                     r"|surrogate|physics|geometry|cases|jobs)/")
FILE_RE = re.compile(r"\b[\w.<>-]+\.(py|csv|json|jsonl|yaml|md|pptx|gz|cfg|dat|png|sha256)\b")
MODULE_RE = re.compile(r"\b(drone|analysis|surrogate|postprocess|worker|mcp_server|geometry|physics"
                       r"|designs|cases)\.[a-z_]+")
CASE_RE = re.compile(r"airfoil2d-[0-9a-f]{10}")
WORDS_RE = re.compile(r"inlet|ramp|supersonic|task 9|carried over", re.IGNORECASE)


def violations(text):
    """Every forbidden match in a text: paths, file names, module names, case ids, earlier study."""
    return [m.group(0) for rx in (PATH_RE, FILE_RE, MODULE_RE, CASE_RE, WORDS_RE)
            for m in rx.finditer(text)]


# ---- figure text: explicit replacements, then a check ------------------------------------------
@functools.cache
def su2_ranks():
    """'2 or 4': the rank counts in the solver block of every SU2 record."""
    ranks = sorted({r.get("solver", {}).get("n_cores") for r in v1.all_su2_records().values()} - {None})
    return " or ".join(str(n) for n in ranks)


def figure_fixes():
    """(old, new) pairs applied to every text of a figure drawn for this deck, in order.

    Each pair is an exact phrase of a version-1 drawing; the sentence it sits in still reads.
    """
    spec_ranks = re.search(r"on (\d+) ranks", (ROOT / v1.SPEC).read_text()).group(1)
    return [
        ("  (drone.naca.coordinates)", ""),
        ("\n(geometry.build)", ""),
        (" (notes.json)", ""),
        ("\n(surrogate/mf_gp.py, Task 9)", ""),
        ("Local: Claude Code and the MCP tools", "Session: the agent and the typed tools"),
        ("Drive queue folder", "Shared queue folder"),
        ("Colab worker", "Cloud worker"),
        ("stage jobs/<id>/\n", "stage the job,\n"),
        ("upload job.json\nto Drive (by hand)", "job file to\nthe queue folder"),
        ("jobs/<id>.json", "job file"),
        ("runs/<id>.result.json\n+ runs/<id>.result.sha256", "result record\n+ its sha256 digest"),
        ("result.json + sha256\nflag 2-done", "result record + sha256\nflag 2-done"),
        (f"SU2 on {spec_ranks} ranks", f"SU2 on {su2_ranks()} ranks"),
        ("record check at ingest, then runs/<tag>/<id>/", ("record check at ingest, then the run "
         "record")),
        (("after ingest: drift rule on history.csv (postprocess/history.py) and the per-design "
         "aggregator (analysis/drone_polar.py)"), ("after ingest: the drift rule on the solver history "
         "and the per-design polar aggregator")),
        (f"SU2 history of {v1.SMOKE2.split('/')[-1]}", "SU2 history of the medium-mesh nominal case"),
    ]


def clean_figure_text(text):
    for old, new in figure_fixes():
        text = text.replace(old, new)
    return text


@contextlib.contextmanager
def clean_figures():
    """While active, every matplotlib figure is cleaned before it is saved, then checked: a figure
    text that still names a path, a module, a case id or the earlier study fails the build."""
    original = matplotlib.figure.Figure.savefig

    def savefig(fig, *args, **kwargs):
        for t in fig.findobj(matplotlib.text.Text):
            s = t.get_text()
            new = clean_figure_text(s)
            if new != s:
                t.set_text(new)
            bad = violations(new)
            if bad and not new.startswith("$"):           # an equation is LaTeX source only
                raise ValueError(f"figure text names {bad}: {new!r}")
        return original(fig, *args, **kwargs)

    matplotlib.figure.Figure.savefig = savefig
    try:
        yield
    finally:
        matplotlib.figure.Figure.savefig = original


@contextlib.contextmanager
def v2_figure_dirs():
    """Point version 1's figure folders at this deck's own, so its drawing functions and bodies
    draw and place the cleaned copies; restored afterwards (version 1 itself is not changed)."""
    saved = (v1.FIG_DRONE, v1.FIG, v1.FLOW)
    v1.FIG_DRONE, v1.FIG, v1.FLOW = FIG_V2, FIG_V2_FD, FIG_V2_FLOW
    try:
        yield
    finally:
        v1.FIG_DRONE, v1.FIG, v1.FLOW = saved


def ensure_figures():
    """Every picture of this deck, drawn under clean_figures() into docs/talk/figures/drone_v2/."""
    for sub in (FIG_V2, FIG_V2_FD, FIG_V2_FLOW):
        (ROOT / sub).mkdir(parents=True, exist_ok=True)
    fd, pa = v1.fd, v1.pa
    for fn in (fd.fig_front_lowfi, fd.fig_pool_replay, fd.fig_online_regret, fd.fig_e387_comparison):
        fn(ROOT, ROOT / FIG_V2_FD)
    flow = ROOT / FIG_V2_FLOW
    pa.cp_panels(pa.E387_CASES, "cp_e387.png", "E387, Re 203,800: pressure coefficient on the surface "
                 "(medium mesh)", flow)
    pa.cp_panels(pa.DESIGN0_CASES, "cp_design0.png", "Pool design 0, Re 121,945: pressure coefficient "
                 "on the surface (coarse mesh)", flow)
    pa.cp_mesh_pair(flow)
    pa.skin_friction_panel(out_dir=flow)
    pa.convergence(out_dir=flow)
    v1.ensure_drawings()
    v1.draw_clean_exit()
    v1.draw_c2_cap()
    v1.draw_bias_bars()
    v1.draw_bias_bars(v1.BIAS_HF, "bias_sweep_hf.png")
    draw_viz_14()
    draw_pipeline_v2()
    draw_queue_v2()
    draw_timeline()
    draw_hf_vs_lf()
    draw_section_polars()


# ---- reading the outline ----------------------------------------------------------------------
SLIDE_HEAD = re.compile(r"^### ([VB]\d+)\. (.+?)(?: \((\d+:\d\d)(?: onward)?(?:, ([\d.]+) min)?\))?$")
FIELDS = (("message", "Message"), ("body", "Body"), ("notes", "Speaker notes"))


def read_outline():
    """[{id, title, start, minutes, message, body, notes}] in outline order (V first, then B)."""
    slides, cur = [], None
    for line in OUTLINE.read_text(encoding="utf-8").splitlines():
        head = SLIDE_HEAD.match(line)
        if head:
            cur = {"id": head.group(1), "title": head.group(2), "start": head.group(3),
                   "minutes": float(head.group(4)) if head.group(4) else None,
                   "message": "", "body": "", "notes": ""}
            slides.append(cur)
        elif line.startswith("## "):
            cur = None
        elif cur is not None:
            for key, tag in FIELDS:
                if line.startswith(f"- **{tag}:** "):
                    cur[key] = line[len(f"- **{tag}:** "):].strip()
    return slides


def placeholders():
    """Every {name} the outline's slides use (messages, bodies and notes)."""
    return {name for s in read_outline() for key, _ in FIELDS
            for name in re.findall(r"\{(\w+)\}", s[key])}


# ---- values -----------------------------------------------------------------------------------
def pool_records():
    """[result.json] of every SU2 pool case (coarse pool and medium bias check)."""
    return [r for (t, _), r in v1.all_su2_records().items() if t in POOL_TAGS]


def when(stamp):
    return datetime.fromisoformat(stamp)


def mf_match():
    """(n0, two-level RMSE at n0, smallest SU2-only n at or below it or None, largest n)."""
    m = v1.mf_means()
    ns = sorted({n for (model, n, _) in m if model == "two"})
    n0 = ns[0]
    target = m[("two", n0, "rmse_endurance")]
    reach = [n for n in sorted({n for (model, n, _) in m if model == "single"})
             if m[("single", n, "rmse_endurance")] <= target]
    return n0, target, (reach[0] if reach else None), ns[-1]


def count_rulings():
    """The highest decision number in the task ledger: decisions 1 to 5 are the answers to the
    opening questions (one section), 6 onward have a heading each; a follow-up note that repeats
    a decision's number is not a new ruling."""
    return max(int(n) for n in re.findall(r"^### Decision (\d+)", (ROOT / v1.TASKS).read_text(),
                                          re.MULTILINE))


def runtime_of(worker_id):
    """'colab-6ac94659bc46-3of4' -> 'colab-6ac94659bc46': the runtime part of a worker id."""
    return re.sub(r"-\d+of\d+$", "", worker_id)


def timeline_records():
    """[(tag, record)] of the SU2 airfoil cases of the pool day: pool, bias check, confirm, viz."""
    return [(t, r) for (t, _), r in sorted(v1.all_su2_records().items()) if t in TIMELINE_TAGS]


def time_values():
    grid = v1.jload(GRID_RECORD)
    recs = pool_records()
    first = min(when(r["run"]["started_at"]) for r in recs)
    last = max(when(r["run"]["finished_at"]) for r in recs)
    n0, _, reach, n_max = mf_match()
    workers = {r["run"]["worker_id"] for _, r in timeline_records()}
    return {"grid_hours": f"{grid['wall_seconds'] / 3600:.1f}",
            "grid_workers": grid["workers"],
            "su2_cases": len(recs),
            "su2_worker_h": f"{sum(r['run']['wall_time_s'] for r in recs) / 3600:.1f}",
            "pool_wall_h": f"{(last - first).total_seconds() / 3600:.1f}",
            "mf_n0": n0,
            "mf_n_match": str(reach) if reach is not None else f"more than {n_max}",
            "n_rulings": count_rulings(),
            "n_worker_ids": len(workers),
            "n_runtimes": len({runtime_of(w) for w in workers}),
            "n_pool_runtimes": len({runtime_of(r["run"]["worker_id"]) for r in recs})}


def confirm_runs():
    """[(label, confirm.json or None, inverse answer it tests or None)] for the two confirmations."""
    inv32 = v1.jload(v1.INVERSE_HF) if v1.exists(v1.INVERSE_HF) else None
    return [("answer on 30 designs", v1.jload(CONFIRM_30) if v1.exists(CONFIRM_30) else None, None),
            ("answer on 32 designs", v1.jload(CONFIRM_32) if v1.exists(CONFIRM_32) else None, inv32)]


def confirm_v2_answer():
    parts = []
    for label, c, _ in confirm_runs():
        if c is None:
            parts.append(f"the {label} is PENDING, its confirmation run has not landed")
            continue
        e, m = c["endurance_h"], c["mtow_kg"]
        parts.append(f"at the {label} SU2 gives {e['simulated']:.2f} h, {e['position']} "
                     f"[{e['lo90']:.2f}, {e['hi90']:.2f}], and {m['simulated']:.3f} kg, "
                     f"{m['position']} [{m['lo90']:.3f}, {m['hi90']:.3f}]: "
                     f"{'pass' if c['c2_pass'] else 'FAIL'}")
    text = "; ".join(parts)
    return text[0].upper() + text[1:] + "."


def mf_answer():
    if not v1.exists(v1.MF):
        return "PENDING: the two-level comparison has not been run."
    return v1.mf_answer()


def hf_front_answer():
    if not v1.exists(v1.PARETO_HF):
        return ("PENDING: the front over the SU2 pool has not been computed; the exact low-fidelity "
                "front is shown beside the place it will take.")
    return v1.hf_front_answer()


def hf_inverse_answer():
    if not v1.exists(v1.INVERSE_HF):
        return "the SU2-pool answer is PENDING."
    return v1.hf_inverse_answer()


@functools.cache
def values():
    """Every {name} of the outline, plus what the new bodies use; each computed from a record."""
    v = dict(v1.values())
    v.update(time_values())
    v.update({"mf_answer": mf_answer(), "hf_front_answer": hf_front_answer(),
              "hf_inverse_answer": hf_inverse_answer(), "confirm_v2_answer": confirm_v2_answer()})
    return v


def fill(text, v):
    """Replace {name} by its value; an unknown name raises KeyError and fails the build."""
    return text.format_map(v)


# ---- slide checks -----------------------------------------------------------------------------
def slide_texts(slide):
    """Every text of a slide: text frames, table cells, and the notes."""
    out = []
    for sh in slide.shapes:
        if sh.has_text_frame:
            out.append(sh.text_frame.text)
        if sh.has_table:
            out += [c.text for row in sh.table.rows for c in row.cells]
    if slide.has_notes_slide:
        out.append(slide.notes_slide.notes_text_frame.text)
    return out


CAPTION_START = ("Figure:", "Record:", "Records:", "sources:")


def remove_source_captions(slide):
    """Drop the text boxes that only name sources (version-1 figure and record captions)."""
    for sh in list(slide.shapes):
        if sh.has_text_frame and sh.text_frame.text.strip().startswith(CAPTION_START):
            sh._element.getparent().remove(sh._element)


def font_sizes(slide):
    """[(points, text)] of every sized run on the slide, tables included, footer label excluded."""
    out = []
    frames = [sh.text_frame for sh in slide.shapes if sh.has_text_frame]
    frames += [c.text_frame for sh in slide.shapes if sh.has_table
               for row in sh.table.rows for c in row.cells]
    for tf in frames:
        if re.fullmatch(r"[VB]\d+  \|  \d+", tf.text):
            continue
        for p in tf.paragraphs:
            for r in p.runs:
                if r.font.size is not None and r.text.strip():
                    out.append((r.font.size.pt, r.text))
    return out


def check_slide(slide, sid, main):
    bad = [b for t in slide_texts(slide) for b in violations(t)]
    if bad:
        raise ValueError(f"{sid}: names {sorted(set(bad))}")
    if main:
        small = [(s, t) for s, t in font_sizes(slide) if s < 12]
        if small:
            raise ValueError(f"{sid}: text below 12 pt: {small[:3]}")


# ---- new drawings -----------------------------------------------------------------------------
BLUE_H, ACCENT_H, GREY_H, TEXT_H = v1.BLUE_H, v1.ACCENT_H, v1.GREY_H, v1.TEXT_H


def draw_pipeline_v2(path_name="pipeline_v2.png"):
    """Agent to records and back, every check on its arrow, the two human touch points marked."""
    v = values()
    queue_src = (ROOT / "mcp_server/queue.py").read_text()
    v1.need(queue_src, "schema -> gates -> geometry -> mesh_quality -> config -> config_keys")
    v1.need((ROOT / "worker/run_worker.py").read_text(), "heartbeat", "in_shard", "gates.check")
    fig = plt.figure(figsize=(12, 4.6), dpi=200)
    ax = v1.blank_axes(fig, [0, 0, 1, 1], (0, 12), (0, 4.6))
    top, bot, w, h = 3.3, 1.2, 2.05, 1.1
    xs = [1.15, 3.55, 5.95, 8.35, 10.75]
    row1 = ["Agent\n(language model)\ncalls tools only",
            f"{v['n_tools']} typed tools\nstrict schemas,\nevery call logged",
            "Gates before staging\nschema, physics gates,\nmesh quality, config keys",
            "Shared queue\njob files with\nstatus flags",
            "Cloud workers\nsharded by case id,\nstarted from the session"]
    row2 = ["Next batch\nback to the tools", "Surrogate and\nacquisition\npick the next batch",
            "Run records\ninputs, solver version,\nseed, logs",
            "Hashed ingest\nsha256 against the\nworker's digest",
            "Checks after the run\nexit code, NaN, timeout,\nconvergence, drift"]
    for i, (x, t) in enumerate(zip(xs, row1)):
        v1.mbox(ax, x, top, w, h, t, fs=10.5, fc="#EAF0F7" if i == 0 else "white")
    for x, t in zip(xs, row2):
        v1.mbox(ax, x, bot, w, h, t, fs=10.5)
    for x0, x1 in itertools.pairwise(xs):
        v1.marrow(ax, (x0 + w / 2, top), (x1 - w / 2, top))
        v1.marrow(ax, (x1 - w / 2, bot), (x0 + w / 2, bot))
    v1.marrow(ax, (xs[-1], top - h / 2), (xs[-1], bot + h / 2))
    v1.marrow(ax, (xs[0] + 0.3, bot + h / 2), (xs[1] - 0.3, top - h / 2), color=BLUE_H)

    def person(x, y, label, right=True):
        ax.add_patch(Circle((x, y), 0.19, fc=ACCENT_H, ec="white", lw=1.2, zorder=4))
        ax.text(x, y, "P", color="white", fontsize=10, ha="center", va="center", fontweight="bold",
                zorder=5)
        ax.text(x + (0.28 if right else -0.28), y, label, color=ACCENT_H, fontsize=11,
                va="center", ha="left" if right else "right", fontweight="bold")

    person(xs[-1] + 0.85, top + h / 2 + 0.3, "sign-in: a person authorises a cloud runtime's storage",
           right=False)
    person(xs[2] - 0.9, bot - h / 2 - 0.3, "ruling: a person decides when the data force a judgment")
    ax.text(xs[2] + 1.2, (top + bot) / 2, "The language model never chooses a design point:\n"
            "the surrogate and the acquisition function do.", fontsize=11, color=BLUE_H,
            va="center", ha="center", fontweight="bold")
    return v1.save(fig, path_name)


def draw_queue_v2(path_name="queue_shards.png"):
    """The queue, the sharded workers and the heartbeat, in large type; names checked in the code."""
    worker_src = (ROOT / "worker/run_worker.py").read_text()
    v1.need(worker_src, "1-running", "2-done", "stale-minutes", "def in_shard", "gates.check",
            "mesh_fingerprint", "config_sha256", "write_digest", "failure_of")
    v1.need((ROOT / "mcp_server/queue.py").read_text(), "ingest_result", "_digest_mismatch",
            "1-pending")
    split = v1.shard_split()
    fig = plt.figure(figsize=(12, 4.6), dpi=200)
    ax = v1.blank_axes(fig, [0, 0, 1, 1], (0, 12), (0, 4.6))
    for y0, hh, label in ((3.3, 1.25, "Session"), (1.95, 1.2, "Shared queue folder"),
                          (0.05, 1.75, "Cloud workers")):
        ax.add_patch(v1.Rectangle((0.05, y0), 11.9, hh, fc="#F7F9FC", ec="#D0D7E2", lw=0.8))
        ax.text(0.12, y0 + hh - 0.05, label, fontsize=11, color=GREY_H, va="top", fontweight="bold")
    fs = 12
    v1.mbox(ax, 2.3, 3.85, 3.3, 0.75, "typed tools: gates passed,\njob staged, flag 1-pending", fs=fs)
    v1.mbox(ax, 9.7, 3.85, 3.6, 0.75, "ingest: sha256 against the digest,\nJSON and record checks",
            fs=fs)
    v1.mbox(ax, 2.3, 2.45, 3.3, 0.75, "job files with status flags:\n1-pending, 1-running, 2-done",
            fs=fs)
    v1.mbox(ax, 6.0, 2.45, 3.3, 0.75, "heartbeat of each running case;\nif it goes stale, the case is re-run",
            fs=fs, ec=ACCENT_H)
    v1.mbox(ax, 9.7, 2.45, 2.7, 0.75, "result record\n+ sha256 digest", fs=fs)
    v1.mbox(ax, 1.55, 1.2, 2.6, 0.55, f"shard 0 of 2: {split[0]} cases", fs=fs, fc="#EAF0F7")
    v1.mbox(ax, 1.55, 0.5, 2.6, 0.55, f"shard 1 of 2: {split[1]} cases", fs=fs, fc="#EAF0F7")
    v1.mbox(ax, 4.85, 0.85, 2.6, 1.15, "rebuild mesh and config,\ncheck fingerprint and hash,\n"
            "run the gates again", fs=fs)
    v1.mbox(ax, 7.85, 0.85, 2.6, 1.15, "SU2, then checks:\nexit code, NaN,\ntimeout", fs=fs)
    v1.mbox(ax, 10.75, 0.85, 2.2, 1.15, "write the result\nand its digest,\nflag 2-done", fs=fs)
    v1.marrow(ax, (2.3, 3.47), (2.3, 2.83))
    v1.marrow(ax, (1.55, 2.07), (1.55, 1.48))
    for p, q in (((2.85, 0.85), (3.55, 0.85)), ((6.15, 0.85), (6.55, 0.85)),
                 ((9.15, 0.85), (9.65, 0.85))):
        v1.marrow(ax, p, q)
    v1.marrow(ax, (10.75, 1.43), (9.9, 2.07))
    v1.marrow(ax, (9.7, 2.83), (9.7, 3.47))
    v1.marrow(ax, (7.3, 1.43), (6.3, 2.07), ls="--", color=ACCENT_H)
    ax.text(5.95, 4.1, "a worker claims a case only if\ncase id hash mod N == K", color=BLUE_H,
            fontsize=fs, ha="center", va="center", fontweight="bold")
    return v1.save(fig, path_name)


def draw_timeline(path_name="timeline.png"):
    """Cases finished per hour by worker id, and the workers with a case running in each hour."""
    recs = timeline_records()
    start = min(when(r["run"]["started_at"]) for _, r in recs).replace(minute=0, second=0)
    end = max(when(r["run"]["finished_at"]) for _, r in recs)
    n_h = math.ceil((end - start).total_seconds() / 3600)
    hours = [start + timedelta(hours=k) for k in range(n_h)]
    workers = sorted({r["run"]["worker_id"] for _, r in recs})
    done = {w: np.zeros(n_h) for w in workers}
    live = [set() for _ in range(n_h)]
    for _, r in recs:
        s, f = when(r["run"]["started_at"]), when(r["run"]["finished_at"])
        k = min(int((f - start).total_seconds() // 3600), n_h - 1)
        done[r["run"]["worker_id"]][k] += 1
        for j, h0 in enumerate(hours):
            if s < h0 + timedelta(hours=1) and f >= h0:
                live[j].add(r["run"]["worker_id"])
    colors = plt.get_cmap("tab20")(np.linspace(0, 1, 20))
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(10, 3.9), dpi=200, sharex=True,
                                  gridspec_kw={"height_ratios": [2.2, 1]})
    x = np.arange(n_h)
    bottom = np.zeros(n_h)
    for i, w in enumerate(workers):
        ax.bar(x, done[w], bottom=bottom, color=colors[i % 20], width=0.85, label=w)
        bottom += done[w]
    ax.set_ylabel("cases finished\nper hour", fontsize=11)
    ax.grid(axis="y", alpha=0.3)
    ax.legend(fontsize=9, ncol=1, loc="upper left", bbox_to_anchor=(1.005, 1.12), frameon=False,
              title=f"{len(workers)} worker ids", title_fontsize=10, handlelength=1.2,
              labelspacing=0.25)
    ax.set_title(f"{len(recs)} SU2 cases of the pool, the bias check, the confirmation and the flow "
                 f"pictures, on {len({runtime_of(w) for w in workers})} runtimes", fontsize=11.5,
                 color=BLUE_H)
    ax2.step(x, [len(s) for s in live], where="mid", color=BLUE_H, lw=2)
    ax2.set_ylabel("workers with a\ncase running", fontsize=11)
    ax2.set_ylim(0, max(len(s) for s in live) + 1)
    ax2.yaxis.set_major_locator(MaxNLocator(integer=True, nbins=4))
    ax2.grid(alpha=0.3)
    ticks = list(range(0, n_h, 3))
    ax2.set_xticks(ticks)
    ax2.set_xticklabels([hours[k].strftime("%d %b\n%H:00") for k in ticks], fontsize=9.5)
    ax2.set_xlabel("hour (UTC), from the start and finish times in the run records", fontsize=10.5)
    ax.tick_params(labelsize=10)
    ax2.tick_params(axis="y", labelsize=10)
    fig.subplots_adjust(left=0.09, right=0.76, top=0.9, bottom=0.22, hspace=0.08)
    return v1.save(fig, path_name)


def pool_pairs():
    """[(design index, SU2 row, low row)] of the complete SU2 pool designs, matched on index; the
    six inputs of each pair are asserted equal so the match cannot pair two different designs."""
    low = {int(r["index"]): r for r in v1.csv_rows(v1.LOW_POOL)}
    out = []
    for r in v1.csv_rows(POOL_RESULTS):
        if r["status"] != "complete":
            continue
        lo = low[int(r["index"])]
        assert all(abs(float(r[k]) - float(lo[k])) < 1e-5 for k in v1.DRONE_BOUNDS), r["index"]
        out.append((int(r["index"]), r, lo))
    return out


def draw_hf_vs_lf(path_name="su2_vs_low.png"):
    """SU2 endurance against low-fidelity endurance per complete pool design, with y = x."""
    pairs = pool_pairs()
    accepted = set(v1.jload(v1.POOL + "/record.json").get("accept_budget_exhausted", []))
    lo = np.array([float(l["endurance_h"]) for _, _, l in pairs])
    hi = np.array([float(h["endurance_h"]) for _, h, _ in pairs])
    acc = np.array([i in accepted for i, _, _ in pairs])
    fig, ax = plt.subplots(figsize=(8.0, 4.4), dpi=200)
    top = max(lo.max(), hi.max()) * 1.05
    ax.plot([0, top], [0, top], color=GREY_H, lw=1.2, ls="--", label="y = x (the two levels agree)")
    ax.scatter(lo[~acc], hi[~acc], s=40, color=BLUE_H, edgecolor="white", zorder=3,
               label=f"{int((~acc).sum())} designs")
    if acc.any():
        ax.scatter(lo[acc], hi[acc], s=55, color=ACCENT_H, edgecolor="white", zorder=3, marker="D",
                   label=f"{int(acc.sum())} designs with budget-exhausted angles admitted by ruling")
    ax.set_xlim(0, top)
    ax.set_ylim(0, top)
    ax.set_aspect("equal")
    ax.set_xlabel("endurance, low-fidelity section (h)", fontsize=11)
    ax.set_ylabel("endurance, SU2 section (h)", fontsize=11)
    ax.legend(loc="upper left", fontsize=9.5)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return v1.save(fig, path_name)


def draw_section_polars(path_name="section_polars_v2.png"):
    """SU2 cl(alpha) and cd(cl) of every pool design, and E387 SU2 against the tunnel."""
    import yaml
    idx = v1.pool_case_index()
    by_design = defaultdict(list)
    for (tag, case), r in v1.all_su2_records().items():
        if tag == "pool_af" and case in idx:
            by_design[idx[case][1]].append((r["params"]["alpha_deg"], r["metrics"]["cl"],
                                            r["metrics"]["cd"]))
    tunnel = {p["nominal_reynolds"]: p for p in
              yaml.safe_load((ROOT / v1.fd.E387_TUNNEL).read_text())["polars"]}[200000.0]
    pts = v1.e387_points(203800.0)
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.0), dpi=200)
    for pts_d in by_design.values():
        a, cl, cd = zip(*sorted(pts_d))
        axes[0].plot(a, cl, "-o", color="#8FA8C8", lw=0.8, ms=2.5)
        axes[1].plot(cd, cl, "-o", color="#8FA8C8", lw=0.8, ms=2.5)
    axes[0].set_title(f"SU2 pool, {len(by_design)} designs: cl against alpha", fontsize=11, color=BLUE_H)
    axes[0].set_xlabel("alpha (deg)")
    axes[0].set_ylabel("cl")
    axes[1].set_title("SU2 pool: cl against cd", fontsize=11, color=BLUE_H)
    axes[1].set_xlabel("cd")
    axes[1].set_ylabel("cl")
    axes[2].plot(tunnel["alpha_deg"], tunnel["cl"], "k^-", ms=4, lw=0.8, label="UIUC tunnel")
    axes[2].plot([p[0] for p in pts], [p[1] for p in pts], "s", color=ACCENT_H, ms=6,
                 label="SU2, medium mesh")
    axes[2].set_title("E387, Re 203,800: SU2 against the tunnel", fontsize=11, color=BLUE_H)
    axes[2].set_xlabel("alpha (deg)")
    axes[2].set_ylabel("cl")
    axes[2].legend(fontsize=9)
    for ax in axes:
        ax.grid(alpha=0.3)
    fig.tight_layout()
    return v1.save(fig, path_name)


def draw_viz_14(path_name="viz_14.png"):
    """The 14 degree volume picture of pool design 0, titled by the design rather than its case."""
    from postprocess.plot_flowfield import plot_airfoil_volume
    case = ROOT / VIZ_14
    params = json.loads((case / "params.json").read_text())
    design0 = next(r for r in v1.csv_rows(v1.CASES) if int(r["index"]) == 0)
    assert abs(float(design0["reynolds"]) - params["reynolds"]) < 1, "viz case is not pool design 0"
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "pool design 0"
        d.mkdir()
        for name in ("flow.dat.gz", "params.json"):
            (d / name).symlink_to(case / name)
        plot_airfoil_volume(d, ROOT / FIG_V2 / path_name)
    return ROOT / FIG_V2 / path_name


# ---- new slide bodies (main) ------------------------------------------------------------------
def body_problem(slide, v):
    cols = [("Slow", ("A design study needs many high-fidelity runs, and each one takes "
             "minutes of a cloud machine."),
             (f"One SU2 angle costs a median {v['hf_coarse_min']} min on the coarse mesh; a design "
             "needs five angles.")),
            ("Manual", "Each case needs a mesh, a configuration and a check written for it.",
             (f"In the pipeline a low-fidelity design costs {v['lf_s_core']} s of one core, and an "
             f"SU2 case is staged by a typed tool call ({v['n_tools']} tools).")),
            ("Silent", "A solver that stops cleanly can still hand back the wrong numbers.",
             (f"The first SU2 case exited with code {v['smoke_exit']} and its lift and drag were "
             f"{v['smoke_cl_off']} and {v['smoke_cd_off']} off (V3)."))]
    w, gap = 3.85, 0.29
    for i, (head, problem, record) in enumerate(cols):
        x = LM + i * (w + gap)
        bd.box(slide, x, CT + 0.05, w, 0.7, head, size=22, bold=True, fill=bd.BLUE, color=bd.WHITE)
        bd.text_box(slide, x, CT + 0.9, w, 1.1, problem, size=16)
        bd.box(slide, x, CT + 2.0, w, 1.6, record, size=15, fill=bd.TINT)
    bd.text_box(slide, LM, CT + 3.95, CW, 0.5, "The loop is propose, simulate, check, decide: the "
                "pipeline runs it unattended and checks every result before anyone sees it.",
                size=16, color=bd.BLUE, bold=True)


def body_clean_exit(slide, v):
    path = v1.draw_clean_exit()
    bd.add_figure(slide, str(path.relative_to(ROOT)), LM, CT - 0.05, 6.9, 4.3)
    a = v1.jload(v1.SMOKE + "/result.json")
    m = a["metrics"]
    steps = [(f"SU2 exits with code {a['run']['exit_code']}\nafter {a['run']['iterations']:,} "
              "iterations, files written"),
             f"postprocess looks for {v['rms_col']}\nand records a postprocess error",
             (f"drift rule on the history:\ncl {m['cl_drift_pct']:.1f} %, cd "
              f"{m['cd_drift_pct']:.1f} % over the last fifth"),
             (f"ruling: budget {v['smoke2_budget']} with a Cauchy stop;\n"
              f"the rerun stops at {v['smoke2_iters']}")]
    x, w, h = LM + 7.2, 4.9, 0.85
    for i, text in enumerate(steps):
        y = CT + i * 1.15
        bd.box(slide, x, y, w, h, text, size=13, fill=bd.TINT if i == 3 else bd.WHITE)
        if i:
            bd.arrow(slide, x + w / 2, y - 0.3, x + w / 2, y)


def body_problem_cap(slide, v):
    path = v1.draw_c2_cap()
    bd.add_figure(slide, str(path.relative_to(ROOT)), LM, CT - 0.05, 7.9, 4.6)
    rows = [["Input", "Range"]] + [[k.replace("_", " "), f"{lo:g} to {hi:g}"]
                                   for k, (lo, hi) in v1.DRONE_BOUNDS.items()]
    bd.add_table(slide, LM + 8.15, CT - 0.05, [2.2, 1.75], rows, size=13, row_h=0.4, flag=())
    bd.text_box(slide, LM + 8.15, CT + 2.85, 3.95, 1.9,
                [(f"Payload fixed at {v['payload_kg']} kg; cap {v['cap_kg']} kg at P(mass <= cap) >= "
                 "0.9, fixed before any run."),
                 f"Heaviest low-pool design: {v['lowpool_max']} kg, so only SU2 tests the cap."],
                size=13, bullets=True)


def body_pipeline_v2(slide, v):
    bd.add_figure(slide, FIG_V2 + "pipeline_v2.png", LM, CT - 0.05, CW, 4.75)


def body_mcp(slide, v):
    v1.need((ROOT / "mcp_server/schemas.py").read_text(), 'extra="forbid", strict=True')
    v1.need((ROOT / "mcp_server/queue.py").read_text(), "mcp_log.jsonl")
    v1.need((ROOT / "worker/run_worker.py").read_text(), "gates.check")
    tools = [name for name, _ in v1.mcp_tools()]
    bd.text_box(slide, LM, CT, 3.6, 0.35, f"The {len(tools)} tools", size=14, bold=True, color=bd.BLUE)
    bd.text_box(slide, LM, CT + 0.45, 3.6, 4.4, tools, size=15, font="Consolas", space_after=1)
    rows = [["What the typed interface adds", "What does not depend on it"],
            ["One entry point for the agent, with typed arguments",
             "The physics gates, run again by the worker before SU2 starts"],
            ["A strict schema per family: unknown fields and wrong types refused",
             "The mesh fingerprint and the configuration hash the worker re-checks"],
            ["An audit line per call: tool, argument hash, ok, case",
             "The sha256 digest checked at ingest"],
            ["Nothing is staged when a check fails",
             "The sampling points: design tables and acquisition code, never the language model"]]
    bd.add_table(slide, LM + 3.9, CT, [4.1, 4.13], rows, size=15, row_h=0.85, flag=())


def gate_rows():
    """[[gate, checks, limits]]: one row per gate number in the evaluator's messages, plus the
    airfoil mesh-quality gate; the limits are read from the rules ledger and the worker."""
    rules = v1.ledger.load("rules")
    names = defaultdict(list)
    for g in v1.drone_gates():
        n, name = re.fullmatch(r"gate (\d) \((.+)\)", g).groups()
        names[int(n)].append(name)
    src = (ROOT / "drone/evaluate.py").read_text()
    max_iter = re.search(r"^_MAX_ITER = (\d+)", src, re.MULTILINE).group(1)
    checks = {
        1: (f"cruise Reynolds number in [{rules['reynolds_min']:g}, {rules['reynolds_max']:g}]",
            "where the section data are validated"),
        2: ((f"V_cruise >= {rules['stall_margin']:g} V_stall; cruise CL <= "
            f"{rules['cruise_cl_fraction_of_clmax']:g} CL_max"), "two checks on one margin"),
        3: (f"structure and propulsion at least {rules['structure_fraction_min']:g} of take-off mass",
            f"closure is a fixed point, at most {max_iter} iterations"),
        4: ((f"manufacturing floor: tip chord >= {rules['tip_chord_min_m']:g} m, root thickness >= "
            f"{rules['spar_depth_min_m']:g} m; wing loading in [{rules['wing_loading_min_N_m2']:g}, "
            f"{rules['wing_loading_max_N_m2']:g}] N/m^2"), "one gate, two checks"),
        5: (f"lattice tip panel aspect ratio <= {rules['lattice_panel_aspect_max']:g}",
            "keeps the lattice panels well shaped"),
    }
    assert sorted(names) == sorted(checks), "the gate numbers in the code changed"
    rows = [["Gate", "Checks", "Note"]]
    for n in sorted(names):
        label = " and ".join(names[n])
        rows.append([f"{n}. {label[:1].upper()}{label[1:]}", *checks[n]])
    from worker import make_case
    rows.append(["Mesh quality (airfoil cases)",
                 (f"no inverted cells; minimum angle >= {make_case.MIN_ANGLE_DEG:g} deg; first cell "
                  f"within {make_case.FIRST_CELL_TOL:.0%} of the request; growth <= "
                  f"{make_case.MAX_GROWTH:g}; cell aspect ratio <= {make_case.MAX_ASPECT:g}"),
                 "before a case is staged; the worker re-checks the mesh fingerprint"])
    return rows


def body_gates(slide, v):
    rows = gate_rows()
    bd.add_table(slide, LM, CT - 0.05, [3.2, 6.1, 2.83], rows, size=13, row_h=0.6, flag=())
    bd.text_box(slide, LM, CT + 4.35, CW, 0.5,
                [(f"Low-fidelity grid: {v['gated_n']} of {v['grid_n']} designs stopped by the gates, "
                 "each with the offending value in its message.")], size=14, color=bd.BLUE, bold=True)


def body_costs(slide, v):
    grid = v1.jload(GRID_RECORD)
    pool = v1.jload("runs/drone_pool_lf/2026-11-08/record.json")
    co, me = v1.wall_minutes("coarse"), v1.wall_minutes("medium")
    rows = [["Level", "Section data", "Measured cost", "Used for"],
            ["Low (container)", "closed-form thin-airfoil lift and flat-plate drag",
             (f"{v['lf_s_core']} s per design per core: the {grid['points_evaluated']:,}-point grid "
              f"in {grid['wall_seconds'] / 3600:.1f} h on {grid['workers']} workers; the "
              f"{pool['points_evaluated']}-point pool in {pool['wall_seconds']:.0f} s"),
             "exact front, low pool, replays, the low level of the two-level model"],
            [f"High (cloud, {su2_ranks()} ranks)", ("SU2 polar of the design's own section at its "
             "cruise Reynolds number"),
             (f"per angle: median {np.median(co):.1f} min coarse ({len(co)} cases), "
              f"{np.median(me):.1f} min medium ({len(me)} cases); five angles per design"),
             f"the SU2 pool: {v['pool_cases']} cases"]]
    bd.add_table(slide, LM, CT + 0.1, [2.1, 2.9, 4.3, 2.83], rows, size=15, row_h=1.05, flag=())
    bd.text_box(slide, LM, CT + 4.2, CW, 0.6, "Medians over every SU2 run record at build time, by "
                "mesh level. Both levels share geometry, lattice, closure and mission.", size=13,
                color=bd.GREY)


def v6_checks():
    return v1.jload(v1.V6)["checks"]


def body_validation(slide, v):
    checks = v6_checks()
    own = [c for c in checks if c["name"][:3] in ("V6a", "V6b", "V6c", "V6d")
           and c["tolerance"] is not None]
    fam = {"V6a": "vortex lattice against closed forms", "V6b": "Warren-12 benchmark wing",
           "V6c": "lattice refinement", "V6d": "mass closure and energy balance"}

    def families(rows):
        n = defaultdict(int)
        for c in rows:
            n[c["name"][:3]] += 1
        return "; ".join(f"{fam[k]} ({k}, {n[k]})" for k in sorted(n))

    passed = [c for c in own if c["verdict"] == "pass"]
    pend = [c for c in own if c["verdict"].startswith("pending")]
    failed = [c for c in own if c["verdict"] == "fail"]
    tunnel = [c for c in checks if c["name"].startswith("V6e ") and c["tolerance"] is not None
              and not c["name"].startswith("V6e mesh")]
    mesh = [c for c in checks if c["name"].startswith("V6e mesh") and c["tolerance"] is not None]
    t_pass = [c for c in tunnel if c["verdict"] == "pass"]
    t_fail = [c for c in tunnel if c["verdict"] == "fail"]

    def dev(c):
        return f"{c['name'][4:]}: {100 * c['deviation']:+.2f} % against {100 * c['tolerance']:.0f} %"

    rows = [["Group", "Verdict", "Rows", "Which"],
            ["Solver's own checks", "pass", len(passed), families(passed)],
            ["", "FAIL" if failed else "fail", len(failed), families(failed) if failed else "none"],
            ["", "PENDING", len(pend), "; ".join(c["name"].split(":")[0][4:] + " "
                                              + c["name"].split(":")[1].split("(")[0].strip() + " ("
                                              + c["verdict"].split("(")[1].rstrip(")") + ")"
                                              for c in pend)],
            ["SU2 against the wind tunnel", "pass", len(t_pass), "; ".join(dev(c) for c in t_pass)],
            ["", "FAIL", len(t_fail), "; ".join(dev(c) for c in t_fail)],
            *[["SU2 medium against fine mesh", c["verdict"].upper() if c["verdict"] == "fail" else c["verdict"],
               1, f"cd at cl 0.6: {100 * c['deviation']:+.2f} % against {100 * c['tolerance']:.0f} %"]
              for c in mesh],
            ["Not run", "not run", len(v1.jload(v1.V6)["not_run"]),
             "; ".join(n["what"] for n in v1.jload(v1.V6)["not_run"])]]
    bd.add_table(slide, LM, CT - 0.05, [2.6, 1.3, 0.8, 7.43], rows, size=13, row_h=0.5,
                 flag=("FAIL", "PENDING", "not run"))
    d8 = re.search(r'### Decision 8 \(([^)]+)\): "([^"]+)"', (ROOT / v1.TASKS).read_text())
    bd.box(slide, LM, CT + 4.0, CW, 0.75, f'Decision 8 ({d8.group(1)}): "{d8.group(2)}". The fail stays '
           "a fail; every SU2 result carries it as a flag.", size=14, fill=bd.TINT)


def body_queue_shards(slide, v):
    _w, h = bd.add_figure(slide, FIG_V2 + "queue_shards.png", LM, CT - 0.1, CW, 4.5)
    split = v1.shard_split()
    bd.text_box(slide, LM, CT - 0.1 + h + 0.05, CW, 0.5,
                f"Every case id lands in exactly one shard: the {sum(split)} pool cases split "
                f"{' and '.join(map(str, split))} over two shards. Adding a worker changes N, nothing "
                "else.", size=14, color=bd.BLUE, bold=True)


def body_timeline(slide, v):
    bd.add_figure(slide, FIG_V2 + "timeline.png", LM, CT - 0.05, CW, 4.5)
    bd.text_box(slide, LM, CT + 4.45, CW, 0.4, "A worker id is a runtime and its shard (for example "
                "1of2); a new shard suffix on the same runtime marks a re-split of the queue.", size=13,
                color=bd.GREY)


def body_caught(slide, v):
    smoke = v1.jload(v1.SMOKE + "/result.json")
    m = smoke["metrics"]
    tasks = (ROOT / v1.TASKS).read_text()
    flat = " ".join(tasks.split())
    inverted = re.search(r"\((\d+) inverted cells\)", tasks).group(1)
    declared = re.search(r"the zone line declares ([\d,]+) nodes", flat).group(1)
    ranks = defaultdict(int)
    for r in pool_records():
        ranks[r["solver"]["n_cores"]] += 1
    planned = re.search(r"on one (\d+)-rank worker", flat).group(1)
    rows = [["Caught", "By", "Resolution"],
            [f"Postprocess looked for the compressible residual {v['rms_col']}",
             "the first airfoil case failing at postprocess", f"the classifier reads {v['rms_used']}"],
            [(f"First case unconverged: cl drift {m['cl_drift_pct']:.1f} %, cd drift "
             f"{m['cd_drift_pct']:.1f} %"), "the drift rule on the recorded history",
             f"budget {v['smoke2_budget']} with a Cauchy stop (a ruling)"],
            ["Fine mesh not reproduced at the 1 nm fingerprint", "the worker's mesh fingerprint check",
             "refused attempt kept beside the rerun"],
            [f"Fine E387 mesh has {inverted} inverted cells", "the mesh inversion gate",
             ("wall-tangent smoothing on every mesh (a ruling); medium against fine "
              + "; ".join(f"{100 * c['deviation']:+.2f} %, {c['verdict']}" for c in v6_checks()
                          if c["name"].startswith("V6e mesh medium vs fine")))],
            ["Point-vortex induced drag under-counts", "the elliptic-wing validation rows",
             "Trefftz-plane drag from a Glauert series"],
            [f"Volume file unreadable: the zone declares {declared} nodes, the file holds more rows",
             "a structure check on reading the file", ("re-run on local disk; one case still "
             "unreadable, nothing drawn from it")],
            [f"The pool was planned on one {planned}-rank worker", "the solver block of every record: "
             + ", ".join(f"{n} pool cases on {k} ranks" for k, n in sorted(ranks.items())),
             "costs and rank counts quoted from the records"]]
    bd.add_table(slide, LM, CT - 0.1, [4.6, 4.0, 3.53], rows, size=13, row_h=0.6, flag=())


def body_gp(slide, v):
    rows = [["Strategy", "Picks the next design by"],
            ["random", "a uniform draw"],
            ["lhs", "a Latin hypercube order fixed by the seed"],
            ["al_maxvar", "the largest summed scaled variance"],
            ["al_ehvi", "the largest expected hypervolume improvement"],
            ["al_ehvi_feas", "EHVI times P(feasible), online only (V15)"]]
    bd.add_table(slide, LM, CT, [1.8, 3.7], rows, size=13, row_h=0.5, flag=())
    bd.text_box(slide, LM, CT + 3.2, 5.5, 1.6,
                ["One GP on endurance, one on log take-off mass, six inputs scaled to [0, 1].",
                 "The language model calls tools; it never picks a point."], size=14, bullets=True)
    x, y = LM + 5.8, CT - 0.15
    for latex, h in ((v1.EQ_GP_KERNEL, 0.62), (v1.EQ_GP_MEAN, 0.4), (v1.EQ_GP_VAR, 0.4),
                     (v1.EQ_GP_OBJECTIVES, 0.4), (v1.EQ_GP_HVI, 0.4), (v1.EQ_GP_EHVI, 0.62),
                     (v1.EQ_GP_VARIANCE, 0.45)):
        _, used = eq.add_equation(slide, latex, x, y, 6.3, h, fontsize=15)
        y += used + 0.1


def body_pool_replay(slide, v):
    rep = v1.csv_rows(v1.fd.POOL_REPLAY)
    ns = (8, 16, 24, 32, 40)
    strategies = ("random", "lhs", "al_ehvi", "al_maxvar")
    rows = [["n", *strategies]] + [[n, *[f"{v1.mean_at(rep, s, 'hv_regret', n):.3f}"
                                         for s in strategies]] for n in ns]
    bd.add_figure(slide, FIG_V2_FD + "b_pool_replay.png", LM, CT - 0.05, 7.4, 4.6)
    x = LM + 7.6
    bd.text_box(slide, x, CT - 0.05, 4.5, 0.3, "Mean hypervolume regret, 10 seeds", size=13,
                color=bd.GREY)
    bd.add_table(slide, x, CT + 0.35, [0.6, 0.95, 0.95, 0.95, 1.05], rows, size=12, row_h=0.37,
                 flag=())
    eq.add_equation(slide, v1.EQ_GP_REGRET, x, CT + 2.75, 4.5, 0.6, fontsize=15)
    bd.text_box(slide, x, CT + 3.5, 4.5, 1.3,
                ["Same 8 initial points for every strategy of a seed.",
                 "The pool is smooth and gate-free: the easy case."], size=13, bullets=True)


def body_mf(slide, v):
    v1.body_mf(slide, v)
    remove_source_captions(slide)
    rows = sum(1 for sh in slide.shapes if sh.has_table for _ in sh.table.rows)
    bd.text_box(slide, LM, CT + 0.4 * rows + 1.0, CW, 0.6,
                "Means over ten seeds; coverage is the share of held-out designs inside the 90 % "
                "interval, and it is below 0.9 for both models.", size=13, color=bd.GREY)


def body_time_saved(slide, v):
    rows = [["What ran", "How many", "How long", "What a person had to do"],
            ["Low-fidelity grid", f"{v['grid_n']} designs",
             f"{v['grid_hours']} h on {v['grid_workers']} workers", "nothing: one command"],
            ["SU2 pool and its bias check", f"{v['su2_cases']} cases",
             f"{v['su2_worker_h']} worker-hours over {v['pool_wall_h']} h elapsed",
             f"sign in to {v['n_pool_runtimes']} cloud runtimes"],
            ["Two-level model", f"{v['mf_n0']} SU2 designs",
             f"reaches the endurance error SU2 alone needs {v['mf_n_match']} designs for",
             "nothing: computed from the records"],
            ["Rulings", f"{v['n_rulings']} recorded", "each when the data forced a judgment",
             "read the evidence and decide"]]
    bd.add_table(slide, LM, CT + 0.05, [3.0, 2.0, 4.1, 3.03], rows, size=16, row_h=0.8, flag=())
    bd.text_box(slide, LM, CT + 4.3, CW, 0.4, "Runtimes counted from the worker ids in the SU2 "
                "records; rulings counted from the decision headings of the task ledger.", size=13,
                color=bd.GREY)


def body_hf_vs_lf(slide, v):
    w, _ = bd.add_figure(slide, FIG_V2 + "su2_vs_low.png", LM, CT - 0.05, 8.3, 4.75)
    pairs = pool_pairs()
    ratio = [float(h["endurance_h"]) / float(lo["endurance_h"]) - 1 for _, h, lo in pairs]
    worst = sorted(pairs, key=lambda p: float(p[1]["endurance_h"]) / float(p[2]["endurance_h"]))[:3]
    bd.text_box(slide, LM + w + 0.25, CT, CW - w - 0.25, 4.6,
                [(f"{len(pairs)} complete designs, every one below the line: SU2 endurance is "
                 f"{v1.signed_range(ratio, 'high', 'low')} against the low model."),
                 "Largest gaps: " + ", ".join(
                     f"design {i} ({100 * (float(h['endurance_h']) / float(lo['endurance_h']) - 1):+.1f} %)"
                     for i, h, lo in worst) + ".",
                 "A gap of one sign is what a scale and a correction surface can learn."],
                size=14, bullets=True)


def body_front(slide, v):
    if v1.exists(v1.PARETO_HF):
        path = v1.draw_hf_front()
        bd.add_figure(slide, str(path.relative_to(ROOT)), LM, CT, 8.4, 4.6)
        return
    bd.add_figure(slide, FIG_V2_FD + "a_front_lowfi.png", LM, CT - 0.05, 7.4, 4.7)
    x = LM + 7.7
    bd.pending(slide, x, CT, 4.4, "PENDING: the SU2-pool front")
    bd.text_box(slide, x, CT + 0.6, 4.4, 4.0,
                [(f"Beside it, the exact low-fidelity front: {v['front_n']} designs over "
                 f"{v['grid_n']} grid points."),
                 ("The SU2 front comes from the GPs over the SU2 pool with their band; it is drawn "
                 "here when it has been computed."),
                 "Every SU2 point will carry the lift-slope bias flag."], size=14, bullets=True)


UNITS = {"span_m": ("span", " m"), "aspect_ratio": ("aspect ratio", ""),
         "taper_ratio": ("taper ratio", ""), "battery_fraction": ("battery fraction", ""),
         "camber_pct": ("camber", " %"), "thickness_pct": ("thickness", " %")}


def design_text(d):
    """'span 3 m, aspect ratio 16, ...' for a design dict."""
    return ", ".join(f"{UNITS[k][0]} {d[k]:g}{UNITS[k][1]}" for k in v1.DRONE_BOUNDS)


def body_inverse(slide, v):
    inv = v1.jload(v1.INVERSE_LF)
    direct = v1.evaluate(inv["design"], v1.ledger.load_all())
    e, m = inv["endurance_h"], inv["mtow_kg"]
    inside = (e["lo90"] <= direct["endurance_h"] <= e["hi90"]
              and m["lo90"] <= direct["mtow_kg"] <= m["hi90"])

    def answer_rows(record, label):
        rows = v1.inverse_rows(record, label)
        rows[0][1] = design_text(record["design"])
        return rows

    rows = [["", "Value"]] + answer_rows(inv, "Low pool GPs")
    rows.append(["Low model, evaluated directly",
                 (f"{direct['endurance_h']:.3f} h and {direct['mtow_kg']:.3f} kg: "
                 f"{'inside' if inside else 'OUTSIDE'} both intervals")])
    if v1.exists(v1.INVERSE_HF):
        hf = v1.jload(v1.INVERSE_HF)
        rows += (answer_rows(hf, "SU2 pool GPs") if hf.get("feasible")
                 else [["SU2 pool GPs", "no design meets the cap at the required probability"]])
    else:
        rows.append(["SU2 pool GPs", "PENDING"])
    bd.add_table(slide, LM, CT - 0.05, [3.0, 9.13], rows, size=13, row_h=0.45,
                 flag=("PENDING", "OUTSIDE"))
    y = CT - 0.05 + 0.45 * len(rows) + 0.2
    eq.add_equation(slide, v1.EQ_INV_QUERY, LM, y, 6.4, 0.45, fontsize=14)
    eq.add_equation(slide, v1.EQ_INV_PROB, LM + 6.6, y - 0.05, 5.5, 0.65, fontsize=14)


def body_confirm(slide, v):
    rows = [["Run", "Objective", "Predicted", "90 % interval", "SU2", "Position", "Pass"]]
    for label, c, inv in confirm_runs():
        if c is not None:
            for key, pred, unit in (("endurance_h", "predicted_mean", "h"),
                                    ("mtow_kg", "predicted_median", "kg")):
                o = c[key]
                rows.append([label if key == "endurance_h" else "", key.split("_")[0],
                             f"{o[pred]:.3f} {unit}", f"[{o['lo90']:.3f}, {o['hi90']:.3f}]",
                             f"{o['simulated']:.3f} {unit}", o["position"],
                             ("pass" if c["c2_pass"] else "FAIL") if key == "endurance_h" else ""])
        else:
            for key, pred, unit in (("endurance_h", "mean", "h"), ("mtow_kg", "median", "kg")):
                o = inv[key] if inv else None
                rows.append([label if key == "endurance_h" else "", key.split("_")[0],
                             f"{o[pred]:.3f} {unit}" if o else "PENDING",
                             f"[{o['lo90']:.3f}, {o['hi90']:.3f}]" if o else "PENDING",
                             "PENDING", "PENDING", "PENDING" if key == "endurance_h" else ""])
    bd.add_table(slide, LM, CT + 0.05, [2.9, 1.6, 1.7, 2.2, 1.5, 1.2, 1.03], rows, size=14,
                 row_h=0.55)
    bd.text_box(slide, LM, CT + 3.0, CW, 1.6,
                [("Pass condition fixed before the run: endurance and mass both inside their 90 % "
                 "intervals, and the mass under the cap."),
                 ("Each run is one SU2 polar (five angles) at the answer of the inverse query, sent "
                 "through the same queue and checks as the pool.")], size=14, bullets=True)


def body_viz(slide, v):
    bd.add_figure(slide, FIG_V2 + "viz_14.png", LM + 0.9, CT - 0.1, CW - 1.8, 4.9)


def body_limits(slide, v):
    text = (ROOT / v1.SPEC).read_text()
    para = re.search(r"Biases that travel with every figure:(.*?)\.\n\n", text, re.DOTALL).group(1)
    items = [" ".join(s.split()) for s in para.split(";")]
    items = [i[:1].upper() + i[1:] for i in items]
    lift = v1.lift_effectiveness()
    items += [f"Drift band of the kept pool cases: cl {v['pool_cl_drift']}, cd {v['pool_cd_drift']}",
              (f"Section lift effectiveness {lift['value']:g}, band {lift['band']}: the tunnel value "
              "lies outside it (open ruling)")]
    flat = " ".join(text.split())
    scope = re.search(r"Out of scope: (.*?)\. Biases", flat).group(1)
    scope = re.sub(r" \(a candidate [^)]*\)", "", scope)           # names later and earlier tasks
    bd.text_box(slide, LM, CT - 0.05, 6.4, 0.4, "Biases that travel with every figure", size=15,
                bold=True, color=bd.BLUE)
    bd.text_box(slide, LM, CT + 0.35, 6.4, 4.5, items, size=14, bullets=True, space_after=3)
    x = LM + 6.7
    bd.text_box(slide, x, CT - 0.05, 5.4, 0.4, "Out of scope", size=15, bold=True, color=bd.BLUE)
    bd.text_box(slide, x, CT + 0.35, 5.4, 1.9, scope[:1].upper() + scope[1:] + ".", size=14)
    bd.text_box(slide, x, CT + 2.35, 5.4, 0.4, "Carried by every SU2 section polar", size=15,
                bold=True, color=bd.BLUE)
    bd.text_box(slide, x, CT + 2.75, 5.4, 2.1, v1.v6e_flags(), size=12, font="Consolas",
                space_after=1)


def body_conclusions(slide, v):
    grid = v1.jload(GRID_RECORD)
    inv = v1.jload(v1.INVERSE_LF)
    _, two, _, _ = mf_match()
    single = v1.mf_means()[("single", v["mf_n0"], "rmse_endurance")] if v1.exists(v1.MF) else None
    hf = v1.jload(v1.INVERSE_HF) if v1.exists(v1.INVERSE_HF) else None
    conf = {label: c for label, c, _ in confirm_runs()}
    conf_text = "; ".join(f"{label}: " + ("PENDING" if c is None else
                                          ("pass" if c["c2_pass"] else "FAIL"))
                          for label, c in conf.items())
    rows = [["Question", "Answer from the records", "Status"],
            ["1. The front",
             (f"Exact low-fidelity front of {grid['front_size']} designs over "
             f"{grid['points_evaluated']:,} points"),
             "low level done; SU2 level " + ("done" if v1.exists(v1.PARETO_HF) else "PENDING")],
            ["2. Active learning",
             (f"Pool: EHVI regret {v['ehvi_32']} at 32 against random {v['rand_40']} at 40. Open box: "
             f"plain EHVI loses ({v['ehvi_on_40']} against {v['rand_on_40']}), weighted by "
             f"P(feasible) it wins ({v['feas_on_40']})"), "answered on the low level"],
            ["3. Two-level model",
             (f"Endurance error with {v['mf_n0']} SU2 designs: {two:.3f} h against {single:.3f} h for "
              f"SU2 alone, which needs {v['mf_n_match']} designs to match it; both intervals "
              "under-cover" if single is not None
              else "PENDING"), "recorded" if single is not None else "PENDING"],
            ["4. Inverse query",
             f"Low level: a box corner at {inv['endurance_h']['mean']:.2f} h, the cap does not bind. "
             + (f"SU2 pool: {hf['endurance_h']['mean']:.2f} h at {hf['mtow_kg']['median']:.2f} kg, "
                f"P = {hf['p_mtow_le_cap']:.3f}" if hf and hf.get("feasible") else "SU2 pool: PENDING"),
             conf_text]]
    bd.add_table(slide, LM, CT - 0.05, [2.4, 6.6, 3.13], rows, size=14, row_h=0.85, flag=())
    bd.text_box(slide, LM, CT + 4.35, CW, 0.5,
                f"What version 2 changed: the cloud runtimes are managed from the session; the records "
                f"show {v['n_worker_ids']} worker ids on {v['n_runtimes']} runtimes.", size=14, color=bd.BLUE,
                bold=True)


QUESTIONS = [("How was the SU2 solver validated, row by row?", ("B3", "B10", "B20")),
             ("How do you know a run converged?", ("B6", "B7", "B21")),
             ("What does the mesh do to the answer?", ("B5", "B8", "B18")),
             ("How good is the low-fidelity model?", ("B9", "B13", "B16")),
             ("Which assumptions move the answer most?", ("B17", "B26")),
             ("What went wrong first, and who decided what?", ("B19", "B25", "B29")),
             ("What did it cost?", ("B27",)),
             ("Where do the equations come from?", ("B28", "B4", "B2"))]


def body_questions(slide, v):
    titles = {s["id"]: s["title"] for s in read_outline()}
    rows = [["Likely question", "Backup"]]
    for q, ids in QUESTIONS:
        rows.append([q, "; ".join(f"{i} {titles[i]}" for i in ids)])
    bd.add_table(slide, LM, CT - 0.05, [4.6, 7.53], rows, size=14, row_h=0.55, flag=())


# ---- backup bodies that had to be rewritten -----------------------------------------------------
def body_lattice(slide, v):
    v1.body_lattice(slide, v)


def body_v6_full(slide, v):
    rows = v1.v6_rows(("V6a", "V6b", "V6c", "V6d"))
    bd.add_table(slide, LM, CT - 0.15, [6.4, 1.1, 1.1, 1.2, 0.9, 1.4], rows, size=8.5, row_h=0.2)
    y = CT - 0.15 + 0.2 * len(rows) + 0.15
    eq.add_equation(slide, v1.EQ_V6_HELMBOLD, LM, y, 2.6, 0.6, fontsize=13)
    eq.add_equation(slide, v1.EQ_V6_INDUCED, LM + 3.0, y, 2.0, 0.6, fontsize=13)
    eq.add_equation(slide, v1.EQ_V6_DEV, LM + 5.4, y + 0.05, 4.0, 0.5, fontsize=13)
    bd.text_box(slide, LM + 9.6, y, 2.5, 0.6, "M measured, R reference", size=11, color=bd.GREY)


def body_stopping(slide, v):
    rows = [["Run", "Budget", "Iterations", "cl drift (%)", "cd drift (%)", "Status"]]
    for rel, label in ((v1.SMOKE, "first smoke case"), (v1.SMOKE2, "rerun with Cauchy stop")):
        r = v1.jload(rel + "/result.json")
        conv, m = r["convergence"], r["metrics"]
        it = conv.get("iterations")
        rows.append([label, r["params"]["max_iter"], it if it else "not recorded (postprocess error)",
                     f"{m['cl_drift_pct']:.2f}", f"{m['cd_drift_pct']:.2f}", conv.get("status")])
    bd.add_table(slide, LM, CT + 0.1, [3.0, 1.2, 3.0, 1.4, 1.4, 2.1], rows, size=12, row_h=0.55)
    bd.text_box(slide, LM, CT + 1.8, 6.0, 0.3, "Drift rule, applied after ingest", size=12, color=bd.GREY)
    bd.text_box(slide, LM + 6.6, CT + 1.8, 5.5, 0.3, "SU2 Cauchy rule, as the case template states it",
                size=12, color=bd.GREY)
    eq.add_equation(slide, v1.EQ_STOP_DRIFT, LM, CT + 2.12, 3.2, 0.75, fontsize=14)
    eq.add_equation(slide, v1.EQ_STOP_WINDOW, LM + 3.3, CT + 2.3, 3.0, 0.4, fontsize=14)
    eq.add_equation(slide, v1.EQ_STOP_CAUCHY, LM + 6.6, CT + 2.12, 5.4, 0.75, fontsize=14)
    cfg = v1.template_cfg()
    keys = ("CONV_FIELD", "CONV_CAUCHY_ELEMS", "CONV_CAUCHY_EPS", "CONV_STARTITER")
    lines = [m.group(0).strip() for k in keys for m in re.finditer(rf"^{k}=.*$", cfg, re.MULTILINE)]
    bd.text_box(slide, LM, CT + 3.0, 5.5, 0.4, "Cauchy settings of the airfoil case template",
                size=13, bold=True)
    bd.text_box(slide, LM, CT + 3.4, 5.5, 1.4, lines, size=13, font="Consolas", space_after=2)
    bd.text_box(slide, LM + 6.0, CT + 3.0, 6.0, 1.8,
                [("The drift rule and SU2's Cauchy rule measure different things; the record carries "
                 "both."), "A run that ends on its budget is flagged, not silently kept."],
                size=13, bullets=True)


def body_v6f(slide, v):
    v1.body_v6f(slide, v)
    for sh in list(slide.shapes):                       # the note names the section module
        if sh.has_text_frame and "Report-only rows" in sh.text_frame.text:
            sh._element.getparent().remove(sh._element)
    bd.text_box(slide, LM, CT + 4.1, CW, 0.8,
                [("Report-only rows by the spec: the closed-form section at the E387's measured camber "
                 "and thickness against tunnel runs 211, 213 and 215."),
                 ("The ledger's assumed lift effectiveness does not contain the value the tunnel "
                 "implies: a ledger ruling, not a number to move here.")], size=13, bullets=True)


def body_v6e(slide, v):
    bd.add_figure(slide, FIG_V2_FD + "d_e387_comparison.png", LM, CT - 0.05, 6.4, 3.35)
    checks = [c for c in v6_checks() if c["name"].startswith("V6e ")]
    rows = [["Row", "Deviation", "Tol.", "Verdict"]]
    for c in checks:
        tol = "report" if c["tolerance"] is None else f"{100 * c['tolerance']:.0f} %"
        verdict = "FAIL" if c["verdict"] == "fail" else c["verdict"]
        dev = (f"{100 * c['deviation']:+.4f} %" if abs(c["deviation"]) < 1e-4
               else f"{100 * c['deviation']:+.2f} %")
        rows.append([c["name"][4:], dev, tol, verdict])
    bd.add_table(slide, LM + 7.0, CT - 0.1, [2.5, 1.0, 0.8, 0.8], rows, size=9, row_h=0.34)
    eq.add_equation(slide, v1.EQ_V6E_SLOPE, LM, CT + 3.9, 3.5, 0.75, fontsize=12)
    eq.add_equation(slide, v1.EQ_V6F_CDDEV, LM + 3.7, CT + 3.9, 3.4, 0.75, fontsize=12)
    nr = v1.jload(v1.V6)["not_run"]
    d8 = re.search(r'### Decision 8 \(([^)]+)\): "([^"]+)"', (ROOT / v1.TASKS).read_text())
    bd.text_box(slide, LM + 7.0, CT + 3.35, 5.1, 1.6,
                [(f"Against the tunnel at the five angles of Re {v['e387_re']}: cl is "
                 f"{v['su2_cl_range']}; cd is {v['su2_cd_range']}."),
                 f'Decision 8 ({d8.group(1)}): "{d8.group(2)}".',
                 "Not run: " + "; ".join(f"{n['what']} ({n['reason']})" for n in nr) + "."],
                size=10, bullets=True)


def body_bias_both(slide, v):
    for i, (rel, name, head) in enumerate(((v1.BIAS_LF, "bias_sweep.png", "At the low-fidelity answer"),
                                           (v1.BIAS_HF, "bias_sweep_hf.png", "At the SU2-pool answer"))):
        x = LM + i * 6.15
        bd.text_box(slide, x, CT - 0.1, 5.95, 0.35, head, size=14, bold=True, color=bd.BLUE)
        if not v1.exists(rel):
            bd.pending(slide, x, CT + 0.4, 5.95, "PENDING")
            continue
        bd.add_figure(slide, FIG_V2 + name, x, CT + 0.3, 5.95, 3.0)
        top = v1.csv_rows(rel)[:3]
        bd.text_box(slide, x, CT + 3.4, 5.95, 1.4,
                    ["Largest: " + ", ".join(f"{v1.pretty(r['name'])} "
                                             f"({float(r['max_abs_pct_endurance']):.1f} %)" for r in top),
                     "One quantity at a time, to each end of its ledger band."], size=12, bullets=True)


def body_mesh_both(slide, v):
    idx = {}
    for r in v1.csv_rows(v1.CASES):
        idx.setdefault(int(r["index"]), r["reynolds"])
    rows = [["Design", "Re", "alpha", "cl coarse", "cl medium", "ratio", "cd coarse", "cd medium",
             "ratio"]]
    for r in v1.csv_rows(v1.POOL + "/bias.csv"):
        rows.append([r["index"], f"{float(idx[int(r['index'])]):,.0f}", f"{float(r['alpha_deg']):g}",
                     f"{float(r['cl_coarse']):.4f}", f"{float(r['cl_medium']):.4f}",
                     f"{float(r['cl_medium_over_coarse']):.4f}", f"{float(r['cd_coarse']):.5f}",
                     f"{float(r['cd_medium']):.5f}", f"{float(r['cd_medium_over_coarse']):.4f}"])
    bd.text_box(slide, LM, CT - 0.15, CW, 0.3, "Pool designs on both meshes", size=12, bold=True,
                color=bd.BLUE)
    bd.add_table(slide, LM, CT + 0.15, [0.9, 1.3, 0.9, 1.4, 1.4, 1.2, 1.4, 1.4, 1.2], rows, size=9.5,
                 row_h=0.24, flag=())
    y = CT + 0.15 + 0.24 * len(rows) + 0.15
    runs = [("coarse", "runs/mesh/airfoil2d-59cd4287e9"), ("medium", v1.SMOKE2),
            ("fine", "runs/mesh/airfoil2d-e161fb7e6b")]
    recs = {lvl: v1.jload(p + "/result.json") for lvl, p in runs}
    fine = recs["fine"]["metrics"]
    mrows = [["Nominal section", "Cells", "Iterations", "Wall (s)", "cl", "cd", "cl, cd against fine"]]
    for lvl, r in recs.items():
        c, m = r["convergence"], r["metrics"]
        how = "budget" if c["iterations"] == r["params"]["max_iter"] else "Cauchy"
        mrows.append([lvl, f"{r['geometry']['cells']:,}", f"{c['iterations']:,} ({how})",
                      f"{r['run']['wall_time_s']:,.0f}", f"{m['cl']:.5f}", f"{m['cd']:.6f}",
                      "reference" if lvl == "fine" else
                      f"{v1.pct(m['cl'] / fine['cl'] - 1)}, {v1.pct(m['cd'] / fine['cd'] - 1)}"])
    bd.add_table(slide, LM, y, [2.0, 1.2, 2.0, 1.2, 1.3, 1.4, 2.4], mrows, size=9.5, row_h=0.24,
                 flag=())


def body_wrong_first(slide, v):
    tasks = (ROOT / v1.TASKS).read_text()
    claim = re.search(r'first said "(drags [^"]+)"', tasks).group(1)
    pts = v1.e387_points()
    cd = v1.signed_range([p[2] / p[4] - 1 for p in pts], "high", "low")
    rect = v1.v6_check("V6a (report) rectangular AR 100 fine: CL_alpha vs 2 pi AR/(AR+2)")
    rows = [["First recorded", "The record now says", "Found by"],
            [f'SU2 "{claim}" (task ledger)', f"per point cd is {cd}; the block is corrected in place",
             "the deck builder reading the E387 records"],
            ["Lattice check: a rectangular AR 100 wing against 2 pi AR / (AR + 2)",
             (f"that is the elliptic slope; the rectangular wing sits {v1.pct(rect['deviation'], 2)} "
             "below it, so the row tests an elliptic wing"), "the solver's own refinement, before any verdict"],
            ["Induced drag from the midpoint point-vortex sum",
             "Trefftz-plane drag of the Glauert series", "the elliptic-wing rows on the first lattice run"],
            [f"Online replay: plain EHVI at regret {v['ehvi_on_40']} against random's {v['rand_on_40']}",
             f"kept as published, with the feasibility-weighted run ({v['feas_on_40']}) beside it",
             "the plan's rule to publish a loss"],
            ["Fine mesh refused at the 1 nm fingerprint",
             "fingerprint at 1 micrometre, the refused attempt kept", "the worker's mesh check"],
            [f"Airfoil budget {v['smoke_budget']} iterations",
             f"{v['smoke2_budget']} with a Cauchy stop (decision 6)", "the first smoke case"],
            ["Volume file corrupted by the shared drive mount",
             ("the writer itself corrupts one case even on local disk; the diagnosis is corrected, "
             "not overwritten"), "re-running on local disk"]]
    stated = re.search(r"(\w+) of the six inputs at a bound", tasks)
    words = {"five": 5, "four": 4, "six": 6, "three": 3}
    if stated and words.get(stated.group(1)) != v["inv_n_bound"]:
        rows.append([f'Task ledger: "{stated.group(0)}" at the low-fidelity inverse answer',
                     f"the record has {v['inv_n_bound']} of six inputs at a bound",
                     "the deck builder reading the inverse record"])
    bd.add_table(slide, LM, CT - 0.1, [4.0, 5.0, 3.1], rows, size=11,
                 row_h=min(0.6, 4.8 / len(rows)), flag=())


def body_e387_points(slide, v):
    for i, re_ in enumerate((203800.0, 305200.0)):
        rows = [["alpha", "SU2 cl", "tunnel cl", "ratio", "SU2 cd", "tunnel cd", "ratio"]]
        for a, cl, cd, tcl, tcd in v1.e387_points(re_):
            rows.append([f"{a:g}", f"{cl:.4f}", f"{tcl:.4f}", v1.pct(cl / tcl - 1), f"{cd:.5f}",
                         f"{tcd:.5f}", v1.pct(cd / tcd - 1)])
        y = CT - 0.05 + i * 2.45
        bd.text_box(slide, LM, y, CW, 0.3, f"Re {re_:,.0f} (medium mesh, SA-BCM; tunnel: UIUC "
                    "low-speed airfoil data)", size=12, bold=True, color=bd.BLUE)
        bd.add_table(slide, LM, y + 0.35, [1.0, 1.6, 1.6, 1.4, 1.6, 1.6, 1.4], rows, size=11,
                     row_h=0.3, flag=())


def confirm_accepted():
    """Case ids of confirmation designs whose record admits budget-exhausted runs by a ruling."""
    out = set()
    for f in sorted((ROOT / "runs/drone_confirm").glob("*/design/result.json")):
        d = json.loads(f.read_text())
        if any(fl.startswith("budget_exhausted_accepted=") for fl in d["section"]["flags"]):
            out.update(d["cases"])
    return out


def body_budget(slide, v):
    from analysis.pool_af_results import kept
    idx = v1.pool_case_index()
    accepted = set(v1.jload(v1.POOL + "/record.json").get("accept_budget_exhausted", []))
    rows = [["Tag", "Design, alpha", "Mesh", "cl", "cd", "cl drift (%)", "cd drift (%)", "Kept"]]
    for tag, case, r in v1.budget_exhausted():
        where = idx.get(case)
        label = (f"{where[1]}, {where[2]:g} deg" if where
                 else f"{r['params']['alpha_deg']:g} deg")
        d = r["convergence"]["drift_pct"]
        if tag == "confirm":
            keep = "yes, by ruling" if case in confirm_accepted() else "no"
        elif not tag.startswith("pool"):
            keep = "not a pool case"
        elif kept([r]):
            keep = "yes"
        elif where and where[1] in accepted and tag == "pool_af":
            keep = "yes, by ruling"
        else:
            keep = "no"
        rows.append([tag.replace("_", " "), label, r["params"]["mesh_level"],
                     f"{r['metrics']['cl']:+.4f}", f"{r['metrics']['cd']:.5f}", f"{d['cl']:.1f}",
                     f"{d['cd']:.1f}", keep])
    half = (len(rows) + 1) // 2
    for i, part in enumerate((rows[:half], [rows[0]] + rows[half:])):
        bd.add_table(slide, LM + i * 6.15, CT - 0.2, [0.75, 0.95, 0.6, 0.65, 0.65, 0.55, 0.55, 1.25],
                     part, size=7.5, row_h=min(0.22, 4.4 / len(part)), flag=())
    bd.text_box(slide, LM, CT + 4.55, CW, 0.4,
                "A drift of tens of percent at cl near zero is the division by |f_n| in the drift rule. "
                f"Kept by ruling: pool designs {' and '.join(map(str, sorted(accepted)))} and "
                f"{sum(r[-1] == 'yes, by ruling' for r in rows if r[0] == 'confirm')} confirmation "
                "case(s).", size=10,
                color=bd.GREY)


DECISION_EFFECT = {
    "9": "designs 8 and 28 complete; the rule for every other run unchanged",
    "10": "the 14 degree confirmation case admitted; the confirmation result unchanged",
}


def body_decisions(slide, v):
    tasks = (ROOT / v1.TASKS).read_text()
    rows = [r[:] for r in v1.decision_rows()]
    for r in rows[1:]:
        r[2] = re.sub(r" \(both templates:[^)]*\)", "", r[2])
    for n, who, quote in re.findall(r'^### Decision (\d+) \(([^)]+)\): "([^"]+)"', tasks, re.MULTILINE):
        if int(n) >= 9:
            rows.append([n, who, f'"{quote}"', DECISION_EFFECT.get(n, "recorded in the task ledger")])
    rows[1:] = sorted(rows[1:], key=lambda r: int(r[0]))      # decision 11 comes from v1's rows
    bd.add_table(slide, LM, CT - 0.1, [1.0, 2.7, 5.1, 3.33], rows, size=10.5,
                 row_h=min(0.95, 4.9 / len(rows)), flag=())


def body_ledger(slide, v):
    counts = v1.ledger_counts()
    rows = [["Set", "Quantities", "Published", "Derived", "Assumed", "With a band"]]
    for name, c in counts.items():
        rows.append([name, c["all"], c["published"], c["derived"], c["assumed"], c["band"]])
    tot = {k: sum(c[k] for c in counts.values()) for k in ("all", "published", "derived", "assumed",
                                                            "band")}
    rows.append(["total", tot["all"], tot["published"], tot["derived"], tot["assumed"], tot["band"]])
    bd.add_table(slide, LM, CT, [3.6, 1.6, 1.6, 1.6, 1.6, 1.8], rows, size=13, row_h=0.45, flag=())
    bd.text_box(slide, LM, CT + 3.5, CW, 1.2,
                [("The ledger loader refuses a quantity without a source, and an assumed one without a "
                 "band that contains its value."),
                 "Validation data (E387, Warren-12) are kept apart and not counted."],
                size=12, bullets=True)


def body_cost(slide, v):
    rows = [["Mesh level", "Cases", "Wall (s): median", "min to max", "Iterations: median",
             "Worker-hours"]]
    for level in ("coarse", "medium", "fine"):
        recs = [r for r in v1.all_su2_records().values() if r["params"]["mesh_level"] == level]
        if not recs:
            continue
        w = [r["run"]["wall_time_s"] for r in recs]
        it = [r["convergence"].get("iterations") or r["run"]["iterations"] for r in recs]
        rows.append([level, len(recs), f"{np.median(w):,.0f}", f"{min(w):,.0f} to {max(w):,.0f}",
                     f"{np.median(it):,.0f}", f"{sum(w) / 3600:.1f}"])
    bd.add_table(slide, LM, CT - 0.05, [1.8, 1.0, 2.0, 2.0, 2.2, 1.6], rows, size=12, row_h=0.42,
                 flag=())
    by_tag = defaultdict(float)
    for (tag, _), r in v1.all_su2_records().items():
        by_tag[tag] += r["run"]["wall_time_s"] / 3600
    trows = [["Tag", "Worker-hours"]] + [[t.replace("_", " "), f"{h:.1f}"]
                                          for t, h in sorted(by_tag.items())]
    bd.add_table(slide, LM, CT + 2.0, [2.2, 2.2], trows, size=11, row_h=0.26, flag=())
    grid = v1.jload(GRID_RECORD)
    pool = v1.jload("runs/drone_pool_lf/2026-11-08/record.json")
    online = v1.jload("runs/replay_drone_online/2026-11-08/record.json")
    feas = v1.jload("runs/replay_drone_online/2026-11-08_feas/record.json")
    bd.text_box(slide, LM + 4.8, CT + 2.0, 7.3, 2.8,
                [f"Low-fidelity grid: {grid['wall_seconds'] / 3600:.2f} h on {grid['workers']} workers.",
                 f"Low pool: {pool['wall_seconds']:.0f} s on {pool['workers']} workers.",
                 f"Online replays: {online['wall_seconds']:.0f} s and {feas['wall_seconds']:.0f} s.",
                 "SU2 wall times are from each run record; ranks per case: " + v1.ranks_line() + "."],
                size=12, bullets=True)


def body_equation_index(slide, v, placed):
    """Every relation a slide of this deck renders, with the slide that carries it."""
    rows = [["Slide", "Relation"]]
    for latex, name, _module in v1.EQUATION_INDEX:
        where = placed.get(latex)
        if where:
            rows.append([", ".join(where), name])
    half = (len(rows) + 1) // 2
    for i, part in enumerate((rows[:half], [rows[0]] + rows[half:])):
        bd.add_table(slide, LM + i * 6.15, CT - 0.15, [1.2, 4.75], part, size=10,
                     row_h=min(0.3, 4.9 / len(part)), flag=())


def body_rulings(slide, v):
    lift = v1.lift_effectiveness()
    cm = v1.v6_check("V6b Warren-12 fine: Cm_alpha (about root LE, reference chord 1.0) vs benchmark")
    report = (ROOT / v1.REPORT).read_text()
    block = re.search(r"## 9\. Open rulings\n\n(.*)", report, re.DOTALL).group(1)
    first = " ".join(re.split(r"\n(?=\d\. )", block.strip())[0].split())
    decided = re.search(r"decided ([\d-]+) \((decision \d+)\)", first)
    rec = v1.jload(v1.POOL + "/record.json")
    rows = [["Ruling", "Evidence", "Status"],
            ["1. Admit budget-exhausted SU2 runs into the pool?",
             "pool cases that used their whole budget; designs "
             + " and ".join(map(str, rec.get("accept_budget_exhausted", []))) + " were incomplete",
             (f"decided {decided.group(1)} ({decided.group(2)}) for those designs only"
              if decided else "open")],
            ["2. The section lift-effectiveness band",
             (f"ledger {lift['value']:g}, band {lift['band']}; closed-form lift slope "
             f"{v['f_clalpha_range']} low against the tunnel"),
             "open: re-centring moves the low-fidelity grid and the replays (a full re-run)"],
            ["3. The Warren-12 moment reference point",
             f"Cm_alpha {v1.pct(cm['deviation'])} about the root leading edge, verdict pending",
             "open: sourcing the point closes the row; no tolerance moves"]]
    bd.add_table(slide, LM, CT, [3.6, 4.8, 3.7], rows, size=12, row_h=1.0, flag=())


E0_ANALYSIS = "runs/e0_analysis/2026-11-11/e0.json"
W1_FIELD_PLANNED = 120


def latest(pattern):
    """The newest record matching a glob under the repository, or None."""
    found = sorted(ROOT.glob(pattern))
    return found[-1] if found else None


def w1_gate_a():
    """Gate A of W1 from its records: both control runs against the E0 cold run they restart."""
    from analysis.s12_numerics import distance, load
    rows = v1.csv_rows("designs/w1_control_cases.csv") if (ROOT / "designs/w1_control_cases.csv").exists() else []
    try:
        runs = [load(r["case_id"], "w1_control") for r in rows]
        cold = load(rows[0]["donor"], "e0")
    except (FileNotFoundError, IndexError):
        return "PENDING"
    ok = all(r["exit_code"] == 0 and r["iterations"] < r["max_iter"]
             and all(distance(r, cold, q) * 100 <= cold[f"drift_{q}_pct"] for q in ("cl", "cd"))
             for r in runs)
    same = len({(r["cl"], r["cd"]) for r in runs}) == 1
    return ((f"pass: {', '.join(str(r['iterations']) for r in runs)} iterations; "
             f"cl {distance(runs[0], cold, 'cl'):.2%}, cd {distance(runs[0], cold, 'cd'):.2%} from the "
             f"cold run; {'identical' if same else 'different'} answers") if ok else "FAIL")


def w1_rows():
    fields = len(list((ROOT / "runs/w1_field").glob("airfoil2d-*/result.json")))
    refs = len(list((ROOT / "runs/w1_ref").glob("airfoil2d-*/result.json")))
    model = latest("runs/w1_model/*/model.json")
    if model:
        m = json.loads(model.read_text())
        model_text = (f"frozen: {m['k']} components, {m['training_cases']} training fields, "
                      f"leave-one-design-out error {m['leave_one_design_out'][str(m['k'])]['mean']:.3f}")
    else:
        model_text = "PENDING"
    res = latest("runs/w1_analysis/*/w1.json")
    if res:
        r = json.loads(res.read_text())
        if r.get("verdict") == "not evaluated":
            near = learn = adds = "not evaluated (fewer than five valid references)"
        else:
            near = f"{r['near']['verdict']}: median saving {r['near']['median_saving']:.1%}"
            learn = f"{r['learn']['verdict']}: median saving {r['learn']['median_saving']:.1%}"
            adds = r["learning_adds"]["result"]
    else:
        near = learn = adds = "PENDING"
    return [["Step", "Status from the records"],
            ["Control: a converged case restarted through the new start files", w1_gate_a()],
            ["Training fields (other pool designs, -2 to 10 deg)",
             f"{fields} of {W1_FIELD_PLANNED} recorded" if fields else "PENDING"],
            ["New references for the second test section", f"{refs} of 3 recorded" if refs else "PENDING"],
            ["Field model", model_text],
            ["Nearest stored case as the start", near],
            ["Learned start", learn],
            ["Learned start better than the nearest case?", adds]]


def body_w1(slide, v):
    e0 = v1.jload(E0_ANALYSIS)["verdict"]
    rows = [["Restart, no model (E0)", "Median iteration saving", "Median wall saving", "cl and cd held",
             "Verdict"]]
    for kind, label in (("angle_step", "from the neighbouring angle"), ("mesh_step", "coarse to medium mesh")):
        k = e0[kind]
        rows.append([label, f"{k['median_iter_saving']:.1%}", f"{k['median_wall_saving']:.1%}",
                     "yes" if k["forces_within_drift"] else "no", k["verdict"].upper()])
    bd.add_table(slide, LM, CT - 0.2, [2.9, 2.3, 2.1, 1.7, 1.2], rows, size=11, row_h=0.36)
    bd.add_table(slide, LM, CT + 1.05, [5.0, 7.13], w1_rows(), size=11, row_h=0.36)
    bd.text_box(slide, LM, CT + 4.0, CW, 0.9,
                [("Seven coarse cases on two sections the model never saw; cold, nearest-case and "
                  "learned starts, two runs each, on one machine."),
                 ("A start passes if every run stops cleanly, cl and cd stay within 2 % of a tightly "
                  "converged reference, and the median wall-time saving is at least 30 % and three "
                  "times the repeat noise.")],
                size=11, bullets=True, space_after=2)


def reuse(d_id):
    """A version-1 body, unchanged (its source captions are removed after it runs)."""
    return v1.BODIES[d_id]


def figure_body(name, max_h=4.6, sub=FIG_V2):
    def body(slide, v):
        bd.add_figure(slide, sub + name, LM, CT - 0.05, CW, max_h)
    return body


BODIES = {
    "V2": body_problem, "V3": body_clean_exit, "V4": body_problem_cap, "V5": body_pipeline_v2,
    "V6": body_mcp, "V7": body_gates, "V8": body_costs, "V9": body_validation,
    "V10": body_queue_shards, "V11": body_timeline, "V12": body_caught, "V13": body_gp,
    "V14": body_pool_replay, "V15": reuse("D32"), "V16": body_mf, "V17": body_time_saved,
    "V18": body_hf_vs_lf, "V19": body_front, "V20": body_inverse, "V21": body_confirm,
    "V22": body_viz, "V23": body_limits, "V24": body_conclusions, "V25": body_questions,
    "B1": figure_body("planform.png", 4.5), "B2": reuse("D11"), "B3": body_v6_full,
    "B4": reuse("D13"), "B5": reuse("D14"), "B6": body_stopping,
    "B7": figure_body("convergence_smoke2.png", 4.7, FIG_V2_FLOW),
    "B8": figure_body("cp_mesh_pair.png", 4.7, FIG_V2_FLOW), "B9": body_v6f, "B10": body_v6e,
    "B11": figure_body("cp_e387.png", 4.7, FIG_V2_FLOW),
    "B12": figure_body("cf_e387.png", 4.7, FIG_V2_FLOW),
    "B13": figure_body("section_polars_v2.png", 4.7),
    "B14": figure_body("cp_design0.png", 4.7, FIG_V2_FLOW),
    "B15": figure_body("design_space.png", 4.5), "B16": reuse("D34"), "B17": body_bias_both,
    "B18": body_mesh_both, "B19": body_wrong_first, "B20": body_e387_points, "B21": body_budget,
    "B22": reuse("DB6"), "B23": reuse("DB7"), "B24": reuse("DB9"), "B25": body_decisions,
    "B26": body_ledger, "B27": body_cost, "B28": body_equation_index, "B29": body_rulings, "B30": body_w1,
}


# ---- the deck ---------------------------------------------------------------------------------
def title_slide(prs, s, v):
    rec = v1.jload(v1.POOL + "/record.json")
    conf = "; ".join(f"confirmation of the {label}: "
                     + ("PENDING" if c is None else "pass" if c["c2_pass"] else "FAIL")
                     for label, c, _ in confirm_runs())
    slide = bd.add_title_slide(
        prs, 1, "A gated, automated design pipeline", fill(s["message"], v),
        ["Version 2", (f"Status at build time: SU2 pool {rec['complete']} of {rec['designs']} designs "
         f"complete; {conf}.")], fill(s["notes"], v))
    for shape in slide.shapes:                     # the shared title helper labels its slide S1
        if shape.has_text_frame and shape.text_frame.text.startswith("S1  |"):
            shape.text_frame.paragraphs[0].runs[0].text = f"{s['id']}  |  1"
    return slide


def build(out_path=DEFAULT_OUT):
    """Build the deck and save it. Returns the number of slides.

    Order: V1 (title), V2 to V25 with no dividers, one "Backup" divider, then B1 onward.
    """
    v1.all_su2_records.cache_clear()
    values.cache_clear()
    slides = read_outline()
    main = [s for s in slides if s["id"].startswith("V")]
    backup = [s for s in slides if s["id"].startswith("B")]
    assert len(main) <= 25, "the main body is at most 25 slides"
    with clean_figures(), v2_figure_dirs():
        ensure_figures()
        v = values()
        missing = placeholders() - set(v)
        assert not missing, f"outline placeholders without a value: {missing}"
        prs = bd.new_deck()
        placed = defaultdict(list)
        for s in main + [None] + backup:
            if s is None:
                bd.add_divider_slide(prs, "Backup", "Opened only on a question")
                continue
            if s["id"] == "V1":
                slide = title_slide(prs, s, v)
            else:
                slide = bd.start_slide(prs, len(prs.slides) + 1, s["id"], s["title"],
                                       fill(s["message"], v), [], fill(s["notes"], v))
                body = BODIES[s["id"]]
                if s["id"] == "B28":
                    body(slide, v, placed)
                else:
                    body(slide, v)
                remove_source_captions(slide)
            for latex, _ in eq.placed_on(slide):
                placed[latex].append(s["id"])
            check_slide(slide, s["id"], main=s["id"].startswith("V"))
    prs.save(str(out_path))
    return len(prs.slides)


if __name__ == "__main__":
    n = build()
    print(f"wrote {DEFAULT_OUT.relative_to(ROOT)} with {n} slides")
