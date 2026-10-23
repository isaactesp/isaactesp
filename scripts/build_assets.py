"""Builds the SVG cards used by README.md, styled after usetalky.com.

GitHub READMEs can't load custom CSS, so every section is drawn as an SVG
with its fonts (Outfit, Manrope, Martian Mono) subset and embedded inline.

Usage:  pip install fonttools brotli
        python scripts/build_assets.py
"""
import base64
import io
import math
import random
import re
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"
CACHE = Path(__file__).resolve().parent / ".fontcache"

# Palette taken from usetalky.com
INK = "#101938"
NAVY = "#16224F"
NAVY_DEEP = "#0F1838"
ORANGE = "#F3572F"
ORANGE_SOFT = "#FDEDE8"
COBALT = "#16318F"
GREY = "#5E6377"
GREY_LIGHT = "#A2A5B2"
LINE = "#E5E7EB"
BG = "#F5F6F8"
CREAM = "#F5EBD3"
GOLD = "#E7D1A1"
SALMON = "#F9D3C6"
MIST = "#E4E7F0"
WHITE = "#FFFFFF"

FAMILIES = {
    "outfit": ("Outfit", "wght@300;400;500"),
    "manrope": ("Manrope", "wght@400;500;600"),
    "mono": ("Martian Mono", "wght@400;500"),
}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


# ---------------------------------------------------------------- fonts

def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req) as r:
        return r.read()


_fonts = {}


def font(family, weight):
    """Static TTFont instance of a Google font at the given weight (cached)."""
    key = (family, weight)
    if key in _fonts:
        return _fonts[key]
    CACHE.mkdir(exist_ok=True)
    path = CACHE / f"{family}-{weight}.ttf"
    if not path.exists():
        name, axes = FAMILIES[family]
        css = _fetch(f"https://fonts.googleapis.com/css2?family={name.replace(' ', '+')}:{axes}&display=swap").decode()
        blocks = re.findall(r"/\* latin \*/\s*@font-face\s*{([^}]*)}", css)
        block = next(b for b in blocks if f"font-weight: {weight};" in b)
        f = TTFont(io.BytesIO(_fetch(re.search(r"url\((https://[^)]+)\)", block).group(1))))
        if "fvar" in f:
            f = instancer.instantiateVariableFont(f, {"wght": weight})
        f.flavor = None
        f.save(path)
    _fonts[key] = TTFont(path)
    return _fonts[key]


def text_width(s, family, weight, size, tracking=0.0):
    f = font(family, weight)
    cmap, hmtx, upm = f.getBestCmap(), f["hmtx"], f["head"].unitsPerEm
    w = 0
    for ch in s:
        g = cmap.get(ord(ch))
        w += hmtx[g][0] if g else upm * 0.5
    return w * size / upm + tracking * size * len(s)


def wrap(s, width, family, weight, size):
    lines, cur = [], ""
    for word in s.split():
        trial = f"{cur} {word}".strip()
        if text_width(trial, family, weight, size) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    return lines + [cur]


# ---------------------------------------------------------------- svg

