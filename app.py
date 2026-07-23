from __future__ import annotations

import html as _html_mod
import json
import re
import textwrap
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import streamlit as st

# ----------------------------------------------------------------------
# Policy constants
# ----------------------------------------------------------------------

TITLE_LIMIT_STANDARD = 75
TITLE_LIMIT_MEDIA = 200
HIGHLIGHT_LIMIT = 125
BULLET_HARD_LIMIT = 500
BULLET_SOFT_TARGET = 240
MAX_BULLETS_SELLER = 5
MAX_BULLETS_VENDOR = 10

BANNED_TITLE_CHARS = set("!$?_~*#^|<>{}[]@=+;\"\\")

PROMO_TERMS = [
    "best seller", "bestseller", "best-selling", "best selling", "#1", "number one",
    "top rated", "top-rated", "top selling", "hottest", "sale", "on sale",
    "discount", "cheap", "cheapest", "free shipping", "free gift",
    "money back", "money-back", "satisfaction guaranteed", "guaranteed",
    "world's best", "world class", "premium quality", "amazing", "perfect",
    "flawless", "miracle", "must have", "must-have", "limited time",
    "limited-time", "buy now", "order now", "new arrival", "brand new",
]

SAFE_STRIP = [
    "best seller", "bestseller", "best-selling", "best selling", "#1",
    "top rated", "top-rated", "top selling", "on sale", "free shipping",
    "free gift", "money back", "money-back", "satisfaction guaranteed",
    "world's best", "limited time", "limited-time", "buy now", "order now",
    "new arrival", "brand new",
]

STOPWORDS = {
    "a", "an", "the", "and", "or", "for", "with", "to", "of", "in", "on", "by",
    "at", "from", "as", "is", "it", "x", "plus",
}

BENEFIT_HINTS = {
    "stainless": "resists rust and wipes clean in seconds for hassle-free daily upkeep",
    "cotton": "stays soft against skin and highly breathable for all-day long-lasting comfort",
    "silicone": "stays flexible, heat-safe, and simple to clean under running water",
    "leather": "ages gracefully and holds a premium look over extended periods of use",
    "wood": "adds natural warmth while remaining sturdy and reliable with daily use",
    "plastic": "keeps the structural weight down and stores easily in tight spaces",
    "insulat": "holds internal temperature far longer than standard single-wall alternatives",
    "rechargeable": "tops up easily over USB connection so you avoid buying disposable batteries",
    "waterproof": "shrugs off spills, rain, and unexpected splashes without absorbing moisture",
    "compact": "slips effortlessly into small spaces and travels without adding extra bulk",
    "portable": "goes wherever you go and sets up completely in just a few seconds",
    "large": "provides ample room to spare while fitting seamlessly into your current space",
    "pack": "stocks you up generously so reordering comes around far less often",
    "set": "arrives with all necessary matching pieces that belong together, ready to use",
    "gift": "arrives ready to give for birthdays, housewarmings, and special holidays",
    "dishwasher": "goes straight onto the top rack of the dishwasher for effortless cleanup",
    "bpa": "skips harmful BPA to ensure complete safety for everyday food and beverage storage",
    "leakproof": "seals tight with a reliable gasket so nothing escapes into a bag or car seat",
    "leak": "seals tight with a reliable gasket so nothing escapes into a bag or car seat",
    "lid": "seals cleanly to protect contents and opens easily with smooth single-handed operation",
    "handle": "provides an ergonomic, secure grip even when your hands are full or wet",
    "non-slip": "stays firmly anchored in place instead of sliding around under heavy loads",
    "nonstick": "releases food cleanly with minimal residue and cuts down drastically on scrubbing time",
    "storage": "keeps essential items organized together in one place instead of scattered about",
    "battery": "delivers long-lasting power to easily get you through a full day of continuous use",
    "washable": "cleans easily in standard wash cycles and comes out fresh for the next round",
    "adjust": "dials in smoothly to give you a custom, comfortable fit or precise operational setting",
    "microwave safe": "heats up food safely straight from the fridge without needing extra transfer dishes",
    "dishwasher safe": "cleans effortlessly on the top rack instead of requiring tedious hand washing",
    "freezer safe": "handles freezing temperatures without risk of cracking, clouding, or warping",
    "oven safe": "transitions smoothly from food preparation straight into a hot oven without damage",
    "food grade": "meets strict food-contact safety standards for everyday family meal prep and storage",
    "airtight": "locks out ambient air completely so stored contents stay noticeably fresher for longer",
    "air tight": "locks out ambient air completely so stored contents stay noticeably fresher for longer",
    "stackable": "stacks neatly together in cupboards to maximize available shelf space",
    "heavy duty": "handles demanding daily workloads reliably without flexing, cracking, or wearing out",
    "unbreakable": "survives accidental drops and bumps that typically break standard alternatives",
    "glass": "will not stain, cloud, or hold onto lingering food odors the way plastic materials do",
    "borosilicate": "handles sudden temperature spikes without thermal shock or structural cracking",
    "ceramic": "distributes heat evenly across the surface and wipes clean without retaining stains",
    "toughened": "stands up to accidental surface knocks that would easily chip ordinary items",
}

