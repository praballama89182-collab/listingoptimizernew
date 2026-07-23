"""
Listing Studio — Amazon Title · Item Highlights · Bullets (2026 rules)
=====================================================================
Two modes, one rule engine:

  • ENHANCE — paste an existing title / highlights / bullets, get a compliance
              audit (health score + specific fixes) and a corrected rewrite.
  • BUILD   — enter structured product facts (brand, product type, category /
              browse node, size, features, keywords…) and generate a compliant
              title, Item Highlights, and bullets from scratch.

The same engine that grades a listing is the one that constrains what the
builder produces, so a generated listing can never fail its own audit.

2026 policy baked in (Amazon Seller Central announcement 10 Jun 2026, enforced
27 Jul 2026; the Jan 2025 title-standards update is still in force):
  • Title <= 75 characters incl. spaces in every category EXCEPT Media
    (Books, Music, Video, Software), which keep the 200-char ceiling.
    Over-limit titles get auto-rewritten by Amazon's AI after 27 Jul 2026.
  • No special characters (! $ ? etc.) except inside a brand name; no repeated
    words; no promotional language; no ALL-CAPS words; no emoji.
  • Priority order inside the 75 chars: Brand -> Product Type -> primary
    keyword -> key variant (size/count/colour). The rest moves to Highlights.
  • Item Highlights: new structured, searchable field, up to 125 characters.
  • Bullets ("About this item"): 5 for sellers / 10 for vendors, <= 500 chars
    each, start capitalised, sentence fragments with no end punctuation,
    feature-then-benefit, no pricing/promo, no HTML.

The generator is deterministic (rules + templates) so it runs with zero setup.
Optional AI polish (Anthropic or OpenAI) is used only if a key is supplied, and
any AI output is re-audited by the same engine before it is shown.

Run:
    pip install -r requirements.txt
    streamlit run app.py
"""

from __future__ import annotations

import html as _html_mod
import json
import re
import textwrap
from dataclasses import dataclass, field

import streamlit as st

# ----------------------------------------------------------------------
# Policy constants
# ----------------------------------------------------------------------

TITLE_LIMIT_STANDARD = 75
TITLE_LIMIT_MEDIA = 200
HIGHLIGHT_LIMIT = 125
BULLET_HARD_LIMIT = 500          # Amazon's ceiling
BULLET_SOFT_TARGET = 240         # readable on mobile
MAX_BULLETS_SELLER = 5
MAX_BULLETS_VENDOR = 10

MEDIA_CATEGORIES = {"book", "music", "video", "dvd", "software", "video game", "media"}

# Characters Amazon disallows in titles (outside a brand name). Punctuation that
# appears legitimately in real titles ( - , . & ' ( ) / % : ) stays allowed.
BANNED_TITLE_CHARS = set("!$?_~*#^|<>{}[]@=+;\"\\")

# Subjective / promotional claims. Flagged everywhere; stripped from titles.
PROMO_TERMS = [
    "best seller", "bestseller", "best-selling", "best selling", "#1", "number one",
    "top rated", "top-rated", "top selling", "hottest", "sale", "on sale",
    "discount", "cheap", "cheapest", "free shipping", "free gift",
    "money back", "money-back", "satisfaction guaranteed", "guaranteed",
    "world's best", "world class", "premium quality", "amazing", "perfect",
    "flawless", "miracle", "must have", "must-have", "limited time",
    "limited-time", "buy now", "order now", "new arrival", "brand new",
]

# Phrases safe to delete outright without wrecking a sentence. Anything else is
# flagged for the human to reword rather than auto-mangled mid-bullet.
SAFE_STRIP = [
    "best seller", "bestseller", "best-selling", "best selling", "#1",
    "top rated", "top-rated", "top selling", "on sale", "free shipping",
    "free gift", "money back", "money-back", "satisfaction guaranteed",
    "world's best", "limited time", "limited-time", "buy now", "order now",
    "new arrival", "brand new",
]

# Ignored when checking a title for repeated words.
STOPWORDS = {
    "a", "an", "the", "and", "or", "for", "with", "to", "of", "in", "on", "by",
    "at", "from", "as", "is", "it", "x", "plus",
}

# Attribute -> benefit hints, used to auto-write bullets when only facts are
# given. Deliberately plain and honest; Amazon flags hype.
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
    "adjustable": "dials in to your preferred fit or setting",
    "compact": "slips into small spaces and travels without bulk",
    "portable": "goes wherever you go and sets up in seconds",
    "large": "leaves room to spare without taking over the space",
    "size": "sized for the way the product actually gets used",
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
}

# Rotated when a feature has no benefit and no hint matches, so several
# auto-written bullets never land on the same filler sentence.
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


def is_media_category(category: str) -> bool:
    c = (category or "").lower()
    return any(m in c for m in MEDIA_CATEGORIES)


def title_limit_for(category: str) -> int:
    return TITLE_LIMIT_MEDIA if is_media_category(category) else TITLE_LIMIT_STANDARD


def find_promo_terms(s: str) -> list:
    low = f" {(s or '').lower()} "
    hits = []
    for term in PROMO_TERMS:
        if re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", low):
            hits.append(term)
    return sorted(set(hits))


