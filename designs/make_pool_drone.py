"""Task 10 drone pools: python -m designs.make_pool_drone

Scrambled 6-d Sobol points over the drone inputs, drawn in order and gate-checked; points that
fail a gate are skipped (and counted). Writes
  designs/pool_drone96.csv     the first 96 gate-passing points of seed 0
  designs/pool_drone_lf192.csv those 96 plus the first 96 gate-passing points of seed 1
"""
from collections import Counter
from pathlib import Path

from scipy.stats import qmc

from physics.gates import check

INPUTS = ("span_m", "aspect_ratio", "taper_ratio", "battery_fraction", "camber_pct", "thickness_pct")
LOW = (1.2, 6.0, 0.3, 0.20, 0.0, 8.0)
HIGH = (3.0, 16.0, 1.0, 0.45, 6.0, 15.0)
N_PASS = 96
HERE = Path(__file__).parent


def design(n, seed):
    """n scrambled Sobol points scaled to the box, rounded to 6 decimals."""
    unit = qmc.Sobol(d=len(INPUTS), scramble=True, seed=seed).random(n)
    return qmc.scale(unit, LOW, HIGH).round(6)


def params_of(row):
    return {"family": "drone", "fidelity": "low", "tag": "pool", **dict(zip(INPUTS, map(float, row)))}


def accepted(seed, n=N_PASS, label=""):
    """First n gate-passing points of the seed, in draw order."""
    pts, drawn, skipped, prefixes = [], 0, 0, Counter()
    chunk = 128
    all_pts = design(chunk * 4, seed)      # Sobol scrambling is fixed by the seed; draw more if needed
    for row in all_pts:
        drawn += 1
        msgs = check(params_of(row))
        if msgs:
            skipped += 1
            prefixes.update(m.split(":")[0] for m in msgs)
            if skipped <= 5:
                print(f"  skip {tuple(row)}: {msgs[0]}")
            continue
        pts.append(row)
        if len(pts) % 16 == 0:
            print(f"  seed {seed}: {len(pts)} accepted after {drawn} drawn", flush=True)
        if len(pts) == n:
            break
    print(f"seed {seed}{label}: drew {drawn}, accepted {len(pts)}, skipped {skipped}; by prefix {dict(prefixes)}")
    if len(pts) < n:
        raise RuntimeError("not enough gate-passing points")
    return pts


def write(path, pts):
    lines = ["index," + ",".join(INPUTS)]
    lines += [f"{i}," + ",".join(f"{v:.6f}" for v in row) for i, row in enumerate(pts)]
    Path(path).write_text("\n".join(lines) + "\n")


def main():
    a = accepted(0)
    write(HERE / "pool_drone96.csv", a)
    b = accepted(1)
    write(HERE / "pool_drone_lf192.csv", a + b)
    print("wrote designs/pool_drone96.csv (96) and designs/pool_drone_lf192.csv (192)")


if __name__ == "__main__":
    main()