class Svg:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.parts = []
        self.used = {}

    def add(self, s):
        self.parts.append(s)

    def text(self, x, y, s, family="manrope", weight=400, size=14, fill=INK,
             anchor="start", tracking=0.0, opacity=1.0):
        self.used.setdefault((family, weight), set()).update(s)
        extra = f' letter-spacing="{tracking}em"' if tracking else ""
        extra += f' text-anchor="{anchor}"' if anchor != "start" else ""
        extra += f' opacity="{opacity}"' if opacity != 1 else ""
        self.add(f'<text x="{x:.1f}" y="{y:.1f}" class="{family}{weight}" font-size="{size}" '
                 f'fill="{fill}"{extra}>{escape(s)}</text>')
        return text_width(s, family, weight, size, tracking)

    def rect(self, x, y, w, h, r=0, fill="none", stroke=None, sw=1, opacity=1.0):
        st = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
        op = f' opacity="{opacity}"' if opacity != 1 else ""
        self.add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r}" fill="{fill}"{st}{op}/>')

    def chip(self, x, y, label, code=None, active=False, h=26):
        """Tool chip in the style of Talky's 'Freight 214' pills."""
        lw = text_width(label, "manrope", 500, 12)
        cw = text_width(code, "mono", 400, 10) + 8 if code else 0
        w = lw + cw + 22
        self.rect(x, y, w, h, r=h / 2, fill=WHITE if not active else ORANGE_SOFT,
                  stroke=ORANGE if active else LINE)
        self.text(x + 11, y + h / 2 + 4.2, label, "manrope", 500, 12, ORANGE if active else INK)
        if code:
            self.text(x + 11 + lw + 8, y + h / 2 + 3.6, code, "mono", 400, 10, ORANGE if active else GREY_LIGHT)
        return w

    def render(self, title):
        faces = []
        for (family, weight), chars in sorted(self.used.items()):
            opts = subset.Options()
            opts.flavor = "woff2"
            opts.layout_features = ["kern", "liga"]
            sub = subset.Subsetter(opts)
            sub.populate(text="".join(chars))
            f = TTFont(CACHE / f"{family}-{weight}.ttf")
            sub.subset(f)
            buf = io.BytesIO()
            f.flavor = "woff2"
            f.save(buf)
            data = base64.b64encode(buf.getvalue()).decode()
            fam = f"{FAMILIES[family][0]} {weight}"
            faces.append(f"@font-face{{font-family:'{fam}';src:url(data:font/woff2;base64,{data}) format('woff2')}}"
                         f".{family}{weight}{{font-family:'{fam}',-apple-system,'Segoe UI',sans-serif}}")
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
                f'viewBox="0 0 {self.w} {self.h}" role="img" aria-label="{escape(title)}">'
                f'<title>{escape(title)}</title><style>{"".join(faces)}</style>'
                + "".join(self.parts) + "</svg>")


def save(svg, name, title):
    OUT.mkdir(exist_ok=True)
    (OUT / name).write_text(svg.render(title), encoding="utf-8")
    print(f"assets/{name}  {(OUT / name).stat().st_size / 1024:.0f} KB")


def contours(svg, x0, y0, w, h, seed, color=GOLD, count=14, opacity=0.35):
    """Topographic lines like the map in Talky's closing card."""
    rnd = random.Random(seed)
    svg.add(f'<g fill="none" stroke="{color}" stroke-width="1" opacity="{opacity}">')
    for _ in range(3):
        cx, cy = x0 + rnd.uniform(0.15, 0.85) * w, y0 + rnd.uniform(0.2, 0.8) * h
        phases = [rnd.uniform(0, 2 * math.pi) for _ in range(4)]
        for i in range(count):
            base = 18 + i * max(w, h) / count * 0.55
            pts = []
            for k in range(73):
                a = k / 72 * 2 * math.pi
                r = base * (1 + 0.16 * math.sin(3 * a + phases[0]) + 0.1 * math.sin(5 * a + phases[1])
                            + 0.06 * math.sin(2 * a + phases[2] + i * 0.15))
                pts.append(f"{cx + r * math.cos(a) * 1.4:.1f},{cy + r * math.sin(a):.1f}")
            svg.add(f'<polyline points="{" ".join(pts)}"/>')
    svg.add("</g>")


def clip_round(svg, cid, x, y, w, h, r):
    svg.add(f'<defs><clipPath id="{cid}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}"/></clipPath></defs>')


# ---------------------------------------------------------------- sections

W = 900


def hero():
    s = Svg(W, 440)
    s.add(f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
          f'<stop offset="0" stop-color="{NAVY_DEEP}"/><stop offset="1" stop-color="#26346B"/></linearGradient></defs>')
    clip_round(s, "c", 0, 0, W, 440, 22)
    s.add('<g clip-path="url(#c)">')
    s.rect(0, 0, W, 440, fill="url(#g)")
    contours(s, 0, 0, W, 440, seed=7, opacity=0.16)
    s.add("</g>")
    # nav bar
    s.rect(28, 24, 92, 32, r=16, fill=WHITE, opacity=0.08, stroke=WHITE, sw=0.6)
    s.text(74, 45, "Madrid", "manrope", 500, 13, WHITE, anchor="middle")
    s.add(f'<path d="M{W/2-60} 40 c0-9 8-14 16-14 c5 0 8 3 8 8 c0 8-8 14-16 14 c-5 0-8-3-8-8z" fill="{WHITE}"/>')
    s.text(W / 2 - 34, 46, "isaactesp", "outfit", 500, 20, WHITE, tracking=-0.02)
    s.text(W - 28, 45, "Data Scientist", "manrope", 400, 13, WHITE, anchor="end", opacity=0.75)
    # headline
    s.text(W / 2, 190, "Hi, I’m Isaac.", "outfit", 400, 52, WHITE, anchor="middle", tracking=-0.035)
    s.text(W / 2, 250, "Mathematician by training.", "outfit", 400, 52, "#9FA5BD", anchor="middle", tracking=-0.035)
    s.text(W / 2, 310, "Data scientist by trade.", "outfit", 400, 52, WHITE, anchor="middle", tracking=-0.035)
    # buttons
    for x, label in [(W / 2 - 160, "Isaac Teres Espallargas"), (W / 2 + 92, "Projects ↓")]:
        bw = text_width(label, "mono", 500, 12) + 36
        s.rect(x - bw / 2, 352, bw, 40, r=20, fill=WHITE, opacity=0.1, stroke=WHITE, sw=0.6)
        s.text(x, 376, label, "mono", 500, 12, WHITE, anchor="middle")
    save(s, "hero.svg", "Hi, I'm Isaac Teres Espallargas. Mathematician by training. Data scientist by trade.")