GENERIC_BENEFITS = [
    "designed to handle everyday requirements with consistent, long-lasting performance",
    "delivers smooth, user-friendly operation to streamline your day-to-day routine",
    "performs its main function reliably without requiring extra tools or complicated steps",
    "crafted from durable materials engineered to hold up through repeated long-term use",
    "provides a convenient, hassle-free solution that simplifies your home or workspace",
]

# ----------------------------------------------------------------------
# Text utilities
# ----------------------------------------------------------------------

EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\u2190-\u21FF\u2B00-\u2BFF\uFE0F]"
)
HTML_RE = re.compile(r"<[^>]+>")
MULTISPACE_RE = re.compile(r"\s+")
ACRONYM_OK = {"USB", "LED", "HD", "UV", "BPA", "XL", "XXL", "XXXL", "USA", "PU",
              "TPU", "3D", "4K", "SPF", "ML", "OZ", "PCS", "ABS", "PVC", "EVA"}

BULLET_MARKER_RE = re.compile(r"^\s*(?:[\u2022\u2023\u25CF\u25AA\u00B7\-\*\u2013\u2014]+|\(?\d{1,2}[\.\)])\s*")


def clean_ws(s: str) -> str:
    return MULTISPACE_RE.sub(" ", (s or "").strip())


def char_count(s: str) -> int:
    return len(s or "")


def strip_emoji(s: str) -> str:
    return EMOJI_RE.sub("", s or "")


def strip_html(s: str) -> str:
    return HTML_RE.sub("", s or "")


def esc(s: str) -> str:
    return _html_mod.escape(s or "")


def norm(s: str) -> str:
    return clean_ws(re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()))


