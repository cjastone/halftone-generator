#!/usr/bin/env python3
"""
Halftone Pattern Generator v9
-----------------------------
Fading shape-grid (halftone) patterns with:
  * Linear / Radial / Curve / None fade modes
  * Draggable on-preview handles: curve points, band edges, radial centre,
    fade start/end, linear angle, flame direction, cell-size ruler
  * Flame effect: noisy, flame-like dropout that favours the small-cell side
  * Adjustable gap between cells (spacing independent of shape size)
  * Randomise / Mutate with per-parameter locks, plus Undo / Redo history
  * Per-section Randomise buttons (respect locks)
  * Saved pattern library with thumbnails (halftone_patterns.json in the
    folder the script is run from)
  * Descriptive default file names built from the current settings
  * Collapsible control sections (state remembered in halftone_ui.json)
  * Keyboard-adjustable sliders (arrows / + - / PgUp PgDn / Home End)
  * Live preview + PNG export at any resolution

Requirements:  pip install pillow
Shortcuts:     R = randomise all, M = mutate, H = show/hide handles,
               Ctrl+S = save pattern, Ctrl+Z = undo, Ctrl+Y = redo
Troubleshooting: set env var HALFTONE_DEBUG_WHEEL=1 to print wheel events.
"""

import colorsys
import json
import math
import os
import random
import shutil
import time
from bisect import bisect_right
from datetime import datetime
from pathlib import Path
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, colorchooser, filedialog, messagebox, simpledialog

from PIL import Image, ImageDraw, ImageTk

try:
    LANCZOS = Image.Resampling.LANCZOS
except AttributeError:  # older Pillow
    LANCZOS = Image.LANCZOS

APP_DIR = Path.cwd()                                         # folder the script is run from
LIBRARY_PATH = APP_DIR / "halftone_patterns.json"
UI_STATE_PATH = APP_DIR / "halftone_ui.json"
OLD_LIBRARY_PATH = Path.home() / ".halftone_patterns.json"   # pre-v9 location
DEBUG_WHEEL = bool(os.environ.get("HALFTONE_DEBUG_WHEEL"))

# Overlay colours
C_CURVE, C_BAND, C_CENTER = "#ff8c1a", "#ffb347", "#3ddc97"
C_ANGLE, C_FLAME, C_RULER = "#b48cff", "#ff5a5a", "#4fc3f7"
C_SELECT, C_SHADOW, C_FOCUS = "#00d8ff", "#1b1b1b", "#ff8c1a"

# Panel text colours (high contrast)
HINT_BG, HINT_FG, HINT_BORDER = "#fdfcf8", "#151515", "#8f8a7f"
TEXT_INFO = "#1f1f1f"

# name: (sides, start_angle_deg, tile_factor)   sides = 0 -> circle
SHAPES = {
    "Hexagon":  (6, -90.0, 2 / math.sqrt(3)),
    "Circle":   (0, 0.0, 1.0),
    "Square":   (4, 45.0, math.sqrt(2)),
    "Diamond":  (4, -90.0, 1.0),
    "Triangle": (3, -90.0, 1.2),
    "Octagon":  (8, 22.5, 1 / math.cos(math.pi / 8)),
    "Star":     (5, -90.0, 1.2),
}

GRIDS = ["Offset (hex)", "Square"]
FADE_MODES = ["Curve", "Linear", "Radial", "None"]

CURVE_PRESETS = {
    "Wave":        [[0.0, 0.85], [0.33, 0.52], [0.62, 0.45], [1.0, 0.02]],
    "Diagonal":    [[0.0, 1.0], [1.0, 0.0]],
    "Arch":        [[0.0, 0.9], [0.5, 0.25], [1.0, 0.9]],
    "Valley":      [[0.0, 0.2], [0.5, 0.8], [1.0, 0.2]],
    "Double wave": [[0.0, 0.6], [0.25, 0.35], [0.5, 0.6], [0.75, 0.35], [1.0, 0.6]],
    "Flat":        [[0.0, 0.5], [1.0, 0.5]],
}

DEFAULTS = dict(
    width=1800, height=1200,
    shape="Hexagon", grid="Offset (hex)",
    cell=48.0, gap=0.0, max_scale=0.93, min_scale=0.02, rotation=0.0, star_inner=0.45,
    fade_mode="Curve", fade_angle=30.0, fade_start=0.2, fade_end=1.0,
    gamma=0.8, center_x=0.0, center_y=0.0, invert=False,
    band_above=0.06, band_below=0.9, band_core=0.0,
    flame=0.45, flame_bias=2.0, flame_scale=5.0, flame_stretch=3.0,
    flame_clump=0.6, flame_taper=0.5, flame_auto=True, flame_angle=90.0,
    jitter=0.0, seed=1.0,
    fg="#46434f", bg="#fbf8ee", transparent=False, supersample="3",
)


# --------------------------------------------------------------------------
# Random generators used by "Randomise"
# --------------------------------------------------------------------------
def _u(a, b):
    return lambda r, p: r.uniform(a, b)


def _maybe_zero(prob_zero, a, b):
    return lambda r, p: 0.0 if r.random() < prob_zero else r.uniform(a, b)


RAND = {
    "shape":        lambda r, p: r.choices(list(SHAPES), weights=[5, 3, 2, 1, 1, 1, 1])[0],
    "grid":         lambda r, p: r.choices(GRIDS, weights=[3, 1])[0],
    "cell":         lambda r, p: math.exp(r.uniform(math.log(0.008), math.log(0.05))) * p["width"],
    "gap":          lambda r, p: 0.0 if r.random() < 0.6 else r.uniform(0, 0.3) * p["cell"],
    "max_scale":    _u(0.7, 1.05),
    "min_scale":    _maybe_zero(0.4, 0.0, 0.25),
    "rotation":     lambda r, p: 0.0 if r.random() < 0.6 else r.uniform(0, 360),
    "star_inner":   _u(0.3, 0.7),
    "fade_mode":    lambda r, p: r.choices(FADE_MODES, weights=[4, 4, 2, 0.5])[0],
    "gamma":        lambda r, p: math.exp(r.uniform(math.log(0.4), math.log(2.5))),
    "invert":       lambda r, p: r.random() < 0.3,
    "fade_angle":   _u(0, 360),
    "fade_start":   _u(0.0, 0.5),
    "fade_end":     _u(0.6, 1.0),
    "center_x":     _u(0.0, 1.0),
    "center_y":     _u(0.0, 1.0),
    "band_core":    _maybe_zero(0.6, 0.0, 0.12),
    "band_above":   _u(0.0, 0.5),
    "band_below":   _u(0.15, 1.0),
    "flame":        _maybe_zero(0.3, 0.1, 0.8),
    "flame_bias":   _u(0.5, 4.0),
    "flame_clump":  _u(0.0, 1.0),
    "flame_scale":  _u(2.0, 15.0),
    "flame_stretch": _u(1.0, 6.0),
    "flame_taper":  _u(0.0, 1.0),
    "flame_auto":   lambda r, p: r.random() < 0.8,
    "flame_angle":  _u(0, 360),
    "jitter":       _maybe_zero(0.6, 0.0, 0.2),
    "seed":         lambda r, p: r.randint(0, 999),
}


# --------------------------------------------------------------------------
# Small maths helpers
# --------------------------------------------------------------------------
def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def snap(v, step, on):
    return round(v / step) * step if on else v


def clip_line(px, py, vx, vy, w, h):
    """Clip the infinite line P + s*V to the rectangle [0,w]x[0,h]."""
    lo, hi = -1e18, 1e18
    for p0, v, lim in ((px, vx, w), (py, vy, h)):
        if abs(v) < 1e-12:
            if p0 < 0 or p0 > lim:
                return None
        else:
            a, b = (0 - p0) / v, (lim - p0) / v
            lo, hi = max(lo, min(a, b)), min(hi, max(a, b))
    if lo > hi:
        return None
    return (px + lo * vx, py + lo * vy, px + hi * vx, py + hi * vy)


# --------------------------------------------------------------------------
# Colour helpers
# --------------------------------------------------------------------------
def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb01_to_hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(c * 255))) for c in rgb)


def hls_of(hexcol):
    return colorsys.rgb_to_hls(*[c / 255 for c in hex_to_rgb(hexcol)])


def random_color(r, light, near_hue=None):
    if near_hue is None:
        h = r.random()
    else:
        h = (near_hue + r.choice([0.0, 0.0, 0.5]) + r.uniform(-0.06, 0.06)) % 1.0
    if light:
        l, s = r.uniform(0.88, 0.97), r.uniform(0.15, 0.7)
    else:
        l, s = r.uniform(0.14, 0.34), r.uniform(0.0, 0.45)
    return rgb01_to_hex(colorsys.hls_to_rgb(h, l, s))


def random_palette(r):
    dark = random_color(r, light=False)
    light = random_color(r, light=True, near_hue=hls_of(dark)[0])
    return (light, dark) if r.random() < 0.25 else (dark, light)  # (fg, bg)


def nudge_color(hexcol, r, strength):
    h, l, s = hls_of(hexcol)
    h = (h + r.gauss(0, 0.05 * strength)) % 1.0
    l = min(1.0, max(0.0, l + r.gauss(0, 0.05 * strength)))
    s = min(1.0, max(0.0, s + r.gauss(0, 0.10 * strength)))
    return rgb01_to_hex(colorsys.hls_to_rgb(h, l, s))


# --------------------------------------------------------------------------
# Curve helpers
# --------------------------------------------------------------------------
def random_curve(r):
    n = r.choice([2, 3, 3, 4, 4, 5])
    step = 1.0 / (n - 1)
    pts = []
    for i in range(n):
        x = i * step
        if 0 < i < n - 1:
            x += r.uniform(-0.3, 0.3) * step
        pts.append([x, r.uniform(0.05, 0.95)])
    return pts


def mutate_curve(pts, r, strength):
    pts = [list(q) for q in pts]
    n = len(pts)
    for i, q in enumerate(pts):
        q[1] = min(1.1, max(-0.1, q[1] + r.gauss(0, 0.12 * strength)))
        if 0 < i < n - 1:
            q[0] = min(0.99, max(0.01, q[0] + r.gauss(0, 0.05 * strength)))
    pts.sort()
    return pts


def make_curve_fn(pts):
    """Smooth cubic-Hermite spline through points, y = f(x). Linear extrapolation."""
    pts = sorted(pts)
    xs = [q[0] for q in pts]
    ys = [q[1] for q in pts]
    n = len(pts)
    if n == 1:
        return lambda x: ys[0]

    def slope(i, j):
        dx = xs[j] - xs[i]
        return (ys[j] - ys[i]) / dx if abs(dx) > 1e-9 else 0.0

    m = [slope(0, 1)] + [slope(i - 1, i + 1) for i in range(1, n - 1)] + [slope(n - 2, n - 1)]

    def f(x):
        if x <= xs[0]:
            return ys[0] + m[0] * (x - xs[0])
        if x >= xs[-1]:
            return ys[-1] + m[-1] * (x - xs[-1])
        i = min(bisect_right(xs, x) - 1, n - 2)
        h = xs[i + 1] - xs[i]
        if h <= 1e-9:
            return ys[i]
        t = (x - xs[i]) / h
        t2, t3 = t * t, t * t * t
        return ((2 * t3 - 3 * t2 + 1) * ys[i] + (t3 - 2 * t2 + t) * h * m[i] +
                (-2 * t3 + 3 * t2) * ys[i + 1] + (t3 - t2) * h * m[i + 1])
    return f


