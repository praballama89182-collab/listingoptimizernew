"""
Listing Studio — Amazon Title · Item Highlights · Bullets (2026 rules)
=====================================================================
Three tools, one rule engine:

  • ENHANCE  — paste a title, highlights, and all your bullets in one box.
               Get a compliance audit and a corrected rewrite.
  • BUILD    — enter product facts and paste your features in one box.
               Get a compliant title, Item Highlights, and bullets.
  • KEYWORDS — pull live search suggestions from Google and Amazon, pick the
               ones worth targeting, and check whether your finished listing
               actually contains them.

Title composition rule (v2): SIZE and PACK COUNT are reserved. Characters for
them are set aside before anything else is placed, so they always survive the
75-character cap. Colour, material, audience, and use case are deliberately
pushed down into Item Highlights instead of competing for title space.

2026 policy baked in (Seller Central announcement 10 Jun 2026, enforced
27 Jul 2026; the Jan 2025 title-standards update is still in force):
  • Title <= 75 characters incl. spaces. Media (Books, Music, Video, Software)
    keeps the 200-char ceiling — one toggle in the sidebar, no browse-node picker.
  • No special characters (! $ ? etc.) except inside a brand name; no repeated
    words; no promotional language; no ALL-CAPS words; no emoji.
  • Item Highlights: searchable structured field, up to 125 characters.
  • Bullets: 5 for sellers / 10 for vendors, <= 500 chars each, capitalised
    sentence fragments with no end punctuation, feature then benefit, no HTML.

The generator is deterministic, so it runs with zero setup. Optional AI polish
is used only if a key is supplied, and its output is re-audited by the same
engine before it is shown.

Run:
    pip install -r requirements.txt
    streamlit run app.py
"""

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
    "stainless": "resists rust and wipes clean in seconds",
    "cotton": "stays soft against skin and breathable for all-day wear",
    "silicone": "stays flexible, heat-safe, and simple to clean",
    "leather": "ages well and holds a premium look over time",
    "wood": "adds natural warmth and stays sturdy with daily use",
    "plastic": "keeps the weight down and stores easily",
    "insulat": "holds temperature far longer than single-wall designs",
    "rechargeable": "tops up over USB so you are not buying batteries",
    "waterproof": "shrugs off spills, rain, and splashes",
    "compact": "slips into small spaces and travels without bulk",
    "portable": "goes wherever you go and sets up in seconds",
    "large": "leaves room to spare without taking over the space",
    "pack": "stocks you up so reordering comes around less often",
    "set": "arrives with the pieces that belong together, ready to use",
    "gift": "arrives ready to give for birthdays and holidays",
    "dishwasher": "goes straight in the dishwasher when you are done",
    "bpa": "skips BPA so it is safe for everyday food and drink",
    "leakproof": "seals tight so nothing escapes into a bag or car seat",
    "leak": "seals tight so nothing escapes into a bag or car seat",
    "lid": "seals cleanly and opens one-handed",
    "handle": "gives you a secure grip even when your hands are full",
    "non-slip": "stays put instead of sliding around under load",
    "nonstick": "releases food cleanly and cuts down on scrubbing",
    "storage": "keeps everything in one place instead of scattered",
    "battery": "runs long enough to get through a full day of use",
    "washable": "goes in the wash and comes out ready for the next round",
    "adjust": "dials in to your preferred fit or setting",
    "microwave safe": "goes straight from fridge to microwave without changing dishes",
    "dishwasher safe": "goes on the top rack instead of being washed by hand",
    "freezer safe": "handles the freezer without cracking or warping",
    "oven safe": "moves from prep straight into the oven",
    "food grade": "meets food-contact standards for everyday eating and drinking",
    "airtight": "keeps air out so contents stay fresh for longer",
    "air tight": "keeps air out so contents stay fresh for longer",
    "stackable": "stacks together so it takes up less cupboard space",
    "heavy duty": "takes daily loads without flexing or cracking",
    "unbreakable": "survives the drops that end most alternatives",
    "glass": "will not stain or hold onto smells the way plastic does",
    "borosilicate": "handles sudden temperature changes without cracking",
    "ceramic": "heats evenly and wipes clean without staining",
    "toughened": "stands up to knocks that would chip ordinary material",
}

GENERIC_BENEFITS = [
    "covers the everyday job people buy this for",
    "keeps day-to-day use simple and predictable",
    "does its part without extra steps or fuss",
    "holds up to repeated use over time",
    "is one less thing to think about once it is set up",
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

# Leading bullet markers people paste in from Seller Central or a doc.
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
    """True only for genuinely SHOUTED words. Model numbers (WH-1000XM5),
    sizes (18/8), and acronyms including hyphen-joined ones (USB-C) are spared."""
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
    """Trim on a word boundary. Returns (kept, overflow)."""
    s = clean_ws(s)
    if char_count(s) <= limit:
        return s, ""
    cut = s[:limit]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return clean_ws(cut).rstrip(",;- "), clean_ws(s[len(cut):]).lstrip(",;- ")


def parse_pasted_lines(text: str) -> list:
    """One item per line, with any leading bullet glyph or numbering removed."""
    out = []
    for raw in (text or "").splitlines():
        line = BULLET_MARKER_RE.sub("", raw)
        line = clean_ws(line)
        if line:
            out.append(line)
    return out


def parse_features(text: str) -> list:
    """Each line is a feature. 'Feature: benefit', 'Feature - benefit', or
    'Feature | benefit' splits into a pair; a bare line leaves benefit blank."""
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
        a.issues.append(Issue(SEV_ERROR,
                              "Special characters are not allowed outside a brand name: " + " ".join(banned)))
    if strip_emoji(title) != title:
        a.issues.append(Issue(SEV_ERROR, "Emoji are not allowed in titles."))
    promo = find_promo_terms(title)
    if promo:
        a.issues.append(Issue(SEV_ERROR, "Promotional or subjective claims: " + ", ".join(promo[:6])))
    caps = find_allcaps_words(title)
    if caps:
        a.issues.append(Issue(SEV_WARN, "ALL-CAPS words are discouraged: " + ", ".join(caps[:6])))
    dupes = find_repeated_words(title)
    if dupes:
        a.issues.append(Issue(SEV_WARN, "Repeated words, a keyword-stuffing risk: " + ", ".join(dupes[:6])))

    if not a.errors and not a.warns:
        a.issues.append(Issue(SEV_OK, f"Compliant. {a.count}/{limit} chars, nothing banned."))
    return a


def audit_highlights(text: str) -> FieldAudit:
    text = text or ""
    a = FieldAudit("Item Highlights", text, char_count(text), HIGHLIGHT_LIMIT)
    if not text.strip():
        a.issues.append(Issue(SEV_WARN,
                              "Empty. Item Highlights is searchable and shows in mobile snippets, so use it."))
        return a
    if a.count > HIGHLIGHT_LIMIT:
        a.issues.append(Issue(SEV_ERROR, f"{a.count}/{HIGHLIGHT_LIMIT}, over the Item Highlights cap."))
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
    elif a.count > BULLET_SOFT_TARGET:
        a.issues.append(Issue(SEV_WARN,
                              f"{a.count} chars, long for mobile. Aim for {BULLET_SOFT_TARGET} or under."))
    first = text.strip()[:1]
    if first and first.isalpha() and not first.isupper():
        a.issues.append(Issue(SEV_WARN, "Should start with a capital letter."))
    if text.strip().endswith((".", "!", "?", ";")):
        a.issues.append(Issue(SEV_WARN, "Ends with punctuation. Amazon wants sentence fragments."))
    if strip_html(text) != text:
        a.issues.append(Issue(SEV_ERROR, "HTML tags are not allowed in bullets."))
    if strip_emoji(text) != text:
        a.issues.append(Issue(SEV_WARN, "Emoji present. Keep bullets plain text."))
    promo = find_promo_terms(text)
    if promo:
        a.issues.append(Issue(SEV_WARN, "Promotional or pricing language: " + ", ".join(promo[:6])))
    if not a.errors and not a.warns:
        a.issues.append(Issue(SEV_OK, f"Good. {a.count} chars."))
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
# Fixers
# ----------------------------------------------------------------------

def _strip_terms(text: str, terms: list) -> str:
    for term in terms:
        text = re.sub(r"(?i)(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", " ", text)
    return clean_ws(text)


def _tidy_punct(text: str) -> str:
    """Cleans the orphaned punctuation left when a phrase is cut from mid-sentence."""
    t = clean_ws(text)
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    t = re.sub(r"([,.;:!?])\s*(?=[,.;:!?])", "", t)
    t = re.sub(r"^[\s,.;:!?\-]+", "", t)
    t = re.sub(r"[\s,.;:!?\-]+$", "", t)
    return clean_ws(t)


def fix_title(title: str, brand: str = "", media: bool = False) -> tuple:
    """Returns (fixed_title, overflow_for_highlights)."""
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
                # the duplicate may carry the comma that separates the size/pack
                # tail, so hand any punctuation to the previous surviving token
                punct = re.sub(r"[A-Za-z0-9]", "", tok)
                if punct and kept:
                    kept[-1] = kept[-1] + punct
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


def fix_bullet(text: str) -> str:
    """Only clearly parenthetical promo is removed. Other flagged wording is
    reported rather than cut, since deleting words from mid-sentence breaks copy."""
    b = _tidy_punct(_strip_terms(clean_ws(strip_html(strip_emoji(text))), SAFE_STRIP))
    if b:
        b = b[:1].upper() + b[1:]
    return trim_to(b, BULLET_HARD_LIMIT)[0]

# ----------------------------------------------------------------------
# Smart title deconstruction
# ----------------------------------------------------------------------
# Rather than truncating a legacy title at character 75, the title is parsed
# into labelled parts (brand, product type, size, pack, colour, material,
# descriptor phrases) and rebuilt in priority order. Anything that does not fit
# is demoted to Item Highlights as a WHOLE PHRASE, never as a cut-off fragment.

# Units are ordered longest-first so "fl oz" wins over "oz" and "litre" over "l".
_UNITS = (r"fl\.?\s?oz|fluid\s?ounces?|ounces?|oz|millilit(?:er|re)s?|ml|"
          r"lit(?:er|re)s?|ltr|gallons?|gal|quarts?|qt|pints?|pt|"
          r"kilograms?|kgs?|milligrams?|mg|grams?|gm|pounds?|lbs?|"
          r"inch(?:es)?|cm|mm|feet|ft|meters?|watts?|volts?|mah|"
          r"sq\.?\s?ft|g|kg|lb|in|l|w|v|m")
SIZE_RE = re.compile(r"\b\d+(?:[\.,]\d+)?\s*(?:" + _UNITS + r")\b", re.I)
PACK_RE = re.compile(
    r"\b(?:pack\s+of\s+\d+|set\s+of\s+\d+|box\s+of\s+\d+|"
    r"\d+\s*[-\s]?(?:pack|pk|pcs?|pieces?|count|ct|units?)\b)", re.I)
# 12 x 8 x 4 inches / 10 × 5 cm — matched before plain sizes so it is not split.
DIMENSION_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:x|\u00D7|\*)\s*\d+(?:\.\d+)?"
    r"(?:\s*(?:x|\u00D7|\*)\s*\d+(?:\.\d+)?)?"
    r"\s*(?:cm|mm|inch(?:es)?|in|ft|feet|m)?\b", re.I)