def find_banned_chars(s: str, allow: str = "") -> list:
    allow_set = set(allow or "")
    return sorted({c for c in (s or "") if c in BANNED_TITLE_CHARS and c not in allow_set})


def is_shouting(word: str) -> bool:
    """True only for genuine SHOUTED words. Model numbers (WH-1000XM5), sizes
    (18/8), and acronyms including hyphen-joined ones (USB-C) are left alone."""
    core = re.sub(r"[-/]", "", word or "")
    if not core.isalpha() or len(core) < 4 or not word.isupper():
        return False
    parts = [p for p in re.split(r"[-/]", word) if p]
    if all(p.upper() in ACRONYM_OK or len(p) <= 2 for p in parts):
        return False
    return True


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
    if w.upper() in ACRONYM_OK:
        return w.upper()
    return w[:1].upper() + w[1:].lower()


def trim_to(s: str, limit: int) -> tuple:
    """Trim on a word boundary. Returns (kept, overflow)."""
    s = clean_ws(s)
    if char_count(s) <= limit:
        return s, ""
    cut = s[:limit]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    overflow = clean_ws(s[len(cut):]).lstrip(",;- ")
    return clean_ws(cut).rstrip(",;- "), overflow

# ----------------------------------------------------------------------
# Audit engine
# ----------------------------------------------------------------------

SEV_ERROR = "error"   # Amazon will rewrite / suppress
SEV_WARN = "warn"     # allowed, but costs performance
SEV_OK = "ok"


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
        a.issues.append(Issue(
            SEV_ERROR,
            f"{a.count} chars — {a.count - limit} over the {limit}-char cap. From 27 Jul 2026 "
            f"Amazon auto-rewrites over-limit titles; move the overflow to Item Highlights."))
    elif a.count > limit * 0.95:
        a.issues.append(Issue(SEV_WARN, f"{a.count}/{limit} — right at the cap; leave some headroom."))

    banned = find_banned_chars(title, allow=brand)
    if banned:
        a.issues.append(Issue(SEV_ERROR,
                              "Special characters aren't allowed outside a brand name: " + " ".join(banned)))
    if strip_emoji(title) != title:
        a.issues.append(Issue(SEV_ERROR, "Emoji aren't allowed in titles."))

    promo = find_promo_terms(title)
    if promo:
        a.issues.append(Issue(SEV_ERROR, "Promotional or subjective claims: " + ", ".join(promo[:6])))

    caps = find_allcaps_words(title)
    if caps:
        a.issues.append(Issue(SEV_WARN, "ALL-CAPS words are discouraged: " + ", ".join(caps[:6])))

    dupes = find_repeated_words(title)
    if dupes:
        a.issues.append(Issue(SEV_WARN, "Repeated words (keyword-stuffing risk): " + ", ".join(dupes[:6])))

    if not a.errors and not a.warns:
        a.issues.append(Issue(SEV_OK, f"Compliant — {a.count}/{limit} chars, nothing banned."))
    return a


def audit_highlights(text: str) -> FieldAudit:
    text = text or ""
    a = FieldAudit("Item Highlights", text, char_count(text), HIGHLIGHT_LIMIT)
    if not text.strip():
        a.issues.append(Issue(SEV_WARN,
                              "Empty — Item Highlights is searchable and shows in mobile snippets. Use it."))
        return a
    if a.count > HIGHLIGHT_LIMIT:
        a.issues.append(Issue(SEV_ERROR, f"{a.count}/{HIGHLIGHT_LIMIT} — over the Item Highlights cap."))
    if strip_emoji(text) != text:
        a.issues.append(Issue(SEV_WARN, "Emoji present — keep highlights plain text."))
    if strip_html(text) != text:
        a.issues.append(Issue(SEV_ERROR, "HTML tags aren't allowed."))
    promo = find_promo_terms(text)
    if promo:
        a.issues.append(Issue(SEV_WARN, "Promotional wording: " + ", ".join(promo[:6])))
    if not a.errors and not a.warns:
        a.issues.append(Issue(SEV_OK, f"Good — {a.count}/{HIGHLIGHT_LIMIT} chars."))
    return a


def audit_bullet(text: str, idx: int) -> FieldAudit:
    text = text or ""
    a = FieldAudit(f"Bullet {idx}", text, char_count(text), BULLET_HARD_LIMIT)
    if not text.strip():
        a.issues.append(Issue(SEV_WARN, "Empty bullet."))
        return a
    if a.count > BULLET_HARD_LIMIT:
        a.issues.append(Issue(SEV_ERROR, f"{a.count}/{BULLET_HARD_LIMIT} — over Amazon's per-bullet cap."))
    elif a.count > BULLET_SOFT_TARGET:
        a.issues.append(Issue(SEV_WARN,
                              f"{a.count} chars — long for mobile; aim for {BULLET_SOFT_TARGET} or under."))
    first = text.strip()[:1]
    if first and first.isalpha() and not first.isupper():
        a.issues.append(Issue(SEV_WARN, "Should start with a capital letter."))
    if text.strip().endswith((".", "!", "?", ";")):
        a.issues.append(Issue(SEV_WARN,
                              "Ends with punctuation — Amazon wants sentence fragments, no full stop."))
    if strip_html(text) != text:
        a.issues.append(Issue(SEV_ERROR, "HTML tags aren't allowed in bullets."))
    if strip_emoji(text) != text:
        a.issues.append(Issue(SEV_WARN, "Emoji present — keep bullets plain text."))
    promo = find_promo_terms(text)
    if promo:
        a.issues.append(Issue(SEV_WARN, "Promotional or pricing language: " + ", ".join(promo[:6])))
    if not a.errors and not a.warns:
        a.issues.append(Issue(SEV_OK, f"Good — {a.count} chars."))
    return a


