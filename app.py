"""
Listing Studio — core rules engine (no Streamlit).
Amazon 2026 rules for title, item highlights, bullets and backend search terms.
"""
from __future__ import annotations
import html as _h, re, unicodedata
from dataclasses import dataclass, field

# ----------------------------------------------------------------- limits
TITLE_LIMIT        = 75
TITLE_LIMIT_MEDIA  = 200
HIGHLIGHT_LIMIT    = 125
BULLET_MIN         = 150     # Amazon-recommended floor
BULLET_MAX         = 200     # Amazon-recommended ceiling
BULLET_HARD        = 500     # absolute cap
BULLETS_TOTAL_MAX  = 1000    # cumulative across all five
DESCRIPTION_LIMIT  = 2000
BACKEND_BYTES      = 249     # strict; one byte over de-indexes the field
MAX_BULLETS        = 5

# ----------------------------------------------------------------- vocab
BANNED_TITLE_CHARS = set("!$?_~*#^|<>{}[]@=+;\"\\")

PROMO_TERMS = ["best seller","bestseller","best selling","#1","number one","top rated",
    "top selling","hottest","sale","on sale","discount","cheap","cheapest","free shipping",
    "free gift","money back","satisfaction guaranteed","guaranteed","world's best",
    "premium quality","amazing","perfect","flawless","miracle","must have","limited time",
    "buy now","order now","new arrival","brand new"]

# words that must never start or end a clause
CONJUNCTIONS = {"and","or","but","so","which","plus","also","then","while","whereas",
                "yet","nor","because","although","though","however"}
DANGLING_END = CONJUNCTIONS | {"the","a","an","with","for","of","in","on","to","at","from",
                               "as","by","that","this","its","your","our","is","are","be"}

BACKEND_STOP = CONJUNCTIONS | {"a","an","the","for","with","to","of","in","on","by","at",
    "from","as","is","it","this","that","these","those","your","our","you","we","they","its",
    "be","are","was","were","can","will","has","have","not","all","any","more","most","very",
    "just","also","than","when","how","what","buy","shop","sale","new","best","free","top",
    "great","good","nice","amazon","asin","com","de","la","el","los","las","del","para","con",
    "una","por","que","le","les","des","du","et","pour","avec","der","die","das","und","mit",
    "ein","il","lo","di","da","per"}

DISEASE_CLAIMS = ["cure","cures","treat","treats","prevent","prevents","heal","heals","remedy",
    "therapeutic","medicine","medicinal","arthritis","cancer","diabetes","infection","disease",
    "anti-inflammatory","antibiotic","fda approved","clinically proven","vet recommended"]

# unit abbreviations that save title characters
UNIT_ABBREV = {"ounces":"oz","ounce":"oz","pounds":"lb","pound":"lb","fluid ounces":"fl oz",
    "millilitres":"ml","millilitres":"ml","milliliters":"ml","litres":"l","liters":"l",
    "grams":"g","kilograms":"kg","inches":"in","centimetres":"cm","centimeters":"cm","count":"ct"}

UNITS = (r"fl\.?\s?oz|ounces?|oz|millilit(?:er|re)s?|ml|lit(?:er|re)s?|ltr|gallons?|gal|"
         r"quarts?|qt|kilograms?|kgs?|milligrams?|mg|grams?|gm|pounds?|lbs?|inch(?:es)?|"
         r"cm|mm|feet|ft|watts?|volts?|mah|g|kg|lb|in|l|w|v|m")
SIZE_RE = re.compile(r"\b\d+(?:[\.,]\d+)?\s*(?:" + UNITS + r")\b", re.I)
PACK_RE = re.compile(r"\b(?:pack\s+of\s+\d+|set\s+of\s+\d+|box\s+of\s+\d+|"
                     r"\d+\s*[-\s]?(?:pack|pk|pcs?|pieces?|count|ct|units?))\b", re.I)
DIM_RE  = re.compile(r"\b\d+(?:\.\d+)?\s*(?:x|\u00D7)\s*\d+(?:\.\d+)?"
                     r"(?:\s*(?:x|\u00D7)\s*\d+(?:\.\d+)?)?\s*(?:cm|mm|inch(?:es)?|in|ft|m)?\b", re.I)
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
                      "\u2190-\u21FF\u2B00-\u2BFF\uFE0F]")
HTML_RE  = re.compile(r"<[^>]+>")
WS_RE    = re.compile(r"\s+")
CONTACT_RE = re.compile(r"(https?://\S+|www\.\S+|\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b|\+?\d[\d\s().-]{8,}\d)")
ACRONYMS = {"USB","LED","HD","UV","BPA","XL","XXL","XXXL","USA","PU","TPU","3D","4K","SPF",
            "ML","OZ","PCS","ABS","PVC","EVA","DHA","EPA","SPF","IPX7","ASTM","CPSC"}
NUM_WORDS = {1:"one",2:"two",3:"three",4:"four",5:"five",6:"six",7:"seven",8:"eight",9:"nine"}
BULLET_MARK_RE = re.compile(r"^\s*(?:[\u2022\u2023\u25CF\u25AA\u00B7\-\*\u2013\u2014]+|\(?\d{1,2}[\.\)])\s*")
SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")

# ----------------------------------------------------------------- helpers
def plain(s):
    """Fold styled Unicode back to plain ASCII. Sellers paste bold or italic text
    from formatting tools, but those are mathematical alphanumeric symbols, not
    letters, and Amazon rejects them."""
    s = unicodedata.normalize("NFKC", s or "")
    s = s.replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"') \
         .replace("\u201d", '"').replace("\u2013", "-").replace("\u2014", "-") \
         .replace("\u00a0", " ").replace("\u200b", "")
    return s


def ws(s):  return WS_RE.sub(" ", plain(s).strip())
def n(s):   return ws(re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()))
def nkw(s): return ws(re.sub(r"[^\w\s]", " ", (s or "").lower(), flags=re.UNICODE))
def clen(s):return len(s or "")
def blen(s):return len((s or "").encode("utf-8"))
def esc(s): return _h.escape(s or "")
def no_emoji(s): return EMOJI_RE.sub("", s or "")
def no_html(s):  return HTML_RE.sub("", s or "")