# --------------------------------------------------------------------------
# Noise helpers
# --------------------------------------------------------------------------
def hash01(ix, iy, seed):
    h = (ix * 374761393 + iy * 668265263 + seed * 2246822519) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    h ^= h >> 16
    return h / 4294967295.0


def value_noise(x, y, seed):
    x0, y0 = math.floor(x), math.floor(y)
    fx, fy = x - x0, y - y0
    sx = fx * fx * (3 - 2 * fx)
    sy = fy * fy * (3 - 2 * fy)
    a = hash01(x0, y0, seed)
    b = hash01(x0 + 1, y0, seed)
    c = hash01(x0, y0 + 1, seed)
    d = hash01(x0 + 1, y0 + 1, seed)
    return a + (b - a) * sx + (c - a) * sy + (a - b - c + d) * sx * sy


def fbm(x, y, seed):
    return (0.65 * value_noise(x, y, seed) +
            0.35 * value_noise(x * 2.03 + 17.1, y * 2.03 + 3.7, seed + 101))


def shape_points(cx, cy, r, sides, start_deg, star=False, inner=0.45):
    pts = []
    n = sides * 2 if star else sides
    for i in range(n):
        a = math.radians(start_deg) + math.pi * 2 * i / n
        rr = r * inner if (star and i % 2) else r
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return pts


# --------------------------------------------------------------------------
# Parameter normalisation
# --------------------------------------------------------------------------
def normalize_params(raw):
    """Fill missing keys with defaults and coerce types so render() is safe."""
    p = dict(DEFAULTS)
    p["curve_pts"] = [pt[:] for pt in CURVE_PRESETS["Wave"]]
    p.update({k: v for k, v in raw.items() if k in p})
    for k in ("width", "height"):
        try:
            p[k] = max(16, min(20000, int(float(p[k]))))
        except (ValueError, TypeError):
            p[k] = DEFAULTS[k]
    try:
        pts = [(float(a), float(b)) for a, b in p["curve_pts"]]
        p["curve_pts"] = pts if len(pts) >= 2 else [tuple(q) for q in CURVE_PRESETS["Wave"]]
    except (TypeError, ValueError):
        p["curve_pts"] = [tuple(q) for q in CURVE_PRESETS["Wave"]]
    if p["shape"] not in SHAPES:
        p["shape"] = DEFAULTS["shape"]
    if p["grid"] not in GRIDS:
        p["grid"] = DEFAULTS["grid"]
    if p["fade_mode"] not in FADE_MODES:
        p["fade_mode"] = DEFAULTS["fade_mode"]
    return p


# --------------------------------------------------------------------------
# Descriptive names
# --------------------------------------------------------------------------
def curve_label(pts):
    """Preset name if the curve matches one, otherwise 'customNpt'."""
    for name, preset in CURVE_PRESETS.items():
        if len(preset) == len(pts) and all(
                abs(a - c) < 1e-3 and abs(b - d) < 1e-3
                for (a, b), (c, d) in zip(preset, pts)):
            return name.lower().replace(" ", "")
    return f"custom{len(pts)}pt"


def describe(p):
    """Short, file-safe description of the key settings."""
    parts = [p["shape"].lower()]
    if p["grid"] == "Square":
        parts.append("sqgrid")
    mode = p["fade_mode"]
    if mode == "Curve":
        parts.append(f"curve-{curve_label(p['curve_pts'])}")
    elif mode == "Linear":
        parts.append(f"linear{p['fade_angle']:.0f}deg")
    elif mode == "Radial":
        parts.append(f"radial{p['center_x'] * 100:.0f}-{p['center_y'] * 100:.0f}")
    else:
        parts.append("nofade")
    if p["invert"]:
        parts.append("inv")
    if p["flame"] > 0:
        parts.append(f"flame{p['flame'] * 100:.0f}")
    parts.append(f"c{p['cell']:.0f}")
    if p["gap"] > 0:
        parts.append(f"g{p['gap']:.0f}")
    parts.append(f"s{int(p['seed'])}")
    return "_".join(parts)


def unique_path(folder, stem, ext):
    """folder/stem.ext, or stem-2.ext, stem-3.ext... if it already exists."""
    path = folder / f"{stem}{ext}"
    n = 2
    while path.exists():
        path = folder / f"{stem}-{n}{ext}"
        n += 1
    return path


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------
def render(p, out_w, out_h, ss=2, transparent=False):
    ss = max(1, int(ss))
    W, H = out_w * ss, out_h * ss
    k = W / p["width"]

    fg, bg = hex_to_rgb(p["fg"]), hex_to_rgb(p["bg"])
    if transparent:
        img = Image.new("RGBA", (W, H), fg + (0,))
        fill = fg + (255,)
    else:
        img = Image.new("RGB", (W, H), bg)
        fill = fg
    draw = ImageDraw.Draw(img)

    size = max(1.0, p["cell"] * k)                  # shape size
    pitch = size + max(0.0, p["gap"]) * k           # centre-to-centre spacing
    offset = p["grid"].startswith("Offset")
    dx = pitch
    dy = pitch * math.sqrt(3) / 2 if offset else pitch

    sides, start, factor = SHAPES[p["shape"]]
    start += p["rotation"]
    is_star = p["shape"] == "Star"
    base_r = size / 2 * factor
    seed = int(p["seed"])

    corners = ((0, 0), (W, 0), (0, H), (W, H))
    mode = p["fade_mode"]
    rcx, rcy = p["center_x"] * W, p["center_y"] * H
    rmax = max(math.hypot(x - rcx, y - rcy) for x, y in corners) or 1.0

    if mode == "Linear":
        a = math.radians(p["fade_angle"])
        ux, uy = math.cos(a), math.sin(a)
        projs = [x * ux + y * uy for x, y in corners]
        pmin, span = min(projs), (max(projs) - min(projs)) or 1.0

        def t_at(x, y):
            return (x * ux + y * uy - pmin) / span

    elif mode == "Radial":
        def t_at(x, y):
            return math.hypot(x - rcx, y - rcy) / rmax

    elif mode == "Curve":
        f = make_curve_fn(p["curve_pts"])
        above, below, core = p["band_above"], p["band_below"], p["band_core"]
        eps = 1e-3

        def t_at(x, y):
            xn = x / W
            cy = f(xn) * H
            sl = (f(xn + eps) - f(xn - eps)) / (2 * eps) * H / W
            d = (y - cy) / math.sqrt(1 + sl * sl) / H
            w = below if d >= 0 else above
            d = max(0.0, abs(d) - core)
            if w <= 1e-6:
                return 0.0 if d <= 0 else 1.0
            return d / w
    else:
        def t_at(x, y):
            return 0.0

    if p["flame_auto"] and mode == "Radial":
        def fcoords(x, y):
            along = math.hypot(x - rcx, y - rcy)
            across = math.atan2(y - rcy, x - rcx) * rmax / math.pi
            return along, across
    else:
        if p["flame_auto"] and mode == "Linear":
            ang = p["fade_angle"]
        elif p["flame_auto"] and mode == "Curve":
            ang = 90.0
        else:
            ang = p["flame_angle"]
        fa = math.radians(ang)
        fux, fuy = math.cos(fa), math.sin(fa)

        def fcoords(x, y):
            return x * fux + y * fuy, -x * fuy + y * fux

    fs, fe = p["fade_start"], p["fade_end"]
    if abs(fe - fs) < 1e-6:
        fe = fs + 1e-6
    gamma = max(0.01, p["gamma"])
    smax, smin = p["max_scale"], p["min_scale"]
    jitter = p["jitter"]
    flame, bias = p["flame"], p["flame_bias"]
    clump, taper = p["flame_clump"], p["flame_taper"]
    ns = max(0.5, p["flame_scale"]) * pitch
    stretch = max(0.1, p["flame_stretch"])
    min_r = 0.3 * ss

    rows = int(H / dy) + 3
    cols = int(W / dx) + 3
    for r in range(-1, rows):
        y = r * dy
        xoff = dx / 2 if (offset and r % 2) else 0.0
        for c in range(-1, cols):
            x = c * dx + xoff

            t = t_at(x, y)
            v = t if mode == "Curve" else (t - fs) / (fe - fs)
            v = min(1.0, max(0.0, v)) ** gamma
            if p["invert"]:
                v = 1.0 - v
            s = smax + (smin - smax) * v

            if flame > 0:
                small = v if smin <= smax else 1.0 - v
                pd = flame * (small ** bias if bias > 0 else 1.0)
                if pd > 0:
                    rnd = hash01(c, r, seed + 7777)
                    if clump > 0:
                        along, across = fcoords(x, y)
                        n = fbm(across / ns, along / (ns * stretch), seed + 31)
                        n = min(1.0, max(0.0, (n - 0.5) * 2.4 + 0.5))
                        rnd = rnd * (1 - clump) + n * clump
                    if rnd < pd:
                        continue
                    if taper > 0:
                        kk = (rnd - pd) / (taper * pd)
                        if kk < 1:
                            s *= kk * kk * (3 - 2 * kk)

            if jitter:
                s *= 1 + (hash01(c, r, seed) * 2 - 1) * jitter

            R = base_r * s
            if R < min_r:
                continue
            if sides == 0:
                draw.ellipse((x - R, y - R, x + R, y + R), fill=fill)
            else:
                draw.polygon(shape_points(x, y, R, sides, start, is_star,
                                          p["star_inner"]), fill=fill)

    if ss > 1:
        img = img.resize((out_w, out_h), LANCZOS)
    return img