def health_score(audits: list) -> tuple:
    """0-100. Each blocking issue -18, each warning -5."""
    score = 100
    for a in audits:
        score -= 18 * len(a.errors)
        score -= 5 * len(a.warns)
    score = max(0, min(100, score))
    grade = ("A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70
             else "D" if score >= 55 else "F")
    return score, grade

# ----------------------------------------------------------------------
# Fixers (Enhance mode)
# ----------------------------------------------------------------------

def _strip_terms(text: str, terms: list) -> str:
    for term in terms:
        text = re.sub(r"(?i)(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", " ", text)
    return clean_ws(text)


def _tidy_punct(text: str) -> str:
    """Cleans up the orphaned punctuation left behind when a phrase is removed
    from the middle of a sentence — e.g. 'hot for 12.  !' -> 'hot for 12'."""
    t = clean_ws(text)
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)        # ' ,'  -> ','
    t = re.sub(r"([,.;:!?])\s*(?=[,.;:!?])", "", t)  # collapse runs of punctuation
    t = re.sub(r"^[\s,.;:!?\-]+", "", t)          # leading orphans
    t = re.sub(r"[\s,.;:!?\-]+$", "", t)          # trailing punctuation and space
    return clean_ws(t)


def fix_title(title: str, brand: str = "", media: bool = False) -> tuple:
    """Returns (fixed_title, overflow_text_for_highlights)."""
    limit = TITLE_LIMIT_MEDIA if media else TITLE_LIMIT_STANDARD
    t = clean_ws(strip_emoji(strip_html(title)))

    # drop banned characters, but keep any that live inside the brand name
    if brand and brand in t:
        head, _sep, tail = t.partition(brand)
        head = "".join(c for c in head if c not in BANNED_TITLE_CHARS)
        tail = "".join(c for c in tail if c not in BANNED_TITLE_CHARS)
        t = f"{head}{brand}{tail}"
    else:
        t = "".join(c for c in t if c not in BANNED_TITLE_CHARS)
    t = clean_ws(t)

    # titles are terse, so promo language is removed outright
    t = _strip_terms(t, PROMO_TERMS)
    t = _tidy_punct(t)

    # de-shout ALL-CAPS words, preserving acronyms and the brand
    brand_words = set(brand.split()) if brand else set()

    def _deshout(m):
        w = m.group(0)
        if w in brand_words:
            return w
        return titlecase_word(w) if is_shouting(w) else w

    t = re.sub(r"[A-Za-z][A-Za-z0-9\-/]*", _deshout, t)

    # drop duplicate content words, keeping the first occurrence
    seen, kept = set(), []
    for tok in t.split(" "):
        key = re.sub(r"[^a-z0-9]", "", tok.lower())
        if key and key not in STOPWORDS and len(key) > 2:
            if key in seen:
                continue
            seen.add(key)
        kept.append(tok)
    t = clean_ws(" ".join(kept))

    return trim_to(t, limit)


def fix_highlights(text: str, appended: str = "") -> str:
    h = clean_ws(strip_emoji(strip_html(text)))
    add = clean_ws(appended)
    if add:
        h = clean_ws(f"{h}, {add}") if h else add
    h = clean_ws(h).strip(",;- ")
    return trim_to(h, HIGHLIGHT_LIMIT)[0]


def fix_bullet(text: str) -> str:
    """Cleans a bullet. Only clearly parenthetical promo phrases are removed —
    other flagged wording is left for the human to reword rather than mangled
    mid-sentence."""
    b = clean_ws(strip_html(strip_emoji(text)))
    b = _strip_terms(b, SAFE_STRIP)
    b = _tidy_punct(b)
    if b:
        b = b[:1].upper() + b[1:]
    return trim_to(b, BULLET_HARD_LIMIT)[0]

# ----------------------------------------------------------------------
# Builders (Build mode)
# ----------------------------------------------------------------------

@dataclass
class ProductFacts:
    brand: str = ""
    product_type: str = ""        # "Coffee Mug", "Running Shoes"
    item_name: str = ""           # optional model / line name
    category: str = ""            # browse-node path or category name
    primary_keyword: str = ""
    secondary_keywords: str = ""  # comma separated
    size: str = ""                # "12 oz", "Pack of 3"
    color: str = ""
    material: str = ""
    audience: str = ""            # "for men", "for toddlers"
    use_case: str = ""            # "for cold brew", "for travel"
    features: list = field(default_factory=list)   # [(feature, benefit), ...]