def strip_conjunctions(text):
    """No clause may open or close on a conjunction or dangling article."""
    words = ws(text).split()
    while words and n(words[0]) in CONJUNCTIONS: words.pop(0)
    while words and n(words[-1]).strip(",;:") in DANGLING_END: words.pop()
    out = " ".join(words)
    out = re.sub(r"\s+([,;:.])", r"\1", out)
    out = re.sub(r"[,;:]+$", "", out)
    return ws(out)

def tidy(text):
    t = ws(text)
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    t = re.sub(r"([,.;:!?])\s*(?=[,.;:!?])", "", t)
    t = re.sub(r"^[\s,.;:!?\-]+", "", t)
    t = re.sub(r"[\s,.;:\-]+$", "", t)
    return ws(t)

def number_units(text):
    """'50ml' -> '50 ml'; standalone 1-9 spelled out, measurements and models left alone."""
    t = re.sub(r"(\d)\s*(" + UNITS + r")\b", r"\1 \2", text or "", flags=re.I)
    def repl(m):
        return NUM_WORDS[int(m.group(1))]
    t = re.sub(r"(?<![\w.\-/])(?<!pack of )(?<!set of )(?<!box of )([1-9])"
               r"(?![\d\w.\-/])(?!\s*(?:" + UNITS + r")\b)", repl, t, flags=re.I)
    return ws(t)

def abbreviate_units(text):
    t = text or ""
    for long, short in UNIT_ABBREV.items():
        t = re.sub(r"(?i)(?<![a-z])" + re.escape(long) + r"(?![a-z])", short, t)
    return ws(t)

def drop_filler(text):
    """'Phone Case with Kickstand for iPhone' -> 'iPhone Kickstand Phone Case' economy:
    removes 'for'/'with' joins that cost characters in a title."""
    t = re.sub(r"(?i)\s+\b(?:for|with)\b\s+", " ", text or "")
    return ws(t)

def strip_promo(text):
    t = text or ""
    for p in PROMO_TERMS:
        t = re.sub(r"(?i)(?<![a-z0-9])" + re.escape(p) + r"(?![a-z0-9])", " ", t)
    return tidy(t)

def find_promo(text):
    low = f" {(text or '').lower()} "
    return sorted({p for p in PROMO_TERMS
                   if re.search(r"(?<![a-z0-9])" + re.escape(p) + r"(?![a-z0-9])", low)})

def find_claims(text):
    low = f" {(text or '').lower()} "
    return sorted({c for c in DISEASE_CLAIMS
                   if re.search(r"(?<![a-z0-9])" + re.escape(c) + r"(?![a-z0-9])", low)})

def find_banned(text, allow=""):
    a = set(allow or "")
    return sorted({c for c in (text or "") if c in BANNED_TITLE_CHARS and c not in a})

def shouting(w):
    core = re.sub(r"[-/]", "", w or "")
    if not core.isalpha() or len(core) < 4 or not w.isupper(): return False
    return not all(p.upper() in ACRONYMS or len(p) <= 2 for p in re.split(r"[-/]", w) if p)

def trim_to(s, limit):
    s = ws(s)
    if clen(s) <= limit: return s, ""
    cut = s[:limit]
    if " " in cut: cut = cut.rsplit(" ", 1)[0]
    return tidy(cut), tidy(s[len(cut):])

def parse_lines(text):
    out = []
    for raw in (text or "").splitlines():
        line = ws(BULLET_MARK_RE.sub("", raw))
        if line: out.append(line)
    return out

# ================================================================= AUDITS
SEV_E, SEV_W, SEV_OK = "error", "warn", "ok"

@dataclass
class Issue:
    severity: str
    message: str

@dataclass
class Audit:
    field: str; value: str; count: int; limit: int
    issues: list = field(default_factory=list)
    @property
    def errors(self): return [i for i in self.issues if i.severity == SEV_E]
    @property
    def warns(self):  return [i for i in self.issues if i.severity == SEV_W]

def audit_title(t, brand="", media=False):
    t = t or ""; lim = TITLE_LIMIT_MEDIA if media else TITLE_LIMIT
    a = Audit("Title", t, clen(t), lim)
    if not t.strip():
        a.issues.append(Issue(SEV_E, "Title is empty.")); return a
    if a.count > lim:
        a.issues.append(Issue(SEV_E, f"{a.count - lim} characters over the {lim} limit. "
                                     "Amazon rewrites over-limit titles automatically from 27 Jul 2026."))
    b = find_banned(t, brand)
    if b: a.issues.append(Issue(SEV_E, "Characters not allowed outside a brand name: " + " ".join(b)))
    if no_emoji(t) != t: a.issues.append(Issue(SEV_E, "Emoji are not allowed."))
    p = find_promo(t)
    if p: a.issues.append(Issue(SEV_E, "Promotional claims: " + ", ".join(p[:5])))
    caps = [w for w in re.findall(r"[A-Za-z][A-Za-z0-9\-/]*", t) if shouting(w)]
    if caps: a.issues.append(Issue(SEV_W, "ALL-CAPS words: " + ", ".join(caps[:5])))
    seen, dup = set(), []
    for w in re.findall(r"[A-Za-z0-9]+", t.lower()):
        if len(w) > 2 and w not in BACKEND_STOP:
            if w in seen and w not in dup: dup.append(w)
            seen.add(w)
    if dup: a.issues.append(Issue(SEV_W, "Repeated words: " + ", ".join(dup[:5])))
    if not a.errors and not a.warns:
        a.issues.append(Issue(SEV_OK, "Compliant."))
    return a

def audit_highlights(t):
    t = t or ""; a = Audit("Item Highlights", t, clen(t), HIGHLIGHT_LIMIT)
    if not t.strip():
        a.issues.append(Issue(SEV_W, "Empty. This field is searchable and shows under the title on mobile."))
        return a
    if a.count > HIGHLIGHT_LIMIT:
        a.issues.append(Issue(SEV_E, f"{a.count - HIGHLIGHT_LIMIT} characters over the {HIGHLIGHT_LIMIT} limit."))
    if no_html(t) != t: a.issues.append(Issue(SEV_E, "HTML is not allowed."))
    if no_emoji(t) != t: a.issues.append(Issue(SEV_W, "Emoji present."))
    p = find_promo(t)
    if p: a.issues.append(Issue(SEV_W, "Subjective marketing wording: " + ", ".join(p[:5])))
    if ";" not in t and len(t.split()) > 6:
        a.issues.append(Issue(SEV_W, "Amazon's format is spec, then a semicolon, then the use case."))
    if not a.errors and not a.warns: a.issues.append(Issue(SEV_OK, "Compliant."))
    return a