# Common Amazon product-type nouns, longest match wins. Used to pull the core
# noun out of a pasted title so the rebuild knows identity from description.
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
    """Returns (product_type, confidence). Tries a known-noun lexicon first,
    then falls back to the trailing words of whatever description is left."""
    t = clean_ws(text)
    if not t:
        return "", "none"
    low = norm(t)
    for noun in sorted(PRODUCT_TYPE_LEXICON, key=len, reverse=True):
        if re.search(r"(?<![a-z0-9])" + re.escape(noun) + r"(?![a-z0-9])", low):
            # give it back in the casing used in the original title
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

# Phrase boundaries in a messy legacy title.
PHRASE_SPLIT_RE = re.compile(r"\s*(?:[,;|/]|\s[\u2013\u2014-]\s)\s*")

# Many legacy titles carry no punctuation at all, so a comma split leaves one
# undivided blob. These well-known attribute phrases act as extra split points.
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
    """Use-case phrases ('for gym', 'cereal or salad') are the first thing to
    demote, since they describe application rather than product identity."""
    low = f" {norm(phrase)} "
    return low.strip().startswith("for ") or " or " in low


def _split_unpunctuated(chunk: str) -> list:
    """Pulls known attribute phrases, materials and colours out of an
    unpunctuated run, then separates any trailing 'for ...' use-case clause.
    Longest match wins, so 'stainless steel' is never severed into 'steel'."""
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
    """The brand always leads. If it appears mid-title it is moved to the front;
    if it is missing entirely it is prepended."""
    brand = clean_ws(brand)
    title = clean_ws(title)
    if not brand:
        return title
    if norm(title).startswith(norm(brand) + " ") or norm(title) == norm(brand):
        return title
    rest = _tidy_punct(_remove_phrase(title, brand))
    return clean_ws(f"{brand} {rest}") if rest else brand


def deconstruct_title(title: str, brand: str = "", product_type: str = "",
                      size_override: str = "", pack_override: str = "",
                      dimensions_override: str = "") -> dict:
    """Parses a legacy title into labelled parts. Explicit overrides win over
    whatever is detected in the text."""
    t = clean_ws(strip_emoji(strip_html(title)))

    # strip banned characters and promo language before parsing
    if brand and brand in t:
        head, _s, tail = t.partition(brand)
        head = "".join(c for c in head if c not in BANNED_TITLE_CHARS)
        tail = "".join(c for c in tail if c not in BANNED_TITLE_CHARS)
        t = f"{head}{brand}{tail}"
    else:
        t = "".join(c for c in t if c not in BANNED_TITLE_CHARS)
    t = _tidy_punct(_strip_terms(clean_ws(t), PROMO_TERMS))

    # parentheses are legal but cost characters, so normalise to plain text
    t = clean_ws(t.replace("(", " ").replace(")", " "))

    pack = clean_ws(pack_override)
    if not pack:
        m = PACK_RE.search(t)
        pack = clean_ws(m.group(0)) if m else ""
    t = PACK_RE.sub(" ", t)

    # dimensions before size, so "12 x 8 inch" is not mistaken for "8 inch"
    dims = clean_ws(dimensions_override)
    found_dims = [clean_ws(m.group(0)) for m in DIMENSION_RE.finditer(t)]
    if not dims and found_dims:
        dims = found_dims[0]
    for d in found_dims:
        t = _remove_phrase(t, d)

    size = clean_ws(size_override)
    found_sizes = [clean_ws(m.group(0)) for m in SIZE_RE.finditer(t)]
    if not size and found_sizes:
        size = found_sizes[0]
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

    # split what remains into whole descriptor phrases
    descriptors, seen = [], set()
    for chunk in PHRASE_SPLIT_RE.split(t):
        chunk = _tidy_punct(clean_ws(chunk))
        if not chunk:
            continue
        # always sub-split: even short runs merge two attributes ("Leakproof Blue")
        pieces = _split_unpunctuated(chunk)
        for piece in pieces:
            piece = _tidy_punct(clean_ws(piece))
            key = norm(piece)
            if not key or key in seen:
                continue
            seen.add(key)
            descriptors.append(piece)

    # identity-ish attributes first, use-case phrases last, so use case is the
    # first thing pushed into Item Highlights when the title runs out of room
    descriptors.sort(key=is_use_case)

    colors = [d for d in descriptors if norm(d) in COLOR_WORDS]
    materials = [d for d in descriptors if norm(d) in MATERIAL_WORDS]

    return {"brand": clean_ws(brand), "product_type": ptype, "product_type_confidence": ptype_conf,
            "size": size, "pack": pack, "dimensions": dims,
            "descriptors": descriptors, "colors": colors, "materials": materials}


def detect_from_title(title: str, brand: str = "") -> dict:
    """Everything the auto-fill button needs from a pasted title."""
    p = deconstruct_title(title, brand=brand)
    return {"product_type": p["product_type"], "product_type_confidence": p["product_type_confidence"],
            "size": p["size"], "pack": p["pack"], "dimensions": p["dimensions"],
            "descriptors": p["descriptors"], "colors": p["colors"], "materials": p["materials"]}


def facts_from_parts(parts: dict) -> ProductFacts:
    """Turns a deconstructed title into product facts, so bullets can be written
    for a listing that arrived with no bullets at all."""
    descriptors = list(parts.get("descriptors", []))
    colors = parts.get("colors", [])
    materials = parts.get("materials", [])
    use_cases = [d for d in descriptors if is_use_case(d)]
    features = [d for d in descriptors
                if d not in colors and d not in materials and not is_use_case(d)]
    return ProductFacts(
        brand=parts.get("brand", ""), product_type=parts.get("product_type", ""),
        size=parts.get("size", ""), pack=parts.get("pack", ""),
        dimensions=parts.get("dimensions", ""),
        color=colors[0] if colors else "", material=materials[0] if materials else "",
        use_case=use_cases[0] if use_cases else "",
        features=[(f, "") for f in features])