def find_promo_terms(s: str) -> list:
    low = f" {(s or '').lower()} "
    return sorted({t for t in PROMO_TERMS
                   if re.search(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])", low)})


def find_banned_chars(s: str, allow: str = "") -> list:
    allow_set = set(allow or "")
    return sorted({c for c in (s or "") if c in BANNED_TITLE_CHARS and c not in allow_set})


def is_shouting(word: str) -> bool:
    core = re.sub(r"[-/]", "", word or "")
    if not core.isalpha() or len(core) < 4 or not word.isupper():
        return False
    parts = [p for p in re.split(r"[-/]", word) if p]
    return not all(p.upper() in ACRONYM_OK or len(p) <= 2 for p in parts)


def find_allcaps_words(s: str) -> list:
    return [w for w in re.findall(r"[A-Za-z][A-Za-z0-9\-/]*", s or "") if is_shouting(w)]


def find_repeated_words(s: str) -> list:
    seen, dupes = set(), []
    for w in re.findall(r"[A-Za-z0-9]+", (s or "").lower()):
        if w in STOPWORDS or len(w) <= 2:
            continue
        if w in seen and w not in dupes:
            dupes.append(w)
        seen.add(w)
    return dupes


def titlecase_word(w: str) -> str:
    return w.upper() if w.upper() in ACRONYM_OK else w[:1].upper() + w[1:].lower()


def trim_to(s: str, limit: int) -> tuple:
    s = clean_ws(s)
    if char_count(s) <= limit:
        return s, ""
    cut = s[:limit]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return clean_ws(cut).rstrip(",;- "), clean_ws(s[len(cut):]).lstrip(",;- ")


def parse_pasted_lines(text: str) -> list:
    out = []
    for raw in (text or "").splitlines():
        line = BULLET_MARKER_RE.sub("", raw)
        line = clean_ws(line)
        if line:
            out.append(line)
    return out


def parse_features(text: str) -> list:
    rows = []
    for line in parse_pasted_lines(text):
        feat, ben = line, ""
        m = re.split(r"\s*(?::|\||\s[\u2013\u2014-]\s)\s*", line, maxsplit=1)
        if len(m) == 2 and len(m[0]) >= 3:
            feat, ben = m[0], m[1]
        rows.append((clean_ws(feat), clean_ws(ben)))
    return rows

# ----------------------------------------------------------------------
# Audit engine
# ----------------------------------------------------------------------

SEV_ERROR, SEV_WARN, SEV_OK = "error", "warn", "ok"


@dataclass
class Issue:
    severity: str
    message: str


@dataclass
class FieldAudit:
    field: str
    value: str
    count: int
    limit: int
    issues: list = field(default_factory=list)

    @property
    def errors(self):
        return [i for i in self.issues if i.severity == SEV_ERROR]

    @property
    def warns(self):
        return [i for i in self.issues if i.severity == SEV_WARN]


def audit_title(title: str, brand: str = "", media: bool = False) -> FieldAudit:
    title = title or ""
    limit = TITLE_LIMIT_MEDIA if media else TITLE_LIMIT_STANDARD
    a = FieldAudit("Title", title, char_count(title), limit)

    if not title.strip():
        a.issues.append(Issue(SEV_ERROR, "Title is empty."))
        return a
    if a.count > limit:
        a.issues.append(Issue(SEV_ERROR,
            f"{a.count} chars, {a.count - limit} over the {limit}-char cap. From 27 Jul 2026 "
            f"Amazon auto-rewrites over-limit titles. Move the overflow to Item Highlights."))
    elif a.count > limit * 0.95:
        a.issues.append(Issue(SEV_WARN, f"{a.count}/{limit}, right at the cap. Leave some headroom."))

    banned = find_banned_chars(title, allow=brand)
    if banned:
        a.issues.append(Issue(SEV_ERROR, "Special characters not allowed outside brand: " + " ".join(banned)))
    if strip_emoji(title) != title:
        a.issues.append(Issue(SEV_ERROR, "Emoji are not allowed in titles."))
    promo = find_promo_terms(title)
    if promo:
        a.issues.append(Issue(SEV_ERROR, "Promotional claims found: " + ", ".join(promo[:6])))
    caps = find_allcaps_words(title)
    if caps:
        a.issues.append(Issue(SEV_WARN, "ALL-CAPS words discouraged: " + ", ".join(caps[:6])))
    dupes = find_repeated_words(title)
    if dupes:
        a.issues.append(Issue(SEV_WARN, "Repeated words risk: " + ", ".join(dupes[:6])))

    if not a.errors and not a.warns:
        a.issues.append(Issue(SEV_OK, f"Compliant. {a.count}/{limit} chars."))
    return a


def audit_highlights(text: str) -> FieldAudit:
    text = text or ""
    a = FieldAudit("Item Highlights", text, char_count(text), HIGHLIGHT_LIMIT)
    if not text.strip():
        a.issues.append(Issue(SEV_WARN, "Empty. Highlights are searchable; populate this field."))
        return a
    if a.count > HIGHLIGHT_LIMIT:
        a.issues.append(Issue(SEV_ERROR, f"{a.count}/{HIGHLIGHT_LIMIT}, over Item Highlights cap."))
    if strip_html(text) != text:
        a.issues.append(Issue(SEV_ERROR, "HTML tags are not allowed."))
    if strip_emoji(text) != text:
        a.issues.append(Issue(SEV_WARN, "Emoji present. Keep highlights plain text."))
    promo = find_promo_terms(text)
    if promo:
        a.issues.append(Issue(SEV_WARN, "Promotional wording: " + ", ".join(promo[:6])))
    if not a.errors and not a.warns:
        a.issues.append(Issue(SEV_OK, f"Good. {a.count}/{HIGHLIGHT_LIMIT} chars."))
    return a


def audit_bullet(text: str, idx: int) -> FieldAudit:
    text = text or ""
    a = FieldAudit(f"Bullet {idx}", text, char_count(text), BULLET_HARD_LIMIT)
    if not text.strip():
        a.issues.append(Issue(SEV_WARN, "Empty bullet."))
        return a
    if a.count > BULLET_HARD_LIMIT:
        a.issues.append(Issue(SEV_ERROR, f"{a.count}/{BULLET_HARD_LIMIT}, over Amazon's per-bullet cap."))
    elif a.count < 80:
        a.issues.append(Issue(SEV_WARN, f"Bullet is too short ({a.count} chars). Elaborate with clear features and benefits."))
    elif a.count > BULLET_SOFT_TARGET:
        a.issues.append(Issue(SEV_WARN, f"{a.count} chars, long for mobile. Target {BULLET_SOFT_TARGET} or under."))
    first = text.strip()[:1]
    if first and first.isalpha() and not first.isupper():
        a.issues.append(Issue(SEV_WARN, "Should start with a capital letter."))
    if text.strip().endswith((".", "!", "?", ";")):
        a.issues.append(Issue(SEV_WARN, "Ends with punctuation. Amazon guidelines require sentence fragments."))
    if strip_html(text) != text:
        a.issues.append(Issue(SEV_ERROR, "HTML tags not allowed in bullets."))
    if strip_emoji(text) != text:
        a.issues.append(Issue(SEV_WARN, "Emoji present. Keep bullets plain text."))
    promo = find_promo_terms(text)
    if promo:
        a.issues.append(Issue(SEV_WARN, "Promotional or pricing language: " + ", ".join(promo[:6])))
    if not a.errors and not a.warns:
        a.issues.append(Issue(SEV_OK, f"Good length. {a.count} chars."))
    return a


def health_score(audits: list) -> tuple:
    score = 100
    for a in audits:
        score -= 18 * len(a.errors) + 5 * len(a.warns)
    score = max(0, min(100, score))
    grade = ("A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70
             else "D" if score >= 55 else "F")
    return score, grade

# ----------------------------------------------------------------------
# Fixers & Elaborators
# ----------------------------------------------------------------------

def _strip_terms(text: str, terms: list) -> str:
    for term in terms:
        text = re.sub(r"(?i)(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", " ", text)
    return clean_ws(text)


def _tidy_punct(text: str) -> str:
    t = clean_ws(text)
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    t = re.sub(r"([,.;:!?])\s*(?=[,.;:!?])", "", t)
    t = re.sub(r"^[\s,.;:!?\-]+", "", t)
    t = re.sub(r"[\s,.;:!?\-]+$", "", t)
    return clean_ws(t)


def fix_title(title: str, brand: str = "", media: bool = False) -> tuple:
    limit = TITLE_LIMIT_MEDIA if media else TITLE_LIMIT_STANDARD
    t = clean_ws(strip_emoji(strip_html(title)))

    if brand and brand in t:
        head, _sep, tail = t.partition(brand)
        head = "".join(c for c in head if c not in BANNED_TITLE_CHARS)
        tail = "".join(c for c in tail if c not in BANNED_TITLE_CHARS)
        t = f"{head}{brand}{tail}"
    else:
        t = "".join(c for c in t if c not in BANNED_TITLE_CHARS)

    t = _tidy_punct(_strip_terms(clean_ws(t), PROMO_TERMS))
    brand_words = set(brand.split()) if brand else set()

    def _deshout(m):
        w = m.group(0)
        return w if w in brand_words else (titlecase_word(w) if is_shouting(w) else w)

    t = re.sub(r"[A-Za-z][A-Za-z0-9\-/]*", _deshout, t)

    seen, kept = set(), []
    for tok in t.split(" "):
        key = re.sub(r"[^a-z0-9]", "", tok.lower())
        if key and key not in STOPWORDS and len(key) > 2:
            if key in seen:
                continue
            seen.add(key)
        kept.append(tok)
    return trim_to(clean_ws(" ".join(kept)), limit)


def fix_highlights(text: str, appended: str = "") -> str:
    h = clean_ws(strip_emoji(strip_html(text)))
    add = clean_ws(appended)
    if add:
        h = clean_ws(f"{h}, {add}") if h else add
    return trim_to(clean_ws(h).strip(",;- "), HIGHLIGHT_LIMIT)[0]


def _benefit_for(feature: str, used: set = None) -> str:
    low = (feature or "").lower()
    for key, benefit in BENEFIT_HINTS.items():
        if key in low and (used is None or benefit not in used):
            return benefit
    for g in GENERIC_BENEFITS:
        if used is None or g not in used:
            return g
    return GENERIC_BENEFITS[0]


def fix_bullet(text: str) -> str:
    """Cleans bullets and expands short fragments/points into detailed feature: benefit formats."""
    b = _tidy_punct(_strip_terms(clean_ws(strip_html(strip_emoji(text))), SAFE_STRIP))
    if not b:
        return ""

    # Check if bullet has existing feature: benefit structure
    m = re.split(r"\s*(?::|\||\s[\u2013\u2014-]\s)\s*", b, maxsplit=1)
    if len(m) == 2 and len(m[0]) >= 3:
        feature, benefit = m[0], m[1]
        if len(benefit) < 30:
            benefit = f"{benefit}, {GENERIC_BENEFITS[0]}"
    else:
        feature = b
        benefit = _benefit_for(feature)

    feature_head = feature.strip().rstrip(":")
    if len(feature_head) <= 28:
        feature_head = feature_head.upper()
    else:
        feature_head = feature_head[:1].upper() + feature_head[1:]

    formatted = f"{feature_head}: {benefit}"

    # Strip ending punctuation for Amazon sentence fragment rules
    formatted = formatted.rstrip(".!?;")
    return trim_to(formatted, BULLET_HARD_LIMIT)[0]

# ----------------------------------------------------------------------
# Smart title deconstruction
# ----------------------------------------------------------------------

_UNITS = (r"fl\.?\s?oz|fluid\s?ounces?|ounces?|oz|millilit(?:er|re)s?|ml|"
          r"lit(?:er|re)s?|ltr|gallons?|gal|quarts?|qt|pints?|pt|"
          r"kilograms?|kgs?|milligrams?|mg|grams?|gm|pounds?|lbs?|"
          r"inch(?:es)?|cm|mm|feet|ft|meters?|watts?|volts?|mah|"
          r"sq\.?\s?ft|g|kg|lb|in|l|w|v|m")
SIZE_RE = re.compile(r"\b\d+(?:[\.,]\d+)?\s*(?:" + _UNITS + r")\b", re.I)
PACK_RE = re.compile(
    r"\b(?:pack\s+of\s+\d+|set\s+of\s+\d+|box\s+of\s+\d+|"
    r"\d+\s*[-\s]?(?:pack|pk|pcs?|pieces?|count|ct|units?)\b)", re.I)
DIMENSION_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:x|\u00D7|\*)\s*\d+(?:\.\d+)?"
    r"(?:\s*(?:x|\u00D7|\*)\s*\d+(?:\.\d+)?)?"
    r"\s*(?:cm|mm|inch(?:es)?|in|ft|feet|m)?\b", re.I)

