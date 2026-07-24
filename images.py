"""
Listing image builder — Amazon 2026 image rules.

Main image rules enforced here: pure white RGB(255,255,255), product fills ~85%
of the frame, no text or graphics, square, 2000 px, sRGB JPEG under 10 MB.
Secondary slots allow text, infographics and lifestyle backgrounds.

Honest scope: this composites YOUR product photo onto generated backgrounds and
lays type over it. It does not invent photographic scenery — for a lifestyle
shot you supply the background photo and the product is placed onto it.
"""
from __future__ import annotations
import io, os, re, zipfile
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

CANVAS      = 2000          # Amazon's recommended 2000 x 2000
MAIN_FILL   = 0.85          # product must fill at least 85% of the main frame
MIN_SIDE    = 1000          # zoom threshold
MAX_SIDE    = 10000
MAX_BYTES   = 10 * 1024 * 1024
JPEG_Q      = 92

RED   = (227, 30, 42)
BLACK = (17, 17, 19)
WHITE = (255, 255, 255)
GREY  = (232, 234, 238)
DARK  = (28, 30, 34)

HERE = os.path.dirname(os.path.abspath(__file__))
def _font(name, size):
    for p in (os.path.join(HERE, "fonts", name),
              f"/usr/share/fonts/truetype/google-fonts/{name}",
              f"/usr/share/fonts/truetype/dejavu/{name}"):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def display(size):  return _font("Anton-Regular.ttf", size)          # headlines
def cond(size):     return _font("BarlowCondensed-Bold.ttf", size)   # sub-heads
def body(size):     return _font("Poppins-Regular.ttf", size)        # body copy
def body_b(size):   return _font("Poppins-Medium.ttf", size)

# ------------------------------------------------------------------ helpers
def to_rgb(im):
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, WHITE)
        bg.paste(im, mask=im.split()[-1])
        return bg
    return im.convert("RGB")

