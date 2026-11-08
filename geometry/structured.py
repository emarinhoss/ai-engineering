"""Block-structured 2D quad mesher and SU2 writer (numpy only).

Pieces:
  stretch_*   1D point distributions (geometric clustering near walls).
  Block       four edges -> interior nodes by transfinite (Coons) interpolation.
  Mesh        blocks glued along shared edges -> global node ids, quads, markers,
              quality numbers, SU2 ASCII output.
Units are whatever the caller uses (metres in this repo).
"""
import hashlib
import json
import math
from itertools import pairwise
from pathlib import Path

import numpy as np

SIDES = ("bottom", "right", "top", "left")


# ----------------------------------------------------------------------------
# 1D stretching. Spacings are d_k = x_{k+1} - x_k, k = 0 .. N-2.
# Every function returns (coords, ratio): coords has N points on [0, L], and
# ratio is the geometric growth ratio that was solved for (stretch_two_sided
# returns a pair, one ratio per half).
# ----------------------------------------------------------------------------
def _bisect_increasing(f, lo, hi, target, iters=200):
    """Find r in [lo, hi] with f(r) = target for a non-decreasing f."""
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        if f(mid) < target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def stretch_one_sided(L, N, d0):
    """N points on [0, L], first spacing exactly d0, spacing growing by a constant ratio r.

    Solves d0 (r^(N-1) - 1) / (r - 1) = L for r by bisection (r = 1 when d0 (N-1) = L).
    Raises ValueError if d0 (N-1) > L, because the spacing would have to shrink.
    """
    if N < 2:
        raise ValueError("need N >= 2")
    n = N - 1                                   # number of spacings
    target = L / d0
    if target < n * (1.0 - 1e-12):
        raise ValueError(f"d0*(N-1) = {d0 * n:.6g} > L = {L:.6g}")
    if abs(target - n) <= 1e-12 * n:
        r = 1.0
    else:
        def total(r):                           # sum of r^k, k = 0..n-1 (safe near r = 1)
            return float(np.sum(r ** np.arange(n)))
        hi = 2.0
        while total(hi) < target:
            hi *= 2.0
        r = _bisect_increasing(total, 1.0, hi, target)
    x = np.concatenate(([0.0], np.cumsum(d0 * r ** np.arange(n))))
    x[-1] = L                                   # remove the bisection residue
    return x, r


def stretch_two_sided(L, N, d0, d1):
    """Clustering at both ends: spacing d0 at x = 0 and d1 at x = L, growing toward L/2.

    Two one-sided halves (N//2 + 1 and N - N//2 points) are joined at L/2. Limitation: the
    two halves do not share a spacing at L/2; each ends at its own d * r^k, so there is a
    spacing jump at the join unless d0 = d1 and the halves have equal point counts.
    Returns (coords, (ratio_first_half, ratio_second_half)).
    """
    na, nb = N // 2 + 1, N - N // 2
    a, ra = stretch_one_sided(L / 2, na, d0)
    b, rb = stretch_one_sided(L / 2, nb, d1)
    x = np.concatenate((a, L - b[::-1][1:]))
    return x, (ra, rb)


def stretch_capped(L, N, d0, dmax):
    """N points on [0, L]: spacing d0 * r^k, but never more than dmax (then uniform at dmax).

    r is solved by bisection so that the spacings sum to L. Raises ValueError, giving the
    required N, if even the fastest growth (r = dmax/d0) cannot reach L with N points.
    """
    if d0 > dmax:
        raise ValueError("d0 > dmax")
    n = N - 1
    n_needed = math.ceil((L - d0) / dmax) + 2
    if d0 + dmax * (n - 1) < L * (1.0 - 1e-12):
        raise ValueError(f"cannot span L={L:.6g} with N={N} at dmax={dmax:.6g}; need N >= {n_needed}")
    if d0 * n > L * (1.0 + 1e-12):
        raise ValueError(f"d0*(N-1) = {d0 * n:.6g} > L = {L:.6g}")

    def spacings(r):
        return np.minimum(d0 * r ** np.arange(n), dmax)

    r = _bisect_increasing(lambda r: spacings(r).sum(), 1.0, dmax / d0, L)
    x = np.concatenate(([0.0], np.cumsum(spacings(r))))
    x[-1] = L
    return x, r