def _norm(s: str) -> str:
    return clean_ws(re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()))


def build_title(f: ProductFacts) -> str:
    media = is_media_category(f.category)
    limit = TITLE_LIMIT_MEDIA if media else TITLE_LIMIT_STANDARD
    ptype = clean_ws(f.product_type or f.item_name)

    # Priority order: brand -> product type -> line name -> primary keyword
    head_tokens = [clean_ws(f.brand), ptype]
    if f.item_name and _norm(f.item_name) not in _norm(ptype):
        head_tokens.append(clean_ws(f.item_name))
    if f.primary_keyword and _norm(f.primary_keyword) not in _norm(" ".join(head_tokens)):
        head_tokens.append(clean_ws(f.primary_keyword))

    title = ""
    for tok in head_tokens:
        if not tok:
            continue
        candidate = clean_ws(f"{title} {tok}")
        if char_count(candidate) > limit:
            break
        title = candidate

    # Then the key variant (size / colour / material), comma separated
    for bit in [f.size, f.color, f.material]:
        bit = clean_ws(bit)
        if not bit or _norm(bit) in _norm(title):
            continue
        candidate = clean_ws(f"{title}, {bit}") if title else bit
        if char_count(candidate) <= limit:
            title = candidate

    # Any room left goes to audience / use case, then secondary keywords
    extras = [f.audience, f.use_case] + [k for k in (f.secondary_keywords or "").split(",")]
    for ex in extras:
        ex = clean_ws(ex)
        if not ex or _norm(ex) in _norm(title):
            continue
        sep = ", " if "," in title else " "
        candidate = clean_ws(f"{title}{sep}{ex}")
        if char_count(candidate) <= limit:
            title = candidate

    return fix_title(title, brand=f.brand, media=media)[0]


def build_highlights(f: ProductFacts, title: str) -> str:
    """Everything that didn't earn a place in the title, in 125 chars."""
    title_tokens = set(_norm(title).split())
    candidates = [f.material, f.size, f.color, f.use_case, f.audience]
    candidates += [k for k in (f.secondary_keywords or "").split(",")]
    candidates += [feat for feat, _b in f.features]

    picks, seen = [], set()
    for c in candidates:
        c = clean_ws(c)
        if not c:
            continue
        core = _norm(c)
        if not core or core in seen:
            continue
        # skip anything already fully represented in the title
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
    """Maps a feature to a plain-language benefit. Falls back to a rotating
    generic line so auto-written bullets don't all end the same way."""
    low = (feature or "").lower()
    for key, benefit in BENEFIT_HINTS.items():
        if key in low and (used is None or benefit not in used):
            return benefit
    for g in GENERIC_BENEFITS:
        if used is None or g not in used:
            return g
    return GENERIC_BENEFITS[0]


def build_bullets(f: ProductFacts, max_bullets: int = MAX_BULLETS_SELLER) -> list:
    rows = []
    used_benefits = set()

    def _take(feature: str, given: str = "") -> str:
        b = clean_ws(given) or _benefit_for(feature, used_benefits)
        used_benefits.add(b)
        return b

    # 1) explicit feature/benefit pairs first
    for feat, benefit in f.features:
        feat = clean_ws(feat)
        if not feat:
            continue
        rows.append((feat, _take(feat, benefit)))

    # 2) derive from structured attributes to fill the remaining slots
    if f.material:
        rows.append((f"{clean_ws(f.material)} build", _take(f.material)))
    if f.size:
        rows.append((f"{clean_ws(f.size)} size", _take(f.size)))
    if f.use_case:
        uc = clean_ws(f.use_case)
        rows.append((f"Built {uc}" if uc.startswith("for") else f"Built for {uc}",
                     "handles the job it was made for without workarounds"))
    if f.audience:
        aud = clean_ws(f.audience)
        rows.append((f"Made {aud}" if aud.startswith("for") else f"Made for {aud}",
                     "matches what this shopper is actually looking for"))
    if f.color:
        rows.append((f"{clean_ws(f.color)} finish",
                     "holds a clean, consistent look on the shelf and in use"))

    bullets, seen = [], set()
    for lead, benefit in rows:
        lead = clean_ws(lead).rstrip(":")
        if not lead:
            continue
        head = lead.upper() if len(lead) <= 28 else lead[:1].upper() + lead[1:]
        b = fix_bullet(f"{head}: {benefit}")
        key = _norm(b)[:40]
        if not b or key in seen:
            continue
        seen.add(key)
        bullets.append(b)
        if len(bullets) >= max_bullets:
            break
    return bullets

# ----------------------------------------------------------------------
# Optional AI polish — used only with a key, always re-audited afterwards
# ----------------------------------------------------------------------