PRODUCT_TYPE_LEXICON = [
    "stainless steel water bottle", "insulated water bottle", "water bottle", "coffee mug",
    "travel mug", "mixing bowl", "serving bowl", "salad bowl", "cereal bowl", "soup bowl",
    "storage container", "lunch box", "tiffin box", "french press", "cutting board",
    "frying pan", "pressure cooker", "dinner set", "bed sheet", "yoga mat", "yoga block",
    "running shoes", "hiking boots", "laptop stand", "phone case", "power bank",
    "smart watch", "air fryer", "vacuum cleaner", "hand blender", "water purifier",
    "room heater", "table lamp", "wall clock", "photo frame", "door mat", "pillow cover",
    "towel set", "shoe rack", "spice rack", "trash can", "dish rack", "ice tray",
    "protein powder", "face wash", "hair oil", "essential oil", "body lotion",
    "colloidal silver", "mineral supplement", "dietary supplement",
    "headphones", "earphones", "earbuds", "speaker", "charger", "keyboard", "monitor",
    "backpack", "wallet", "handbag", "sandals", "sneakers", "t shirt", "tshirt",
    "bowl", "bottle", "mug", "cup", "plate", "tumbler", "jar", "container", "box",
    "pan", "pot", "kettle", "knife", "spoon", "fork", "tray", "basket", "rack",
    "shoes", "shirt", "pants", "jacket", "socks", "bag", "belt", "watch", "cable",
    "mouse", "lamp", "chair", "table", "desk", "mat", "rug", "pillow", "blanket",
    "towel", "brush", "comb", "shampoo", "soap", "cream", "serum", "oil", "capsules",
    "tablets", "powder", "supplement", "toy", "puzzle", "pen", "notebook", "marker",
]