def audit_bullet(t, idx):
    t = t or ""; a = Audit(f"Bullet {idx}", t, clen(t), BULLET_HARD)
    if not t.strip():
        a.issues.append(Issue(SEV_W, "Empty bullet.")); return a
    if a.count > BULLET_HARD:
        a.issues.append(Issue(SEV_E, f"Over the {BULLET_HARD} character cap."))
    elif a.count > BULLET_MAX:
        a.issues.append(Issue(SEV_W, f"{a.count} characters. Amazon's guidance is {BULLET_MIN} to {BULLET_MAX}."))
    elif a.count < BULLET_MIN:
        a.issues.append(Issue(SEV_W, f"{a.count} characters, under the {BULLET_MIN} guidance. Add the supporting detail."))
    if t.strip().endswith((".", "!", "?")):
        a.issues.append(Issue(SEV_W, "Ends with punctuation. Bullets are sentence fragments."))
    if no_html(t) != t: a.issues.append(Issue(SEV_E, "HTML is not allowed."))
    if no_emoji(t) != t: a.issues.append(Issue(SEV_W, "Emoji present."))
    first = t.split(":")[0]
    if ":" not in t or not first.isupper():
        a.issues.append(Issue(SEV_W, "Amazon's format is an ALL-CAPS header, a colon, then the benefit."))
    words = t.split()
    if words and n(words[0]) in CONJUNCTIONS:
        a.issues.append(Issue(SEV_E, f"Starts with '{words[0]}', which is not a sentence."))
    if words and n(words[-1]).strip(",;:") in DANGLING_END:
        a.issues.append(Issue(SEV_E, f"Ends on '{words[-1]}', leaving the clause unfinished."))
    p = find_promo(t)
    if p: a.issues.append(Issue(SEV_W, "Promotional wording: " + ", ".join(p[:5])))
    if not a.errors and not a.warns: a.issues.append(Issue(SEV_OK, "Compliant."))
    return a

def audit_bullets_total(bullets):
    total = sum(clen(b) for b in bullets or [])
    a = Audit("All bullets", "", total, BULLETS_TOTAL_MAX)
    if total > BULLETS_TOTAL_MAX:
        a.issues.append(Issue(SEV_W, f"{total} characters across all bullets. Amazon's guidance keeps "
                                     f"the total under {BULLETS_TOTAL_MAX}."))
    else:
        a.issues.append(Issue(SEV_OK, f"{total}/{BULLETS_TOTAL_MAX} characters across all bullets."))
    return a

def audit_backend(terms):
    t = terms or ""; a = Audit("Search terms", t, blen(t), BACKEND_BYTES)
    if not t.strip():
        a.issues.append(Issue(SEV_W, "Empty.")); return a
    if a.count > BACKEND_BYTES:
        a.issues.append(Issue(SEV_E, f"{a.count} bytes. Over {BACKEND_BYTES} and Amazon ignores the whole field."))
    if "," in t or ";" in t:
        a.issues.append(Issue(SEV_E, "Commas or semicolons present. Separate terms with single spaces only."))
    if t != t.lower():
        a.issues.append(Issue(SEV_W, "Should be all lowercase."))
    words = t.split()
    if len(words) != len(set(words)):
        a.issues.append(Issue(SEV_E, "A word is repeated. Every term must be unique."))
    if not a.errors and not a.warns: a.issues.append(Issue(SEV_OK, "Compliant."))
    return a

def audit_description(t):
    t = t or ""; a = Audit("Description", t, clen(t), DESCRIPTION_LIMIT)
    if not t.strip():
        a.issues.append(Issue(SEV_W, "Empty.")); return a
    if a.count > DESCRIPTION_LIMIT: a.issues.append(Issue(SEV_E, "Over the 2000 character cap."))
    if no_html(t) != t: a.issues.append(Issue(SEV_E, "HTML is not allowed."))
    if CONTACT_RE.search(t):
        a.issues.append(Issue(SEV_E, "Contains a link, email or phone number, which is prohibited."))
    p = find_promo(t)
    if p: a.issues.append(Issue(SEV_W, "Promotional wording: " + ", ".join(p[:5])))
    c = find_claims(t)
    if c: a.issues.append(Issue(SEV_W, "Claim language to verify: " + ", ".join(c[:5])))
    if not a.errors and not a.warns: a.issues.append(Issue(SEV_OK, "Compliant."))
    return a

def score(audits):
    s = 100
    for a in audits: s -= 18 * len(a.errors) + 5 * len(a.warns)
    s = max(0, min(100, s))
    g = "A" if s >= 90 else "B" if s >= 80 else "C" if s >= 70 else "D" if s >= 55 else "F"
    return s, g

# ================================================================= FACTS
@dataclass
class Facts:
    brand: str = ""
    product_type: str = ""
    attr1: str = ""          # strongest qualifier, sits before the product type
    attr2: str = ""
    attr3: str = ""
    attr4: str = ""
    usp: str = ""            # the single differentiator worth title space
    size_gender: str = ""    # size, capacity, pack count or gender
    features: list = field(default_factory=list)
    use_case: str = ""

    # kept so older calls still work
    @property
    def size(self): return self.size_gender

    def ordered(self):
        """Content in the order it competes for space: title, then highlights,
        then bullets."""
        return [("brand", self.brand), ("attr1", self.attr1),
                ("product_type", self.product_type), ("usp", self.usp),
                ("size_gender", self.size_gender), ("attr2", self.attr2),
                ("attr3", self.attr3), ("attr4", self.attr4)]