def stretch_two_sided_smooth(L, N, d0, d1, dmax=None):
    """N points on [0, L]: spacing d0 at x = 0, d1 at x = L, one growth ratio r from both ends.

    Spacing k is min(d0 r^k, d1 r^(n-1-k)): growth from the left meets the decay toward the
    right, so the largest spacing is in the middle and no consecutive spacing ratio exceeds r.
    With dmax the spacing never exceeds dmax (a uniform stretch in the middle). r is solved by
    bisection so the spacings sum to L (the sum is non-decreasing in r). Raises ValueError if
    d0 and d1 cannot both be reached. Returns (coords, info) with info = {"ratio": r,
    "max_spacing": ..., "max_growth": largest consecutive spacing ratio}.
    """
    n = N - 1
    k = np.arange(n)

    def spacings(r):
        with np.errstate(over="ignore"):             # huge trial ratios overflow to inf; min() copes
            d = np.minimum(d0 * r ** k, d1 * r ** (n - 1 - k))
        return d if dmax is None else np.minimum(d, dmax)

    if spacings(1.0).sum() > L * (1.0 + 1e-12):
        raise ValueError(f"n*min(d0, d1) = {spacings(1.0).sum():.6g} > L = {L:.6g}")
    hi = 2.0
    while spacings(hi).sum() < L:
        hi *= 2.0
        if hi > 1e6:
            raise ValueError("cannot span L with these spacings")
    r = _bisect_increasing(lambda r: spacings(r).sum(), 1.0, hi, L)
    d = spacings(r)
    if abs(d[0] - d0) > 1e-9 * d0 or abs(d[-1] - d1) > 1e-9 * d1:
        raise ValueError(f"end spacings {d0:.6g}, {d1:.6g} not reachable with N={N}, L={L:.6g}")
    x = np.concatenate(([0.0], np.cumsum(d)))
    x[-1] = L
    growth = np.maximum(d[1:] / d[:-1], d[:-1] / d[1:]) if n > 1 else np.ones(1)
    return x, {"ratio": r, "max_spacing": float(d.max()), "max_growth": float(growth.max())}


# ----------------------------------------------------------------------------
# Block
# ----------------------------------------------------------------------------
def _arc_param(pts):
    """Normalised arc length 0..1 along a polyline."""
    s = np.concatenate(([0.0], np.cumsum(np.hypot(*np.diff(pts, axis=0).T))))
    return s / s[-1]


class Block:
    """One structured block. Edges are (K, 2) point arrays:
    bottom (N1 pts, left->right), top (N1 pts, left->right),
    left (N2 pts, bottom->top), right (N2 pts, bottom->top).
    nodes[i, j] is the point at bottom/top index i and left/right index j.
    """

    def __init__(self, bottom, right, top, left):
        self.bottom, self.right, self.top, self.left = (
            np.asarray(e, dtype=float) for e in (bottom, right, top, left))
        self.N1, self.N2 = len(self.bottom), len(self.left)
        if len(self.top) != self.N1 or len(self.right) != self.N2:
            raise ValueError("opposite edges need equal point counts")
        for a, b, name in ((self.bottom[0], self.left[0], "bottom-left"),
                           (self.bottom[-1], self.right[0], "bottom-right"),
                           (self.top[0], self.left[-1], "top-left"),
                           (self.top[-1], self.right[-1], "top-right")):
            assert np.max(np.abs(a - b)) < 1e-12, f"corner {name} does not coincide"
        self.nodes = self._coons()

    def _coons(self):
        """Transfinite interpolation: edge-blended sum minus the bilinear corner term.

        (s, t) in [0,1]^2 are normalised arc-length parameters. The four edges have their
        own parameter sets sb, st (bottom, top) and tl, tr (left, right). At node (i, j) we
        take s from sb/st blended by the mean t of that row, and t from tl/tr blended by s,
        so the formula returns every edge point exactly.
        """
        B, R, T, L = self.bottom, self.right, self.top, self.left
        sb, st, tl, tr = _arc_param(B), _arc_param(T), _arc_param(L), _arc_param(R)
        tj = 0.5 * (tl + tr)
        s = (1 - tj)[None, :] * sb[:, None] + tj[None, :] * st[:, None]       # (N1, N2)
        t = (1 - s) * tl[None, :] + s * tr[None, :]
        s, t = s[..., None], t[..., None]
        p00, p10, p01, p11 = B[0], B[-1], T[0], T[-1]
        X = ((1 - s) * L[None, :, :] + s * R[None, :, :]
             + (1 - t) * B[:, None, :] + t * T[:, None, :]
             - ((1 - s) * (1 - t) * p00 + s * (1 - t) * p10 + (1 - s) * t * p01 + s * t * p11))
        X[:, 0], X[:, -1], X[0, :], X[-1, :] = B, T, L, R                       # exact edges
        return X

    def side_indices(self, side):
        """(i, j) index pairs along a side, in increasing index direction."""
        if side == "bottom":
            return [(i, 0) for i in range(self.N1)]
        if side == "top":
            return [(i, self.N2 - 1) for i in range(self.N1)]
        if side == "left":
            return [(0, j) for j in range(self.N2)]
        if side == "right":
            return [(self.N1 - 1, j) for j in range(self.N2)]
        raise ValueError(f"unknown side {side!r}")

    def layers(self, side):
        """Nodes as (K, M, 2): K positions along the side, M layers going inward from it."""
        X = self.nodes
        return {"bottom": X, "top": X[:, ::-1],
                "left": X.transpose(1, 0, 2), "right": X[::-1].transpose(1, 0, 2)}[side]