def detect_product_type(text: str) -> tuple:
    t = clean_ws(text)
    if not t:
        return "", "none"
    low = norm(t)
    for noun in sorted(PRODUCT_TYPE_LEXICON, key=len, reverse=True):
        if re.search(r"(?<![a-z0-9])" + re.escape(noun) + r"(?![a-z0-9])", low):
            m = re.search(r"(?i)(?<![a-z0-9])" + re.escape(noun) + r"(?![a-z0-9])", t)
            return (clean_ws(m.group(0)) if m else noun.title()), "known"
    words = [w for w in t.split() if w]
    if not words:
        return "", "none"
    guess = " ".join(words[-2:]) if len(words) >= 2 else words[-1]
    return clean_ws(guess), "guess"

COLOR_WORDS = {
    "black", "white", "grey", "gray", "silver", "gold", "rose gold", "blue", "navy",
    "red", "green", "pink", "purple", "violet", "yellow", "orange", "brown", "beige",
    "cream", "ivory", "clear", "transparent", "amber", "teal", "maroon", "charcoal",
    "matte black", "multicolor", "multicolour", "assorted",
}
MATERIAL_WORDS = {
    "glass", "borosilicate", "stainless steel", "steel", "plastic", "silicone",
    "ceramic", "porcelain", "bamboo", "wood", "wooden", "leather", "cotton",
    "polyester", "nylon", "aluminium", "aluminum", "copper", "brass", "melamine",
    "acrylic", "rubber", "tpu", "abs", "pvc", "titanium", "carbon fiber",
}

PHRASE_SPLIT_RE = re.compile(r"\s*(?:[,;|/]|\s[\u2013\u2014-]\s)\s*")

ATTRIBUTE_PHRASES = [
    "microwave safe", "dishwasher safe", "freezer safe", "oven safe", "refrigerator safe",
    "bpa free", "food grade", "lead free", "odor free", "odour free",
    "leak proof", "leakproof", "spill proof", "spillproof", "air tight", "airtight",
    "non stick", "nonstick", "non slip", "non-slip", "scratch resistant",
    "stain resistant", "heat resistant", "shatter proof", "shatterproof",
    "eco friendly", "easy to clean", "easy clean", "unbreakable", "reusable",
    "stackable", "space saving", "heavy duty", "long lasting", "quick dry",
]


def is_use_case(phrase: str) -> bool:
    low = f" {norm(phrase)} "
    return low.strip().startswith("for ") or " or " in low


def _split_unpunctuated(chunk: str) -> list:
    rest = chunk
    extracted = []

    def pull(vocab):
        nonlocal rest
        for ph in sorted(vocab, key=len, reverse=True):
            if len(ph) < 4:
                continue
            m = re.search(r"(?i)(?<![a-z0-9])" + re.escape(ph) + r"(?![a-z0-9])", rest)
            if m:
                extracted.append(clean_ws(m.group(0)))
                rest = _remove_phrase(rest, m.group(0))

    pull(ATTRIBUTE_PHRASES)
    pull(MATERIAL_WORDS)
    pull(COLOR_WORDS)
    rest = _tidy_punct(clean_ws(rest))

    tail = ""
    m = re.search(r"(?i)(?<![a-z0-9])for\s+\S.*$", rest)
    if m and m.start() > 0:
        tail = clean_ws(m.group(0))
        rest = _tidy_punct(clean_ws(rest[:m.start()]))

    return ([rest] if rest else []) + extracted + ([tail] if tail else [])


def _remove_phrase(text: str, phrase: str) -> str:
    if not phrase:
        return text
    return re.sub(r"(?i)(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", " ", text)