AI_SYSTEM = (
    "You are an Amazon catalog copywriter. Follow Amazon's 2026 rules exactly: "
    f"title <= {TITLE_LIMIT_STANDARD} characters including spaces (Media categories allow "
    f"{TITLE_LIMIT_MEDIA}); no special characters except inside a brand name; no promotional or "
    "subjective claims; no repeated words; no ALL-CAPS words; no emoji. "
    f"Item Highlights <= {HIGHLIGHT_LIMIT} characters, plain text. "
    "Write exactly 5 bullets, each a capitalised sentence fragment with NO end punctuation, "
    f"<= {BULLET_SOFT_TARGET} characters, feature then benefit, no pricing or promo, no HTML. "
    'Return STRICT JSON only: {"title": str, "highlights": str, "bullets": [str, ...]}'
)


def ai_generate(provider: str, api_key: str, model: str, brief: str):
    """Returns a dict, or None on any failure so the caller falls back to rules."""
    st.session_state.pop("_ai_error", None)
    try:
        if provider == "Anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            msg = client.messages.create(
                model=model or "claude-sonnet-4-5",
                max_tokens=1200,
                system=AI_SYSTEM,
                messages=[{"role": "user", "content": brief}],
            )
            raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        elif provider == "OpenAI":
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            resp = client.chat.completions.create(
                model=model or "gpt-4o-mini",
                messages=[{"role": "system", "content": AI_SYSTEM},
                          {"role": "user", "content": brief}],
                max_tokens=1200,
            )
            raw = resp.choices[0].message.content
        else:
            return None
        raw = re.sub(r"^```(?:json)?|```$", "", (raw or "").strip(), flags=re.MULTILINE).strip()
        data = json.loads(raw)
        if isinstance(data, dict) and data.get("title"):
            return data
    except Exception as exc:  # noqa: BLE001 — any failure degrades to rule-based
        st.session_state["_ai_error"] = str(exc)
    return None


def facts_to_brief(f: ProductFacts) -> str:
    feats = "; ".join(f"{a} => {b}" if b else a for a, b in f.features if a.strip())
    return textwrap.dedent(f"""
        Write an Amazon listing.
        Brand: {f.brand}
        Product type: {f.product_type}
        Item / line name: {f.item_name}
        Category / browse node: {f.category}
        Primary keyword: {f.primary_keyword}
        Secondary keywords: {f.secondary_keywords}
        Size / count / capacity: {f.size}
        Colour: {f.color}
        Material: {f.material}
        Audience: {f.audience}
        Use case: {f.use_case}
        Key features (feature => benefit): {feats}
    """).strip()

# ----------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------