# ----------------------------------------------------------------------------
# Mesh
# ----------------------------------------------------------------------------
def _signed_area(P):
    """Shoelace area of quads P with shape (..., 4, 2); positive when counter-clockwise."""
    x, y = P[..., 0], P[..., 1]
    return 0.5 * np.sum(x * np.roll(y, -1, axis=-1) - np.roll(x, -1, axis=-1) * y, axis=-1)


class Mesh:
    """Glued blocks. Build with Mesh.from_blocks."""

    def __init__(self):
        self.blocks = []
        self.node_ids = {}        # (block_index, i, j) -> global node id
        self.coords = None        # (n_nodes, 2)
        self.cells = None         # (n_cells, 4) global ids, counter-clockwise
        self.n_inverted = 0       # cells with signed area <= 0 in the original node order
        self.markers = {}         # name -> list of (id_a, id_b) boundary lines
        self.marker_sides = {}    # name -> list of (block_index, side)
        self.walls = []           # marker names flagged as walls
        self.level = None

    @classmethod
    def from_blocks(cls, blocks, shared, level=None):
        """shared: list of (block_a, side_a, block_b, side_b, reversed) giving the same physical
        edge seen from two blocks (indices into blocks). reversed=True when the index
        directions of the two sides run opposite. Ids are merged by identity, never by
        coordinates; coordinates are only compared as a sanity check."""
        m = cls()
        m.blocks, m.level = list(blocks), level
        parent = {}

        def find(k):
            while parent.get(k, k) != k:
                parent[k] = parent.get(parent[k], parent[k])
                k = parent[k]
            return k

        for a, sa, b, sb, rev in shared:
            na = [(a, i, j) for i, j in m.blocks[a].side_indices(sa)]
            nb = [(b, i, j) for i, j in m.blocks[b].side_indices(sb)]
            if rev:
                nb = nb[::-1]
            if len(na) != len(nb):
                raise ValueError(f"shared sides {(a, sa)} and {(b, sb)} have different node counts")
            for ka, kb in zip(na, nb):
                if np.max(np.abs(m.blocks[a].nodes[ka[1:]] - m.blocks[b].nodes[kb[1:]])) > 1e-9:
                    raise ValueError(f"shared nodes {ka} and {kb} are at different positions")
                ra, rb = find(ka), find(kb)
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)

        # One global id per physical node, assigned in block / j / i order.
        gid, coords = {}, []
        for bi, blk in enumerate(m.blocks):
            for j in range(blk.N2):
                for i in range(blk.N1):
                    root = find((bi, i, j))
                    if root not in gid:
                        gid[root] = len(coords)
                        coords.append(blk.nodes[i, j])
                    m.node_ids[(bi, i, j)] = gid[root]
        m.coords = np.array(coords)

        # Quads (i,j), (i+1,j), (i+1,j+1), (i,j+1); flip any that come out clockwise.
        cells = []
        for bi, blk in enumerate(m.blocks):
            ids = np.array([[m.node_ids[(bi, i, j)] for j in range(blk.N2)] for i in range(blk.N1)])
            X = blk.nodes
            P = np.stack((X[:-1, :-1], X[1:, :-1], X[1:, 1:], X[:-1, 1:]), axis=2)   # (N1-1, N2-1, 4, 2)
            C = np.stack((ids[:-1, :-1], ids[1:, :-1], ids[1:, 1:], ids[:-1, 1:]), axis=2)
            area = _signed_area(P)
            m.n_inverted += int(np.sum(area <= 0))
            C = np.where((area < 0)[..., None], C[..., ::-1][..., [3, 0, 1, 2]], C)   # (a,b,c,d) -> (a,d,c,b)
            cells.append(C.reshape(-1, 4))
        m.cells = np.concatenate(cells)
        return m

    def add_marker(self, name, sides, wall=False):
        """Boundary lines of the given [(block_index, side), ...]; wall=True for no-slip walls
        (quality() reports first-cell height and growth for those)."""
        lines = []
        for b, side in sides:
            ids = [self.node_ids[(b, i, j)] for i, j in self.blocks[b].side_indices(side)]
            lines += list(pairwise(ids))
        self.markers[name] = lines
        self.marker_sides[name] = list(sides)
        if wall:
            self.walls.append(name)

    # -- quality -------------------------------------------------------------
    def quality(self):
        """min_angle_deg, max_aspect_ratio (longest / shortest cell edge), n_inverted,
        first_cell_height {wall marker: mean wall-normal distance to the first interior node},
        max_growth (largest ratio of consecutive cell heights, either direction, along the
        index direction normal to a wall; measured inside the wall's own block only)."""
        P = self.coords[self.cells]                                   # (M, 4, 2)
        e = np.roll(P, -1, axis=1) - P                                # edge k: vertex k -> k+1
        length = np.hypot(e[..., 0], e[..., 1])
        a, b = -np.roll(e, 1, axis=1), e                              # the two edges at each vertex
        cos = np.sum(a * b, axis=2) / (np.hypot(a[..., 0], a[..., 1]) * length)
        with np.errstate(invalid="ignore", divide="ignore"):
            ang = np.degrees(np.arccos(np.clip(cos, -1, 1)))
            aspect = length.max(axis=1) / length.min(axis=1)
        first, growth = {}, []
        for name in self.walls:
            vals = []
            for b_idx, side in self.marker_sides[name]:
                lay = self.blocks[b_idx].layers(side)                 # (K, M, 2)
                h = np.hypot(*np.diff(lay, axis=1).transpose(2, 0, 1))   # (K, M-1) cell heights
                # first cell height measured normal to the wall: |(p1 - p0) x t| with t the
                # local wall tangent (central difference, one-sided at the ends)
                tang = np.gradient(lay[:, 0, :], axis=0)
                tang /= np.hypot(tang[:, 0], tang[:, 1])[:, None]
                d = lay[:, 1, :] - lay[:, 0, :]
                vals.append(np.abs(d[:, 0] * tang[:, 1] - d[:, 1] * tang[:, 0]))
                if h.shape[1] > 1:
                    ratio = h[:, 1:] / h[:, :-1]
                    growth.append(np.max(np.maximum(ratio, 1 / ratio)))
            first[name] = float(np.mean(np.concatenate(vals)))
        return {"min_angle_deg": float(np.nanmin(ang)) if not np.isnan(ang).any() else 0.0,
                "max_aspect_ratio": float(np.max(aspect)),
                "n_inverted": int(self.n_inverted),
                "first_cell_height": first,
                "max_growth": float(max(growth)) if growth else None}

    # -- output --------------------------------------------------------------
    def write_su2(self, path):
        """SU2 ASCII mesh: quads are element type 9, boundary lines type 3."""
        out = ["NDIME= 2", f"NELEM= {len(self.cells)}"]
        out += [f"9 {a} {b} {c} {d} {k}" for k, (a, b, c, d) in enumerate(self.cells)]
        out.append(f"NPOIN= {len(self.coords)}")
        out += [f"{x:.16e} {y:.16e} {k}" for k, (x, y) in enumerate(self.coords)]
        out.append(f"NMARK= {len(self.markers)}")
        for name, lines in self.markers.items():
            out += [f"MARKER_TAG= {name}", f"MARKER_ELEMS= {len(lines)}"]
            out += [f"3 {a} {b}" for a, b in lines]
        with open(path, "w") as f:
            f.write("\n".join(out) + "\n")

    def write_markers(self, path):
        """JSON {marker: [node ids]} plus nodes, cells, level, first_cell_m (01_interfaces.md)."""
        d = {}
        for name, lines in self.markers.items():
            d[name] = sorted({int(k) for line in lines for k in line})
        d["nodes"] = len(self.coords)
        d["cells"] = len(self.cells)
        d["level"] = self.level
        d["first_cell_m"] = self.quality()["first_cell_height"]
        with open(path, "w") as f:
            json.dump(d, f, indent=1)
            f.write("\n")