def enforce_brand_first(title: str, brand: str) -> str:
    brand = clean_ws(brand)
    title = clean_ws(title)
    if not brand:
        return title
    if norm(title).startswith(norm(brand) + " ") or norm(title) == norm(brand):
        return title
    rest = _tidy_punct(_remove_phrase(title, brand))
    return clean_ws(f"{brand} {rest}") if rest else brand


def deconstruct_title(title: str, brand: str = "", product_type: str = "",
                      attr1_override: str = "", attr2_override: str = "",
                      size_override: str = "") -> dict:
    t = clean_ws(strip_emoji(strip_html(title)))

    if brand and brand in t:
        head, _s, tail = t.partition(brand)
        head = "".join(c for c in head if c not in BANNED_TITLE_CHARS)
        tail = "".join(c for c in tail if c not in BANNED_TITLE_CHARS)
        t = f"{head}{brand}{tail}"
    else:
        t = "".join(c for c in t if c not in BANNED_TITLE_CHARS)
    t = _tidy_punct(_strip_terms(clean_ws(t), PROMO_TERMS))
    t = clean_ws(t.replace("(", " ").replace(")", " "))

    attr2 = clean_ws(attr2_override)
    if not attr2:
        m = PACK_RE.search(t)
        attr2 = clean_ws(m.group(0)) if m else ""
    t = PACK_RE.sub(" ", t)

    size = clean_ws(size_override)
    found_dims = [clean_ws(m.group(0)) for m in DIMENSION_RE.finditer(t)]
    if not size and found_dims:
        size = found_dims[0]
    for d in found_dims:
        t = _remove_phrase(t, d)

    attr1 = clean_ws(attr1_override)
    found_sizes = [clean_ws(m.group(0)) for m in SIZE_RE.finditer(t)]
    if not attr1 and found_sizes:
        attr1 = found_sizes[0]
    for s in found_sizes:
        t = _remove_phrase(t, s)

    if brand:
        t = _remove_phrase(t, brand)

    ptype = clean_ws(product_type)
    ptype_conf = "given" if ptype else "none"
    if not ptype:
        ptype, ptype_conf = detect_product_type(t)
    if ptype:
        t = _remove_phrase(t, ptype)

    t = _tidy_punct(clean_ws(t))

    descriptors, seen = [], set()
    for chunk in PHRASE_SPLIT_RE.split(t):
        chunk = _tidy_punct(clean_ws(chunk))
        if not chunk:
            continue
        pieces = _split_unpunctuated(chunk)
        for piece in pieces:
            piece = _tidy_punct(clean_ws(piece))
            key = norm(piece)
            if not key or key in seen:
                continue
            seen.add(key)
            descriptors.append(piece)

    descriptors.sort(key=is_use_case)
    colors = [d for d in descriptors if norm(d) in COLOR_WORDS]
    materials = [d for d in descriptors if norm(d) in MATERIAL_WORDS]

    return {"brand": clean_ws(brand), "product_type": ptype, "product_type_confidence": ptype_conf,
            "attr1": attr1, "attr2": attr2, "size": size,
            "descriptors": descriptors, "colors": colors, "materials": materials}


def detect_from_title(title: str, brand: str = "") -> dict:
    p = deconstruct_title(title, brand=brand)
    return {"product_type": p["product_type"], "product_type_confidence": p["product_type_confidence"],
            "attr1": p["attr1"], "attr2": p["attr2"], "size": p["size"],
            "descriptors": p["descriptors"], "colors": p["colors"], "materials": p["materials"]}


def facts_from_parts(parts: dict) -> ProductFacts:
    descriptors = list(parts.get("descriptors", []))
    colors = parts.get("colors", [])
    materials = parts.get("materials", [])
    use_cases = [d for d in descriptors if is_use_case(d)]
    features = [d for d in descriptors
                if d not in colors and d not in materials and not is_use_case(d)]
    return ProductFacts(
        brand=parts.get("brand", ""), product_type=parts.get("product_type", ""),
        attr1=parts.get("attr1", ""), attr2=parts.get("attr2", ""),
        size=parts.get("size", ""),
        color=colors[0] if colors else "", material=materials[0] if materials else "",
        use_case=use_cases[0] if use_cases else "",
        features=[(f, "") for f in features])


def smart_title_rebuild(parts: dict, limit: int, minimal: bool = False) -> tuple:
    brand = parts.get("brand", "")
    ptype = parts.get("product_type", "")
    attr1 = parts.get("attr1", "")
    attr2 = parts.get("attr2", "")

    variant = ", ".join([x for x in [attr1, attr2] if x])
    if char_count(variant) > limit:
        variant = trim_to(variant, limit)[0]
    reserve = char_count(", " + variant) if variant else 0
    budget = max(0, limit - reserve)

    head = ""
    for tok in [brand, ptype]:
        if not tok:
            continue
        candidate = clean_ws(f"{head} {tok}") if head else tok
        if char_count(candidate) <= budget:
            head = candidate

    demoted = []
    for d in parts.get("descriptors", []):
        if norm(d) in norm(head):
            continue
        if minimal:
            demoted.append(d)
            continue
        candidate = clean_ws(f"{head} {d}") if head else d
        if char_count(candidate) <= budget:
            head = candidate
        else:
            demoted.append(d)

    title = clean_ws(f"{head}, {variant}") if (head and variant) else (head or variant)
    title = enforce_brand_first(title, brand)
    title, cut = trim_to(title, limit)
    if cut:
        demoted.append(cut)
    return title, demoted