# ================================================================= TITLE
def fix_title(t, brand="", media=False):
    lim = TITLE_LIMIT_MEDIA if media else TITLE_LIMIT
    t = ws(no_emoji(no_html(t)))
    if brand and brand in t:
        h, _s, tail = t.partition(brand)
        h = "".join(c for c in h if c not in BANNED_TITLE_CHARS)
        tail = "".join(c for c in tail if c not in BANNED_TITLE_CHARS)
        t = f"{h}{brand}{tail}"
    else:
        t = "".join(c for c in t if c not in BANNED_TITLE_CHARS)
    t = tidy(strip_promo(ws(t)))
    bw = set(brand.split()) if brand else set()
    t = re.sub(r"[A-Za-z][A-Za-z0-9\-/]*",
               lambda m: m.group(0) if m.group(0) in bw or not shouting(m.group(0))
               else (m.group(0).upper() if m.group(0).upper() in ACRONYMS
                     else m.group(0)[:1].upper() + m.group(0)[1:].lower()), t)
    seen, kept = set(), []
    for tok in t.split(" "):
        k = re.sub(r"[^a-z0-9]", "", tok.lower())
        if k and k not in BACKEND_STOP and len(k) > 2:
            if k in seen:
                punct = re.sub(r"[A-Za-z0-9]", "", tok)
                if punct and kept: kept[-1] += punct
                continue
            seen.add(k)
        kept.append(tok)
    return trim_to(ws(" ".join(kept)), lim)

def brand_first(title, brand):
    brand, title = ws(brand), ws(title)
    if not brand: return title
    if n(title).startswith(n(brand) + " ") or n(title) == n(brand): return title
    rest = tidy(re.sub(r"(?i)(?<![a-z0-9])" + re.escape(brand) + r"(?![a-z0-9])", " ", title))
    return ws(f"{brand} {rest}") if rest else brand

def build_title(f: Facts, media=False):
    """[Brand] + [Attribute 1] + [Product Type] + [USP], [Size or Gender].
    Returns the title only; use compose() to get what did not fit."""
    return compose(f, media)["title"]


def _title_pass(f: Facts, media=False):
    lim = TITLE_LIMIT_MEDIA if media else TITLE_LIMIT
    size = abbreviate_units(ws(f.size_gender))
    tail = f", {size}" if size else ""
    budget = max(0, lim - clen(tail))

    head, used = "", set()
    for key, val in [("brand", f.brand), ("attr1", f.attr1),
                     ("product_type", f.product_type), ("usp", f.usp)]:
        v = drop_filler(ws(val)) if key in ("attr1", "product_type", "usp") else ws(val)
        if not v: continue
        cand = ws(f"{head} {v}") if head else v
        if clen(cand) <= budget and n(v) not in n(head):
            head, _ = cand, used.add(key)
    if size: used.add("size_gender")
    title = ws(head + tail) if head else ws(tail.lstrip(", "))
    title = brand_first(title, f.brand)
    return fix_title(title, f.brand, media)[0], used


# ================================================================= HIGHLIGHTS
def build_highlights(f: Facts, title, extra=None):
    return compose(f, extra=extra)["highlights"]


def _highlights_pass(f: Facts, title, used, extra=None):
    """[spec]; [differentiator or use case], <=125. Fed by whatever the title
    could not carry, in the same priority order."""
    spec_side = [ws(f.attr1), abbreviate_units(ws(f.size_gender))]
    left, seen = "", set()
    for sp in [x for x in spec_side if x]:
        k = n(sp)
        if not k or k in seen: continue
        cand = f"{left}, {sp}" if left else sp
        if clen(cand) <= HIGHLIGHT_LIMIT // 2:
            seen.add(k); left = cand

    leftovers = [v for key, v in f.ordered() if key not in used and ws(v)]
    use_pool = leftovers + [ws(f.usp), ws(f.use_case)] + \
               [ws(x) for x in (f.features or [])] + list(extra or [])
    right, placed = "", set()
    for u in use_pool:
        if not u: continue
        k = n(u)
        if not k or k in seen: continue
        seen.add(k)
        cand = f"{right}, {u}" if right else u
        whole = f"{left}; {cand}" if left else cand
        if clen(whole) <= HIGHLIGHT_LIMIT:
            right = cand; placed.add(k)

    out = f"{left}; {right}" if (left and right) else (left or right)
    out = strip_conjunctions(tidy(no_emoji(no_html(out))))
    out = trim_to(out, HIGHLIGHT_LIMIT)[0]
    unplaced = [u for u in use_pool if ws(u) and n(u) not in placed and n(u) not in n(out)]
    return out, unplaced


# ================================================================= BULLETS
BENEFIT = {
 "stainless":"resists rust and wipes clean in seconds","glass":"will not stain or hold onto smells",
 "borosilicate":"handles sudden temperature change without cracking","cotton":"stays soft and breathable all day",
 "silicone":"stays flexible and heat safe","leather":"ages well and keeps a premium look",
 "wood":"adds natural warmth and stays sturdy","plastic":"keeps the weight down and stores easily",
 "abs":"absorbs impact without cracking","eps":"absorbs impact energy on contact",
 "insulat":"holds temperature far longer than a single wall design","rechargeable":"tops up over USB rather than eating batteries",
 "waterproof":"shrugs off rain and splashes","adjustable":"dials in to the fit you want",
 "compact":"slips into small spaces and travels without bulk","portable":"sets up in seconds wherever you go",
 "vented":"moves air across the head so it stays cooler","padded":"cushions pressure points on longer sessions",
 "helmet":"protects the head where it matters most","certified":"meets the published safety standard for its class",
 "leakproof":"seals tight so nothing escapes into a bag","lid":"seals cleanly and opens one handed",
 "dishwasher":"goes on the top rack instead of being washed by hand","microwave":"moves from fridge to microwave without changing dish",
 "bpa":"skips BPA for everyday food and drink contact","strap":"holds position instead of sliding loose",
 "buckle":"clicks shut quickly and releases just as fast","washable":"comes out of the wash ready to use again",
 "kelp":"delivers iodine from a whole food source","oil":"pours cleanly and mixes into food without fuss",
}