def read_su2_counts(path):
    """Tiny reader for tests: {'nodes', 'cells', 'markers': {name: number of lines}}."""
    out = {"markers": {}}
    name = None
    with open(path) as f:
        for line in f:
            if line.startswith("NELEM="):
                out["cells"] = int(line.split("=")[1])
            elif line.startswith("NPOIN="):
                out["nodes"] = int(line.split("=")[1].split()[0])
            elif line.startswith("MARKER_TAG="):
                name = line.split("=")[1].strip()
            elif line.startswith("MARKER_ELEMS="):
                out["markers"][name] = int(line.split("=")[1])
    return out


# -- mesh identity -------------------------------------------------------------------------
# The bytes of mesh.su2 are not comparable between machines: the last digit of a coordinate
# (written with 16 decimals) can differ with the numpy build and platform. The fingerprint hashes
# what defines the mesh instead: coordinates rounded to 1 um (1 nm before 2026-11-08), cells and marker node ids.

def _read_su2(path):
    """(coords (N, 2) float by node id, cells (M, 6) int64 rows "type n0 n1 n2 n3 index",
    {marker: sorted unique node ids}) of a 2D quad SU2 mesh as written by Mesh.write_su2."""
    lines = Path(path).read_text().splitlines()
    cells, coords, markers, k = [], None, {}, 0
    while k < len(lines):
        key, _, value = lines[k].partition("=")
        key = key.strip()
        if key == "NELEM":
            cells = [list(map(int, row.split())) for row in lines[k + 1:k + 1 + int(value.split()[0])]]
            k += len(cells)
        elif key == "NPOIN":
            rows = [row.split() for row in lines[k + 1:k + 1 + int(value.split()[0])]]
            coords = np.zeros((len(rows), 2))
            for x, y, node in rows:
                coords[int(node)] = (float(x), float(y))
            k += len(rows)
        elif key == "MARKER_TAG":
            name = value.strip()
            n = int(lines[k + 1].partition("=")[2])
            ids = {int(i) for row in lines[k + 2:k + 2 + n] for i in row.split()[1:]}
            markers[name] = sorted(ids)
            k += 1 + n
        k += 1
    if coords is None:
        raise ValueError(f"{path}: no NPOIN section")
    return coords, np.array(cells, dtype="<i8").reshape(len(cells), -1), markers