PROJECTS = [
    ("SQL-Query-Agent", "REPO·01", "Plain-English queries over a dbt warehouse.", ["dbt", "Ollama", "ChromaDB"]),
    ("Distributed-ML-Server", "REPO·02", "Train and serve ML models, client–server.", ["Java", "Python"]),
    ("Library-Management", "REPO·03", "Library system built on SOLID principles.", ["Java"]),
    ("gradient_descent", "REPO·04", "Gradient descent, from scratch.", ["Python", "NumPy"]),
]


def project(name, code, line, stack, slug):
    w, h = 440, 150
    s = Svg(w, h)
    s.rect(0.5, 0.5, w - 1, h - 1, r=16, fill=WHITE, stroke=LINE)
    tw = text_width(code, "mono", 500, 10.5) + 12
    s.rect(20, 20, tw, 20, r=4, fill=ORANGE)
    s.text(26, 34, code, "mono", 500, 10.5, WHITE)
    s.text(w - 20, 34, "→", "mono", 400, 13, ORANGE, anchor="end")
    s.text(20, 74, name, "outfit", 400, 22, INK, tracking=-0.02)
    s.text(20, 96, line, "manrope", 400, 12.5, GREY)
    x = 20
    for tool in stack:
        x += s.chip(x, 110, tool, h=24) + 6
    save(s, f"project-{slug}.svg", f"{name}: {line} {', '.join(stack)}.")


def cta():
    h = 300
    s = Svg(W, h)
    s.rect(0, 0, W, h, r=22, fill="#E9D3A2")
    s.text(40, 100, "Thanks for stopping by.", "outfit", 400, 38, INK, tracking=-0.04)
    w1 = s.text(40, 146, "Say hi.", "outfit", 400, 38, INK, tracking=-0.04)
    s.text(48 + w1, 146, "Anytime.", "outfit", 400, 38, "#8C8577", tracking=-0.04)
    for k, line in enumerate(wrap("I enjoy maths, data and building things that work. Always happy to chat about any of it.",
                                  380, "manrope", 400, 14)):
        s.text(40, 186 + k * 22, line, "manrope", 400, 14, "#4A4F63")
    bw = text_width("isaactesp.com →", "mono", 500, 12) + 36
    s.rect(40, 236, bw, 38, r=19, fill=INK)
    s.text(40 + bw / 2, 259, "isaactesp.com →", "mono", 500, 12, WHITE, anchor="middle")
    px, py, pw, ph = 470, 24, W - 470 - 24, h - 48
    clip_round(s, "mc", px, py, pw, ph, 14)
    s.add('<g clip-path="url(#mc)">')
    s.rect(px, py, pw, ph, fill=INK)
    contours(s, px, py, pw, ph, seed=11, count=16, opacity=0.55)
    s.add(f'<circle cx="{px + pw * 0.62}" cy="{py + ph * 0.46}" r="5" fill="{ORANGE}"/>'
          f'<circle cx="{px + pw * 0.62}" cy="{py + ph * 0.46}" r="12" fill="none" stroke="{ORANGE}" opacity="0.5"/>')
    s.add("</g>")
    s.text(px + 16, py + ph - 16, "40.4509° N · 3.7082° W  Madrid", "mono", 400, 10, GOLD, opacity=0.8)
    save(s, "cta.svg", "Thanks for stopping by. Say hi, anytime. isaactesp.com")


if __name__ == "__main__":
    hero()
    for p in PROJECTS:
        project(*p, slug=p[0].lower().replace("_", "-"))
    cta()
