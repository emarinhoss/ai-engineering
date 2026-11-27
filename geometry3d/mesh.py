"""Triangle surfaces: lofting rings into a closed surface, the watertight check, area, volume and the STL file.

A surface is (V, T): V is an array of points (n, 3) and T an array of triangles (k, 3) holding row numbers of V.
Because triangles share point numbers, "every edge is shared by exactly two triangles" is a count on integers.
"""
import numpy as np


def loft(rings, start="fan", end="fan"):
    """Closed surface through a stack of rings. rings has shape (stations, points, 3); each ring is a closed
    outline (the last point joins the first). Neighbouring rings are joined by quads, each cut into two
    triangles. The two ends are closed by `start` and `end`:
    "fan": triangles from the ring's mean point (for a convex ring);
    "strip": triangles across the ring between point j and point m-1-j (for a section outline that runs
             along the upper surface and back along the lower one, so that no triangle leaves the section);
    a point (x, y, z): a cone to that point (a nose or tail point).
    The triangles are turned so that the normals point outward."""
    rings = np.asarray(rings, dtype=float)
    ns, m, _ = rings.shape
    V = [rings.reshape(-1, 3)]
    T = []
    for i in range(ns - 1):
        for j in range(m):
            a, b = i * m + j, i * m + (j + 1) % m
            c, d = (i + 1) * m + (j + 1) % m, (i + 1) * m + j
            T += [(a, b, c), (a, c, d)]
    n_points = ns * m
    for kind, base, flip in ((start, 0, True), (end, (ns - 1) * m, False)):
        tris = []
        if isinstance(kind, str) and kind == "strip":
            for j in range(m // 2):
                p, q, r, s = base + j, base + j + 1, base + m - 2 - j, base + m - 1 - j
                if q != r:
                    tris.append((p, q, r))
                tris.append((p, r, s))
        else:
            point = rings[base // m].mean(axis=0) if isinstance(kind, str) else np.asarray(kind, dtype=float)
            V.append(point[None, :])
            tris = [(n_points, base + j, base + (j + 1) % m) for j in range(m)]
            n_points += 1
        T += [(a, c, b) for a, b, c in tris] if flip else tris
    V, T = np.vstack(V), np.array(T, dtype=int)
    if volume(V, T) < 0.0:
        T = T[:, ::-1].copy()
    return V, T


def triangles(V, T):
    """The corner points of every triangle, shape (k, 3, 3)."""
    return V[T]


def areas(V, T):
    """Area of each triangle: half the length of the cross product of two edges."""
    P = V[T]
    return 0.5 * np.linalg.norm(np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]), axis=1)


def area(V, T):
    return float(areas(V, T).sum())


def volume(V, T):
    """Enclosed volume by the divergence theorem: the sum over the triangles of a . (b x c) / 6. Positive when
    the normals point outward."""
    P = V[T]
    return float(np.einsum("ij,ij->i", P[:, 0], np.cross(P[:, 1], P[:, 2])).sum() / 6.0)


def centroids(V, T):
    return V[T].mean(axis=1)


def watertight(V, T):
    """Gate 1. Each triangle gives three directed edges (a, b). The surface is closed and consistently turned
    when every directed edge occurs once and its reverse (b, a) occurs once, so that every edge is shared by
    exactly two triangles. Returns the counts; `ok` also needs outward normals (positive volume) and no
    triangle of zero area."""
    edges = np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
    seen = {}
    for a, b in edges:
        seen[(int(a), int(b))] = seen.get((int(a), int(b)), 0) + 1
    repeated = sum(1 for n in seen.values() if n != 1)
    unmatched = sum(1 for (a, b) in seen if (b, a) not in seen)
    zero = int((areas(V, T) <= 0.0).sum())
    vol = volume(V, T)
    return {"triangles": int(len(T)), "edges": len(seen) // 2, "edges_repeated": repeated,
            "edges_unmatched": unmatched, "zero_area_triangles": zero, "volume_ft3": vol,
            "ok": repeated == 0 and unmatched == 0 and zero == 0 and vol > 0.0}


def write_stl(path, parts):
    """ASCII STL written here (E5). parts: {name: (V, T)}; one `solid` per part. Coordinates are written with
    17 significant digits, so a file read back gives the same numbers."""
    with open(path, "w") as f:
        for name, (V, T) in parts.items():
            f.write(f"solid {name}\n")
            P = V[T]
            N = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
            N = N / np.linalg.norm(N, axis=1, keepdims=True)
            for tri, n in zip(P, N):
                f.write(f"facet normal {n[0]:.17g} {n[1]:.17g} {n[2]:.17g}\n outer loop\n")
                for p in tri:
                    f.write(f"  vertex {p[0]:.17g} {p[1]:.17g} {p[2]:.17g}\n")
                f.write(" endloop\nendfacet\n")
            f.write(f"endsolid {name}\n")


def read_stl(path):
    """{name: (V, T)} from an ASCII STL. Points are not merged: every triangle has its own three rows."""
    parts, name, pts = {}, None, []
    with open(path) as f:
        for line in f:
            w = line.split()
            if not w:
                continue
            if w[0] == "solid":
                name, pts = w[1], []
            elif w[0] == "vertex":
                pts.append([float(v) for v in w[1:4]])
            elif w[0] == "endsolid":
                V = np.array(pts)
                parts[name] = (V, np.arange(len(V)).reshape(-1, 3))
    return parts