# ----------------------------------------------------------------------
# Builders
# ----------------------------------------------------------------------

@dataclass
class ProductFacts:
    brand: str = ""
    product_type: str = ""
    item_name: str = ""
    primary_keyword: str = ""
    secondary_keywords: str = ""
    attr1: str = ""
    attr2: str = ""
    size: str = ""
    color: str = ""
    material: str = ""
    audience: str = ""
    use_case: str = ""
    features: list = field(default_factory=list)


def variant_string(f: ProductFacts) -> str:
    bits = [clean_ws(f.attr1), clean_ws(f.attr2)]
    return ", ".join([b for b in bits if b])


def build_title(f: ProductFacts, media: bool = False) -> str:
    limit = TITLE_LIMIT_MEDIA if media else TITLE_LIMIT_STANDARD
    variant = variant_string(f)
    if char_count(variant) > limit:
        variant = trim_to(variant, limit)[0]

    reserve = char_count(", " + variant) if variant else 0
    budget = max(0, limit - reserve)

    ptype = clean_ws(f.product_type or f.item_name)
    head_tokens = [clean_ws(f.brand), ptype]
    if f.item_name and norm(f.item_name) not in norm(ptype):
        head_tokens.append(clean_ws(f.item_name))
    if f.primary_keyword and norm(f.primary_keyword) not in norm(" ".join(head_tokens)):
        head_tokens.append(clean_ws(f.primary_keyword))

    head = ""
    for tok in head_tokens:
        if not tok:
            continue
        candidate = clean_ws(f"{head} {tok}")
        if char_count(candidate) > budget:
            continue
        head = candidate

    if not head and variant:
        title = variant
    elif variant:
        title = clean_ws(f"{head}, {variant}")
    else:
        title = head

    title = enforce_brand_first(title, f.brand)
    return fix_title(title, brand=f.brand, media=media)[0]


def build_highlights(f: ProductFacts, title: str, extra_keywords: list = None) -> str:
    title_tokens = set(norm(title).split())
    candidates = [f.material, f.color, f.use_case, f.audience]
    candidates += [k for k in (f.secondary_keywords or "").split(",")]
    candidates += list(extra_keywords or [])
    candidates += [feat for feat, _b in f.features]

    picks, seen = [], set()
    for c in candidates:
        c = clean_ws(c)
        if not c:
            continue
        core = norm(c)
        if not core or core in seen:
            continue
        if all(tok in title_tokens for tok in core.split()):
            continue
        seen.add(core)
        picks.append(c[:1].upper() + c[1:])

    out = ""
    for p in picks:
        candidate = f"{out}, {p}" if out else p
        if char_count(candidate) > HIGHLIGHT_LIMIT:
            continue
        out = candidate
    return out


def build_bullets(f: ProductFacts, max_bullets: int = MAX_BULLETS_SELLER) -> list:
    rows, used_benefits = [], set()

    def take(feature: str, given: str = "") -> str:
        b = clean_ws(given) or _benefit_for(feature, used_benefits)
        used_benefits.add(b)
        return b

    for feat, benefit in f.features:
        feat = clean_ws(feat)
        if feat:
            rows.append((feat, take(feat, benefit)))

    if f.attr1 or f.attr2:
        a1_txt, a2_txt = clean_ws(f.attr1), clean_ws(f.attr2)
        bits = [x for x in [a1_txt, a2_txt] if x]
        lead = ("Attributes" if (a1_txt and a2_txt) else "Specifications")
        rows.append((lead, take(lead, ", ".join(bits) + " engineered for everyday reliability")))
    if f.size:
        d = clean_ws(f.size)
        rows.append((f"Size details {d}",
                     take(d, "designed to give you an optimal fit and clean dimensions")))
    if f.material:
        rows.append((f"{clean_ws(f.material)} construction", take(f.material)))
    if f.use_case:
        uc = clean_ws(f.use_case)
        rows.append((uc if uc.lower().startswith("for") else f"For {uc}",
                     take(uc, "handles the job it was made for without workarounds")))
    if f.audience:
        aud = clean_ws(f.audience)
        rows.append((f"Made {aud}" if aud.lower().startswith("for") else f"Made for {aud}",
                     take(aud, "matches what this shopper is actually looking for")))
    if f.color:
        rows.append((f"{clean_ws(f.color)} finish",
                     take(f.color, "holds a clean, consistent look in every setting")))

    bullets, seen = [], set()
    for lead, benefit in rows:
        b = fix_bullet(f"{lead}: {benefit}")
        key = norm(b)[:40]
        if not b or key in seen:
            continue
        seen.add(key)
        bullets.append(b)
        if len(bullets) >= max_bullets:
            break
    return bullets

