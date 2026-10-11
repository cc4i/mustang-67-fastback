"""Trace the running-horse emblem from a reference photo into a polygon (run inside Blender).

The chrome horse is thresholded (Otsu) against the dark grille, holes from reflections are
filled, it is thickened a little so the slender legs survive a 0.4 mm nozzle at 1:24, and the
outer boundary is traced and simplified. The result is saved as JSON (pixel units, y up,
horse running toward -x) so the model build does not depend on the photo.

usage (Blender): import pony_trace; pony_trace.main(photo, crop, out_json)
"""
import json

import bpy
import numpy as np


def load_luminance(path, crop):
    img = bpy.data.images.load(path, check_existing=True)
    w, h = img.size
    px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)[::-1]     # top-down rows
    x0, x1, y0, y1 = crop
    c = px[y0:y1, x0:x1, :3]
    return 0.2126 * c[..., 0] + 0.7152 * c[..., 1] + 0.0722 * c[..., 2]


def otsu(values):
    hist, edges = np.histogram(values, bins=128, range=(0, 1))
    mids = (edges[:-1] + edges[1:]) / 2
    cdf, wsum = np.cumsum(hist), np.cumsum(hist * mids)
    best, t = -1.0, 0.5
    for k in range(1, 127):
        w0, w1 = cdf[k], cdf[-1] - cdf[k]
        if w0 and w1:
            v = w0 * w1 * (wsum[k] / w0 - (wsum[-1] - wsum[k]) / w1) ** 2
            if v > best:
                best, t = v, mids[k]
    return t


def shift(m, dy, dx):
    out = np.zeros_like(m)
    h, w = m.shape
    out[max(dy, 0):h + min(dy, 0), max(dx, 0):w + min(dx, 0)] = m[max(-dy, 0):h + min(-dy, 0), max(-dx, 0):w + min(-dx, 0)]
    return out


def dilate(m, r):
    out = m.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy <= r * r:
                out |= shift(m, dy, dx)
    return out


def erode(m, r):
    return ~dilate(~m, r)


def components(m):
    """Label 4-connected components; returns (labels, sizes)."""
    labels = np.zeros(m.shape, dtype=np.int32)
    sizes = [0]
    h, w = m.shape
    for sy in range(h):
        for sx in range(w):
            if m[sy, sx] and not labels[sy, sx]:
                lab = len(sizes)
                stack = [(sy, sx)]
                labels[sy, sx] = lab
                n = 0
                while stack:
                    y, x = stack.pop()
                    n += 1
                    for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                        if 0 <= ny < h and 0 <= nx < w and m[ny, nx] and not labels[ny, nx]:
                            labels[ny, nx] = lab
                            stack.append((ny, nx))
                sizes.append(n)
    return labels, sizes


def fill_holes(m):
    """Background = everything reachable from the border; the rest is the solid shape."""
    bg_labels, _ = components(~m)
    border = set(np.unique(np.concatenate([bg_labels[0], bg_labels[-1], bg_labels[:, 0], bg_labels[:, -1]])))
    return ~np.isin(bg_labels, list(border - {0}))


def trace(m):
    """Moore-neighbour boundary trace of the single shape in m (pixel centres, ordered)."""
    h, w = m.shape
    ys, xs = np.nonzero(m)
    start = (ys.min(), xs[ys == ys.min()].min())
    nbrs = [(-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1)]
    path = [start]
    cur, back = start, 7          # came from the west
    for _ in range(4 * m.size):
        for k in range(8):
            d = (back + 1 + k) % 8
            ny, nx = cur[0] + nbrs[d][0], cur[1] + nbrs[d][1]
            if 0 <= ny < h and 0 <= nx < w and m[ny, nx]:
                back = (d + 4) % 8
                cur = (ny, nx)
                break
        if cur == start:
            break
        path.append(cur)
    return path


def rdp(points, eps):
    if len(points) < 3:
        return points
    a, b = np.array(points[0], float), np.array(points[-1], float)
    ab = b - a
    norm = np.hypot(*ab) or 1.0
    d = [abs(np.cross(ab, np.array(p, float) - a)) / norm for p in points[1:-1]]
    i = int(np.argmax(d)) + 1
    if d[i - 1] > eps:
        return rdp(points[:i + 1], eps)[:-1] + rdp(points[i:], eps)
    return [points[0], points[-1]]


def main(photo, crop, out_json, thicken=2, eps=0.7):
    lum = load_luminance(photo, crop)
    mask = lum > otsu(lum)
    labels, sizes = components(mask)
    horse = labels == int(np.argmax(sizes))
    horse = fill_holes(erode(dilate(horse, 1), 1))       # close hairline reflection gaps, fill holes
    horse = dilate(horse, thicken)                        # keep slender legs printable
    pts = trace(horse)
    # closed polyline -> simplify in two halves so the ends stay fixed
    mid = len(pts) // 2
    simple = rdp(pts[:mid + 1], eps)[:-1] + rdp(pts[mid:] + [pts[0]], eps)[:-1]
    h = horse.shape[0]
    poly = [(float(x), float(h - 1 - y)) for (y, x) in simple]          # y up
    with open(out_json, "w") as f:
        json.dump({"source": photo, "crop": crop, "points": poly}, f, indent=1)
    return {"points": len(poly), "mask_px": int(horse.sum()), "size": list(horse.shape)}