# Short category headers, so a long feature phrase becomes the benefit statement
# rather than being truncated into the header.
HEADER_MAP = [
 ("AIRFLOW",           r"vent|airflow|breathab|mesh|cool"),
 ("SUN VISOR",         r"sun visor|sun shield|tint|glare|drop down"),
 ("CLEAR VISOR",       r"clear visor|face shield|field of view|anti fog"),
 ("CHIN BAR",          r"chin bar|chin guard|flip up|modular"),
 ("CARBON SHELL",      r"carbon|fibre|fiber|composite|shell"),
 ("LIGHTWEIGHT",       r"lightweight|light weight|\bkg\b|grams|neck fatigue|neck strain"),
 ("ADJUSTABLE FIT",    r"adjust|dial|strap|fit\b|sizing|circumference"),
 ("SAFETY CERTIFIED",  r"cpsc|astm|ce\b|certif|standard|tested|compliance"),
 ("IMPACT PROTECTION", r"impact|shell|abs|eps|absorb|protect"),
 ("EASY TO CLEAN",     r"washabl|removab|liner|wipe|clean|dishwasher"),
 ("QUICK RELEASE",     r"buckle|clip|clasp|release|snap"),
 ("SIZE AND PACK",     r"pack of|set of|\bsize\b|capacity|\d+\s*(?:ml|oz|lb|kg|cm|inch)"),
 ("MATERIAL",          r"steel|glass|cotton|silicone|leather|wood|plastic|alumin|borosilicate"),
 ("EVERYDAY USE",      r"use it|ideal for|great for|designed for|suitable for|for daily"),
 ("WHAT IS INCLUDED",  r"includ|comes with|in the box|bundle"),
 ("BUILT TO LAST",     r"durab|sturd|reinforc|heavy duty|long last"),
]
HEADER_FALLBACK = ["KEY FEATURE","ALSO INCLUDED","WORTH KNOWING","EVERYDAY DETAIL","ONE MORE THING"]


def short_header(phrase, used):
    """A short, complete category header. Never a truncated slice of the phrase."""
    low = n(phrase)
    for name, pat in HEADER_MAP:
        if re.search(pat, low) and name not in used:
            return name
    words = [w for w in ws(phrase).split() if n(w) not in BACKEND_STOP][:2]
    guess = " ".join(words).upper()[:26]
    if guess and guess not in used and len(guess) >= 4:
        return guess
    for fb in HEADER_FALLBACK:
        if fb not in used: return fb
    return "KEY FEATURE"


# Supporting clauses tied to each header category, so every bullet has its own
# material to reach Amazon's 150 character floor without competing for the same
# phrases as its neighbours.
HEADER_DETAIL = {
 "AIRFLOW": ["air moves across the head instead of sitting still",
             "so long sessions stay comfortable rather than clammy"],
 "ADJUSTABLE FIT": ["the fit is set once and holds where you left it",
                    "so the same unit works as a child grows"],
 "SAFETY CERTIFIED": ["tested against the published standard for its class",
                      "so compliance can be checked before anyone rides"],
 "IMPACT PROTECTION": ["the outer layer spreads force across a wider area",
                       "rather than concentrating it at the point of contact"],
 "EASY TO CLEAN": ["the parts that touch skin come away without tools",
                   "so a full clean takes minutes rather than an evening"],
 "QUICK RELEASE": ["it stays shut under load and opens with one hand",
                   "so nobody is wrestling with it at the end of a ride"],
 "SIZE AND PACK": ["what arrives matches what is listed",
                   "so there is no guessing at the point of order"],
 "MATERIAL": ["the construction is consistent from batch to batch",
              "so replacements behave the same as the original"],
 "EVERYDAY USE": ["it slots into the routine already in place",
                  "rather than asking anyone to change how they do things"],
 "WHAT IS INCLUDED": ["everything needed is in the one box",
                      "so there is no second order before first use"],
 "BUILT TO LAST": ["it takes daily handling without loosening",
                   "so it is not back in the basket in a few months"],
}

GENERIC = ["handles the everyday job it was bought to do","keeps the routine simple day to day",
           "holds up to repeated use over time","earns the space it takes up",
           "needs no extra setup before the first use"]

def benefit_for(text, used):
    low = (text or "").lower()
    for k, v in BENEFIT.items():
        if k in low and v not in used: return v
    for g in GENERIC:
        if g not in used: return g
    return GENERIC[0]

HEADER_RE = re.compile(r"^\s*([A-Za-z0-9][\w\s&/'\-]{2,40}?)\s*:\s*(.+)$", re.S)


def split_header(text):
    """Returns (existing_header, remainder). Sellers often write their own
    'Superior Ventilation System: ...' lead, and that must become THE header
    rather than getting a second one bolted in front of it."""
    m = HEADER_RE.match(ws(text))
    if not m: return "", ws(text)
    head, rest = ws(m.group(1)), ws(m.group(2))
    if len(head.split()) > 6 or not rest: return "", ws(text)
    return head, rest


def make_bullet(header, benefit, detail=""):
    """[ALL CAPS HEADER]: [benefit-first statement]; [supporting detail].
    Exactly one header and exactly one colon."""
    inner, benefit = split_header(benefit)
    if inner and not header:
        header = inner
    elif inner and header:
        # the seller's own lead wins; the derived category header is dropped
        header = inner
    header = ws(re.sub(r"[^\w\s\-&/]", "", header)).upper()[:38]
    benefit = strip_conjunctions(ws(benefit))
    detail = strip_conjunctions(ws(detail))
    body = f"{benefit}; {detail}" if detail else benefit
    body = number_units(body)
    # any further colon in the body would read as a second heading
    body = body.replace(":", ";")
    body = re.sub(r"\s*;\s*;+", "; ", body)
    body = re.sub(r"[.\s;]+$", "", body)
    out = f"{header}: {body}" if header else body
    out = ws(no_html(no_emoji(strip_promo(out))))
    return re.sub(r"[.\s]+$", "", out)

def pad_bullet(b, pool, used, target=BULLET_MIN, cap=BULLET_MAX, max_clauses=2):
    """Grow a bullet toward Amazon's 150-200 window. Capped so the first bullet
    cannot swallow every available detail and starve the rest."""
    added = 0
    for extra in pool:
        if clen(b) >= target or added >= max_clauses: break
        extra = strip_conjunctions(ws(extra))
        if not extra or extra in used: continue
        if n(extra) in n(b): continue
        cand = re.sub(r"[.\s]+$", "", f"{b}; {number_units(extra)}")
        if clen(cand) <= cap:
            used.add(extra); b = cand; added += 1
    return b