def cutout(im, tol=18):
    """Returns (RGBA product with background removed, bbox). Works on the
    studio-white shots sellers already have; flood-fills from the corners so a
    light grey studio sweep is removed too."""
    im = to_rgb(im)
    w, h = im.size
    px = im.load()
    corners = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
    base = tuple(sum(c[i] for c in corners) // 4 for i in range(3))
    if min(base) < 200:                       # dark background: keep as-is
        out = im.convert("RGBA")
        return out, (0, 0, w, h)
    diff = ImageChops.difference(im, Image.new("RGB", im.size, base)).convert("L")
    mask = diff.point(lambda v: 255 if v > tol else 0).filter(ImageFilter.MedianFilter(3))
    bbox = mask.getbbox() or (0, 0, w, h)
    out = im.convert("RGBA")
    out.putalpha(mask)
    return out, bbox

def fit(im, box_w, box_h):
    r = min(box_w / im.width, box_h / im.height)
    return im.resize((max(1, int(im.width * r)), max(1, int(im.height * r))), Image.LANCZOS)

def wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = f"{cur} {w}".strip()
        if draw.textlength(t, font=font) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines

def draw_lines(draw, xy, lines, font, fill, leading=1.06):
    x, y = xy
    asc = font.getbbox("Hg")[3] - font.getbbox("Hg")[1]
    for ln in lines:
        draw.text((x, y), ln, font=font, fill=fill)
        y += int(asc * leading) + 6
    return y

def hex_pattern(canvas, colour=(255, 255, 255), alpha=16, step=120):
    """Faint hexagon texture, the motif used across the reference set."""
    lay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    r = step * 0.45
    for row, y in enumerate(range(-step, canvas.height + step, int(step * 0.86))):
        for x in range(-step, canvas.width + step, step):
            cx = x + (step // 2 if row % 2 else 0)
            pts = [(cx + r * (0.5 if i % 3 else 1) * (1 if i < 3 else -1), y) for i in range(1)]
            pts = [(cx + r * __import__("math").cos(__import__("math").radians(60 * i)),
                    y + r * __import__("math").sin(__import__("math").radians(60 * i)))
                   for i in range(6)]
            d.polygon(pts, outline=colour + (alpha,))
    return Image.alpha_composite(canvas.convert("RGBA"), lay).convert("RGB")

def gradient(size, top, bottom, diagonal=False):
    w, h = size
    g = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        g.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    g = g.resize(size, Image.BILINEAR)
    if diagonal: g = g.rotate(12, resample=Image.BICUBIC, expand=False)
    return g

def shadow(canvas, prod, pos, blur=42, opacity=110):
    sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    a = prod.split()[-1].point(lambda v: min(opacity, v))
    solid = Image.new("RGBA", prod.size, (0, 0, 0, 255)); solid.putalpha(a)
    sh.paste(solid, (pos[0] + 14, pos[1] + 26), solid)
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    return Image.alpha_composite(canvas.convert("RGBA"), sh).convert("RGB")

def red_rule(d, x, y, w=180, h=10):
    d.rectangle([x, y, x + w, y + h], fill=RED)

# ------------------------------------------------------------------ templates
def main_image(src, size=CANVAS, fill=MAIN_FILL):
    """Slot 1. Pure white, product at ~85% frame fill, nothing else."""
    prod, bbox = cutout(src)
    prod = prod.crop(bbox)
    target = int(size * fill)
    prod = fit(prod, target, target)
    canvas = Image.new("RGB", (size, size), WHITE)
    pos = ((size - prod.width) // 2, (size - prod.height) // 2)
    canvas = shadow(canvas, prod, pos, blur=30, opacity=55)
    canvas.paste(prod, pos, prod)
    # guarantee the corners read as exactly 255,255,255
    d = ImageDraw.Draw(canvas)
    m = int(size * 0.012)
    for box in [(0, 0, size, m), (0, size - m, size, size),
                (0, 0, m, size), (size - m, 0, size, size)]:
        d.rectangle(box, fill=WHITE)
    return canvas

def hero(src, headline, accent, subline="", size=CANVAS, bg=None):
    """Headline top-left in two colours, product right. Slots 2-3."""
    if bg is not None:
        canvas = fit(to_rgb(bg), size, size).resize((size, size), Image.LANCZOS)
        veil = Image.new("RGBA", (size, size), (10, 10, 12, 120))
        canvas = Image.alpha_composite(canvas.convert("RGBA"), veil).convert("RGB")
    else:
        canvas = gradient((size, size), (44, 47, 54), (12, 13, 15))
        canvas = hex_pattern(canvas, alpha=13)
    prod, bbox = cutout(src); prod = prod.crop(bbox)
    prod = fit(prod, int(size * .62), int(size * .58))
    pos = (size - prod.width - int(size * .05), int(size * .38))
    canvas = shadow(canvas, prod, pos, blur=55, opacity=140)
    canvas.paste(prod, pos, prod)

    d = ImageDraw.Draw(canvas)
    m = int(size * .06)
    f1 = display(int(size * .085))
    y = m
    y = draw_lines(d, (m, y), wrap(d, headline.upper(), f1, size * .62), f1, WHITE)
    y = draw_lines(d, (m, y), wrap(d, accent.upper(), f1, size * .62), f1, RED)
    red_rule(d, m, y + 14, int(size * .11), int(size * .006))
    if subline:
        fb = body(int(size * .028))
        draw_lines(d, (m, y + int(size * .05)), wrap(d, subline, fb, size * .48), fb, (232, 234, 238), 1.35)
    return canvas

def badge_card(src, headline, accent, badges, size=CANVAS, bg=None):
    """Top bar headline, badge stack on the left, product right. Slot 4-5."""
    if bg is not None:
        canvas = fit(to_rgb(bg), size, size).resize((size, size), Image.LANCZOS)
    else:
        canvas = gradient((size, size), (238, 240, 244), (203, 208, 215))
    d = ImageDraw.Draw(canvas)
    bar = int(size * .155)
    d.rectangle([0, 0, size, bar], fill=BLACK)
    d.polygon([(int(size * .62), bar), (size, bar), (size, bar + int(size * .028))], fill=RED)

    prod, bbox = cutout(src); prod = prod.crop(bbox)
    prod = fit(prod, int(size * .62), int(size * .55))
    pos = (size - prod.width - int(size * .04), int(size * .40))
    canvas = shadow(canvas, prod, pos, blur=50, opacity=120)
    canvas.paste(prod, pos, prod)

    d = ImageDraw.Draw(canvas)
    m = int(size * .045)
    f1 = display(int(size * .058))
    lines = wrap(d, headline.upper(), f1, size * .78)
    yy = int(bar * .18)
    for ln in lines[:1]:
        d.text((m, yy), ln, font=f1, fill=WHITE)
        wln = d.textlength(ln, font=f1)
        if accent: d.text((m + wln + 18, yy), accent.upper(), font=f1, fill=RED)
    fb = body(int(size * .026))
    d.text((m, int(bar * .66)), " ", font=fb, fill=WHITE)

    y = int(size * .27)
    for label, sub in badges[:4]:
        h = int(size * .085)
        d.rounded_rectangle([m, y, m + int(size * .40), y + h], radius=int(h * .18), fill=BLACK)
        d.rectangle([m + int(size * .40) - 8, y, m + int(size * .40), y + h], fill=RED)
        d.text((m + int(size * .035), y + int(h * .16)), label.upper(),
               font=cond(int(size * .035)), fill=WHITE)
        if sub:
            d.text((m + int(size * .035), y + int(h * .58)), sub,
                   font=body(int(size * .018)), fill=(190, 194, 200))
        y += h + int(size * .028)
    return canvas

def callouts(src, items, headline="", size=CANVAS):
    """Product centred with feature callouts down both sides. Slot 6-7."""
    canvas = gradient((size, size), (243, 244, 246), (214, 217, 222))
    prod, bbox = cutout(src); prod = prod.crop(bbox)
    prod = fit(prod, int(size * .46), int(size * .46))
    pos = ((size - prod.width) // 2, (size - prod.height) // 2 + int(size * .03))
    canvas = shadow(canvas, prod, pos, blur=45, opacity=110)
    canvas.paste(prod, pos, prod)
    d = ImageDraw.Draw(canvas)
    if headline:
        f1 = display(int(size * .05))
        d.text((int(size * .05), int(size * .045)), headline.upper(), font=f1, fill=BLACK)
        red_rule(d, int(size * .05), int(size * .045) + int(size * .062), int(size * .09), 8)

    left = [i for n, i in enumerate(items) if n % 2 == 0][:3]
    right = [i for n, i in enumerate(items) if n % 2 == 1][:3]
    fh, fb = cond(int(size * .033)), body(int(size * .0195))
    for col, side in ((left, "l"), (right, "r")):
        y = int(size * .21)
        for title, sub in col:
            x = int(size * .045) if side == "l" else int(size * .60)
            w = int(size * .34)
            d.text((x, y), title.upper(), font=fh, fill=RED)
            ly = y + int(size * .042)
            for ln in wrap(d, sub, fb, w)[:3]:
                d.text((x, ly), ln, font=fb, fill=(48, 52, 60)); ly += int(size * .026)
            ax = x + w if side == "l" else x
            d.line([(ax, y + int(size * .02)),
                    (size // 2 - (int(size * .17) if side == "l" else -int(size * .17)),
                     y + int(size * .02))], fill=(150, 155, 163), width=3)
            d.ellipse([ax - 9, y + int(size * .02) - 9, ax + 9, y + int(size * .02) + 9], fill=RED)
            y += int(size * .245)
    return canvas

def angle_grid(images, labels=None, headline="360 view", accent="every angle covered", size=CANVAS):
    """Four-up grid of angles. Great when several studio shots already exist."""
    canvas = gradient((size, size), (245, 246, 248), (223, 226, 231))
    d = ImageDraw.Draw(canvas)
    f1 = display(int(size * .052))
    m = int(size * .045)
    d.text((m, int(size * .04)), headline.upper(), font=f1, fill=BLACK)
    wln = d.textlength(headline.upper(), font=f1)
    d.text((m + wln + 16, int(size * .04)), accent.upper(), font=f1, fill=RED)
    red_rule(d, m, int(size * .04) + int(size * .066), int(size * .10), 8)

    top = int(size * .18)
    cell = (size - m * 2 - int(size * .02)) // 2
    labels = labels or ["Front view", "Side view", "Top view", "Angled view"]
    for i, im in enumerate(images[:4]):
        cx = m + (i % 2) * (cell + int(size * .02))
        cy = top + (i // 2) * (cell + int(size * .02))
        d.rounded_rectangle([cx, cy, cx + cell, cy + cell], radius=18, fill=WHITE)
        p, bb = cutout(im); p = p.crop(bb)
        p = fit(p, int(cell * .78), int(cell * .70))
        px = cx + (cell - p.width) // 2
        py = cy + (cell - p.height) // 2 + int(cell * .05)
        canvas.paste(p, (px, py), p)
        d = ImageDraw.Draw(canvas)
        tag = labels[i] if i < len(labels) else ""
        tw = d.textlength(tag.upper(), font=cond(int(size * .022)))
        d.rectangle([cx + 16, cy + 16, cx + 40 + tw, cy + 16 + int(size * .04)], fill=BLACK)
        d.rectangle([cx + 16, cy + 16, cx + 24, cy + 16 + int(size * .04)], fill=RED)
        d.text((cx + 34, cy + 22), tag.upper(), font=cond(int(size * .022)), fill=WHITE)
    return canvas

# ------------------------------------------------------------------ compliance
def audit_image(im, is_main=False):
    """Checks an image against Amazon's published rules."""
    out = []
    w, h = im.size
    longest = max(w, h)
    if longest < MIN_SIDE:
        out.append(("error", f"{w}x{h}. Under {MIN_SIDE} px on the longest side, so zoom is disabled."))
    elif longest < 1600:
        out.append(("warn", f"{w}x{h}. Works, but 2000 px is the 2026 recommendation."))
    if longest > MAX_SIDE:
        out.append(("error", f"Longest side {longest} px exceeds the {MAX_SIDE} px maximum."))
    if max(w, h) / max(1, min(w, h)) > 5:
        out.append(("error", "Aspect ratio wider than 5:1."))
    if is_main:
        rgb = to_rgb(im)
        px = rgb.load()
        pts = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
               (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)]
        bad = [p for p in pts if px[p] != (255, 255, 255)]
        if bad:
            out.append(("error", f"Background is not pure white at {len(bad)} of {len(pts)} sampled "
                                 f"edge points. Amazon samples these and suppresses the listing."))
        prod, bbox = cutout(rgb)
        fillpc = ((bbox[2] - bbox[0]) * (bbox[3] - bbox[1])) / (w * h)
        if fillpc < 0.55:
            out.append(("warn", f"Product occupies roughly {fillpc*100:.0f}% of the frame. "
                                "Amazon wants 85% or more of the longest dimension filled."))
        if w != h:
            out.append(("warn", "Not square. 1:1 is the convention for the main image."))
    if not out:
        out.append(("ok", f"{w}x{h}, compliant."))
    return out

def encode(im, quality=JPEG_Q):
    """sRGB JPEG under Amazon's 10 MB cap."""
    for q in (quality, 88, 82, 76, 70):
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "JPEG", quality=q, subsampling=0, optimize=True, dpi=(72, 72))
        if buf.tell() <= MAX_BYTES:
            return buf.getvalue()
    return buf.getvalue()

def safe_asin(s):
    s = re.sub(r"[^A-Za-z0-9]", "", s or "")
    return s.upper() or "PRODUCT"

def filename(asin, slot):
    """Amazon's convention: ASIN.MAIN.jpg, ASIN.PT01.jpg — no spaces or dashes."""
    return f"{safe_asin(asin)}.MAIN.jpg" if slot == 0 else f"{safe_asin(asin)}.PT{slot:02d}.jpg"

def build_zip(pairs):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in pairs:
            z.writestr(name, data)
    return buf.getvalue()

# ------------------------------------------------------------------ slot plan
SLOT_PLAN = [
    (0,  "Main",            "Pure white, product only, 85% fill. No text, logos or props — this is "
                            "the one slot Amazon actively suppresses."),
    (1,  "Hero benefit",    "The single strongest reason to buy, as a headline over the product."),
    (2,  "Feature callouts","Exploded or annotated view naming the parts. Carries the most detail."),
    (3,  "Certification",   "Standards, testing and compliance badges. Removes the safety objection."),
    (4,  "Material or build","What it is made of and why that matters."),
    (5,  "Scale or spec",   "Weight, dimensions or fit, so nobody guesses and returns it."),
    (6,  "Lifestyle in use","The product in its real context. Needs a background photo from you."),
    (7,  "Angle grid",      "Every angle in one frame, for shoppers who will not swipe."),
    (8,  "What is included","Everything in the box, so expectations match delivery."),
]


def spec_card(src, headline, accent, stat, stat_label, chips=None, size=CANVAS, bg=None):
    """Big statistic left, product right, icon chips along the bottom.
    Use for weight, capacity, dimensions — the numbers that stop returns."""
    if bg is not None:
        canvas = fit(to_rgb(bg), size, size).resize((size, size), Image.LANCZOS)
        canvas = Image.alpha_composite(canvas.convert("RGBA"),
                                       Image.new("RGBA", (size, size), (245, 246, 248, 165))).convert("RGB")
    else:
        canvas = gradient((size, size), (250, 250, 252), (219, 223, 229))
    d = ImageDraw.Draw(canvas)
    d.polygon([(0, 0), (int(size * .30), 0), (0, int(size * .30))], fill=BLACK)
    d.polygon([(0, 0), (int(size * .17), 0), (0, int(size * .17))], fill=RED)

    prod, bbox = cutout(src); prod = prod.crop(bbox)
    prod = fit(prod, int(size * .55), int(size * .46))
    pos = (size - prod.width - int(size * .06), int(size * .30))
    canvas = shadow(canvas, prod, pos, blur=48, opacity=115)
    canvas.paste(prod, pos, prod)

    d = ImageDraw.Draw(canvas)
    m = int(size * .055)
    f1 = display(int(size * .062))
    y = int(size * .10)
    y = draw_lines(d, (m, y), wrap(d, headline.upper(), f1, size * .55), f1, BLACK)
    if accent:
        y = draw_lines(d, (m, y), wrap(d, accent.upper(), f1, size * .55), f1, RED)
    red_rule(d, m, y + 12, int(size * .10), 9)

    if stat:
        fs = display(int(size * .14))
        d.text((m, int(size * .42)), str(stat), font=fs, fill=BLACK)
        w = d.textlength(str(stat), font=fs)
        d.text((m + w + 12, int(size * .50)), stat_label or "", font=cond(int(size * .04)), fill=RED)

    for i, (t, s2) in enumerate((chips or [])[:3]):
        cw = (size - m * 2) // 3
        x = m + i * cw
        yy = int(size * .84)
        d.rounded_rectangle([x, yy, x + cw - 18, yy + int(size * .10)], radius=14,
                            fill=WHITE, outline=(214, 218, 224), width=3)
        d.rectangle([x, yy, x + 10, yy + int(size * .10)], fill=RED)
        d.text((x + 30, yy + int(size * .018)), t.upper(), font=cond(int(size * .028)), fill=BLACK)
        if s2:
            d.text((x + 30, yy + int(size * .058)), s2, font=body(int(size * .019)), fill=(90, 96, 106))
    return canvas


TEMPLATES = {
    "Main — pure white":      "main",
    "Hero benefit":           "hero",
    "Feature callouts":       "callouts",
    "Certification badges":   "badge",
    "Spec or statistic":      "spec",
    "Angle grid":             "grid",
}


def render(kind, src, cfg, extras=None, bg=None, size=CANVAS):
    """One entry point the UI can call for any template."""
    if kind == "main":
        return main_image(src, size)
    if kind == "hero":
        return hero(src, cfg.get("headline", ""), cfg.get("accent", ""),
                    cfg.get("subline", ""), size, bg=bg)
    if kind == "callouts":
        return callouts(src, cfg.get("items", []), cfg.get("headline", ""), size)
    if kind == "badge":
        return badge_card(src, cfg.get("headline", "Certified for"), cfg.get("accent", "safety"),
                          cfg.get("items", []), size, bg=bg)
    if kind == "spec":
        return spec_card(src, cfg.get("headline", ""), cfg.get("accent", ""),
                         cfg.get("stat", ""), cfg.get("stat_label", ""),
                         cfg.get("items", []), size, bg=bg)
    if kind == "grid":
        return angle_grid([src] + list(extras or []), cfg.get("labels"),
                          cfg.get("headline", "360 view"), cfg.get("accent", "every angle covered"),
                          size)
    return main_image(src, size)


# ------------------------------------------------------------------ auto plan
CERT_RE  = re.compile(r"certif|standard|dot\b|ece\b|astm|cpsc|iso\b|fmvss|tested|compliance", re.I)
STAT_RE  = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|g|lb|lbs|oz|ml|l|litre|liter|cm|mm|inch|inches|hours?|hrs?)", re.I)
USE_RE   = re.compile(r"\bfor\b|use|ride|commut|travel|touring|daily|everyday", re.I)


def features_from_copy(title="", bullets=None, attributes=None):
    """Pulls (heading, detail) pairs out of whatever copy is available."""
    out, seen = [], set()
    for b in (bullets or []):
        b = re.sub(r"\s+", " ", str(b)).strip()
        if not b: continue
        head, _, body = b.partition(":")
        if not body: head, body = "", b
        detail = body.split(";")[0].strip()
        head = (head or " ".join(detail.split()[:2])).strip().title()
        k = head.lower()
        if head and detail and k not in seen:
            seen.add(k); out.append((head, detail))
    for a in (attributes or []):
        a = re.sub(r"\s+", " ", str(a)).strip()
        if not a: continue
        head, _, body = a.partition("|")
        head, detail = head.strip().title(), (body.strip() or a.strip())
        if head.lower() in seen: continue
        seen.add(head.lower()); out.append((head, detail))
    if not out and title:
        for seg in re.split(r"\s*[|,]\s*", title):
            seg = seg.strip()
            if len(seg.split()) >= 2 and seg.lower() not in seen:
                seen.add(seg.lower()); out.append((" ".join(seg.split()[:2]).title(), seg))
    return out


def plan_from_copy(title="", bullets=None, attributes=None, brand="",
                   have_bg=False, n_extra=0, target=6):
    """Decides the image set: which template goes in which slot, and what copy
    each one carries. Strongest material first, per Amazon's slot conventions."""
    feats = features_from_copy(title, bullets, attributes)
    certs = [f for f in feats if CERT_RE.search(f[0] + " " + f[1])]
    stats = [f for f in feats if STAT_RE.search(f[0] + " " + f[1])]
    uses  = [f for f in feats if USE_RE.search(f[0] + " " + f[1])]
    lead  = feats[0] if feats else ("Built for the ride", "")

    plan = [{"kind": "main", "name": "Main — pure white", "cfg": {}}]

    plan.append({"kind": "hero", "name": "Hero benefit", "use_bg": have_bg, "cfg": {
        "headline": " ".join(lead[0].split()[:2]) or "Built for",
        "accent": " ".join(lead[0].split()[2:]) or "the ride",
        "subline": lead[1][:150]}})

    if feats:
        plan.append({"kind": "callouts", "name": "Feature callouts", "cfg": {
            "headline": "Engineered in detail", "items": feats[:6]}})

    if certs:
        plan.append({"kind": "badge", "name": "Certification", "cfg": {
            "headline": "Certified for", "accent": "safety",
            "items": [(c[0], c[1][:44]) for c in certs[:4]]}})

    if stats:
        m = STAT_RE.search(stats[0][0] + " " + stats[0][1])
        plan.append({"kind": "spec", "name": "Spec or statistic", "cfg": {
            "headline": stats[0][0], "accent": "", "stat": m.group(1),
            "stat_label": m.group(2), "items": [(f[0], f[1][:36]) for f in feats[1:4]]}})

    if have_bg:
        u = uses[0] if uses else lead
        plan.append({"kind": "hero", "name": "Lifestyle in use", "use_bg": True, "cfg": {
            "headline": "Ready for", "accent": "any road", "subline": u[1][:150]}})

    if n_extra:
        plan.append({"kind": "grid", "name": "Angle grid", "cfg": {
            "headline": "360 view", "accent": "every angle covered"}})

    if len(plan) < target and len(feats) > 3:
        plan.append({"kind": "callouts", "name": "More features", "cfg": {
            "headline": "More to know", "items": feats[3:9]}})

    return plan[:max(5, min(target, 9))]