st.set_page_config(page_title="Listing Studio — Amazon 2026", page_icon="🛠️", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@500;600&display=swap');
html, body, [class*="css"] { font-family:'Inter', system-ui, sans-serif; }
.stApp { background:#0f1115; }
.block-container { padding-top:1.6rem; }
h1,h2,h3,h4 { color:#f4f5f7; letter-spacing:-0.01em; }
p, label, .stMarkdown { color:#c9cdd6; }

.brandbar { display:flex; align-items:baseline; gap:14px; flex-wrap:wrap;
    border-bottom:1px solid #23262e; padding-bottom:12px; margin-bottom:14px; }
.brandbar .logo { font-family:'IBM Plex Mono',monospace; font-weight:600; font-size:22px;
    color:#f4f5f7; letter-spacing:-0.5px; }
.brandbar .logo b { color:#ffcf56; }
.brandbar .tag { font-size:12.5px; color:#7d828e; font-weight:500; }

.counter { font-family:'IBM Plex Mono',monospace; font-size:12px; font-weight:600;
    padding:2px 9px; border-radius:999px; display:inline-block; }
.c-ok   { background:#123524; color:#54d18c; border:1px solid #1f5e40; }
.c-warn { background:#3a2f12; color:#ffcf56; border:1px solid #6b551d; }
.c-bad  { background:#3a1717; color:#ff8a7a; border:1px solid #6b2626; }

.scorewrap { display:flex; align-items:center; gap:18px; background:#151821;
    border:1px solid #23262e; border-radius:16px; padding:16px 20px; margin:6px 0 14px; }
.scorenum { font-family:'IBM Plex Mono',monospace; font-size:40px; font-weight:600; line-height:1; }
.scoremeta { font-size:12.5px; color:#8b909c; }
.grade { font-family:'IBM Plex Mono',monospace; font-weight:600; font-size:15px;
    padding:3px 11px; border-radius:8px; }

.issue { font-size:13px; padding:7px 12px; border-radius:9px; margin:5px 0;
    border-left:3px solid #2a2e37; background:#141720; color:#c9cdd6; }
.issue.error { border-left-color:#ff6b57; }
.issue.warn  { border-left-color:#ffcf56; }
.issue.ok    { border-left-color:#54d18c; }
.issue .sev { font-family:'IBM Plex Mono',monospace; font-size:10.5px; font-weight:600;
    text-transform:uppercase; letter-spacing:.06em; margin-right:8px; }
.issue.error .sev { color:#ff6b57; }
.issue.warn  .sev { color:#ffcf56; }
.issue.ok    .sev { color:#54d18c; }

.outfield { background:#151821; border:1px solid #262a34; border-radius:12px;
    padding:14px 16px; margin:8px 0; }
.outfield .flabel { font-family:'IBM Plex Mono',monospace; font-size:11px;
    text-transform:uppercase; letter-spacing:.08em; color:#8b909c; margin-bottom:6px; }
.outfield .fval { color:#eef0f4; font-size:14.5px; line-height:1.55; }
.outfield ul { margin:6px 0 0 0; padding-left:18px; }
.outfield li { margin:6px 0; color:#eef0f4; font-size:14.5px; line-height:1.55; }
.stTabs [data-baseweb="tab-list"] { gap:4px; }
[data-baseweb="tab"] { font-weight:600; }
</style>
""", unsafe_allow_html=True)

st.markdown(
    '<div class="brandbar"><span class="logo">Listing<b>·</b>Studio</span>'
    '<span class="tag">Amazon title · item highlights · bullets — built to the 2026 rules '
    '(75-char titles, 125-char highlights, enforced 27 Jul 2026)</span></div>',
    unsafe_allow_html=True,
)


def counter_pill(count: int, limit: int, soft: bool = False) -> str:
    cls = "c-bad" if count > limit else "c-warn" if count > limit * 0.9 else "c-ok"
    return f'<span class="counter {cls}">{count}/{limit}{" soft" if soft else ""}</span>'


def render_issues(a: FieldAudit):
    for i in a.issues:
        label = {"error": "Fix", "warn": "Warn", "ok": "OK"}[i.severity]
        st.markdown(
            f'<div class="issue {i.severity}"><span class="sev">{label}</span>{esc(i.message)}</div>',
            unsafe_allow_html=True)


def render_scorecard(audits: list):
    score, grade = health_score(audits)
    color = "#54d18c" if score >= 80 else "#ffcf56" if score >= 55 else "#ff6b57"
    n_err = sum(len(a.errors) for a in audits)
    n_warn = sum(len(a.warns) for a in audits)
    st.markdown(
        f'<div class="scorewrap"><div class="scorenum" style="color:{color}">{score}</div>'
        f'<div><span class="grade" style="background:{color}22;color:{color}">Grade {grade}</span>'
        f'<div class="scoremeta" style="margin-top:6px">{n_err} blocking · {n_warn} warnings · '
        f'across title, highlights and bullets</div></div></div>',
        unsafe_allow_html=True)


def build_export_text(title: str, highlights: str, bullets: list) -> str:
    lines = [f"TITLE ({char_count(title)} chars):", title, "",
             f"ITEM HIGHLIGHTS ({char_count(highlights)} chars):", highlights, "",
             "ABOUT THIS ITEM:"]
    lines += [f"- {b}" for b in bullets if b]
    return "\n".join(lines)


def render_output_block(title: str, highlights: str, bullets: list, media: bool, key: str):
    tl = TITLE_LIMIT_MEDIA if media else TITLE_LIMIT_STANDARD
    st.markdown(
        f'<div class="outfield"><div class="flabel">Title &nbsp; {counter_pill(char_count(title), tl)}</div>'
        f'<div class="fval">{esc(title) or "<i>—</i>"}</div></div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="outfield"><div class="flabel">Item Highlights &nbsp; '
        f'{counter_pill(char_count(highlights), HIGHLIGHT_LIMIT)}</div>'
        f'<div class="fval">{esc(highlights) or "<i>—</i>"}</div></div>', unsafe_allow_html=True)
    lis = "".join(
        f'<li>{esc(b)} &nbsp; {counter_pill(char_count(b), BULLET_SOFT_TARGET, soft=True)}</li>'
        for b in bullets if b)
    st.markdown(
        f'<div class="outfield"><div class="flabel">About This Item — '
        f'{len([b for b in bullets if b])} bullets</div><ul>{lis or "<li><i>—</i></li>"}</ul></div>',
        unsafe_allow_html=True)

    export = build_export_text(title, highlights, bullets)
    st.download_button("Download listing (.txt)", data=export.encode("utf-8"),
                       file_name="listing.txt", mime="text/plain", key=f"dl_{key}")
    with st.expander("Copy-paste block"):
        st.code(export, language="text")


# ---- Sidebar ----
with st.sidebar:
    st.subheader("Settings")
    seller_type = st.radio("Account type", ["Seller — 5 bullets", "Vendor — 10 bullets"], index=0)
    max_bullets = MAX_BULLETS_VENDOR if seller_type.startswith("Vendor") else MAX_BULLETS_SELLER
    st.caption("Media categories (Books, Music, Video, Software) keep the 200-character title "
               "limit. Everything else is capped at 75.")

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
                                help=f"Or set {secret_name} in .streamlit/secrets.toml. Never hard-code keys.")
        model = st.text_input("Model", value="claude-sonnet-4-5" if provider == "Anthropic" else "gpt-4o-mini")
        st.caption("AI output is re-checked by the same rule engine before it's shown, so it can't "
                   "hand back a non-compliant listing.")

use_ai = provider != "None — rule-based only" and bool(api_key)

tab_enhance, tab_build, tab_rules = st.tabs(
    ["Enhance an existing listing", "Build from scratch", "The 2026 rules"])

# ======================================================================
# ENHANCE
# ======================================================================
with tab_enhance:
    st.markdown("#### Paste what's live now")
    st.caption("You get a health score with specific fixes, then a corrected rewrite that fits the "
               "2026 limits. Anything trimmed from the title is offered back as Item Highlights.")

    c1, c2 = st.columns(2)
    with c1:
        e_brand = st.text_input("Brand name", key="e_brand",
                                help="Given here so characters inside your brand aren't stripped.")
    with c2:
        e_category = st.text_input("Category / browse node", key="e_cat",
                                   help="Used to detect the Media 200-character exception.")

    e_media = is_media_category(e_category)
    e_limit = TITLE_LIMIT_MEDIA if e_media else TITLE_LIMIT_STANDARD
    st.caption(f"Title limit for this category: **{e_limit} characters**"
               + (" (Media exception)" if e_media else ""))

    e_title = st.text_area("Current title", height=70, key="e_title")
    st.markdown(counter_pill(char_count(e_title), e_limit), unsafe_allow_html=True)

    e_high = st.text_area("Current Item Highlights, if any", height=70, key="e_high")
    st.markdown(counter_pill(char_count(e_high), HIGHLIGHT_LIMIT), unsafe_allow_html=True)

    e_bullets_raw = st.text_area("Current bullets — one per line", height=150, key="e_bul")

    if st.button("Audit and fix", type="primary", key="e_go"):
        bullets_in = [b for b in (e_bullets_raw or "").splitlines() if b.strip()]
        audits = [audit_title(e_title, e_brand, e_media), audit_highlights(e_high)]
        audits += [audit_bullet(b, i + 1) for i, b in enumerate(bullets_in)]

        render_scorecard(audits)
        st.markdown("##### What's wrong now")
        for a in audits:
            st.markdown(f"**{a.field}** &nbsp; {counter_pill(a.count, a.limit)}", unsafe_allow_html=True)
            render_issues(a)

        st.markdown("---")
        st.markdown("##### Corrected rewrite")

        fixed_title, overflow = fix_title(e_title, e_brand, e_media)
        fixed_high = fix_highlights(e_high, appended=overflow)
        fixed_bullets = [fix_bullet(b) for b in bullets_in][:max_bullets]

        if use_ai:
            brief = (f"Rewrite this listing to be fully compliant while keeping its meaning and "
                     f"keywords.\nCategory: {e_category}\nBrand: {e_brand}\nTitle: {e_title}\n"
                     f"Highlights: {e_high}\nBullets: {bullets_in}")
            data = ai_generate(provider, api_key, model, brief)
            if data:
                fixed_title = fix_title(data.get("title") or fixed_title, e_brand, e_media)[0]
                fixed_high = fix_highlights(data.get("highlights") or fixed_high)
                fixed_bullets = [fix_bullet(b) for b in (data.get("bullets") or fixed_bullets)][:max_bullets]
            elif st.session_state.get("_ai_error"):
                st.warning("AI polish unavailable, so this is the rule-based rewrite. "
                           f"({st.session_state['_ai_error']})")

        if overflow:
            st.caption(f"Moved out of the title and into Item Highlights: “{overflow}”")

        render_output_block(fixed_title, fixed_high, fixed_bullets, e_media, key="enh")

        post = [audit_title(fixed_title, e_brand, e_media), audit_highlights(fixed_high)]
        post += [audit_bullet(b, i + 1) for i, b in enumerate(fixed_bullets)]
        before, _ = health_score(audits)
        after, _ = health_score(post)
        st.success(f"Health score {before} → {after} out of 100")

        with st.expander("Audit of the rewrite"):
            for a in post:
                st.markdown(f"**{a.field}** &nbsp; {counter_pill(a.count, a.limit)}", unsafe_allow_html=True)
                render_issues(a)

# ======================================================================
# BUILD
# ======================================================================
with tab_build:
    st.markdown("#### Start from product facts")
    st.caption("Enter what you know. The most important facts go into the 75-character title in "
               "priority order — brand, product type, primary keyword, key variant — and everything "
               "else flows down into Item Highlights and the bullets.")

    b1, b2, b3 = st.columns(3)
    with b1:
        f_brand = st.text_input("Brand name (required)", key="b_brand")
        f_type = st.text_input("Product type (required)", key="b_type",
                               placeholder="Coffee Mug, Running Shoes…")
        f_item = st.text_input("Item or line name", key="b_item")
    with b2:
        f_cat = st.text_input("Category / browse node", key="b_cat",
                              placeholder="Home & Kitchen > Kitchen & Dining > Drinkware",
                              help="Paste the browse-node path. Detects the Media 200-char exception.")
        f_pk = st.text_input("Primary keyword", key="b_pk")
        f_sk = st.text_input("Secondary keywords, comma separated", key="b_sk")
    with b3:
        f_size = st.text_input("Size / count / capacity", key="b_size", placeholder="12 oz, Pack of 3…")
        f_color = st.text_input("Colour or finish", key="b_color")
        f_mat = st.text_input("Material", key="b_mat")

    b4, b5 = st.columns(2)
    with b4:
        f_aud = st.text_input("Audience", key="b_aud", placeholder="for men, for toddlers…")
    with b5:
        f_use = st.text_input("Use case", key="b_use", placeholder="for cold brew, for travel…")

    b_media = is_media_category(f_cat)
    st.caption(f"Title limit for this category: **{TITLE_LIMIT_MEDIA if b_media else TITLE_LIMIT_STANDARD} "
               f"characters**" + (" (Media exception)" if b_media else ""))

    st.markdown("**Key features and what they do for the buyer** — benefit is optional, it gets inferred")
    feat_rows = []
    for i in range(5):
        fc1, fc2 = st.columns([1, 1.4])
        with fc1:
            feat = st.text_input(f"Feature {i+1}", key=f"feat_{i}", label_visibility="collapsed",
                                 placeholder=f"Feature {i+1} — e.g. Double-wall insulation")
        with fc2:
            ben = st.text_input(f"Benefit {i+1}", key=f"ben_{i}", label_visibility="collapsed",
                                placeholder="Benefit — e.g. keeps drinks hot for six hours")
        if feat.strip():
            feat_rows.append((feat, ben))

    if st.button("Generate listing", type="primary", key="b_go"):
        if not f_brand.strip() or not f_type.strip():
            st.error("Add a brand name and a product type — the title is built around them.")
        else:
            facts = ProductFacts(
                brand=f_brand, product_type=f_type, item_name=f_item, category=f_cat,
                primary_keyword=f_pk, secondary_keywords=f_sk, size=f_size, color=f_color,
                material=f_mat, audience=f_aud, use_case=f_use, features=feat_rows,
            )
            title = build_title(facts)
            highlights = build_highlights(facts, title)
            bullets = build_bullets(facts, max_bullets)

            if use_ai:
                data = ai_generate(provider, api_key, model, facts_to_brief(facts))
                if data:
                    title = fix_title(data.get("title") or title, f_brand, b_media)[0]
                    highlights = fix_highlights(data.get("highlights") or highlights)
                    bullets = [fix_bullet(b) for b in (data.get("bullets") or bullets)][:max_bullets]
                elif st.session_state.get("_ai_error"):
                    st.warning("AI unavailable, so this is the rule-based build. "
                               f"({st.session_state['_ai_error']})")

            audits = [audit_title(title, f_brand, b_media), audit_highlights(highlights)]
            audits += [audit_bullet(b, i + 1) for i, b in enumerate(bullets)]
            render_scorecard(audits)

            st.markdown("##### Generated listing")
            render_output_block(title, highlights, bullets, b_media, key="bld")

            with st.expander("Field-by-field audit"):
                for a in audits:
                    st.markdown(f"**{a.field}** &nbsp; {counter_pill(a.count, a.limit)}",
                                unsafe_allow_html=True)
                    render_issues(a)

# ======================================================================
# RULES
# ======================================================================
with tab_rules:
    st.markdown("#### What this tool enforces")
    st.markdown(f"""
**Title**
- **{TITLE_LIMIT_STANDARD} characters** including spaces in every category **except Media**
  (Books, Music, Video, Software), which keep the **{TITLE_LIMIT_MEDIA}-character** ceiling.
- Enforced from **27 July 2026**. Amazon gradually **auto-rewrites** over-limit titles with its own
  AI, so going over means losing editorial control of your strongest ranking signal.
- **No special characters** (`!` `$` `?` and similar) except inside a brand name. **No emoji.**
- **No repeated words**, **no ALL-CAPS words**, **no promotional or subjective claims**
  ("best seller", "#1", "on sale", "satisfaction guaranteed").
- Priority order inside the limit: **brand → product type → primary keyword → key variant**
  (size, count, colour). Everything else belongs in Item Highlights.

**Item Highlights** — the new field
- Up to **{HIGHLIGHT_LIMIT} characters**, **searchable**, and shown in **mobile** search snippets and
  on the detail page. This is where the detail that no longer fits the title goes.

**Bullets — "About this item"**
- **{MAX_BULLETS_SELLER}** bullets for sellers, **{MAX_BULLETS_VENDOR}** for vendors,
  up to **{BULLET_HARD_LIMIT} characters** each.
- Start with a **capital**. Write **sentence fragments with no end punctuation**. Lead with the
  **feature, then the benefit**.
- No pricing or promotional language, no HTML, no emoji.
- This tool aims for **{BULLET_SOFT_TARGET} characters** as a mobile-readable target and warns above it,
  well under Amazon's hard {BULLET_HARD_LIMIT}.

**How the score works**
- Each blocking issue (over the limit, banned characters, promo claim, HTML) costs **18 points**.
- Each warning (long for mobile, ALL-CAPS, repeated word, trailing full stop) costs **5 points**.
- Grade A at 90 and above, down to F below 55.

**One deliberate limitation**
- In bullets, only clearly parenthetical promo phrases are deleted automatically. Other flagged
  wording is reported rather than cut, because stripping words out of the middle of a 500-character
  sentence produces broken copy. Reword those yourself.
    """)
    st.caption("Rules reflect Amazon's Seller Central announcement of 10 June 2026 (enforced 27 July "
               "2026) and the January 2025 title-standards update. Category style guides can set "
               "stricter caps than the global limit — check yours before publishing.")