def build_bullets(f: Facts, max_bullets=MAX_BULLETS):
    """[ALL CAPS HEADER]: [benefit-first statement]; [supporting detail].
    The feature phrase itself carries the benefit statement, so nothing is
    truncated and every bullet reaches Amazon's 150 to 200 window."""
    feats = [ws(x) for x in (f.features or []) if ws(x)]
    size_clause = f"supplied as {abbreviate_units(ws(f.size))}" if ws(f.size) else ""

    rows = list(feats)
    for a in [ws(f.attr1), ws(f.attr2)]:
        if a and not any(n(a) == n(r) for r in rows): rows.append(a)
    if ws(f.use_case) and not any(n(f.use_case) == n(r) for r in rows): rows.append(ws(f.use_case))
    if size_clause and len(rows) < max_bullets: rows.append(size_clause)
    if not rows and ws(f.product_type): rows.append(ws(f.product_type))

    used_h, used_b, used_d, out, seen = set(), set(), set(), [], set()
    # reserve every heading phrase before the loop starts, otherwise an earlier
    # bullet borrows a phrase that a later bullet needs to lead with
    for r in rows[:max_bullets]:
        if r != "__size__": used_d.add(r)
    for row in rows:
        if len(out) >= max_bullets: break
        header = short_header(row, used_h); used_h.add(header)
        benefit = strip_conjunctions(row)
        # supporting clauses: the canned benefit for this feature, then anything unused
        pool = HEADER_DETAIL.get(header, [])[:] + [benefit_for(row, used_b)]
        pool += [d for d in feats + [ws(f.use_case), size_clause]
                 if d and n(d) != n(row) and d not in used_d]
        b = make_bullet(header, benefit)
        b = pad_bullet(b, pool, used_d, target=BULLET_MIN, cap=BULLET_MAX, max_clauses=2)
        used_b.add(pool[0])
        k = n(b)[:40]
        if not b or k in seen: continue
        seen.add(k); out.append(b)

    # top up anything still short, using clauses nothing else claimed
    for i, b in enumerate(out):
        if clen(b) < BULLET_MIN:
            hdr = b.split(":")[0]
            spare = HEADER_DETAIL.get(hdr, [])[:] + GENERIC + \
                    [d for d in feats + [ws(f.use_case), size_clause] if d and d not in used_d]
            out[i] = pad_bullet(b, spare, used_d, target=BULLET_MIN, cap=BULLET_MAX, max_clauses=4)
    return out


# ---------------------------------------------------- paragraph -> bullets
def is_paragraph(text):
    lines = [l for l in (text or "").splitlines() if l.strip()]
    if len(lines) >= 3: return False
    body = ws(text)
    return clen(body) > 160 and len(re.findall(r"[.!?]", body)) >= 2

THEMES = [("SIZE AND FIT", r"\d+\s*(?:ml|oz|litre|liter|cm|mm|inch|inches|kg|g|lb)\b|\bx\b"),
          ("EVERYDAY USE", r"\buse it\b|\bideal for\b|\bgreat for\b|\bperfect for\b|\bdesigned for\b"),
          ("EASY TO LOOK AFTER", r"\bclean\b|\bwash\b|\bwipe\b|\brinse\b"),
          ("MATERIAL AND BUILD", r"\bmade\b|\bmaterial\b|\bglass\b|\bsteel\b|\bplastic\b|\bcotton\b|\babs\b"),
          ("SAFETY AND FIT", r"\bcertified\b|\bstandard\b|\bprotect\b|\bsafety\b|\bimpact\b")]

def derive_header(chunk, used):
    low = n(chunk)
    for k in sorted(BENEFIT, key=len, reverse=True):
        if len(k) >= 5 and re.search(r"(?<![a-z0-9])" + re.escape(k), low):
            h = k.upper()
            if h not in used: return h
    for name, pat in THEMES:
        if re.search(pat, low) and name not in used: return name
    for fb in ["KEY DETAIL","ALSO WORTH KNOWING","GOOD TO KNOW","IN THE BOX","ONE MORE THING"]:
        if fb not in used: return fb
    return "KEY DETAIL"