def smart_title_rebuild(parts: dict, limit: int, minimal: bool = False) -> tuple:
    """Rebuilds in priority order: brand, product type, descriptors that fit,
    then the reserved size and pack. Returns (title, demoted_phrases).
    With minimal=True every descriptor is demoted, leaving brand, type, size, pack."""
    brand = parts.get("brand", "")
    ptype = parts.get("product_type", "")
    size = parts.get("size", "")
    pack = parts.get("pack", "")

    variant = ", ".join([x for x in [size, pack] if x])
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
        # whole phrases only: a descriptor either fits or it is demoted intact
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
# Builders — size and pack are reserved in the title
# ----------------------------------------------------------------------

@dataclass
class ProductFacts:
    brand: str = ""
    product_type: str = ""
    item_name: str = ""
    primary_keyword: str = ""
    secondary_keywords: str = ""
    size: str = ""
    pack: str = ""
    dimensions: str = ""
    color: str = ""
    material: str = ""
    audience: str = ""
    use_case: str = ""
    features: list = field(default_factory=list)


def variant_string(f: ProductFacts) -> str:
    """The size / pack fragment that is guaranteed a place in the title."""
    bits = [clean_ws(f.size), clean_ws(f.pack)]
    return ", ".join([b for b in bits if b])


def build_title(f: ProductFacts, media: bool = False) -> str:
    """Size and pack are reserved first, then brand -> type -> keyword fill the
    remaining budget. Colour, material, audience, and use case go to Highlights."""
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
    """Everything that did not earn a place in the title, inside 125 chars."""
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


def _benefit_for(feature: str, used: set = None) -> str:
    low = (feature or "").lower()
    for key, benefit in BENEFIT_HINTS.items():
        if key in low and (used is None or benefit not in used):
            return benefit
    for g in GENERIC_BENEFITS:
        if used is None or g not in used:
            return g
    return GENERIC_BENEFITS[0]


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

    if f.size or f.pack:
        size_txt, pack_txt = clean_ws(f.size), clean_ws(f.pack)
        n = re.search(r"\d+", pack_txt)
        bits = []
        if size_txt:
            bits.append(f"{size_txt} capacity")
        if n:
            bits.append(f"{n.group(0)} in every pack")
        elif pack_txt:
            bits.append(pack_txt.lower())
        lead = ("Size and pack" if (size_txt and pack_txt) else
                ("Size" if size_txt else "Pack"))
        rows.append((lead, take(lead, ", ".join(bits))))
    if f.dimensions:
        d = clean_ws(f.dimensions)
        rows.append((f"Measures {d}",
                     take(d, "so you can check it fits your shelf or cupboard before you order")))
    if f.material:
        rows.append((f"{clean_ws(f.material)} build", take(f.material)))
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
                     take(f.color, "holds a clean, consistent look on the shelf and in use")))

    bullets, seen = [], set()
    for lead, benefit in rows:
        lead = clean_ws(lead).rstrip(":")
        if not lead:
            continue
        head = lead.upper() if len(lead) <= 28 else lead[:1].upper() + lead[1:]
        b = fix_bullet(f"{head}: {benefit}")
        key = norm(b)[:40]
        if not b or key in seen:
            continue
        seen.add(key)
        bullets.append(b)
        if len(bullets) >= max_bullets:
            break
    return bullets

# ----------------------------------------------------------------------
# Keyword research — Google and Amazon search suggestions
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
    """Google returns ["query", ["suggestion", ...], ...]."""
    try:
        if isinstance(payload, list) and len(payload) > 1 and isinstance(payload[1], list):
            return [str(s) for s in payload[1] if isinstance(s, (str, bytes))]
    except Exception:
        pass
    return []


def parse_amazon_suggest(payload) -> list:
    """Amazon returns {"suggestions":[{"value": "..."}, ...]}."""
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
    """Returns (scored_rows, error_message). Never raises. Each row carries the
    best autocomplete rank and how many seed expansions surfaced the term, which
    together form the relevance proxy."""
    seed = clean_ws(seed)
    if not seed:
        return [], "Enter a seed keyword first."

    seeds = [seed]
    if expand:
        seeds += [f"{seed} {c}" for c in "abcdefghijklmnopqrstuvwxyz"]

    fn = (lambda s: _google_once(s)) if source == "Google" else (lambda s: _amazon_once(s, mid))

    best_rank, freq, display = {}, {}, {}
    errors = []
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for got in pool.map(lambda s: _safe_call(fn, s, errors), seeds):
                for i, term in enumerate(got):
                    term = clean_ws(term)
                    if not term:
                        continue
                    k = term.lower()
                    display.setdefault(k, term)
                    freq[k] = freq.get(k, 0) + 1
                    best_rank[k] = min(best_rank.get(k, 99), i)
    except Exception as exc:
        return [], f"Could not reach {source}: {exc}"

    if not display:
        detail = errors[0] if errors else "no suggestions returned"
        return [], (f"Could not reach {source} ({detail}). Suggestion lookup needs outbound "
                    f"internet access, which some hosts block. Type keywords in manually below.")

    rows = [{"term": display[k], "rank": best_rank[k], "freq": freq[k],
             "score": score_keyword(best_rank[k], freq[k], source)} for k in display]
    rows.sort(key=lambda r: (-r["score"], r["rank"], r["term"]))
    return rows, ""


def _safe_call(fn, seed, errors: list) -> list:
    try:
        return fn(seed)
    except Exception as exc:
        errors.append(str(exc))
        return []


def keyword_coverage(keywords: list, title: str, highlights: str, bullets: list) -> list:
    """Where each target keyword actually appears. A keyword counts as present
    when all of its words appear in that field."""
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
# Backend search terms (Generic Keywords) — 250 BYTES, not characters
# ----------------------------------------------------------------------
# Rules applied, per Amazon's 2026 guidance:
#   • 250 bytes measured in UTF-8. Going over by one byte can de-index the
#     WHOLE field, so the builder stops short rather than truncating mid-word.
#   • Single spaces between terms. No commas or punctuation.
#   • Never repeat a word already in the title, highlights or bullets — those
#     are indexed already, so repeating them burns bytes for nothing.
#   • No brand names, no ASINs, no subjective claims, no stop words.
#   • Skip a plural when the singular is already present, and vice versa.

BACKEND_LIMIT_BYTES = 250

BACKEND_STOPWORDS = STOPWORDS | {
    "this", "that", "these", "those", "your", "our", "you", "we", "they", "its",
    "be", "are", "was", "were", "can", "will", "has", "have", "not", "all", "any",
    "more", "most", "very", "just", "also", "than", "then", "when", "how", "what",
    "buy", "shop", "sale", "new", "best", "free", "top", "great", "good", "nice",
    "amazon", "asin", "com",
    # foreign-language stop words: the content words are worth bytes, these are not
    "de", "la", "el", "los", "las", "del", "para", "con", "una", "uno", "por", "que",
    "le", "les", "des", "du", "et", "pour", "avec", "der", "die", "das", "und",
    "fur", "mit", "ein", "eine", "il", "lo", "di", "da", "per",
}

ASIN_RE = re.compile(r"^b0[a-z0-9]{8}$", re.I)


def byte_len(s: str) -> int:
    return len((s or "").encode("utf-8"))


def norm_kw(s: str) -> str:
    """Like norm(), but keeps accented and non-Latin letters. Backend keywords in
    Spanish or German are a real ranking lever, so 'espátula' must not become
    'esp tula' the way a strict a-z filter would leave it."""
    s = (s or "").lower()
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return clean_ws(s.replace("_", " "))


def build_backend_terms(keywords: list, exclude_text: str = "", brand: str = "",
                        intent_phrases: bool = False,
                        limit_bytes: int = BACKEND_LIMIT_BYTES) -> dict:
    """Returns the refined string plus a breakdown of what was dropped and why."""
    exclude = set(norm_kw(exclude_text).split()) | set(norm_kw(brand).split())

    kept, seen, dropped_dupe, dropped_visible, dropped_stop = [], set(), [], [], []
    for kw in keywords:
        for w in norm_kw(kw).split():
            if len(w) < 2 or w in BACKEND_STOPWORDS or ASIN_RE.match(w):
                dropped_stop.append(w)
                continue
            if w in exclude:
                dropped_visible.append(w)
                continue
            singular, plural = (w[:-1] if w.endswith("s") else w), (w if w.endswith("s") else w + "s")
            if w in seen or singular in seen or plural in seen:
                dropped_dupe.append(w)
                continue
            seen.add(w)
            kept.append(w)

    out = ""
    overflow = []
    for w in kept:
        candidate = f"{out} {w}" if out else w
        if byte_len(candidate) > limit_bytes:
            overflow.append(w)
            continue
        out = candidate

    phrases_added = []
    if intent_phrases:
        for kw in keywords:
            phrase = norm_kw(kw)
            if len(phrase.split()) < 3:
                continue
            candidate = f"{out} {phrase}" if out else phrase
            if byte_len(candidate) <= limit_bytes and phrase not in out:
                out = candidate
                phrases_added.append(phrase)
            if len(phrases_added) >= 3:
                break

    return {"terms": out, "bytes": byte_len(out), "limit": limit_bytes,
            "kept": len(out.split()) if out else 0,
            "dropped_visible": sorted(set(dropped_visible)),
            "dropped_dupe": sorted(set(dropped_dupe)),
            "dropped_stop": sorted(set(dropped_stop)),
            "overflow": overflow, "phrases": phrases_added}