def checkerboard(w, h, tile=10):
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    for yy in range(0, h, tile):
        for xx in range((yy // tile) % 2 * tile, w, tile * 2):
            d.rectangle((xx, yy, xx + tile - 1, yy + tile - 1), fill=(210, 210, 210))
    return img


def render_display(p, w, h, ss):
    img = render(p, w, h, ss=ss, transparent=p["transparent"])
    if p["transparent"]:
        base = checkerboard(w, h, tile=max(4, min(10, w // 16)))
        base.paste(img, (0, 0), img)
        img = base
    return img


# --------------------------------------------------------------------------
# Small JSON file helpers
# --------------------------------------------------------------------------
def read_library(path):
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    pats = data.get("patterns", []) if isinstance(data, dict) else data
    if not isinstance(pats, list):
        raise ValueError("Unexpected library format")
    return [q for q in pats if isinstance(q, dict) and "name" in q
            and isinstance(q.get("params"), dict)]


def write_json_atomic(path, obj):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def write_library(path, patterns):
    write_json_atomic(path, {"version": 1, "patterns": patterns})


def read_ui_state():
    try:
        data = json.loads(UI_STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


# --------------------------------------------------------------------------
# Tooltip
# --------------------------------------------------------------------------
class Tooltip:
    """Small hover tooltip for any widget."""

    def __init__(self, widget, text, delay=500):
        self.w, self.text, self.delay = widget, text, delay
        self.tip = self.job = None
        widget.bind("<Enter>", self.schedule, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")

    def schedule(self, _e=None):
        self.cancel()
        self.job = self.w.after(self.delay, self.show)

    def cancel(self):
        if self.job:
            self.w.after_cancel(self.job)
            self.job = None

    def show(self):
        self.job = None
        if self.tip or not self.w.winfo_viewable():
            return
        x = self.w.winfo_rootx() + 10
        y = self.w.winfo_rooty() + self.w.winfo_height() + 4
        self.tip = tw = tk.Toplevel(self.w)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(tw, text=self.text, bg="#ffffe0", fg="#111", relief="solid", bd=1,
                 padx=6, pady=3, justify="left").pack()

    def hide(self, _e=None):
        self.cancel()
        if self.tip:
            self.tip.destroy()
            self.tip = None


# --------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------
class App:
    HANDLE_R = 7
    MAX_HISTORY = 200
    THUMB_W, THUMB_H = 290, 150
    WHEEL_PX = 60
    EDIT_COALESCE_S = 1.0      # key presses within this window = one undo step
    STATUS_KEEP = ("Saved", "Loaded", "Updated", "Deleted", "Imported",
                   "Exported", "Reset", "Randomised", "Copied")

    def __init__(self, root):
        self.root = root
        root.title("Halftone Pattern Generator")
        root.geometry("1460x940")
        self.vars, self.locks, self.meta, self.scales = {}, {}, {}, {}
        self.sections = []
        self._sec = None
        self.undo_stack, self.redo_stack = [], []
        self.rng = random.Random()
        self._job = None
        self._fast = False
        self.tkimg = None
        self.thumb_img = None
        self.geom = None
        self.curve_pts = [pt[:] for pt in CURVE_PRESETS["Wave"]]
        self.mut_strength = tk.DoubleVar(value=0.3)
        self.show_handles = tk.BooleanVar(value=True)
        self.hist_text = tk.StringVar(value="")
        self.status = tk.StringVar(value="")
        self.thumb_text = tk.StringVar(value="")
        self.patterns = []
        self.ui_state = read_ui_state()
        self._collapsed_init = set(self.ui_state.get("collapsed", []))
        self._panel_w = 0
        self._wheel_acc = 0.0
        # interaction state
        self.handles = []
        self.hover_id = self.drag_id = self.sel_id = None
        self._grab = (0, 0)
        self._press_snap = None
        self._edit_key, self._edit_t = None, 0.0
        self._last_click = 0.0

        self.setup_styles()

        # ---- left panel: scrollable controls ----
        self.panel = panel = ttk.Frame(root)
        panel.pack(side="left", fill="y")

        holder = ttk.Frame(panel)
        holder.pack(fill="both", expand=True)
        cv = tk.Canvas(holder, width=360, highlightthickness=0, bd=0,
                       yscrollincrement=1, bg=self.base_bg)
        self.panel_canvas = cv
        sb = ttk.Scrollbar(holder, orient="vertical", command=cv.yview)
        self.ctrl = ttk.Frame(cv, padding=(8, 6, 8, 10))
        self._win = cv.create_window((0, 0), window=self.ctrl, anchor="nw")
        cv.configure(yscrollcommand=sb.set)
        cv.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.ctrl.bind("<Configure>", self.on_ctrl_configure)
        cv.bind("<Configure>", lambda e: cv.itemconfigure(self._win, width=e.width))

        # ---- preview ----
        self.preview = pv = tk.Canvas(root, bg="#2b2b2b", highlightthickness=0)
        pv.pack(side="left", fill="both", expand=True)
        pv.bind("<Configure>", lambda e: self.schedule())
        pv.bind("<ButtonPress-1>", self.on_press)
        pv.bind("<B1-Motion>", self.on_drag)
        pv.bind("<ButtonRelease-1>", self.on_release)
        pv.bind("<Double-Button-1>", self.on_double)
        pv.bind("<Button-3>", self.on_right)
        pv.bind("<Button-2>", self.on_right)
        pv.bind("<Motion>", self.on_motion)
        pv.bind("<Leave>", self.on_leave)
        for seq, d in (("<Left>", (-1, 0)), ("<Right>", (1, 0)),
                       ("<Up>", (0, -1)), ("<Down>", (0, 1))):
            pv.bind(seq, lambda e, d=d: self.nudge_selected(d[0], d[1], e))
        pv.bind("<Escape>", lambda e: self.deselect())
        pv.bind("<Delete>", lambda e: self.delete_selected_point())
        pv.bind("<BackSpace>", lambda e: self.delete_selected_point())

        self.build_controls()
        self.sync_section_locks()
        self.install_wheel()
        self.root.bind_all("<ButtonPress>", self._note_click, add="+")
        self.root.bind_all("<FocusIn>", self.on_focus_in, add="+")
        self.bind_shortcuts()
        self.update_history_label()
        self.load_library()
        self.schedule()

    # ======================================================================
    # Styles
    # ======================================================================
    def setup_styles(self):
        st = ttk.Style()
        self.base_bg = st.lookup("TFrame", "background") or "#dcdad5"
        hdr = "#c8c4bb"
        bold = tkfont.nametofont("TkDefaultFont").copy()
        bold.configure(weight="bold")
        self.head_font = bold
        small = tkfont.nametofont("TkDefaultFont").copy()
        small.configure(size=max(8, abs(small.cget("size")) - 1))
        self.small_font = small
        st.configure("Sec.TFrame", background="#aaa69d")
        st.configure("SecHead.TFrame", background=hdr)
        st.configure("SecHead.TLabel", background=hdr, foreground="#111", font=bold)
        st.configure("SecHead.TCheckbutton", background=hdr, foreground="#111")
        st.map("SecHead.TCheckbutton", background=[("active", hdr)])
        st.configure("SecHead.TButton", padding=(6, 0))
        # instructions / info text
        st.configure("HintBorder.TFrame", background=HINT_BORDER)
        st.configure("HintBox.TFrame", background=HINT_BG)
        st.configure("Hint.TLabel", background=HINT_BG, foreground=HINT_FG)
        st.configure("HintTitle.TLabel", background=HINT_BG, foreground=HINT_FG, font=bold)
        st.configure("Info.TLabel", foreground=TEXT_INFO)
        st.configure("Sub.TLabel", foreground=TEXT_INFO, font=bold)
        st.configure("Path.TLabel", foreground="#333333", font=small)

    # ======================================================================
    # Panel layout / sizing / visibility
    # ======================================================================
    def on_ctrl_configure(self, e):
        cv = self.panel_canvas
        req = self.ctrl.winfo_reqwidth()
        if req > self._panel_w:
            self._panel_w = req
            cv.configure(width=req)
        cv.configure(scrollregion=(0, 0, max(1, cv.winfo_width()), e.height))
        if e.height <= cv.winfo_height():
            cv.yview_moveto(0)

    def content_fits(self):
        first, last = self.panel_canvas.yview()
        return first <= 0.0 and last >= 1.0

    def ensure_visible(self, w, pad_top=30, pad_bottom=8):
        """Scroll the panel so widget w is fully visible (used for Tab focus)."""
        self.root.update_idletasks()
        cv = self.panel_canvas
        total, vh = self.ctrl.winfo_height(), cv.winfo_height()
        if total <= vh:
            return
        top = w.winfo_rooty() - self.ctrl.winfo_rooty() - pad_top
        bottom = top + pad_top + w.winfo_height() + pad_bottom
        vt = cv.canvasy(0)
        if top < vt:
            target = top
        elif bottom > vt + vh:
            target = bottom - vh
        else:
            return
        cv.yview_moveto(max(0, target) / total)

    def _note_click(self, _e):
        self._last_click = time.monotonic()

    def on_focus_in(self, e):
        w = e.widget
        if not isinstance(w, tk.Misc) or time.monotonic() - self._last_click < 0.3:
            return   # mouse-initiated focus: don't jump the panel around
        if self._inside(str(w), self.ctrl) and str(w) != str(self.ctrl):
            self.ensure_visible(w)

    # ======================================================================
    # Mouse wheel: decided by POINTER POSITION, never changes widget values
    # ======================================================================
    def install_wheel(self):
        tag = "WheelGuard"
        ws = self.root.tk.call("tk", "windowingsystem")
        self._aqua_legacy = (ws == "aqua" and tk.TkVersion < 8.7)
        seqs = ["<MouseWheel>", "<Shift-MouseWheel>"]
        if ws == "x11":
            seqs += ["<Button-4>", "<Button-5>", "<Shift-Button-4>", "<Shift-Button-5>"]
        for seq in seqs:
            self.root.bind_class(tag, seq, self.on_wheel)
            self.root.bind_all(seq, self.on_wheel)

        def tag_tree(w):
            tags = w.bindtags()
            if tag not in tags:
                w.bindtags((tag,) + tags)
            for child in w.winfo_children():
                tag_tree(child)
        tag_tree(self.root)

    @staticmethod
    def _inside(path, widget):
        a = str(widget)
        return path == a or path.startswith(a + ".")

    def wheel_pixels(self, e):
        if e.num == 4:
            return -self.WHEEL_PX
        if e.num == 5:
            return self.WHEEL_PX
        d = getattr(e, "delta", 0) or 0
        if not d:
            return 0
        if self._aqua_legacy:
            return -d * 18
        return -d / 120.0 * self.WHEEL_PX

    def on_wheel(self, e):
        try:
            path = str(self.root.tk.call("winfo", "containing", "-displayof", ".",
                                         e.x_root, e.y_root))
        except tk.TclError:
            path = ""
        if DEBUG_WHEEL:
            print(f"wheel: widget={e.widget} delta={getattr(e, 'delta', None)} "
                  f"num={e.num} pointer_over={path!r}")
        if not path or ".popdown" in path:
            return None
        if self._inside(path, self.panel):
            px = self.wheel_pixels(e)
            if self._inside(path, self.lib_list):
                first, last = self.lib_list.yview()
                if not (first <= 0.0 and last >= 1.0):
                    steps = max(1, round(abs(px) / 30)) * (1 if px > 0 else -1)
                    self.lib_list.yview_scroll(steps, "units")
                    return "break"
            if not self.content_fits():
                self._wheel_acc += px
                n = int(self._wheel_acc)
                self._wheel_acc -= n
                if n:
                    self.panel_canvas.yview_scroll(n, "units")
            return "break"
        if self._inside(path, self.preview):
            return "break"
        return None

    # ======================================================================
    # Collapsible sections
    # ======================================================================
    def section(self, title, lockable=True):
        outer = ttk.Frame(self.ctrl, style="Sec.TFrame", padding=1)
        outer.pack(fill="x", pady=3)
        head = ttk.Frame(outer, style="SecHead.TFrame", padding=(6, 4))
        head.pack(fill="x")
        arrow = ttk.Label(head, text="▾", style="SecHead.TLabel", width=2)
        arrow.pack(side="left")
        label = ttk.Label(head, text=title, style="SecHead.TLabel")
        label.pack(side="left")
        body = ttk.Frame(outer, padding=(8, 4, 8, 8))
        body.pack(fill="x")

        sec = {"title": title, "keys": [], "lock": None, "rand": None, "outer": outer,
               "body": body, "arrow": arrow, "label": label, "collapsed": False}
        if lockable:
            var = tk.BooleanVar(value=False)
            sec["lock"] = var
            ttk.Checkbutton(head, text="lock section", variable=var, takefocus=False,
                            style="SecHead.TCheckbutton",
                            command=lambda s=sec: self.lock_keys(s["keys"], s["lock"].get())
                            ).pack(side="right")
            btn = ttk.Button(head, text="Randomise", takefocus=False,
                             style="SecHead.TButton",
                             command=lambda s=sec: self.randomise_section(s))
            btn.pack(side="right", padx=(0, 6))
            Tooltip(btn, f"Randomise the '{title}' section only.\n"
                         f"Locked values are not changed.")
            sec["rand"] = btn
        for w in (head, arrow, label):
            w.configure(cursor="hand2")
            w.bind("<Button-1>", lambda e, s=sec: self.toggle_section(
                s, solo=bool(e.state & 0x0001)))
        self.sections.append(sec)
        self._sec = sec if lockable else None
        if title in self._collapsed_init:
            self.set_collapsed(sec, True)
        return body

    def set_collapsed(self, sec, collapsed):
        if sec["collapsed"] == collapsed:
            return
        sec["collapsed"] = collapsed
        if collapsed:
            sec["body"].pack_forget()
            sec["arrow"].configure(text="▸")
        else:
            sec["body"].pack(fill="x")
            sec["arrow"].configure(text="▾")

    def toggle_section(self, sec, solo=False):
        if solo:
            for s in self.sections:
                self.set_collapsed(s, s is not sec)
        else:
            self.set_collapsed(sec, not sec["collapsed"])
        self.save_ui_state()
        if not sec["collapsed"]:
            self.root.after_idle(lambda: self.scroll_into_view(sec))
        return "break"

    def scroll_into_view(self, sec):
        self.root.update_idletasks()
        cv = self.panel_canvas
        total, vh = self.ctrl.winfo_height(), cv.winfo_height()
        if total <= vh:
            return
        top = sec["outer"].winfo_y()
        bottom = top + sec["outer"].winfo_height()
        vt = cv.canvasy(0)
        if bottom > vt + vh:
            target = min(top, bottom - vh)
        elif top < vt:
            target = top
        else:
            return
        cv.yview_moveto(max(0, target) / total)

    def save_ui_state(self):
        self.ui_state["collapsed"] = [s["title"] for s in self.sections if s["collapsed"]]
        try:
            write_json_atomic(UI_STATE_PATH, self.ui_state)
        except OSError:
            pass

    # ======================================================================
    # Widget helpers
    # ======================================================================
    def add_lock(self, row, key):
        lv = tk.BooleanVar(value=False)
        self.locks[key] = lv
        ttk.Checkbutton(row, text="lock", variable=lv, takefocus=False,
                        command=self.sync_section_locks).pack(side="right")
        if self._sec:
            self._sec["keys"].append(key)

    @staticmethod
    def quantize(value, lo, hi, res):
        value = round(round(value / res) * res, 6)
        return min(hi, max(lo, value))

    def make_scale(self, parent, var, lo, hi, res, key=None):
        sc = tk.Scale(parent, from_=lo, to=hi, resolution=res, orient="horizontal",
                      variable=var, length=200, takefocus=1,
                      highlightthickness=2, highlightbackground=self.base_bg,
                      highlightcolor=C_FOCUS,
                      command=(lambda _e: self.schedule()) if key else None)
        sc.pack(fill="x")
        self.bind_scale_keys(sc, var, lo, hi, res, key)
        return sc

    def bind_scale_keys(self, sc, var, lo, hi, res, key):
        arrows = ("Left", "Right", "Up", "Down")

        def step(n):
            def h(e):
                big = 10 if (e.state & 0x0001 and e.keysym in arrows) else 1
                self.step_scale(var, lo, hi, res, key, n * big)
                return "break"   # override Tk's default (Up = decrease) bindings
            return h

        def jump(value):
            def h(_e):
                self.step_scale(var, lo, hi, res, key, 0, absolute=value)
                return "break"
            return h

        for s in ("<Right>", "<Up>", "<plus>", "<equal>", "<KP_Add>"):
            sc.bind(s, step(1))
        for s in ("<Left>", "<Down>", "<minus>", "<underscore>", "<KP_Subtract>"):
            sc.bind(s, step(-1))
        sc.bind("<Prior>", step(10))
        sc.bind("<Next>", step(-10))
        sc.bind("<Home>", jump(lo))
        sc.bind("<End>", jump(hi))
        sc.bind("<ButtonPress-1>", lambda e: self.scale_press(sc), add="+")
        sc.bind("<ButtonRelease-1>", lambda e: self.scale_release(), add="+")

    def step_scale(self, var, lo, hi, res, key, n, absolute=None):
        if key:
            self.begin_edit("slider:" + key)
        try:
            cur = float(var.get())
        except (tk.TclError, ValueError):
            cur = lo
        new = absolute if absolute is not None else cur + n * res
        var.set(self.quantize(new, lo, hi, res))
        if key:
            self.schedule()

    def scale_press(self, sc):
        sc.focus_set()
        self._press_snap = self.snapshot()

    def scale_release(self):
        if self._press_snap is not None and self.snapshot() != self._press_snap:
            self.push_history(self._press_snap)
        self._press_snap = None
        self._edit_key = None

    def slider(self, parent, key, label, lo, hi, res, lock=True):
        var = tk.DoubleVar(value=DEFAULTS[key])
        self.vars[key] = var
        self.meta[key] = ("num", lo, hi, res)
        row = ttk.Frame(parent)
        row.pack(fill="x")
        ttk.Label(row, text=label).pack(side="left")
        if lock:
            self.add_lock(row, key)
        self.scales[key] = self.make_scale(parent, var, lo, hi, res, key)

    def combo(self, parent, key, label, values, lock=True):
        var = tk.StringVar(value=DEFAULTS[key])
        self.vars[key] = var
        self.meta[key] = ("choice", values)
        row = ttk.Frame(parent)
        row.pack(fill="x")
        ttk.Label(row, text=label).pack(side="left")
        if lock:
            self.add_lock(row, key)
        cb = ttk.Combobox(parent, textvariable=var, values=values, state="readonly")
        cb.pack(fill="x", pady=(0, 4))
        cb.bind("<<ComboboxSelected>>", lambda e: self.schedule())

    def check(self, parent, key, label, lock=True):
        var = tk.BooleanVar(value=DEFAULTS[key])
        self.vars[key] = var
        self.meta[key] = ("bool",)
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Checkbutton(row, text=label, variable=var,
                        command=self.schedule).pack(side="left")
        if lock:
            self.add_lock(row, key)

    def color(self, parent, key, label, lock=True):
        var = tk.StringVar(value=DEFAULTS[key])
        self.vars[key] = var
        self.meta[key] = ("color",)
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        sw = tk.Label(row, width=4, bg=var.get(), relief="solid", bd=1)
        sw.pack(side="left")

        def pick():
            c = colorchooser.askcolor(var.get(), title=label)[1]
            if c:
                self.push_history()
                var.set(c)
                self.schedule()

        ttk.Button(row, text=label, command=pick).pack(side="left", padx=6)
        if lock:
            self.add_lock(row, key)
        var.trace_add("write", lambda *a: sw.configure(bg=var.get()))

    @staticmethod
    def button_row(parent, items, pady=2):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=pady)
        for i, (text, cmd) in enumerate(items):
            ttk.Button(row, text=text, command=cmd).pack(
                side="left", fill="x", expand=True, padx=(0 if i == 0 else 3, 0))
        return row

    def hint(self, parent, lines, title=None):
        """High-contrast instruction box: optional bold title + bulleted lines."""
        border = ttk.Frame(parent, style="HintBorder.TFrame", padding=1)
        border.pack(fill="x", pady=(2, 6))
        box = ttk.Frame(border, style="HintBox.TFrame", padding=(8, 6))
        box.pack(fill="x")
        box.columnconfigure(1, weight=1)
        r = 0
        if title:
            ttk.Label(box, text=title, style="HintTitle.TLabel").grid(
                row=0, column=0, columnspan=2, sticky="w", pady=(0, 3))
            r = 1
        for i, line in enumerate(lines):
            ttk.Label(box, text="•", style="Hint.TLabel").grid(
                row=r + i, column=0, sticky="nw", padx=(0, 6), pady=1)
            ttk.Label(box, text=line, style="Hint.TLabel", wraplength=270,
                      justify="left").grid(row=r + i, column=1, sticky="w", pady=1)

    # ======================================================================
    # Controls
    # ======================================================================
    def build_controls(self):
        # ----- How to use -----
        s = self.section("How to use", lockable=False)
        self.hint(s, title="Panel", lines=[
            "Click a section header to fold or unfold it.",
            "Shift+click a header to open that section and fold all others.",
            "Tick 'lock' next to a setting to protect it from randomising.",
            "'Randomise' in a header changes only that section. "
            "Locked settings are never changed.",
        ])
        self.hint(s, title="Sliders", lines=[
            "Click a slider, then press ← → or + − to adjust it.",
            "Hold Shift, or use Page Up / Page Down, for steps of 10.",
            "Home / End jump to the minimum / maximum.",
            "The mouse wheel only scrolls the panel.",
        ])
        self.hint(s, title="Keyboard shortcuts", lines=[
            "R  –  randomise all unlocked settings",
            "M  –  mutate (small random changes)",
            "H  –  show / hide preview handles",
            "Ctrl+S  –  save pattern",
            "Ctrl+Z / Ctrl+Y  –  undo / redo",
        ])

        # ----- Explore -----
        s = self.section("Explore", lockable=False)
        row = ttk.Frame(s)
        row.pack(fill="x", pady=2)
        ttk.Button(row, text="Randomise all  (R)", command=self.randomise
                   ).pack(side="left", fill="x", expand=True, ipady=4)
        ttk.Button(row, text="Mutate  (M)", command=self.mutate
                   ).pack(side="left", fill="x", expand=True, ipady=4, padx=(4, 0))
        ttk.Label(s, text="Mutate strength (low = subtle tweaks)").pack(anchor="w")
        self.make_scale(s, self.mut_strength, 0.05, 1.0, 0.05)
        self.button_row(s, [("◀ Undo", self.undo), ("Redo ▶", self.redo)])
        self.button_row(s, [("Lock all", lambda: self.lock_keys(self.locks, True)),
                            ("Unlock all", lambda: self.lock_keys(self.locks, False))])
        ttk.Label(s, textvariable=self.hist_text, style="Info.TLabel").pack(anchor="w")

        # ----- Preview handles -----
        s = self.section("Preview handles", lockable=False)
        ttk.Checkbutton(s, text="Show handles on preview  (H)", variable=self.show_handles,
                        command=self.on_toggle_handles).pack(anchor="w", pady=(0, 4))
        for sym, col, text in (
                ("●", C_CURVE, "Curve point (Curve mode)"),
                ("◆", C_BAND, "Fade start / end, band distance"),
                ("■", C_CENTER, "Radial centre"),
                ("●", C_ANGLE, "Linear fade angle knob"),
                ("●", C_FLAME, "Flame direction (Auto direction off)"),
                ("■", C_RULER, "Cell size ruler (bottom-left)")):
            row = ttk.Frame(s)
            row.pack(fill="x", pady=1)
            tk.Label(row, text=sym, fg=col, bg="#2b2b2b", width=2).pack(side="left")
            ttk.Label(row, text=text).pack(side="left", padx=6)
        self.hint(s, lines=[
            "Drag a handle to adjust it. Hold Shift to snap.",
            "Double-click a handle to reset it to its default.",
            "Click a handle, then use the arrow keys to nudge it (Shift = ×10).",
            "Esc deselects. Delete removes the selected curve point.",
        ])

        # ----- Saved patterns -----
        s = self.section("Saved patterns", lockable=False)
        ttk.Button(s, text="💾 Save current pattern…  (Ctrl+S)",
                   command=self.save_pattern).pack(fill="x", ipady=3, pady=(0, 4))
        lf = ttk.Frame(s)
        lf.pack(fill="x")
        self.lib_list = tk.Listbox(lf, height=7, exportselection=False,
                                   activestyle="dotbox")
        lsb = ttk.Scrollbar(lf, orient="vertical", command=self.lib_list.yview)
        self.lib_list.configure(yscrollcommand=lsb.set)
        self.lib_list.pack(side="left", fill="x", expand=True)
        lsb.pack(side="left", fill="y")
        self.lib_list.bind("<<ListboxSelect>>", lambda e: self.update_thumbnail())
        self.lib_list.bind("<Double-Button-1>", lambda e: self.load_selected())
        self.lib_list.bind("<Return>", lambda e: self.load_selected())

        self.thumb = tk.Canvas(s, width=self.THUMB_W, height=self.THUMB_H,
                               bg="#2b2b2b", highlightthickness=0)
        self.thumb.pack(pady=(6, 2))
        ttk.Label(s, textvariable=self.thumb_text, style="Info.TLabel",
                  wraplength=300).pack(anchor="w")
        self.button_row(s, [("Load", self.load_selected),
                            ("Update", self.update_selected),
                            ("Rename", self.rename_selected),
                            ("Delete", self.delete_selected)])
        self.button_row(s, [("Import…", self.import_library),
                            ("Export…", self.export_library)])
        ttk.Label(s, text=f"Library file: {LIBRARY_PATH}", style="Path.TLabel",
                  wraplength=300).pack(anchor="w", pady=(2, 0))

        # ----- Size -----
        s = self.section("Image size (export, px)", lockable=False)
        row = ttk.Frame(s)
        row.pack(fill="x")
        for key, lbl in (("width", "W"), ("height", "H")):
            var = tk.StringVar(value=str(DEFAULTS[key]))
            self.vars[key] = var
            ttk.Label(row, text=lbl).pack(side="left")
            e = ttk.Entry(row, textvariable=var, width=7)
            e.pack(side="left", padx=(2, 10))
            e.bind("<Return>", lambda ev: self.schedule())
            e.bind("<FocusOut>", lambda ev: self.schedule())

        # ----- Shape -----
        s = self.section("Shape")
        self.combo(s, "shape", "Shape", list(SHAPES))
        self.combo(s, "grid", "Grid", GRIDS)
        self.slider(s, "cell", "Cell size (px)", 4, 250, 1)
        self.slider(s, "gap", "Gap between cells (px)", 0, 100, 1)
        self.slider(s, "max_scale", "Max size (full end)", 0.0, 1.5, 0.01)
        self.slider(s, "min_scale", "Min size (faded end)", 0.0, 1.5, 0.01)
        self.slider(s, "rotation", "Shape rotation (°)", 0, 360, 1)
        self.slider(s, "star_inner", "Star inner ratio", 0.1, 0.9, 0.01)

        # ----- Fade -----
        s = self.section("Fade")
        self.combo(s, "fade_mode", "Fade mode", FADE_MODES)
        self.slider(s, "gamma", "Falloff curve (gamma)", 0.1, 4.0, 0.05)
        self.check(s, "invert", "Invert fade")
        ttk.Label(s, text="Linear / Radial settings", style="Sub.TLabel"
                  ).pack(anchor="w", pady=(6, 0))
        self.slider(s, "fade_angle", "Linear angle (°)", 0, 360, 1)
        self.slider(s, "fade_start", "Fade start", 0.0, 1.0, 0.01)
        self.slider(s, "fade_end", "Fade end", 0.0, 1.0, 0.01)
        self.slider(s, "center_x", "Radial centre X", 0.0, 1.0, 0.01)
        self.slider(s, "center_y", "Radial centre Y", 0.0, 1.0, 0.01)

        # ----- Curve -----
        s = self.section("Curve (Curve mode)")
        self.hint(s, lines=[
            "Drag the orange points on the preview to reshape the curve.",
            "Double-click empty space on the preview to add a point.",
            "Right-click a point to remove it.",
        ])
        row = ttk.Frame(s)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Curve shape (handles)").pack(side="left")
        self.meta["curve_pts"] = ("curve",)
        self.add_lock(row, "curve_pts")
        self.slider(s, "band_core", "Solid core width", 0.0, 0.5, 0.005)
        self.slider(s, "band_above", "Fade distance above", 0.0, 1.5, 0.005)
        self.slider(s, "band_below", "Fade distance below", 0.0, 1.5, 0.005)
        ttk.Label(s, text="Presets", style="Sub.TLabel").pack(anchor="w", pady=(4, 0))
        grid = ttk.Frame(s)
        grid.pack(fill="x")
        for i, name in enumerate(CURVE_PRESETS):
            ttk.Button(grid, text=name, command=lambda n=name: self.set_preset(n)
                       ).grid(row=i // 3, column=i % 3, sticky="ew", padx=1, pady=1)
        for col in range(3):
            grid.columnconfigure(col, weight=1)
        ttk.Button(s, text="Flip curve vertically",
                   command=self.flip_curve).pack(fill="x", pady=(4, 0))

        # ----- Flame -----
        s = self.section("Flame effect")
        self.slider(s, "flame", "Amount", 0.0, 1.0, 0.01)
        self.slider(s, "flame_bias", "Small-side bias (0 = uniform)", 0.0, 6.0, 0.1)
        self.slider(s, "flame_clump", "Clumping (0 = speckle)", 0.0, 1.0, 0.01)
        self.slider(s, "flame_scale", "Flame size (cells)", 1.0, 30.0, 0.5)
        self.slider(s, "flame_stretch", "Flame stretch", 0.5, 10.0, 0.1)
        self.slider(s, "flame_taper", "Edge taper", 0.0, 2.0, 0.05)
        self.check(s, "flame_auto", "Auto direction (follow fade)")
        self.slider(s, "flame_angle", "Manual flame direction (°)", 0, 360, 1)

        # ----- Variation -----
        s = self.section("Variation")
        self.slider(s, "jitter", "Size jitter", 0.0, 0.6, 0.01)
        self.slider(s, "seed", "Random seed", 0, 999, 1)
        ttk.Button(s, text="New seed only", command=self.new_seed).pack(fill="x")

        # ----- Colours -----
        s = self.section("Colours")
        self.color(s, "fg", "Shape colour")
        self.color(s, "bg", "Background")
        ttk.Button(s, text="Swap colours", command=self.swap_colours).pack(fill="x", pady=2)
        self.check(s, "transparent", "Transparent background", lock=False)

        # ----- Export -----
        s = self.section("Export", lockable=False)
        self.combo(s, "supersample", "Antialias quality (supersample)",
                   ["1", "2", "3", "4"], lock=False)
        ttk.Button(s, text="Export PNG…", command=self.export).pack(fill="x", pady=3)
        ttk.Button(s, text="Reset to defaults", command=self.reset).pack(fill="x")
        ttk.Label(s, textvariable=self.status, style="Info.TLabel",
                  wraplength=300).pack(anchor="w", pady=4)
        ttk.Label(s, text=f"Export folder: {APP_DIR}", style="Path.TLabel",
                  wraplength=300).pack(anchor="w")

    def bind_shortcuts(self):
        def guarded(fn):
            def handler(_e):
                if isinstance(self.root.focus_get(), tk.Entry):
                    return None
                fn()
                return "break"
            return handler

        self.root.bind("<KeyPress-r>", guarded(self.randomise))
        self.root.bind("<KeyPress-m>", guarded(self.mutate))
        self.root.bind("<KeyPress-h>", guarded(self.toggle_handles_key))
        for seq, fn in (("<Control-z>", self.undo), ("<Control-y>", self.redo),
                        ("<Control-Z>", self.redo), ("<Control-s>", self.save_pattern),
                        ("<Command-z>", self.undo), ("<Command-Z>", self.redo),
                        ("<Command-s>", self.save_pattern)):
            try:
                self.root.bind(seq, guarded(fn))
            except tk.TclError:
                pass

    # ======================================================================
    # Pattern library
    # ======================================================================
    def load_library(self):
        # one-time copy from the old home-folder location
        if not LIBRARY_PATH.exists() and OLD_LIBRARY_PATH.exists():
            try:
                shutil.copy2(OLD_LIBRARY_PATH, LIBRARY_PATH)
                self.status.set(f"Copied saved patterns from {OLD_LIBRARY_PATH}")
            except OSError:
                pass
        try:
            self.patterns = read_library(LIBRARY_PATH)
        except (OSError, ValueError) as ex:
            backup = LIBRARY_PATH.with_name(LIBRARY_PATH.name + ".corrupt")
            try:
                os.replace(LIBRARY_PATH, backup)
            except OSError:
                pass
            messagebox.showwarning(
                "Pattern library",
                f"Could not read the saved pattern library:\n{ex}\n\n"
                f"It was moved to:\n{backup}\nA new library will be started.")
            self.patterns = []
        self.refresh_list()

    def persist(self):
        try:
            write_library(LIBRARY_PATH, self.patterns)
            return True
        except OSError as ex:
            messagebox.showerror("Save failed", f"Could not write library:\n{ex}")
            return False

    def find_pattern(self, name):
        low = name.strip().lower()
        for i, q in enumerate(self.patterns):
            if q["name"].strip().lower() == low:
                return i
        return None

    def selected_index(self):
        sel = self.lib_list.curselection()
        return sel[0] if sel else None

    def refresh_list(self, select=None):
        self.lib_list.delete(0, "end")
        for q in self.patterns:
            self.lib_list.insert("end", q["name"])
        if select is not None:
            i = self.find_pattern(select)
            if i is not None:
                self.lib_list.selection_set(i)
                self.lib_list.see(i)
        self.update_thumbnail()

    def update_thumbnail(self):
        self.thumb.delete("all")
        i = self.selected_index()
        if i is None:
            self.thumb_img = None
            n = len(self.patterns)
            self.thumb.create_text(self.THUMB_W // 2, self.THUMB_H // 2, fill="#d8d8d8",
                                   text="No saved patterns yet" if n == 0
                                   else "Select a pattern to preview")
            self.thumb_text.set(f"{n} saved pattern{'s' if n != 1 else ''}")
            return
        entry = self.patterns[i]
        p = normalize_params(entry["params"])
        aspect = p["width"] / p["height"]
        tw, th = self.THUMB_W, int(self.THUMB_W / aspect)
        if th > self.THUMB_H:
            th = self.THUMB_H
            tw = int(th * aspect)
        tw, th = max(8, tw), max(8, th)
        try:
            img = render_display(p, tw, th, ss=2)
        except Exception as ex:  # noqa
            self.thumb.create_text(self.THUMB_W // 2, self.THUMB_H // 2,
                                   fill="#ff8080", text=f"Preview failed: {ex}")
            return
        self.thumb_img = ImageTk.PhotoImage(img)
        self.thumb.create_image(self.THUMB_W // 2, self.THUMB_H // 2, image=self.thumb_img)
        info = f"{entry['name']} · {p['shape']} · {p['fade_mode']} · {p['width']}×{p['height']}"
        if entry.get("saved"):
            info += f"\nSaved {entry['saved'].replace('T', ' ')}"
        self.thumb_text.set(info)

    def suggest_name(self):
        base = describe(self.get_params())
        name, n = base, 2
        while self.find_pattern(name) is not None:
            name = f"{base}-{n}"
            n += 1
        return name

    def make_entry(self, name):
        return {"name": name, "params": self.snapshot(),
                "saved": datetime.now().isoformat(timespec="seconds")}

    def save_pattern(self):
        name = simpledialog.askstring("Save pattern", "Pattern name:",
                                      initialvalue=self.suggest_name(), parent=self.root)
        if not name or not name.strip():
            return
        name = name.strip()
        i = self.find_pattern(name)
        if i is not None:
            if not messagebox.askyesno("Overwrite?",
                                       f"A pattern named '{self.patterns[i]['name']}' "
                                       f"already exists.\nOverwrite it?"):
                return
            self.patterns[i] = self.make_entry(name)
        else:
            self.patterns.append(self.make_entry(name))
        if self.persist():
            self.refresh_list(select=name)
            self.status.set(f"Saved pattern '{name}'")

    def load_selected(self):
        i = self.selected_index()
        if i is None:
            self.status.set("Select a saved pattern first")
            return
        self.push_history()
        self.apply_params(self.patterns[i]["params"])
        self.status.set(f"Loaded '{self.patterns[i]['name']}'  (Undo to go back)")

    def update_selected(self):
        i = self.selected_index()
        if i is None:
            self.status.set("Select a saved pattern first")
            return
        name = self.patterns[i]["name"]
        if not messagebox.askyesno("Update pattern",
                                   f"Replace '{name}' with the current settings?"):
            return
        self.patterns[i] = self.make_entry(name)
        if self.persist():
            self.refresh_list(select=name)
            self.status.set(f"Updated '{name}'")

    def rename_selected(self):
        i = self.selected_index()
        if i is None:
            self.status.set("Select a saved pattern first")
            return
        old = self.patterns[i]["name"]
        new = simpledialog.askstring("Rename pattern", "New name:",
                                     initialvalue=old, parent=self.root)
        if not new or not new.strip() or new.strip() == old:
            return
        new = new.strip()
        j = self.find_pattern(new)
        if j is not None and j != i:
            messagebox.showerror("Rename", f"A pattern named '{new}' already exists.")
            return
        self.patterns[i]["name"] = new
        if self.persist():
            self.refresh_list(select=new)

    def delete_selected(self):
        i = self.selected_index()
        if i is None:
            self.status.set("Select a saved pattern first")
            return
        name = self.patterns[i]["name"]
        if not messagebox.askyesno("Delete pattern", f"Delete '{name}'?"):
            return
        self.patterns.pop(i)
        if self.persist():
            self.refresh_list()
            if self.patterns:
                self.lib_list.selection_set(min(i, len(self.patterns) - 1))
                self.update_thumbnail()
            self.status.set(f"Deleted '{name}'")

    def import_library(self):
        path = filedialog.askopenfilename(initialdir=str(APP_DIR),
                                          filetypes=[("Pattern library", "*.json"),
                                                     ("All files", "*.*")])
        if not path:
            return
        try:
            incoming = read_library(Path(path))
        except (OSError, ValueError) as ex:
            messagebox.showerror("Import failed", str(ex))
            return
        added = 0
        for q in incoming:
            name = str(q["name"]).strip() or "Imported"
            base, n = name, 2
            while self.find_pattern(name) is not None:
                name = f"{base} ({n})"
                n += 1
            self.patterns.append({"name": name, "params": q["params"],
                                  "saved": q.get("saved", "")})
            added += 1
        if self.persist():
            self.refresh_list()
            self.status.set(f"Imported {added} pattern(s)")

    def export_library(self):
        if not self.patterns:
            self.status.set("No saved patterns to export")
            return
        default = unique_path(APP_DIR, "halftone_patterns_export", ".json")
        path = filedialog.asksaveasfilename(defaultextension=".json",
                                            filetypes=[("Pattern library", "*.json")],
                                            initialdir=str(APP_DIR),
                                            initialfile=default.name)
        if not path:
            return
        try:
            write_library(Path(path), self.patterns)
            self.status.set(f"Exported {len(self.patterns)} pattern(s)")
        except OSError as ex:
            messagebox.showerror("Export failed", str(ex))

    def apply_params(self, params):
        p = normalize_params(params)
        snap = {k: p[k] for k in self.vars}
        snap["width"], snap["height"] = str(p["width"]), str(p["height"])
        snap["curve_pts"] = [list(q) for q in p["curve_pts"]]
        self.restore(snap)

    # ======================================================================
    # Locks
    # ======================================================================
    def lock_keys(self, keys, value):
        for k in keys:
            self.locks[k].set(value)
        self.sync_section_locks()

    def sync_section_locks(self):
        for sec in self.sections:
            if sec["lock"] is None:
                continue
            keys = sec["keys"]
            n = sum(1 for k in keys if self.locks[k].get())
            all_locked = bool(keys) and n == len(keys)
            sec["lock"].set(all_locked)
            suffix = f"  ({n} locked)" if 0 < n < len(keys) else ""
            sec["label"].configure(text=sec["title"] + suffix)
            if sec["rand"] is not None:
                sec["rand"].state(["disabled"] if all_locked else ["!disabled"])

    def unlocked(self, key):
        return key in self.locks and not self.locks[key].get()

    # ======================================================================
    # History
    # ======================================================================
    def snapshot(self):
        snap = {}
        for k, var in self.vars.items():
            try:
                snap[k] = var.get()
            except tk.TclError:
                snap[k] = DEFAULTS[k]
        snap["curve_pts"] = [list(q) for q in self.curve_pts]
        return snap

    def restore(self, snap):
        for k, v in snap.items():
            if k == "curve_pts":
                self.curve_pts = [list(q) for q in v]
            elif k in self.vars:
                self.vars[k].set(v)
        self.schedule()

    def push_history(self, snap=None):
        snap = snap if snap is not None else self.snapshot()
        if self.undo_stack and self.undo_stack[-1] == snap:
            return
        self.undo_stack.append(snap)
        if len(self.undo_stack) > self.MAX_HISTORY:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        self.update_history_label()

    def begin_edit(self, key):
        """Group rapid repeated edits (key presses) into one undo step."""
        now = time.monotonic()
        if key != self._edit_key or now - self._edit_t > self.EDIT_COALESCE_S:
            self.push_history()
        self._edit_key, self._edit_t = key, now

    def undo(self):
        if not self.undo_stack:
            return
        self.redo_stack.append(self.snapshot())
        self.restore(self.undo_stack.pop())
        self._edit_key = None
        self.update_history_label()

    def redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append(self.snapshot())
        self.restore(self.redo_stack.pop())
        self._edit_key = None
        self.update_history_label()

    def update_history_label(self):
        self.hist_text.set(f"History: {len(self.undo_stack)} back · "
                           f"{len(self.redo_stack)} forward")

    # ======================================================================
    # Randomise / mutate
    # ======================================================================
    def set_value(self, key, value):
        kind = self.meta[key][0]
        var = self.vars[key]
        if kind == "num":
            _, lo, hi, res = self.meta[key]
            var.set(self.quantize(value, lo, hi, res))
        elif kind == "bool":
            var.set(bool(value))
        else:
            var.set(value)

    def randomise(self, keys=None):
        """Randomise the given keys (default: everything). Locked keys are skipped.
        Returns the number of values that were randomised."""
        keys = list(self.locks) if keys is None else keys
        free = [k for k in keys if self.unlocked(k)]
        if not free:
            return 0
        self.push_history()
        p = self.get_params()
        r = self.rng
        for key in free:
            if key == "curve_pts":
                self.curve_pts = random_curve(r)
            elif key in RAND:
                self.set_value(key, RAND[key](r, p))
        self.randomise_colours(r, free)
        self.schedule()
        return len(free)

    def randomise_section(self, sec):
        keys = sec["keys"]
        n = self.randomise(keys)
        if n == 0:
            self.status.set(f"{sec['title']}: all values are locked")
            return
        kept = len(keys) - n
        msg = f"Randomised {sec['title']}"
        if kept:
            msg += f" ({kept} locked value{'s' if kept != 1 else ''} kept)"
        self.status.set(msg)

    def randomise_colours(self, r, free):
        fg_free, bg_free = "fg" in free, "bg" in free
        if fg_free and bg_free:
            fg, bg = random_palette(r)
            self.vars["fg"].set(fg)
            self.vars["bg"].set(bg)
        elif fg_free:
            h, l, _ = hls_of(self.vars["bg"].get())
            self.vars["fg"].set(random_color(r, light=l < 0.5, near_hue=h))
        elif bg_free:
            h, l, _ = hls_of(self.vars["fg"].get())
            self.vars["bg"].set(random_color(r, light=l < 0.5, near_hue=h))

    def mutate(self):
        self.push_history()
        p = self.get_params()
        r = self.rng
        st = self.mut_strength.get()
        for key in self.locks:
            if not self.unlocked(key):
                continue
            kind = self.meta[key][0]
            if kind == "curve":
                self.curve_pts = mutate_curve(self.curve_pts, r, st)
            elif kind == "num":
                if key == "seed":
                    if r.random() < st * 0.5:
                        self.set_value(key, r.randint(0, 999))
                    continue
                _, lo, hi, _res = self.meta[key]
                self.set_value(key, p[key] + r.gauss(0, st * 0.12 * (hi - lo)))
            elif kind == "choice":
                if key in RAND and r.random() < st * 0.25:
                    self.set_value(key, RAND[key](r, p))
            elif kind == "bool":
                if r.random() < st * 0.2:
                    self.vars[key].set(not self.vars[key].get())
            elif kind == "color":
                self.vars[key].set(nudge_color(p[key], r, st))
        self.schedule()

    def new_seed(self):
        self.push_history()
        self.vars["seed"].set(self.rng.randint(0, 999))
        self.schedule()

    def swap_colours(self):
        self.push_history()
        fg, bg = self.vars["fg"].get(), self.vars["bg"].get()
        self.vars["fg"].set(bg)
        self.vars["bg"].set(fg)
        self.schedule()

    # ======================================================================
    # Params / rendering
    # ======================================================================
    def get_params(self):
        return normalize_params(self.snapshot())

    def schedule(self, fast=False):
        if self._job:
            self.root.after_cancel(self._job)
        self._fast = fast
        self._job = self.root.after(20 if fast else 60, self.redraw)

    def redraw(self):
        self._job = None
        p = self.get_params()
        cw, ch = self.preview.winfo_width(), self.preview.winfo_height()
        if cw < 100 or ch < 100:
            return
        margin = 40
        aspect = p["width"] / p["height"]
        pw, ph = cw - 2 * margin, int((cw - 2 * margin) / aspect)
        if ph > ch - 2 * margin:
            ph = ch - 2 * margin
            pw = int(ph * aspect)
        pw, ph = max(10, pw), max(10, ph)
        ox, oy = (cw - pw) // 2, (ch - ph) // 2
        self.geom = (ox, oy, pw, ph)

        img = render_display(p, pw, ph, ss=1 if self._fast else 2)
        self.tkimg = ImageTk.PhotoImage(img)
        self.preview.delete("all")
        self.preview.create_image(ox, oy, image=self.tkimg, anchor="nw")
        self.draw_overlay(p)
        if not self.status.get().startswith(self.STATUS_KEEP):
            self.status.set(f"Export size: {p['width']} × {p['height']} px")

    # ======================================================================
    # Overlay handles: definition
    # ======================================================================
    def handles_visible(self):
        return self.geom is not None and self.show_handles.get()

    def angle_drag(self, key, cx, cy):
        def drag(mx, my, sh):
            ang = math.degrees(math.atan2(my - cy, mx - cx)) % 360
            if sh:
                ang = (round(ang / 15) * 15) % 360
            self.set_value(key, ang)
        return drag

    def angle_nudge(self, key):
        def nudge(dx, dy):  # right / up = clockwise on screen
            self.set_value(key, (float(self.vars[key].get()) + dx - dy) % 360)
        return nudge

    def collect_overlay(self, p):
        """Return (guides, handles) for the current mode, in canvas coordinates."""
        ox, oy, pw, ph = self.geom
        G, H = [], []
        mode = p["fade_mode"]
        m = min(pw, ph)

        def line(pts, color, width=1, dash=None, arrow=None):
            if pts and len(pts) >= 4:
                G.append(("line", list(pts), dict(fill=color, width=width,
                                                   dash=dash, arrow=arrow)))

        def ring(cx, cy, r, color, dash=None):
            if r > 0.5:
                G.append(("oval", (cx - r, cy - r, cx + r, cy + r),
                          dict(outline=color, width=1, dash=dash)))

        def handle(hid, name, x, y, drag, value, style="circle", color=C_CURVE,
                   reset=(), axis=None, nudge=None, removable=False):
            H.append(dict(id=hid, name=name, x=x, y=y, drag=drag, value=value,
                          style=style, color=color, reset=tuple(reset), axis=axis,
                          nudge=nudge, removable=removable))

        def seg(px, py, vx, vy):
            s = clip_line(px, py, vx, vy, pw, ph)
            return None if s is None else [s[0] + ox, s[1] + oy, s[2] + ox, s[3] + oy]

        # ---------------- Curve mode ----------------
        if mode == "Curve":
            f = make_curve_fn(self.curve_pts)
            core, above, below = p["band_core"], p["band_above"], p["band_below"]
            up, dn = core + above, core + below

            def kk_at(xn):
                sl = (f(xn + 1e-3) - f(xn - 1e-3)) / 2e-3 * ph / pw
                return math.sqrt(1 + sl * sl)

            centre, top, bot = [], [], []
            for i in range(161):
                xn = i / 160
                yn, kk = f(xn), kk_at(xn)
                X = ox + xn * pw
                centre += [X, oy + yn * ph]
                top += [X, oy + (yn - up * kk) * ph]
                bot += [X, oy + (yn + dn * kk) * ph]
            line(top, C_BAND, dash=(4, 4))
            line(bot, C_BAND, dash=(4, 4))
            line(centre, C_CURVE, width=2)

            xs = [q[0] for q in self.curve_pts]
            bx = max((0.5, 0.3, 0.7, 0.15, 0.85),
                     key=lambda c: min(abs(c - x) for x in xs))
            yc, kb = f(bx), kk_at(bx)
            X, Yc = ox + bx * pw, oy + yc * ph
            Yt, Yb = oy + (yc - up * kb) * ph, oy + (yc + dn * kb) * ph
            line([X, Yc, X, Yt], C_BAND, dash=(2, 3))
            line([X, Yc, X, Yb], C_BAND, dash=(2, 3))

            def drag_above(mx, my, sh, Yc=Yc, kb=kb, core=core):
                self.set_value("band_above",
                               snap(max(0.0, (Yc - my) / ph / kb - core), 0.05, sh))

            def drag_below(mx, my, sh, Yc=Yc, kb=kb, core=core):
                self.set_value("band_below",
                               snap(max(0.0, (my - Yc) / ph / kb - core), 0.05, sh))

            handle("band_above", "Fade distance above", X, Yt, drag_above,
                   f"{above:.3f}", "diamond", C_BAND, ("band_above",), axis=(0, -1))
            handle("band_below", "Fade distance below", X, Yb, drag_below,
                   f"{below:.3f}", "diamond", C_BAND, ("band_below",), axis=(0, 1))

            for i, (nx, ny) in enumerate(self.curve_pts):
                handle(f"curve:{i}", f"Curve point {i + 1}", ox + nx * pw, oy + ny * ph,
                       lambda mx, my, sh, i=i: self.drag_curve_point(i, mx, my, sh),
                       f"({nx:.2f}, {ny:.2f})", "circle", C_CURVE, removable=True)

        # ---------------- Linear mode ----------------
        elif mode == "Linear":
            a = math.radians(p["fade_angle"])
            ux, uy = math.cos(a), math.sin(a)
            projs = [x * ux + y * uy for x, y in ((0, 0), (pw, 0), (0, ph), (pw, ph))]
            pmin, span = min(projs), (max(projs) - min(projs)) or 1.0
            cxr, cyr = pw / 2, ph / 2
            pc = cxr * ux + cyr * uy

            def P(t):
                s = pmin + t * span - pc
                return ox + cxr + s * ux, oy + cyr + s * uy

            line(seg(cxr, cyr, ux, uy), C_BAND, dash=(1, 4))
            for key, name in (("fade_start", "Fade start"), ("fade_end", "Fade end")):
                t = p[key]
                X, Y = P(t)
                line(seg(X - ox, Y - oy, -uy, ux), C_BAND, width=1, dash=(5, 4))

                def drag(mx, my, sh, key=key):
                    t = ((mx - ox) * ux + (my - oy) * uy - pmin) / span
                    self.set_value(key, snap(clamp(t, 0.0, 1.0), 0.05, sh))

                handle(key, name, X, Y, drag, f"{t:.2f}", "diamond", C_BAND,
                       (key,), axis=(ux, uy))

            Cx, Cy = ox + cxr, oy + cyr
            Rr = 0.16 * m
            ring(Cx, Cy, Rr, C_ANGLE, dash=(2, 3))
            line([Cx, Cy, Cx + Rr * ux, Cy + Rr * uy], C_ANGLE, width=2)
            handle("fade_angle", "Linear angle", Cx + Rr * ux, Cy + Rr * uy,
                   self.angle_drag("fade_angle", Cx, Cy), f"{p['fade_angle']:.0f}°",
                   "circle", C_ANGLE, ("fade_angle",), nudge=self.angle_nudge("fade_angle"))

        # ---------------- Radial mode ----------------
        elif mode == "Radial":
            cxp, cyp = p["center_x"] * pw, p["center_y"] * ph
            far = max(((0, 0), (pw, 0), (0, ph), (pw, ph)),
                      key=lambda c: math.hypot(c[0] - cxp, c[1] - cyp))
            rmax = math.hypot(far[0] - cxp, far[1] - cyp) or 1.0
            dx_, dy_ = (far[0] - cxp) / rmax, (far[1] - cyp) / rmax
            Cx, Cy = ox + cxp, oy + cyp
            line([Cx, Cy, ox + far[0], oy + far[1]], C_BAND, dash=(1, 4))
            for key, name in (("fade_start", "Fade start radius"),
                              ("fade_end", "Fade end radius")):
                t = p[key]
                ring(Cx, Cy, t * rmax, C_BAND, dash=(5, 4))

                def drag(mx, my, sh, key=key):
                    t = math.hypot(mx - Cx, my - Cy) / rmax
                    self.set_value(key, snap(clamp(t, 0.0, 1.0), 0.05, sh))

                handle(key, name, Cx + t * rmax * dx_, Cy + t * rmax * dy_, drag,
                       f"{t:.2f}", "diamond", C_BAND, (key,), axis=(dx_, dy_))

            def drag_centre(mx, my, sh):
                self.set_value("center_x", snap(clamp((mx - ox) / pw, 0, 1), 0.05, sh))
                self.set_value("center_y", snap(clamp((my - oy) / ph, 0, 1), 0.05, sh))

            handle("center", "Radial centre", Cx, Cy, drag_centre,
                   f"({p['center_x']:.2f}, {p['center_y']:.2f})", "square", C_CENTER,
                   ("center_x", "center_y"))

        # ---------------- Flame direction (manual) ----------------
        if p["flame"] > 0 and not p["flame_auto"]:
            a = math.radians(p["flame_angle"])
            ux, uy = math.cos(a), math.sin(a)
            Cx, Cy = ox + pw / 2, oy + ph / 2
            Rf = 0.27 * m
            line([Cx - Rf * ux, Cy - Rf * uy, Cx + Rf * ux, Cy + Rf * uy],
                 C_FLAME, width=2, dash=(6, 3), arrow="last")
            handle("flame_angle", "Flame direction", Cx + Rf * ux, Cy + Rf * uy,
                   self.angle_drag("flame_angle", Cx, Cy), f"{p['flame_angle']:.0f}°",
                   "circle", C_FLAME, ("flame_angle",), nudge=self.angle_nudge("flame_angle"))

        # ---------------- Cell-size ruler (all modes) ----------------
        sc = pw / p["width"]
        cpx = p["cell"] * sc
        N = 2
        x0, y0 = ox + 14, oy + ph - 16
        x1 = x0 + N * cpx
        line([x0, y0, x1, y0], C_RULER, width=2)
        for i in range(N + 1):
            xt = x0 + i * cpx
            line([xt, y0 - 5, xt, y0 + 5], C_RULER, width=2)

        def drag_cell(mx, my, sh):
            cell = (mx - x0) / N / sc
            self.set_value("cell", snap(cell, 4, sh))

        handle("cell", "Cell size", x1, y0, drag_cell, f"{p['cell']:.0f} px",
               "square", C_RULER, ("cell",), axis=(1, 0))
        return G, H

    def drag_curve_point(self, i, mx, my, sh):
        ox, oy, pw, ph = self.geom
        pts = self.curve_pts
        n = len(pts)
        if i >= n:
            return
        lo = pts[i - 1][0] + 0.01 if i > 0 else 0.0
        hi = pts[i + 1][0] - 0.01 if i < n - 1 else 1.0
        nx = snap((mx - ox) / pw, 0.05, sh)
        ny = snap((my - oy) / ph, 0.05, sh)
        ymin, ymax = -oy / ph, (self.preview.winfo_height() - oy) / ph
        pts[i] = [clamp(nx, lo, hi), clamp(ny, ymin, ymax)]

    # ======================================================================
    # Overlay handles: drawing
    # ======================================================================
    def disp(self, h):
        """Display position: clamped so off-image handles stay grabbable."""
        cw, ch = self.preview.winfo_width(), self.preview.winfo_height()
        return clamp(h["x"], 8, cw - 8), clamp(h["y"], 8, ch - 8)

    def draw_overlay(self, p=None):
        cv = self.preview
        cv.delete("overlay")
        self.handles = []
        if not self.handles_visible():
            return
        p = p or self.get_params()
        guides, self.handles = self.collect_overlay(p)

        for kind, coords, kw in guides:
            w = kw.pop("width", 1)
            if kind == "line":
                cv.create_line(coords, fill=C_SHADOW, width=w + 2, dash=kw.get("dash"),
                               arrow=kw.get("arrow"), tags="overlay")
                cv.create_line(coords, width=w, tags="overlay", **kw)
            else:
                cv.create_oval(coords, outline=C_SHADOW, width=w + 2,
                               dash=kw.get("dash"), tags="overlay")
                cv.create_oval(coords, width=w, tags="overlay", **kw)

        R = self.HANDLE_R
        for h in self.handles:
            x, y = self.disp(h)
            sel = h["id"] == self.sel_id
            hot = sel or h["id"] in (self.hover_id, self.drag_id)
            r = R + (2 if hot else 0)
            opts = dict(fill=h["color"], outline=C_SELECT if sel else "white",
                        width=3 if sel else 2, tags="overlay")
            if h["style"] == "square":
                cv.create_rectangle(x - r + 1, y - r + 1, x + r - 1, y + r - 1, **opts)
            elif h["style"] == "diamond":
                cv.create_polygon(x, y - r - 2, x + r + 2, y, x, y + r + 2, x - r - 2, y, **opts)
            else:
                cv.create_oval(x - r, y - r, x + r, y + r, **opts)

        active = self.find_handle(self.drag_id or self.hover_id or self.sel_id)
        if active:
            self.draw_label(active)

        # help strip along the bottom: bright text on a dark backing
        cw, ch = cv.winfo_width(), cv.winfo_height()
        t = cv.create_text(cw // 2, ch - 13, fill="#f2f2f2", tags="overlay",
                           text="Drag a handle to adjust  ·  Shift = snap  ·  "
                                "Double-click = reset  ·  Click + arrow keys = nudge  ·  "
                                "H = hide handles")
        bb = cv.bbox(t)
        r = cv.create_rectangle(bb[0] - 8, bb[1] - 3, bb[2] + 8, bb[3] + 3,
                                fill="#111111", outline="#555555", tags="overlay")
        cv.tag_lower(r, t)

    def draw_label(self, h):
        cv = self.preview
        cw = cv.winfo_width()
        x, y = self.disp(h)
        extra = "  (double-click to reset)" if h["reset"] else ""
        t = cv.create_text(x + 14, y - 14, text=f"{h['name']}: {h['value']}{extra}",
                           anchor="sw", fill="white", tags="overlay")
        bb = cv.bbox(t)
        if bb[2] > cw - 4:
            cv.itemconfigure(t, anchor="se")
            cv.coords(t, x - 14, y - 14)
            bb = cv.bbox(t)
        if bb[1] < 4:
            cv.move(t, 0, 28 + (bb[3] - bb[1]))
            bb = cv.bbox(t)
        r = cv.create_rectangle(bb[0] - 5, bb[1] - 3, bb[2] + 5, bb[3] + 3,
                                fill="#111111", outline="#555555", tags="overlay")
        cv.tag_lower(r, t)

    def find_handle(self, hid):
        if hid is None:
            return None
        for h in self.handles:
            if h["id"] == hid:
                return h
        return None

    def hit(self, ex, ey):
        best, bd = None, (self.HANDLE_R + 6) ** 2
        for h in self.handles:       # later handles win ties (drawn on top)
            x, y = self.disp(h)
            d = (x - ex) ** 2 + (y - ey) ** 2
            if d <= bd:
                best, bd = h, d
        return best

    # ======================================================================
    # Overlay handles: interaction
    # ======================================================================
    def on_toggle_handles(self):
        self.hover_id = self.sel_id = self.drag_id = None
        self.preview.configure(cursor="")
        self.draw_overlay()

    def toggle_handles_key(self):
        self.show_handles.set(not self.show_handles.get())
        self.on_toggle_handles()

    def on_motion(self, e):
        if self.drag_id or not self.handles_visible():
            return
        h = self.hit(e.x, e.y)
        hid = h["id"] if h else None
        if hid != self.hover_id:
            self.hover_id = hid
            self.preview.configure(cursor="fleur" if hid else "")
            self.draw_overlay()

    def on_leave(self, _e):
        if self.drag_id is None and self.hover_id is not None:
            self.hover_id = None
            self.preview.configure(cursor="")
            self.draw_overlay()

    def on_press(self, e):
        self.preview.focus_set()
        if not self.handles_visible():
            return
        h = self.hit(e.x, e.y)
        if h is None:
            if self.sel_id is not None:
                self.sel_id = None
                self.draw_overlay()
            return
        self._press_snap = self.snapshot()
        self._edit_key = None
        x, y = self.disp(h)
        self._grab = (x - e.x, y - e.y)
        self.drag_id = self.sel_id = h["id"]
        self.draw_overlay()

    def on_drag(self, e):
        h = self.find_handle(self.drag_id)
        if h is None:
            return
        h["drag"](e.x + self._grab[0], e.y + self._grab[1], bool(e.state & 0x0001))
        self.draw_overlay()
        self.schedule(fast=True)

    def on_release(self, _e):
        if self.drag_id is None:
            return
        self.drag_id = None
        if self._press_snap is not None and self.snapshot() != self._press_snap:
            self.push_history(self._press_snap)
        self._press_snap = None
        self.schedule()

    def on_double(self, e):
        if not self.handles_visible():
            return
        h = self.hit(e.x, e.y)
        if h is not None:
            if h["reset"]:
                self.push_history()
                for k in h["reset"]:
                    self.vars[k].set(DEFAULTS[k])
                self.status.set(f"Reset {h['name'].lower()}")
                self.schedule()
            return
        if self.get_params()["fade_mode"] != "Curve":
            return
        ox, oy, pw, ph = self.geom
        nx, ny = (e.x - ox) / pw, (e.y - oy) / ph
        if not 0 <= nx <= 1 or any(abs(nx - q[0]) < 0.015 for q in self.curve_pts):
            return
        self.push_history()
        self.curve_pts.append([nx, ny])
        self.curve_pts.sort()
        self.schedule()

    def on_right(self, e):
        if not self.handles_visible():
            return
        h = self.hit(e.x, e.y)
        if h and h["removable"]:
            self.remove_curve_point(int(h["id"].split(":")[1]))

    def remove_curve_point(self, i):
        if len(self.curve_pts) <= 2 or i >= len(self.curve_pts):
            return
        self.push_history()
        self.curve_pts.pop(i)
        self.sel_id = self.hover_id = None
        self.schedule()

    def delete_selected_point(self):
        if self.sel_id and self.sel_id.startswith("curve:"):
            self.remove_curve_point(int(self.sel_id.split(":")[1]))
        return "break"

    def deselect(self):
        self.sel_id = None
        self.draw_overlay()
        return "break"

    def nudge_selected(self, dx, dy, e):
        h = self.find_handle(self.sel_id) if self.handles_visible() else None
        if h is None:
            return None
        k = 10 if e.state & 0x0001 else 1
        dx, dy = dx * k, dy * k
        self.begin_edit("handle:" + h["id"])
        if h["nudge"]:
            h["nudge"](dx, dy)
        elif h["axis"]:
            ax, ay = h["axis"]
            amt = dx * ax + dy * ay
            if abs(amt) < 0.35 * max(abs(dx), abs(dy)):   # key roughly perpendicular
                amt = dx - dy
            h["drag"](h["x"] + amt * ax, h["y"] + amt * ay, False)
        else:
            h["drag"](h["x"] + dx, h["y"] + dy, False)
        self.draw_overlay()
        self.schedule()
        return "break"

    # ======================================================================
    # Curve presets
    # ======================================================================
    def set_preset(self, name):
        self.push_history()
        self.curve_pts = [pt[:] for pt in CURVE_PRESETS[name]]
        self.vars["fade_mode"].set("Curve")
        self.schedule()

    def flip_curve(self):
        self.push_history()
        self.curve_pts = [[x, 1 - y] for x, y in self.curve_pts]
        a, b = self.vars["band_above"].get(), self.vars["band_below"].get()
        self.vars["band_above"].set(b)
        self.vars["band_below"].set(a)
        self.schedule()

    # ======================================================================
    # Export / reset
    # ======================================================================
    def export(self):
        p = self.get_params()
        default = unique_path(APP_DIR, f"halftone_{describe(p)}_{p['width']}x{p['height']}",
                              ".png")
        path = filedialog.asksaveasfilename(
            defaultextension=".png", filetypes=[("PNG image", "*.png")],
            initialdir=str(APP_DIR), initialfile=default.name)
        if not path:
            return
        self.status.set("Rendering…")
        self.root.config(cursor="watch")
        self.root.update_idletasks()
        try:
            img = render(p, p["width"], p["height"],
                         ss=int(p["supersample"]), transparent=p["transparent"])
            img.save(path, "PNG")
            self.status.set(f"Saved PNG: {path}")
        except Exception as ex:  # noqa
            messagebox.showerror("Export failed", str(ex))
            self.status.set("Export failed")
        finally:
            self.root.config(cursor="")

    def reset(self):
        self.push_history()
        for k, var in self.vars.items():
            var.set(str(DEFAULTS[k]) if k in ("width", "height") else DEFAULTS[k])
        self.curve_pts = [pt[:] for pt in CURVE_PRESETS["Wave"]]
        self.schedule()


if __name__ == "__main__":
    root = tk.Tk()
    try:
        ttk.Style().theme_use("clam")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()