def paragraph_to_bullets(text, max_bullets=MAX_BULLETS):
    body = ws(no_html(no_emoji(text)))
    if not body: return []
    units = [u for u in SENT_SPLIT_RE.split(body) if ws(u)]
    while len(units) < max_bullets:
        if not units: break
        i = max(range(len(units)), key=lambda x: len(units[x]))
        if len(units[i]) < 90: break
        cut = re.split(r"\s*;\s*|\s+(?:and|plus|while|whereas)\s+", units[i], maxsplit=1)
        if len(cut) < 2 or min(len(c) for c in cut) < 30: break
        units[i:i+1] = [ws(cut[0]), ws(cut[1])]
    if not units: return []
    target = max(1, sum(len(u) for u in units) // min(max_bullets, len(units)) + 1)
    groups, cur = [], ""
    for u in units:
        cand = ws(f"{cur} {u}") if cur else ws(u)
        if cur and len(cand) > target and len(groups) < max_bullets - 1:
            groups.append(cur); cur = ws(u)
        else: cur = cand
    if cur: groups.append(cur)

    out, used, used_d = [], set(), set()
    for g in groups[:max_bullets]:
        h = short_header(g, used); used.add(h)
        body_txt = strip_conjunctions(re.sub(r"[.\s]+$", "", ws(g)))
        parts = [p for p in re.split(r"(?<=[.!?])\s+", body_txt) if ws(p)]
        if len(parts) > 1:
            body_txt = "; ".join(strip_conjunctions(re.sub(r"[.\s]+$", "", p)) for p in parts)
        b = make_bullet(h, body_txt)
        b = pad_bullet(b, HEADER_DETAIL.get(h, [])[:] + GENERIC, used_d,
                       target=BULLET_MIN, cap=BULLET_MAX, max_clauses=3)
        out.append(b)
    return out

def parse_bullets(text, max_bullets=MAX_BULLETS):
    if is_paragraph(text): return paragraph_to_bullets(text, max_bullets), "paragraph"
    return parse_lines(text), "lines"

def rewrite_bullet(b, pool, used, used_headers=None, header_hint=""):
    """Reformat a seller's own bullet into Amazon's header/benefit/detail shape
    and grow it to the 150-200 window using category clauses."""
    used_headers = used_headers if used_headers is not None else set()
    b = ws(no_html(no_emoji(strip_promo(b))))
    b = re.sub(r"[.\s]+$", "", b)
    if ":" in b and b.split(":")[0].isupper() and len(b.split(":")[0]) <= 34:
        header, _, body = b.partition(":")
        header = ws(header)
    else:
        header, body = (header_hint or short_header(b, used_headers)), b
    used_headers.add(header)
    body = strip_conjunctions(ws(body))
    out = make_bullet(header, body)
    # shared features are scarce, so they are capped; category clauses are not,
    # and keep filling until the bullet reaches Amazon's floor
    out = pad_bullet(out, list(pool or []), used, target=BULLET_MIN, cap=BULLET_MAX, max_clauses=2)
    if clen(out) < BULLET_MIN:
        out = pad_bullet(out, HEADER_DETAIL.get(header, [])[:] + GENERIC, used,
                         target=BULLET_MIN, cap=BULLET_MAX, max_clauses=4)
    return out

# ================================================================= BACKEND
def build_backend(keywords, exclude_text="", brand="", limit=BACKEND_BYTES):
    """Unique lowercase single words, single spaces, no punctuation, <=249 bytes.
    Words already visible in the title, highlights, bullets or brand are dropped."""
    exclude = set(nkw(exclude_text).split()) | set(nkw(brand).split())
    kept, seen = [], set()
    dropped_visible, dropped_dupe, dropped_stop = [], [], []
    for kw in keywords or []:
        for w in nkw(kw).split():
            if len(w) < 2 or w in BACKEND_STOP or re.match(r"^b0[a-z0-9]{8}$", w):
                dropped_stop.append(w); continue
            if w in exclude:
                dropped_visible.append(w); continue
            sing = w[:-1] if w.endswith("s") else w
            plur = w if w.endswith("s") else w + "s"
            if w in seen or sing in seen or plur in seen:
                dropped_dupe.append(w); continue
            seen.add(w); kept.append(w)
    out, overflow = "", []
    for w in kept:
        cand = f"{out} {w}" if out else w
        if blen(cand) > limit: overflow.append(w); continue
        out = cand
    return {"terms": out, "bytes": blen(out), "limit": limit,
            "words": len(out.split()) if out else 0,
            "dropped_visible": sorted(set(dropped_visible)),
            "dropped_dupe": sorted(set(dropped_dupe)),
            "dropped_stop": sorted(set(dropped_stop)), "overflow": overflow}

# ================================================================= RAW TITLE MINING
LEXICON = ["stainless steel water bottle","insulated water bottle","water bottle","coffee mug",
 "travel mug","mixing bowl","serving bowl","salad bowl","cereal bowl","scooter helmet","bike helmet",
 "cycling helmet","skate helmet","helmet","storage container","lunch box","cutting board",
 "frying pan","pressure cooker","dinner set","yoga mat","running shoes","laptop stand","phone case",
 "power bank","smart watch","air fryer","kelp supplement","fish oil","salmon oil","krill oil",
 "joint supplement","dietary supplement","mineral supplement","knee pads","elbow pads",
 "headphones","earphones","speaker","charger","backpack","wallet","sandals","sneakers",
 "bowl","bottle","mug","cup","plate","tumbler","jar","container","pan","pot","kettle","knife",
 "tray","basket","rack","shoes","shirt","jacket","socks","bag","belt","watch","cable","lamp",
 "chair","table","mat","rug","pillow","blanket","towel","brush","shampoo","cream","serum",
 "supplement","oil","powder","capsules","tablets","chews","pads","gloves","toy","pen","notebook"]
GENERIC_TYPES = {"supplement","oil","powder","capsules","tablets","chews","container","bag",
                 "pads","set","kit","pack","item","bowl","bottle","cup"}

def detect_type(text):
    t = ws(text); low = n(t)
    spec = [x for x in LEXICON if x not in GENERIC_TYPES]
    gen  = [x for x in LEXICON if x in GENERIC_TYPES]
    for pool in (spec, gen):
        for noun in sorted(pool, key=len, reverse=True):
            if re.search(r"(?<![a-z0-9])" + re.escape(noun) + r"(?![a-z0-9])", low):
                m = re.search(r"(?i)(?<![a-z0-9])" + re.escape(noun) + r"(?![a-z0-9])", t)
                return (ws(m.group(0)) if m else noun.title()), "known"
    w = ws(t).split()
    return (" ".join(w[-2:]) if len(w) >= 2 else (w[0] if w else "")), "guess"

def mine_title(raw, brand=""):
    """Pull every reusable feature phrase out of a raw marketing title."""
    t = ws(no_html(no_emoji(raw)))
    size = ""
    m = PACK_RE.search(t)
    pack = ws(m.group(0)) if m else ""
    t2 = PACK_RE.sub(" ", t)
    dims = ""
    md = DIM_RE.search(t2)
    if md: dims = ws(md.group(0)); t2 = DIM_RE.sub(" ", t2)
    ms = SIZE_RE.search(t2)
    if ms: size = ws(ms.group(0))
    ptype, conf = detect_type(t)
    segs = [ws(x) for x in re.split(r"\s*[|\u2013\u2014]\s*", t) if ws(x)]
    if len(segs) < 2:
        segs = [ws(x) for x in re.split(r"\s*[,;/]\s*", t) if ws(x)]
    feats, seen = [], set()
    for s in segs:
        s2 = s
        if brand: s2 = re.sub(r"(?i)(?<![a-z0-9])" + re.escape(brand) + r"(?![a-z0-9])", " ", s2)
        s2 = PACK_RE.sub(" ", DIM_RE.sub(" ", SIZE_RE.sub(" ", s2)))
        s2 = "".join(c for c in s2 if c not in BANNED_TITLE_CHARS)
        s2 = strip_conjunctions(tidy(s2))
        k = n(s2)
        if k and k not in seen and len(s2.split()) >= 2:
            seen.add(k); feats.append(s2)
    return {"product_type": ptype, "type_confidence": conf, "size": size or dims,
            "pack": pack, "dimensions": dims, "features": feats}

# ================================================================= KEYWORDS
def kw_score(rank, freq, source):
    return int(round(min(100, max(0, 10 - min(rank, 10)) / 10 * 60
                         + min(freq, 5) / 5 * 25 + (15 if source == "Amazon" else 8))))

def volume_colour(s):
    """Continuous green (high) to red (low). Light background, dark text."""
    s = max(0, min(100, s)); hue = int(s * 1.2)          # 0 red -> 120 green
    return f"hsl({hue},72%,90%)", f"hsl({hue},70%,26%)", f"hsl({hue},60%,72%)"

def band(s):
    return "High" if s >= 70 else "Medium" if s >= 45 else "Low"

def coverage(keywords, title, highlights, bullets):
    fields = {"Title": set(n(title).split()), "Highlights": set(n(highlights).split()),
              "Bullets": set(n(" ".join(bullets or [])).split())}
    rows = []
    for kw in keywords or []:
        kw = ws(kw)
        wds = [w for w in n(kw).split() if w]
        if not wds: continue
        hit = {k: all(w in v for w in wds) for k, v in fields.items()}
        rows.append({"keyword": kw, **hit, "anywhere": any(hit.values())})
    return rows

def force_into_title(title, keywords, brand, limit=TITLE_LIMIT, media=False):
    cur = ws(title); already, added, failed = [], [], []
    for kw in keywords or []:
        kw = ws(kw)
        if not kw: continue
        if all(w in set(n(cur).split()) for w in n(kw).split()):
            already.append(kw); continue
        if "," in cur:
            h, _s, tail = cur.partition(",")
            cand = ws(f"{ws(h)} {kw},{tail}")
        else:
            cand = ws(f"{cur} {kw}")
        cand = brand_first(fix_title(cand, brand, media)[0], brand)
        if clen(cand) <= limit and not audit_title(cand, brand, media).errors \
           and all(w in set(n(cand).split()) for w in n(kw).split()):
            cur = cand; added.append(kw)
        else: failed.append(kw)
    return cur, already, added, failed

def force_into_bullets(bullets, keywords, pool=None, max_bullets=MAX_BULLETS):
    out = [b for b in (bullets or []) if b]
    already, added, failed = [], [], []
    used = set()
    for kw in keywords or []:
        kw = ws(kw)
        if not kw: continue
        if all(w in set(n(" ".join(out)).split()) for w in n(kw).split()):
            already.append(kw); continue
        placed = False
        for i in sorted(range(len(out)), key=lambda x: len(out[x])):
            cand = re.sub(r"[.\s]+$", "", f"{out[i]}; {kw}")
            if clen(cand) <= BULLET_MAX and not audit_bullet(cand, i + 1).errors:
                out[i] = cand; added.append(kw); placed = True; break
        if not placed and len(out) < max_bullets:
            b = make_bullet(kw, benefit_for(kw, used))
            used.add(b)
            b = pad_bullet(b, pool or [], used)
            out.append(b); added.append(kw); placed = True
        if not placed: failed.append(kw)
    return out, already, added, failed


# ================================================================= CASCADE
def logic_issues(bullet):
    """Grammar and sense checks run over every bullet before it is shown."""
    out = []
    b = ws(bullet)
    if b.count(":") > 1:
        out.append("More than one heading.")
    head, body = (b.split(":", 1) + [""])[:2]
    if not body.strip():
        out.append("Heading with nothing after it.")
        return out
    clauses = [c.strip() for c in body.split(";") if c.strip()]
    seen = set()
    for c in clauses:
        k = n(c)
        if k in seen: out.append(f"Repeats the clause '{c[:34]}'.")
        seen.add(k)
        if n(c) and n(c) == n(head): out.append("A clause just repeats the heading.")
        first = n(c).split()[0] if n(c).split() else ""
        if first in CONJUNCTIONS: out.append(f"A clause opens on '{first}'.")
        last = n(c).split()[-1] if n(c).split() else ""
        if last in DANGLING_END: out.append(f"A clause ends on '{last}'.")
        if len(n(c).split()) < 3: out.append(f"'{c[:24]}' is too short to be a clause.")
    if re.search(r"\b(\w+)\s+\1\b", n(b)): out.append("A word is doubled.")
    if b != b.strip() or "  " in b: out.append("Stray whitespace.")
    return out


def polish_bullet(b):
    """Final clean-up so nothing ungrammatical reaches the output."""
    b = ws(b)
    head, sep, body = b.partition(":")
    if not sep: head, body = "", b
    # a detail clause may carry its own colon, which would read as a second
    # heading, so everything after the first colon is demoted to a semicolon
    body = body.replace(":", ";")
    clauses, seen = [], set()
    for c in body.split(";"):
        c = strip_conjunctions(ws(c))
        c = re.sub(r"\b(\w+)(\s+\1\b)+", r"\1", c, flags=re.I)   # doubled words
        k = n(c)
        if not c or k in seen or (head and k == n(head)) or len(k.split()) < 3:
            continue
        seen.add(k); clauses.append(c)
    body = "; ".join(clauses)
    out = f"{ws(head).upper()}: {body}" if head and body else (body or ws(head))
    return re.sub(r"[.\s;]+$", "", ws(out))


def compose(f: Facts, media=False, extra=None, max_bullets=MAX_BULLETS):
    """Priority cascade. Content competes for the title first; what does not fit
    drops to Item Highlights; what still does not fit becomes bullet material."""
    title, used = _title_pass(f, media)
    highlights, unplaced = _highlights_pass(f, title, used, extra)

    merged, seen_f = [], set()
    for x in list(f.features or []) + [u for u in unplaced if n(u) not in n(highlights)]:
        k = n(x)
        if k and k not in seen_f:
            seen_f.add(k); merged.append(ws(x))
    bullet_facts = Facts(brand=f.brand, product_type=f.product_type, attr1=f.attr1,
                         attr2=f.attr2, attr3=f.attr3, attr4=f.attr4, usp=f.usp,
                         size_gender=f.size_gender, use_case=f.use_case, features=merged)
    bullets = [polish_bullet(b) for b in build_bullets(bullet_facts, max_bullets)]
    bullets = [b for b in bullets if b]
    # four strong bullets beat five with one padded out of filler
    strong = [b for b in bullets if clen(b) >= 90]
    if len(strong) >= 3:
        bullets = strong

    dropped_to_high = [v for k, v in f.ordered() if k not in used and ws(v)
                       and n(v) in n(highlights)]
    dropped_to_bul = [u for u in unplaced if n(u) not in n(highlights)]
    return {"title": title, "highlights": highlights, "bullets": bullets,
            "in_title": sorted(used), "to_highlights": dropped_to_high,
            "to_bullets": dropped_to_bul,
            "logic": {i + 1: logic_issues(b) for i, b in enumerate(bullets)}}