# ----------------------------------------------------------------------
# Making selected keywords actually land in the title and bullets
# ----------------------------------------------------------------------

def _contains_keyword(text: str, kw: str) -> bool:
    toks = set(norm(text).split())
    return all(w in toks for w in norm(kw).split() if w)


def ensure_keywords_in_title(title: str, keywords: list, brand: str,
                             limit: int, media: bool = False) -> tuple:
    """Tries to work each keyword into the title without breaking compliance.
    Returns (title, already_there, inserted, failed)."""
    cur = clean_ws(title)
    already, inserted, failed = [], [], []
    for kw in keywords:
        kw = clean_ws(kw)
        if not kw:
            continue
        if _contains_keyword(cur, kw):
            already.append(kw)
            continue
        # insert ahead of the reserved size/pack tail, which sits after the first comma
        if "," in cur:
            head, _sep, tail = cur.partition(",")
            candidate = clean_ws(f"{clean_ws(head)} {kw},{tail}")
        else:
            candidate = clean_ws(f"{cur} {kw}")
        candidate = fix_title(candidate, brand, media)[0]
        candidate = enforce_brand_first(candidate, brand)
        if (char_count(candidate) <= limit and not audit_title(candidate, brand, media).errors
                and _contains_keyword(candidate, kw)):
            cur = candidate
            inserted.append(kw)
        else:
            failed.append(kw)
    return cur, already, inserted, failed


def ensure_keywords_in_bullets(bullets: list, keywords: list, max_bullets: int) -> tuple:
    """Adds a bullet for a missing keyword when a slot is free, otherwise appends
    it to the shortest bullet that has room. Returns (bullets, already, inserted, failed)."""
    out = [b for b in (bullets or []) if b]
    already, inserted, failed = [], [], []
    used_benefits = set()
    for kw in keywords:
        kw = clean_ws(kw)
        if not kw:
            continue
        if _contains_keyword(" ".join(out), kw):
            already.append(kw)
            continue
        if len(out) < max_bullets:
            benefit = _benefit_for(kw, used_benefits)
            used_benefits.add(benefit)
            lead = kw.upper() if len(kw) <= 28 else kw[:1].upper() + kw[1:]
            b = fix_bullet(f"{lead}: {benefit}")
            if b:
                out.append(b)
                inserted.append(kw)
                continue
        shortest = sorted(range(len(out)), key=lambda i: len(out[i])) if out else []
        placed = False
        for i in shortest:
            candidate = fix_bullet(f"{out[i]}, {kw}")
            if char_count(candidate) <= BULLET_SOFT_TARGET and not audit_bullet(candidate, i + 1).errors:
                out[i] = candidate
                inserted.append(kw)
                placed = True
                break
        if not placed:
            failed.append(kw)
    return out, already, inserted, failed


# ----------------------------------------------------------------------
# Keyword scoring and density
# ----------------------------------------------------------------------
# There is no free public source for real Amazon search volume, so this is an
# explicit PROXY built from autocomplete behaviour: how near the top a term is
# suggested, and how many different seed expansions surfaced it. Amazon
# autocomplete is weighted above Google because it reflects buying intent on
# the marketplace being ranked in.

def score_keyword(rank: int, freq: int, source: str) -> int:
    rank_pts = max(0, 10 - min(rank, 10)) / 10 * 60
    freq_pts = min(freq, 5) / 5 * 25
    src_pts = 15 if source == "Amazon" else 8
    return int(round(min(100, rank_pts + freq_pts + src_pts)))


def priority_band(score: int) -> tuple:
    """Returns (label, colour, background)."""
    if score >= 70:
        return "High", "#0B7A46", "#DCFCE7"
    if score >= 45:
        return "Medium", "#96690B", "#FEF3C7"
    return "Low", "#4B5266", "#EEF1F6"


def keyword_density(title: str, highlights: str, bullets: list) -> dict:
    """Word counts across the visible copy, used to flag stuffing."""
    words = norm(f"{title} {highlights} {' '.join(bullets or [])}").split()
    counts = {}
    for w in words:
        if len(w) <= 2 or w in BACKEND_STOPWORDS:
            continue
        counts[w] = counts.get(w, 0) + 1
    return counts

# ----------------------------------------------------------------------
# Optional AI polish
# ----------------------------------------------------------------------