def _fingerprint(mesh_su2_path, scale):
    coords, cells, markers = _read_su2(mesh_su2_path)
    digest = hashlib.sha256()
    digest.update(np.rint(coords * scale).astype("<i8").tobytes())
    digest.update(cells.tobytes())
    for name in sorted(markers):
        digest.update(name.encode() + b"\0" + np.array(markers[name], dtype="<i8").tobytes())
    return digest.hexdigest()


def mesh_fingerprint(mesh_su2_path):
    """sha256 hex of: node coordinates in micrometres (rounded integers, node order), the cell
    connectivity array, and the marker node-id lists (markers sorted by name); all as
    little-endian int64 bytes.

    Why 1 um and not 1 nm (measured 2026-11-08): on the fine airfoil2d mesh (84,152 cells) the
    Colab worker and the staging machine agreed on every mesh-quality figure to 16 significant
    digits, yet their 1 nm digests differed. libm-level noise (about 1e-14 m on coordinates up to
    31 m) puts a coordinate within noise of a rounding boundary with probability about 1e-5 per
    coordinate; over 1.7e5 coordinates that is about a coin toss per mesh. At 1 um it is about
    2e-3 per mesh, and 1 um is 3 percent of the smallest first-cell height this study meshes, so
    a real geometry change still changes the digest."""
    return _fingerprint(mesh_su2_path, 1e6)


def mesh_fingerprint_nm(mesh_su2_path):
    """The previous rule (coordinates rounded to 1 nm), kept so the worker can still accept job
    files staged before 2026-11-08 evening. Same digest layout as mesh_fingerprint."""
    return _fingerprint(mesh_su2_path, 1e9)


def mesh_bbox(mesh_su2_path):
    """[xmin, xmax, ymin, ymax] of the nodes in metres, rounded to 1e-9 (a debugging aid)."""
    coords = _read_su2(mesh_su2_path)[0]
    lo, hi = coords.min(axis=0), coords.max(axis=0)
    return [round(float(v), 9) for v in (lo[0], hi[0], lo[1], hi[1])]