# ----------------------------------------------------------------------
# Keyword research
# ----------------------------------------------------------------------

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

AMAZON_MARKETS = {
    "amazon.com (US)": "ATVPDKIKX0DER",
    "amazon.co.uk (UK)": "A1F83G8C2ARO7P",
    "amazon.de (DE)": "A1PA6795UKMFR9",
    "amazon.ca (CA)": "A2EUQ1WTGCTBG2",
    "amazon.in (IN)": "A21TJRUUN4KGV",
}


def _fetch_json(url: str, timeout: int = 6):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def parse_google_suggest(payload) -> list:
    try:
        if isinstance(payload, list) and len(payload) > 1 and isinstance(payload[1], list):
            return [str(s) for s in payload[1] if isinstance(s, (str, bytes))]
    except Exception:
        pass
    return []


def parse_amazon_suggest(payload) -> list:
    try:
        if isinstance(payload, dict):
            return [s.get("value", "") for s in payload.get("suggestions", [])
                    if isinstance(s, dict) and s.get("value")]
    except Exception:
        pass
    return []


def _google_once(seed: str) -> list:
    url = ("https://suggestqueries.google.com/complete/search?client=firefox&q="
           + urllib.parse.quote(seed))
    return parse_google_suggest(_fetch_json(url))


def _amazon_once(seed: str, mid: str) -> list:
    url = ("https://completion.amazon.com/api/2017/suggestions?mid=" + mid +
           "&alias=aps&limit=11&prefix=" + urllib.parse.quote(seed))
    return parse_amazon_suggest(_fetch_json(url))


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_suggestions(seed: str, source: str, mid: str, expand: bool) -> tuple:
    seed = clean_ws(seed)
    if not seed:
        return [], "Enter a seed keyword first."

    seeds = [seed]
    if expand:
        seeds += [f"{seed} {c}" for c in "abcdefghijklmnopqrstuvwxyz"]

    fn = (lambda s: _google_once(s)) if source == "Google" else (lambda s: _amazon_once(s, mid))

    results, errors = [], []
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for got in pool.map(lambda s: _safe_call(fn, s, errors), seeds):
                results.extend(got)
    except Exception as exc:
        return [], f"Could not reach {source}: {exc}"

    seen, out = set(), []
    for s in results:
        s = clean_ws(s)
        k = s.lower()
        if s and k not in seen:
            seen.add(k)
            out.append(s)

    if not out:
        detail = errors[0] if errors else "no suggestions returned"
        return [], (f"Could not reach {source} ({detail}). Suggestion lookup needs outbound "
                    f"internet access. Enter keywords manually below.")
    return out, ""


def _safe_call(fn, seed, errors: list) -> list:
    try:
        return fn(seed)
    except Exception as exc:
        errors.append(str(exc))
        return []


def keyword_coverage(keywords: list, title: str, highlights: str, bullets: list) -> list:
    fields = {
        "Title": set(norm(title).split()),
        "Highlights": set(norm(highlights).split()),
        "Bullets": set(norm(" ".join(bullets or [])).split()),
    }
    rows = []
    for kw in keywords:
        kw = clean_ws(kw)
        if not kw:
            continue
        words = [w for w in norm(kw).split() if w]
        if not words:
            continue
        hit = {name: all(w in toks for w in words) for name, toks in fields.items()}
        rows.append({"keyword": kw, **hit, "anywhere": any(hit.values())})
    return rows

# ----------------------------------------------------------------------
# Optional AI polish
# ----------------------------------------------------------------------

AI_SYSTEM = (
    "You are an Amazon catalog copywriter. Follow Amazon's 2026 rules exactly: "
    f"title <= {TITLE_LIMIT_STANDARD} characters including spaces (Media categories allow "
    f"{TITLE_LIMIT_MEDIA}); key attributes MUST appear in the title; no special "
    "characters except inside a brand name; no promotional or subjective claims; no repeated "
    "words; no ALL-CAPS words; no emoji. "
    f"Item Highlights <= {HIGHLIGHT_LIMIT} characters, plain text. "
    "Write bullets as capitalised sentence fragments with NO end punctuation, "
    f"<= {BULLET_SOFT_TARGET} characters each, detailed feature then benefit, no pricing or promo, no HTML. "
    'Return STRICT JSON only: {"title": str, "highlights": str, "bullets": [str, ...]}'
)


def ai_generate(provider: str, api_key: str, model: str, brief: str):
    st.session_state.pop("_ai_error", None)
    try:
        if provider == "Anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            msg = client.messages.create(
                model=model or "claude-sonnet-4-5", max_tokens=1200,
                system=AI_SYSTEM, messages=[{"role": "user", "content": brief}])
            raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        elif provider == "OpenAI":
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            resp = client.chat.completions.create(
                model=model or "gpt-4o-mini",
                messages=[{"role": "system", "content": AI_SYSTEM},
                          {"role": "user", "content": brief}], max_tokens=1200)
            raw = resp.choices[0].message.content
        else:
            return None
        raw = re.sub(r"^```(?:json)?|