AI_SYSTEM = (
    "You are an Amazon catalog copywriter. Follow Amazon's 2026 rules exactly: "
    f"title <= {TITLE_LIMIT_STANDARD} characters including spaces (Media categories allow "
    f"{TITLE_LIMIT_MEDIA}); the size and pack count MUST appear in the title; no special "
    "characters except inside a brand name; no promotional or subjective claims; no repeated "
    "words; no ALL-CAPS words; no emoji. "
    f"Item Highlights <= {HIGHLIGHT_LIMIT} characters, plain text. "
    "Write bullets as capitalised sentence fragments with NO end punctuation, "
    f"<= {BULLET_SOFT_TARGET} characters each, feature then benefit, no pricing or promo, no HTML. "
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
        raw = re.sub(r"^```(?:json)?|```$", "", (raw or "").strip(), flags=re.MULTILINE).strip()
        data = json.loads(raw)
        if isinstance(data, dict) and data.get("title"):
            return data
    except Exception as exc:
        st.session_state["_ai_error"] = str(exc)
    return None


def facts_to_brief(f: ProductFacts, targets: list) -> str:
    feats = "; ".join(f"{a} => {b}" if b else a for a, b in f.features if a.strip())
    return textwrap.dedent(f"""
        Write an Amazon listing.
        Brand: {f.brand}
        Product type: {f.product_type}
        Item / line name: {f.item_name}
        Primary keyword: {f.primary_keyword}
        Secondary keywords: {f.secondary_keywords}
        Target search terms to work in: {", ".join(targets)}
        Size: {f.size}
        Pack / count: {f.pack}
        Colour: {f.color}
        Material: {f.material}
        Audience: {f.audience}
        Use case: {f.use_case}
        Key features (feature => benefit): {feats}
        The size and pack count must appear in the title.
    """).strip()

# ----------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------

st.set_page_config(page_title="Listing Studio", page_icon="🛍️", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;600;700;800&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@500;700&display=swap');

.stApp { background:#FFFFFF; }
html, body, [class*="css"] { font-family:'Inter', system-ui, sans-serif; color:#1B2233; }
h1,h2,h3,h4,h5 { font-family:'Plus Jakarta Sans', sans-serif; color:#141A29; letter-spacing:-.02em; }
.block-container { padding-top:1.4rem; max-width:1400px; }
p, label, .stMarkdown, li { color:#3A4256; }

.hero { background:linear-gradient(115deg,#FFE29A 0%,#FF9A8B 38%,#FF6FA5 68%,#7B6CFF 100%);
    border-radius:20px; padding:22px 26px; margin-bottom:18px;
    box-shadow:0 10px 28px rgba(123,108,255,.22); }
.hero h1 { font-size:27px; font-weight:800; margin:0; color:#20142E; letter-spacing:-.03em; }
.hero p { margin:7px 0 0; font-size:13.5px; color:#3A2440; font-weight:500; max-width:820px; }

.counter { font-family:'JetBrains Mono',monospace; font-size:12px; font-weight:700;
    padding:3px 10px; border-radius:999px; display:inline-block; }
.c-ok   { background:#DCFCE7; color:#0B7A46; border:1px solid #86EFAC; }
.c-warn { background:#FEF3C7; color:#96690B; border:1px solid #FCD34D; }
.c-bad  { background:#FFE4E6; color:#B4143C; border:1px solid #FDA4AF; }

.scorewrap { display:flex; align-items:center; gap:20px; background:#FFFFFF;
    border:1px solid #E7EAF3; border-left:8px solid var(--sc,#22C55E); border-radius:16px;
    padding:16px 22px; margin:8px 0 16px; box-shadow:0 4px 16px rgba(20,26,41,.07); }
.scorenum { font-family:'JetBrains Mono',monospace; font-size:42px; font-weight:700; line-height:1; }
.scoremeta { font-size:12.5px; color:#6B7391; }
.grade { font-family:'JetBrains Mono',monospace; font-weight:700; font-size:15px;
    padding:3px 12px; border-radius:9px; }

.issue { font-size:13px; padding:8px 13px; border-radius:10px; margin:5px 0;
    background:#F7F9FC; border-left:4px solid #CBD5E1; color:#3A4256; }
.issue.error { background:#FFF1F2; border-left-color:#F43F5E; }
.issue.warn  { background:#FFFBEB; border-left-color:#F59E0B; }
.issue.ok    { background:#F0FDF4; border-left-color:#22C55E; }
.issue .sev { font-family:'JetBrains Mono',monospace; font-size:10.5px; font-weight:700;
    text-transform:uppercase; letter-spacing:.07em; margin-right:8px; }
.issue.error .sev { color:#E11D48; }
.issue.warn  .sev { color:#D97706; }
.issue.ok    .sev { color:#16A34A; }

.outfield { background:#FFFFFF; border:1px solid #E7EAF3; border-radius:14px;
    padding:15px 18px; margin:9px 0; box-shadow:0 3px 12px rgba(20,26,41,.06); }
.outfield .flabel { font-family:'JetBrains Mono',monospace; font-size:10.5px;
    text-transform:uppercase; letter-spacing:.09em; color:#6B7391; margin-bottom:7px; }
.outfield .fval { color:#141A29; font-size:15px; line-height:1.6; font-weight:500; }
.outfield ul { margin:7px 0 0; padding-left:20px; }
.outfield li { margin:7px 0; color:#141A29; font-size:14.5px; line-height:1.6; }

.kwchip { display:inline-block; font-size:12px; font-weight:600; padding:4px 11px; margin:3px;
    border-radius:999px; background:#EEF2FF; color:#4338CA; border:1px solid #C7D2FE; }
.kwmiss { background:#FFE4E6; color:#B4143C; border-color:#FDA4AF; }
.kwhit  { background:#DCFCE7; color:#0B7A46; border-color:#86EFAC; }

.stTabs [data-baseweb="tab-list"] { gap:6px; }
[data-baseweb="tab"] { font-weight:700; font-family:'Plus Jakarta Sans',sans-serif; }
div.stButton > button[kind="primary"] { background:#7B6CFF; border:0; font-weight:700; border-radius:10px; }
div.stButton > button[kind="primary"]:hover { background:#6455F0; }
</style>
""", unsafe_allow_html=True)

st.markdown(
    '<div class="hero"><h1>Listing Studio</h1>'
    '<p>Amazon title, item highlights and bullets, built to the 2026 rules. '
    'Titles cap at 75 characters from 27 July 2026, with size and pack count reserved so they '
    'always survive the cut. Everything else moves into the 125-character Item Highlights field.</p></div>',
    unsafe_allow_html=True)


def counter_pill(count: int, limit: int, soft: bool = False) -> str:
    cls = "c-bad" if count > limit else "c-warn" if count > limit * 0.9 else "c-ok"
    return f'<span class="counter {cls}">{count}/{limit}{" soft" if soft else ""}</span>'


def render_issues(a: FieldAudit):
    for i in a.issues:
        label = {"error": "Fix", "warn": "Check", "ok": "OK"}[i.severity]
        st.markdown(f'<div class="issue {i.severity}"><span class="sev">{label}</span>{esc(i.message)}</div>',
                    unsafe_allow_html=True)


def render_scorecard(audits: list):
    score, grade = health_score(audits)
    color = "#22C55E" if score >= 80 else "#F59E0B" if score >= 55 else "#F43F5E"
    n_err = sum(len(a.errors) for a in audits)
    n_warn = sum(len(a.warns) for a in audits)
    st.markdown(
        f'<div class="scorewrap" style="--sc:{color}">'
        f'<div class="scorenum" style="color:{color}">{score}</div><div>'
        f'<span class="grade" style="background:{color}1F;color:{color}">Grade {grade}</span>'
        f'<div class="scoremeta" style="margin-top:6px">{n_err} blocking · {n_warn} to check · '
        f'title, highlights and bullets</div></div></div>', unsafe_allow_html=True)


def build_export_text(title, highlights, bullets) -> str:
    lines = [f"TITLE ({char_count(title)} chars):", title, "",
             f"ITEM HIGHLIGHTS ({char_count(highlights)} chars):", highlights, "",
             "ABOUT THIS ITEM:"]
    lines += [f"- {b}" for b in bullets if b]
    return "\n".join(lines)


def render_output_block(title, highlights, bullets, media, key):
    tl = TITLE_LIMIT_MEDIA if media else TITLE_LIMIT_STANDARD
    st.markdown(f'<div class="outfield"><div class="flabel">Title &nbsp; {counter_pill(char_count(title), tl)}</div>'
                f'<div class="fval">{esc(title) or "<i>—</i>"}</div></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="outfield"><div class="flabel">Item Highlights &nbsp; '
                f'{counter_pill(char_count(highlights), HIGHLIGHT_LIMIT)}</div>'
                f'<div class="fval">{esc(highlights) or "<i>—</i>"}</div></div>', unsafe_allow_html=True)
    lis = "".join(f'<li>{esc(b)} &nbsp; {counter_pill(char_count(b), BULLET_SOFT_TARGET, soft=True)}</li>'
                  for b in bullets if b)
    st.markdown(f'<div class="outfield"><div class="flabel">About This Item — '
                f'{len([b for b in bullets if b])} bullets</div><ul>{lis or "<li><i>—</i></li>"}</ul></div>',
                unsafe_allow_html=True)

    # Every field on its own, because Seller Central has a separate box for each.
    # st.code gives a native copy button on hover.
    st.markdown("##### Copy each field")
    st.caption("Hover any box and use the copy icon on the right.")
    st.caption("Title")
    st.code(title or "", language=None)
    st.caption("Item Highlights")
    st.code(highlights or "", language=None)
    for i, b in enumerate([b for b in bullets if b], start=1):
        st.caption(f"Bullet {i}")
        st.code(b, language=None)

    export = build_export_text(title, highlights, bullets)
    with st.expander("Everything in one block"):
        st.code(export, language=None)
    st.download_button("Download listing (.txt)", data=export.encode("utf-8"),
                       file_name="listing.txt", mime="text/plain", key=f"dl_{key}")


def render_coverage(targets, title, highlights, bullets):
    rows = keyword_coverage(targets, title, highlights, bullets)
    if not rows:
        return
    st.markdown("##### Keyword coverage")
    chips = "".join(
        f'<span class="kwchip {"kwhit" if r["anywhere"] else "kwmiss"}">{esc(r["keyword"])}'
        f'{" · title" if r["Title"] else " · highlights" if r["Highlights"] else " · bullets" if r["Bullets"] else " · missing"}'
        f'</span>' for r in rows)
    st.markdown(chips, unsafe_allow_html=True)
    missing = [r["keyword"] for r in rows if not r["anywhere"]]
    if missing:
        st.warning("Not present anywhere in the listing: " + ", ".join(missing[:10]))
    else:
        st.success("Every target keyword appears somewhere in the listing.")


# ---- Sidebar ----
with st.sidebar:
    st.subheader("Settings")
    seller_type = st.radio("Account type", ["Seller — 5 bullets", "Vendor — 10 bullets"], index=0)
    max_bullets = MAX_BULLETS_VENDOR if seller_type.startswith("Vendor") else MAX_BULLETS_SELLER
    media_mode = st.checkbox("Media category (Books, Music, Video, Software)", value=False,
                             help="The only category exception left. Media keeps a 200-character "
                                  "title limit; everything else is capped at 75.")
    active_limit = TITLE_LIMIT_MEDIA if media_mode else TITLE_LIMIT_STANDARD
    st.caption(f"Title limit in use: **{active_limit} characters**")

    st.markdown("---")
    st.subheader("AI polish — optional")
    provider = st.selectbox("Provider", ["None — rule-based only", "Anthropic", "OpenAI"], index=0)
    api_key, model = "", ""
    if provider != "None — rule-based only":
        secret_name = "ANTHROPIC_API_KEY" if provider == "Anthropic" else "OPENAI_API_KEY"
        try:
            default_key = st.secrets.get(secret_name, "")
        except Exception:
            default_key = ""
        api_key = st.text_input("API key", value=default_key, type="password",
                                help=f"Or set {secret_name} in .streamlit/secrets.toml.")
        model = st.text_input("Model", value="claude-sonnet-4-5" if provider == "Anthropic" else "gpt-4o-mini")
        st.caption("AI output is re-checked by the same rule engine before it is shown.")

use_ai = provider != "None — rule-based only" and bool(api_key)
targets = list(dict.fromkeys(
    st.session_state.get("kw_sel_title", []) + st.session_state.get("kw_sel_bul", [])))
if targets:
    st.sidebar.markdown("---")
    st.sidebar.caption(f"**{len(targets)} keywords** selected in Keyword research")

tab_enhance, tab_build, tab_keywords, tab_rules = st.tabs(
    ["Enhance a listing", "Build a listing", "Keyword research", "The 2026 rules"])

# ======================================================================
# ENHANCE
# ======================================================================
with tab_enhance:

    def _autofill_from_title():
        """Runs before the widgets are rebuilt, so it can safely set their values."""
        det = detect_from_title(st.session_state.get("e_title", ""),
                                st.session_state.get("e_brand", ""))
        for src, dst in [("size", "e_size"), ("pack", "e_pack"),
                         ("product_type", "e_ptype"), ("dimensions", "e_dims")]:
            if det.get(src):
                st.session_state[dst] = det[src]
        st.session_state["_autofill"] = det

    st.markdown("### Step 1 — Paste your current title")
    st.caption("Then press the button and the details below fill in on their own.")

    e_brand = st.text_input("Brand name", key="e_brand", placeholder="Borosil",
                            help="This always goes first in the new title.")
    e_title = st.text_area("Current title", height=80, key="e_title",
                           placeholder="Borosil Cereal or Salad Glass Bowl 500 ML (Pack of 2) Microwave Safe")
    st.markdown(counter_pill(char_count(e_title), active_limit), unsafe_allow_html=True)
    st.button("Read the title and fill in the details", on_click=_autofill_from_title,
              key="e_autofill", type="secondary")

    det = st.session_state.get("_autofill")
    if det:
        found = [f"Size: {det['size']}" if det["size"] else "",
                 f"Pack: {det['pack']}" if det["pack"] else "",
                 f"Dimensions: {det['dimensions']}" if det["dimensions"] else "",
                 f"Product type: {det['product_type']}" if det["product_type"] else ""]
        found = [f for f in found if f]
        if found:
            st.markdown("".join(f'<span class="kwchip kwhit">{esc(x)}</span>' for x in found),
                        unsafe_allow_html=True)
            if det.get("product_type_confidence") == "guess":
                st.caption("The product type is a guess from the last words of the title. "
                           "Correct it below if it is wrong.")
        else:
            st.caption("Nothing detectable in that title. Fill the boxes below by hand.")

    st.markdown("### Step 2 — Check the details")
    st.caption("Size and pack are locked into the new title. Everything else moves to Item Highlights.")

    d1, d2, d3 = st.columns(3)
    with d1:
        e_ptype = st.text_input("Product type", key="e_ptype", placeholder="Bowl")
    with d2:
        e_size = st.text_input("Size", key="e_size", placeholder="500 ML")
    with d3:
        e_pack = st.text_input("Pack or count", key="e_pack", placeholder="Pack of 2")
    e_dims = st.text_input("Dimensions, if you have them", key="e_dims",
                           placeholder="12 x 8 x 4 inches",
                           help="Used to write a size-and-fit bullet, which cuts returns.")

    st.markdown("### Step 3 — Your current bullets")
    e_bul = st.text_area("Paste all of them here, one per line. Leave it empty and they get written for you.",
                         height=165, key="e_bul",
                         placeholder="• Microwave and dishwasher safe\n- Made from toughened glass\n3. Ideal for cereal, salad and soup")
    _preview = parse_pasted_lines(e_bul)
    st.caption(f"Found **{len(_preview)}** bullets." if _preview
               else "Empty, so bullets will be written from the details in Step 2.")

    with st.expander("Title style — advanced"):
        e_style = st.radio(
            "How much should the title carry?",
            ["Keyword-rich — use the space that is left",
             "Minimal — brand, type, size and pack only"],
            index=0, key="e_style",
            help="Keyword-rich fills leftover characters and drops use-case phrases first. "
                 "Minimal sends every descriptor to Item Highlights.")
        e_high = st.text_area("Current Item Highlights, if you already have them", height=68, key="e_high")
        st.markdown(counter_pill(char_count(e_high), HIGHLIGHT_LIMIT), unsafe_allow_html=True)
    e_minimal = e_style.startswith("Minimal")

    st.markdown("")
    if st.button("Fix my listing", type="primary", key="e_go", use_container_width=True):
        bullets_in = parse_pasted_lines(e_bul)
        audits = [audit_title(e_title, e_brand, media_mode), audit_highlights(e_high)]
        audits += [audit_bullet(b, i + 1) for i, b in enumerate(bullets_in)]
        render_scorecard(audits)

        st.markdown("##### What is wrong now")
        for a in audits:
            st.markdown(f"**{a.field}** &nbsp; {counter_pill(a.count, a.limit)}", unsafe_allow_html=True)
            render_issues(a)

        st.markdown("---")
        st.markdown("##### Corrected rewrite")

        # --- smart breakdown: parse into parts, then rebuild in priority order ---
        parts = deconstruct_title(e_title, brand=e_brand, product_type=e_ptype,
                                  size_override=e_size, pack_override=e_pack,
                                  dimensions_override=e_dims)
        fixed_title, demoted = smart_title_rebuild(parts, active_limit, minimal=e_minimal)
        fixed_title = fix_title(fixed_title, e_brand, media_mode)[0]
        fixed_title = enforce_brand_first(fixed_title, e_brand)

        overflow = ", ".join(demoted)
        fixed_high = fix_highlights(e_high, appended=overflow)

        # Item Highlights is searchable, so never leave it blank. If the title
        # absorbed everything, fill it from the parsed details instead.
        highlights_generated = False
        if not fixed_high.strip():
            fixed_high = build_highlights(facts_from_parts(parts), "", extra_keywords=targets)
            highlights_generated = bool(fixed_high.strip())

        # bullets: clean what was pasted, or write them from the parsed details
        bullets_generated = False
        if bullets_in:
            fixed_bullets = [fix_bullet(b) for b in bullets_in][:max_bullets]
        else:
            fixed_bullets = build_bullets(facts_from_parts(parts), max_bullets)
            bullets_generated = True

        with st.expander("How the old title was broken down", expanded=True):
            bd1, bd2 = st.columns(2)
            with bd1:
                st.markdown(
                    f"**Kept in the title**\n\n"
                    f"- Brand: `{parts['brand'] or '—'}`\n"
                    f"- Product type: `{parts['product_type'] or '—'}`\n"
                    f"- Size: `{parts['size'] or '—'}`\n"
                    f"- Pack: `{parts['pack'] or '—'}`")
            with bd2:
                st.markdown("**Moved to Item Highlights**\n\n"
                            + ("\n".join(f"- {d}" for d in demoted) if demoted else "Nothing — it all fit."))

        if use_ai:
            brief = (f"Rewrite this listing to be fully compliant, keeping its meaning and keywords.\n"
                     f"The title MUST start with the brand name and MUST contain the size and pack.\n"
                     f"Brand: {e_brand}\nProduct type: {parts['product_type']}\nSize: {parts['size']}\n"
                     f"Pack: {parts['pack']}\nDimensions: {parts['dimensions']}\nTitle: {e_title}\n"
                     f"Highlights: {e_high}\nBullets: {bullets_in or 'none, write five'}\n"
                     f"Target search terms: {', '.join(targets)}")
            data = ai_generate(provider, api_key, model, brief)
            if data:
                fixed_title = fix_title(data.get("title") or fixed_title, e_brand, media_mode)[0]
                fixed_title = enforce_brand_first(fixed_title, e_brand)
                fixed_high = fix_highlights(data.get("highlights") or fixed_high)
                fixed_bullets = [fix_bullet(b) for b in (data.get("bullets") or fixed_bullets)][:max_bullets]
            elif st.session_state.get("_ai_error"):
                st.warning(f"AI polish unavailable, showing the rule-based rewrite. "
                           f"({st.session_state['_ai_error']})")

        if highlights_generated:
            st.info("Item Highlights was empty, so it was filled from the product details. "
                    "The field is searchable, so leaving it blank gives up free ranking surface.")
        if bullets_generated and fixed_bullets:
            st.info("You had no bullets, so these were written from the details in Step 2. "
                    "Treat them as a first draft and add anything only you would know.")

        render_output_block(fixed_title, fixed_high, fixed_bullets, media_mode, key="enh")

        post = [audit_title(fixed_title, e_brand, media_mode), audit_highlights(fixed_high)]
        post += [audit_bullet(b, i + 1) for i, b in enumerate(fixed_bullets)]
        before, _ = health_score(audits)
        after, _ = health_score(post)
        st.success(f"Health score {before} → {after} out of 100")

        st.session_state["listing"] = {"title": fixed_title, "highlights": fixed_high,
                                       "bullets": fixed_bullets, "brand": e_brand,
                                       "source": "Enhance"}

        if targets:
            render_coverage(targets, fixed_title, fixed_high, fixed_bullets)
        with st.expander("Audit of the rewrite"):
            for a in post:
                st.markdown(f"**{a.field}** &nbsp; {counter_pill(a.count, a.limit)}", unsafe_allow_html=True)
                render_issues(a)

# ======================================================================
# BUILD
# ======================================================================
with tab_build:
    st.markdown("#### Start from product facts")
    st.caption("Size and pack are reserved in the title. Colour, material, audience and use case "
               "are pushed into Item Highlights on purpose, so they do not eat title characters.")

    b1, b2, b3 = st.columns(3)
    with b1:
        f_brand = st.text_input("Brand name (required)", key="b_brand")
        f_type = st.text_input("Product type (required)", key="b_type", placeholder="Coffee Mug…")
        f_item = st.text_input("Item or line name", key="b_item")
    with b2:
        f_size = st.text_input("Size (reserved in title)", key="b_size", placeholder="32 oz, 8 inch…")
        f_pack = st.text_input("Pack / count (reserved in title)", key="b_pack", placeholder="Pack of 3…")
        f_pk = st.text_input("Primary keyword", key="b_pk")
    with b3:
        f_color = st.text_input("Colour or finish → highlights", key="b_color")
        f_mat = st.text_input("Material → highlights", key="b_mat")
        f_sk = st.text_input("Secondary keywords, comma separated", key="b_sk")

    b4, b5 = st.columns(2)
    with b4:
        f_aud = st.text_input("Who it is for → highlights", key="b_aud", placeholder="for men, for toddlers…")
    with b5:
        f_use = st.text_input("What it is used for → highlights", key="b_use",
                              placeholder="for cold brew, for travel…")
    f_dims = st.text_input("Dimensions", key="b_dims", placeholder="12 x 8 x 4 inches",
                           help="Used to write a size-and-fit bullet, which cuts returns.")

    f_feats_raw = st.text_area(
        "Key features — paste them all here, one per line", height=180, key="b_feats",
        placeholder="Double-wall insulation: keeps drinks cold for 24 hours\n"
                    "Leakproof lid\n- Dishwasher safe\n3. BPA free")
    st.caption("Optional: add a benefit after a colon, a dash or a pipe. Bare lines get a benefit inferred.")
    _fpreview = parse_features(f_feats_raw)
    if _fpreview:
        st.caption(f"Detected **{len(_fpreview)}** features.")

    if st.button("Generate listing", type="primary", key="b_go"):
        if not f_brand.strip() or not f_type.strip():
            st.error("Add a brand name and a product type. The title is built around them.")
        else:
            facts = ProductFacts(
                brand=f_brand, product_type=f_type, item_name=f_item, primary_keyword=f_pk,
                secondary_keywords=f_sk, size=f_size, pack=f_pack, dimensions=f_dims,
                color=f_color, material=f_mat,
                audience=f_aud, use_case=f_use, features=parse_features(f_feats_raw))

            title = build_title(facts, media_mode)
            highlights = build_highlights(facts, title, extra_keywords=targets)
            bullets = build_bullets(facts, max_bullets)

            if use_ai:
                data = ai_generate(provider, api_key, model, facts_to_brief(facts, targets))
                if data:
                    title = fix_title(data.get("title") or title, f_brand, media_mode)[0]
                    highlights = fix_highlights(data.get("highlights") or highlights)
                    bullets = [fix_bullet(b) for b in (data.get("bullets") or bullets)][:max_bullets]
                elif st.session_state.get("_ai_error"):
                    st.warning(f"AI unavailable, showing the rule-based build. "
                               f"({st.session_state['_ai_error']})")

            audits = [audit_title(title, f_brand, media_mode), audit_highlights(highlights)]
            audits += [audit_bullet(b, i + 1) for i, b in enumerate(bullets)]
            render_scorecard(audits)

            st.markdown("##### Generated listing")
            render_output_block(title, highlights, bullets, media_mode, key="bld")

            v = variant_string(facts)
            if v:
                kept = all(norm(x) in norm(title) for x in [clean_ws(facts.size), clean_ws(facts.pack)] if x)
                (st.success if kept else st.warning)(
                    f"Size and pack in title: “{v}”" if kept
                    else f"Size and pack could not fit in {active_limit} characters. Shorten the brand or product type.")

            st.session_state["listing"] = {"title": title, "highlights": highlights,
                                           "bullets": bullets, "brand": f_brand,
                                           "source": "Build"}

            if targets:
                render_coverage(targets, title, highlights, bullets)
            with st.expander("Field-by-field audit"):
                for a in audits:
                    st.markdown(f"**{a.field}** &nbsp; {counter_pill(a.count, a.limit)}", unsafe_allow_html=True)
                    render_issues(a)

# ======================================================================
# KEYWORDS
# ======================================================================
with tab_keywords:
    st.markdown("### Step 1 — Find keywords")
    st.caption("Live autocomplete from Google or Amazon. These are phrases people actually type, "
               "which makes them a good source for the title, bullets and backend terms.")

    k1, k2, k3 = st.columns([2, 1.1, 1.1])
    with k1:
        seed = st.text_input("Seed keyword", key="kw_seed", placeholder="glass cereal bowl")
    with k2:
        source = st.selectbox("Source", ["Amazon", "Google"], index=0,
                              help="Amazon reflects buying intent and is scored higher.")
    with k3:
        market = st.selectbox("Marketplace", list(AMAZON_MARKETS.keys()), index=0,
                              disabled=(source != "Amazon"))
    expand = st.checkbox("Expand A–Z for long-tail terms (27 lookups, slower)", value=False)

    if st.button("Fetch keywords", type="primary", key="kw_go"):
        with st.spinner(f"Asking {source}…"):
            rows, err = fetch_suggestions(seed, source, AMAZON_MARKETS[market], expand)
        st.session_state["kw_rows"] = rows
        st.session_state["kw_error"] = err
        # widget defaults are ignored once a key exists, so pre-seed the buckets here
        st.session_state["kw_sel_title"] = [r["term"] for r in rows if r["score"] >= 70][:4]
        st.session_state["kw_sel_bul"] = [r["term"] for r in rows if 45 <= r["score"] < 70][:6]
        st.session_state["kw_sel_back"] = [r["term"] for r in rows if r["score"] < 45][:20]

    if st.session_state.get("kw_error"):
        st.warning(st.session_state["kw_error"])

    rows = st.session_state.get("kw_rows", [])

    st.markdown(
        '<div style="background:#F7F9FC;border:1px solid #E7EAF3;border-radius:12px;'
        'padding:12px 15px;margin:10px 0;font-size:12.5px;color:#3A4256;">'
        '<b>Colour key</b> &nbsp;'
        '<span class="kwchip" style="background:#DCFCE7;color:#0B7A46;border-color:#86EFAC">High</span>'
        ' suggested near the top and across many searches — put these in the title.&nbsp;'
        '<span class="kwchip" style="background:#FEF3C7;color:#96690B;border-color:#FCD34D">Medium</span>'
        ' solid supporting terms — good for bullets.&nbsp;'
        '<span class="kwchip" style="background:#EEF1F6;color:#4B5266;border-color:#D5DAE5">Low</span>'
        ' long-tail — send these to backend search terms.'
        '<br><span style="color:#6B7391">Score is a <b>relevance proxy</b> built from autocomplete '
        'position and how many searches surfaced the term. It is not real search volume — no free '
        'source publishes that. For true volume use Brand Analytics or your Search Query '
        'Performance report.</span></div>',
        unsafe_allow_html=True)

    if rows:
        st.success(f"{len(rows)} keywords from {source}, strongest first.")
        chips = []
        for r in rows[:100]:
            label, fg, bg = priority_band(r["score"])
            chips.append(
                f'<span class="kwchip" style="background:{bg};color:{fg};border-color:{fg}44">'
                f'{esc(r["term"])} <b>{r["score"]}</b></span>')
        st.markdown("".join(chips), unsafe_allow_html=True)

    st.markdown("### Step 2 — Decide where each keyword goes")
    st.caption("Title keywords get forced into the title. Bullet keywords get forced into the "
               "bullets. Backend terms are cleaned up and packed into the 250-byte field.")

    previously_picked = (st.session_state.get("kw_sel_title", [])
                         + st.session_state.get("kw_sel_bul", [])
                         + st.session_state.get("kw_sel_back", []))
    all_terms = list(dict.fromkeys(
        [r["term"] for r in rows]
        + parse_pasted_lines(st.session_state.get("kw_manual", ""))
        + previously_picked))

    a1, a2, a3 = st.columns(3)
    with a1:
        sel_title = st.multiselect("Into the title", all_terms, key="kw_sel_title",
                                   help="Only two or three will fit inside 75 characters.")
    with a2:
        sel_bul = st.multiselect("Into the bullets", all_terms, key="kw_sel_bul")
    with a3:
        sel_back = st.multiselect("Into backend search terms", all_terms, key="kw_sel_back")

    st.text_area("Add your own keywords, one per line", height=90, key="kw_manual")

    if sel_title or sel_bul or sel_back:
        with st.expander("Copy the keyword lists"):
            for lbl, lst in [("Title keywords", sel_title), ("Bullet keywords", sel_bul),
                             ("Backend keywords", sel_back)]:
                st.caption(lbl)
                st.code(", ".join(lst) or "", language=None)

    intent_phrases = st.checkbox(
        "Add up to 3 intent phrases to the backend field", value=False,
        help="Amazon\'s AI-assisted search favours context phrases like \'hiking rain jacket wet "
             "weather\' alongside single words. Costs bytes, so it is off by default.")

    listing = st.session_state.get("listing")
    st.markdown("### Step 3 — Apply them to your listing")

    if not listing:
        st.info("Run **Enhance a listing** or **Build a listing** first. The result lands here "
                "automatically and this step rewrites it around the keywords you picked.")
    else:
        st.caption(f"Working on the listing from the **{listing['source']}** tab.")
        if st.button("Apply keywords and rebuild", type="primary", key="kw_apply",
                     use_container_width=True):
            brand = listing.get("brand", "")

            new_title, t_already, t_ins, t_fail = ensure_keywords_in_title(
                listing["title"], sel_title, brand, active_limit, media_mode)
            new_bullets, b_already, b_ins, b_fail = ensure_keywords_in_bullets(
                listing["bullets"], sel_bul, max_bullets)

            visible = f"{new_title} {listing['highlights']} {' '.join(new_bullets)}"
            back = build_backend_terms(sel_back, exclude_text=visible, brand=brand,
                                       intent_phrases=intent_phrases)

            st.markdown("##### Refreshed listing")
            render_output_block(new_title, listing["highlights"], new_bullets, media_mode, key="kw")

            bcls = "c-bad" if back["bytes"] > back["limit"] else "c-ok"
            st.markdown(
                f'<div class="outfield"><div class="flabel">Backend search terms &nbsp;'
                f'<span class="counter {bcls}">{back["bytes"]}/{back["limit"]} bytes</span></div>'
                f'<div class="fval" style="font-family:JetBrains Mono,monospace;font-size:13px">'
                f'{esc(back["terms"]) or "<i>nothing left to add</i>"}</div></div>',
                unsafe_allow_html=True)
            st.caption("Copy the backend search terms")
            st.code(back["terms"] or "", language=None)
            st.download_button(
                "Download backend terms (.txt)", data=back["terms"].encode("utf-8"),
                file_name="backend_search_terms.txt", mime="text/plain", key="dl_back")

            r1, r2 = st.columns(2)
            with r1:
                st.markdown("**Title**")
                if t_already:
                    st.markdown(" ".join(f'<span class="kwchip kwhit">{esc(k)} already there</span>'
                                         for k in t_already), unsafe_allow_html=True)
                if t_ins:
                    st.markdown(" ".join(f'<span class="kwchip kwhit">{esc(k)} added</span>'
                                         for k in t_ins), unsafe_allow_html=True)
                if t_fail:
                    st.markdown(" ".join(f'<span class="kwchip kwmiss">{esc(k)} would not fit</span>'
                                         for k in t_fail), unsafe_allow_html=True)
                    st.caption("No room inside 75 characters. Drop one, shorten the product type, "
                               "or move these to backend terms.")
            with r2:
                st.markdown("**Bullets**")
                if b_already:
                    st.markdown(" ".join(f'<span class="kwchip kwhit">{esc(k)} already there</span>'
                                         for k in b_already), unsafe_allow_html=True)
                if b_ins:
                    st.markdown(" ".join(f'<span class="kwchip kwhit">{esc(k)} added</span>'
                                         for k in b_ins), unsafe_allow_html=True)
                if b_fail:
                    st.markdown(" ".join(f'<span class="kwchip kwmiss">{esc(k)} did not fit</span>'
                                         for k in b_fail), unsafe_allow_html=True)

            with st.expander("What the backend cleanup removed, and why"):
                st.markdown(
                    f"- **Already in your visible copy** ({len(back['dropped_visible'])}): "
                    f"`{', '.join(back['dropped_visible'][:25]) or 'none'}`  \n"
                    f"  Amazon already indexes your title, highlights and bullets, so repeating "
                    f"these would waste bytes.\n"
                    f"- **Duplicates or plural forms** ({len(back['dropped_dupe'])}): "
                    f"`{', '.join(back['dropped_dupe'][:25]) or 'none'}`\n"
                    f"- **Stop words, brand and filler** ({len(back['dropped_stop'])}): "
                    f"`{', '.join(back['dropped_stop'][:25]) or 'none'}`\n"
                    f"- **Did not fit in 250 bytes** ({len(back['overflow'])}): "
                    f"`{', '.join(back['overflow'][:25]) or 'none'}`")
                if back["phrases"]:
                    st.markdown("- **Intent phrases kept**: `" + "`, `".join(back["phrases"]) + "`")
                st.caption("Terms are single words separated by single spaces, with no commas. "
                           "Word order does not matter to Amazon, and going one byte over 250 can "
                           "de-index the entire field, so the builder stops short rather than trimming "
                           "mid-word.")

            density = keyword_density(new_title, listing["highlights"], new_bullets)
            over = sorted([(w, c) for w, c in density.items() if c >= 4],
                          key=lambda x: -x[1])[:10]
            if over:
                st.warning("Repeated a lot in the visible copy, which reads as stuffing: "
                           + ", ".join(f"{w} ×{c}" for w, c in over))
            else:
                st.success("No word is over-repeated in the visible copy.")

            audits = [audit_title(new_title, brand, media_mode), audit_highlights(listing["highlights"])]
            audits += [audit_bullet(b, i + 1) for i, b in enumerate(new_bullets)]
            render_scorecard(audits)
            st.session_state["listing"] = {**listing, "title": new_title, "bullets": new_bullets}

# ======================================================================
# RULES
# ======================================================================
with tab_rules:
    st.markdown("#### What this tool enforces")
    st.markdown(f"""
**Title**
- **{TITLE_LIMIT_STANDARD} characters** including spaces. Media (Books, Music, Video, Software) keeps
  **{TITLE_LIMIT_MEDIA}** — the sidebar toggle, since it is the only category exception left.
- Enforced from **27 July 2026**. Amazon gradually **auto-rewrites** over-limit titles with its own AI.
- **Size and pack count are reserved.** Characters are set aside for them before anything else is
  placed, so they survive the cap. Colour, material, audience and use case go to Item Highlights.
- No special characters outside a brand name, no emoji, no repeated words, no ALL-CAPS, no promo claims.

**Item Highlights**
- Up to **{HIGHLIGHT_LIMIT} characters**, searchable, shown in mobile snippets. This is where the
  detail that no longer fits the title belongs.

**Bullets**
- **{MAX_BULLETS_SELLER}** for sellers, **{MAX_BULLETS_VENDOR}** for vendors, up to
  **{BULLET_HARD_LIMIT} characters** each. Start with a capital, sentence fragments with no end
  punctuation, feature then benefit, no HTML, no promo. The tool targets **{BULLET_SOFT_TARGET}**
  characters for mobile readability.

**Scoring**
- Blocking issue **−18**, warning **−5**. Grade A at 90 and above, F below 55.

**Two deliberate limits**
- In bullets, only clearly parenthetical promo is deleted. Other flagged wording is reported, not cut,
  because deleting words from mid-sentence breaks the copy. Reword those yourself.
- Keyword suggestions come from Google and Amazon autocomplete, which are public endpoints rather
  than official APIs. They can rate-limit or change shape, so the tool degrades to manual entry
  rather than failing.
    """)
    st.caption("Rules reflect Amazon's Seller Central announcement of 10 June 2026 (enforced 27 July "
               "2026) and the January 2025 title-standards update. Category style guides can still set "
               "stricter caps than the global limit.")
