"""
Listing Studio — Amazon title, item highlights, bullets and search terms (2026 rules).
Rules engine lives in core.py. This file is presentation only.
"""
import json, re, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
import streamlit as st
import core as C
import images as IMG
from PIL import Image

st.set_page_config(page_title="Listing Studio", page_icon="🛍️", layout="wide")

st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@600;700;800&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@500;700&display=swap');
.stApp{background:#fff}
html,body,[class*="css"]{font-family:'Inter',system-ui,sans-serif;color:#1b2233}
h1,h2,h3,h4,h5{font-family:'Plus Jakarta Sans',sans-serif;color:#141a29;letter-spacing:-.02em}
.block-container{padding-top:1.3rem;max-width:1380px}
.hero{background:linear-gradient(115deg,#ffe29a,#ff9a8b 38%,#ff6fa5 68%,#7b6cff);
 border-radius:18px;padding:20px 24px;margin-bottom:16px;box-shadow:0 10px 26px rgba(123,108,255,.2)}
.hero h1{font-size:25px;font-weight:800;margin:0;color:#20142e}
.hero p{margin:6px 0 0;font-size:13px;color:#3a2440;font-weight:500;max-width:840px}
.lbl{display:flex;justify-content:space-between;align-items:baseline;margin:14px 0 2px}
.lbl b{font-size:13.5px;font-weight:700;color:#141a29}
.lbl span{font-family:'JetBrains Mono',monospace;font-size:11.5px;font-weight:700;
 padding:2px 9px;border-radius:999px}
.ok{background:#dcfce7;color:#0b7a46;border:1px solid #86efac}
.warn{background:#fef3c7;color:#96690b;border:1px solid #fcd34d}
.bad{background:#ffe4e6;color:#b4143c;border:1px solid #fda4af}
.sc{display:flex;align-items:center;gap:18px;background:#fff;border:1px solid #e7eaf3;
 border-left:8px solid var(--c,#22c55e);border-radius:14px;padding:14px 20px;margin:8px 0 14px;
 box-shadow:0 4px 14px rgba(20,26,41,.06)}
.sc .n{font-family:'JetBrains Mono',monospace;font-size:38px;font-weight:700;line-height:1}
.sc .m{font-size:12.5px;color:#6b7391}
.iss{font-size:12.5px;padding:7px 12px;border-radius:9px;margin:4px 0;background:#f7f9fc;
 border-left:4px solid #cbd5e1;color:#3a4256}
.iss.error{background:#fff1f2;border-left-color:#f43f5e}
.iss.warn{background:#fffbeb;border-left-color:#f59e0b}
.iss.ok{background:#f0fdf4;border-left-color:#22c55e}
.chip{display:inline-block;font-size:12px;font-weight:600;padding:4px 10px;margin:3px;
 border-radius:999px;border:1px solid}
.stTabs [data-baseweb="tab-list"]{gap:6px}
[data-baseweb="tab"]{font-weight:700;font-family:'Plus Jakarta Sans',sans-serif}
div.stButton>button[kind="primary"]{background:#7b6cff;border:0;font-weight:700;border-radius:10px}
</style>""", unsafe_allow_html=True)

st.markdown('<div class="hero"><h1>Listing Studio</h1><p>Amazon title, item highlights, bullets '
 'and backend search terms, built to the 2026 rules. Everything updates as you type — there is no '
 'button to press.</p></div>', unsafe_allow_html=True)

# --------------------------------------------------------------- helpers
def cls(count, limit):
    return "bad" if count > limit else "warn" if count > limit * .9 else "ok"

def label(text, count=None, limit=None, unit="characters"):
    right = f'<span class="{cls(count,limit)}">{count} / {limit} {unit}</span>' if limit else ""
    st.markdown(f'<div class="lbl"><b>{C.esc(text)}</b>{right}</div>', unsafe_allow_html=True)

def issues(a):
    for i in a.issues:
        tag = {"error": "Fix", "warn": "Check", "ok": "OK"}[i.severity]
        st.markdown(f'<div class="iss {i.severity}"><b>{tag}</b> &nbsp;{C.esc(i.message)}</div>',
                    unsafe_allow_html=True)

def scorecard(audits):
    s, g = C.score(audits)
    col = "#22c55e" if s >= 80 else "#f59e0b" if s >= 55 else "#f43f5e"
    e = sum(len(a.errors) for a in audits); w = sum(len(a.warns) for a in audits)
    st.markdown(f'<div class="sc" style="--c:{col}"><div class="n" style="color:{col}">{s}</div>'
                f'<div><b style="color:{col}">Grade {g}</b><div class="m">{e} blocking · {w} to check'
                f'</div></div></div>', unsafe_allow_html=True)

def copy_out(title, high, bullets, backend="", desc="", key="x"):
    live = [b for b in bullets if b]
    st.markdown("#### Copy each field")
    label("Title", C.clen(title), C.TITLE_LIMIT); st.code(title or "", language=None)
    label("Item Highlights", C.clen(high), C.HIGHLIGHT_LIMIT); st.code(high or "", language=None)
    for i, b in enumerate(live, 1):
        label(f"Bullet {i}", C.clen(b), C.BULLET_MAX); st.code(b, language=None)
    label(f"All {len(live)} bullets, one per line",
          sum(C.clen(b) for b in live), C.BULLETS_TOTAL_MAX)
    st.code("\n".join(live), language=None)
    if backend:
        label("Backend search terms", C.blen(backend), C.BACKEND_BYTES, "bytes")
        st.code(backend, language=None)
    if desc:
        label("Description", C.clen(desc), C.DESCRIPTION_LIMIT); st.code(desc, language=None)
    pack = "\n".join([f"TITLE\n{title}", f"\nITEM HIGHLIGHTS\n{high}", "\nBULLETS"]
                     + [f"- {b}" for b in live] + ([f"\nSEARCH TERMS\n{backend}"] if backend else []))
    st.download_button("Download everything (.txt)", pack.encode(), "listing.txt",
                       "text/plain", key=f"dl{key}")

def copy_raw(pairs, key="r"):
    with st.expander("Copy the original details you pasted"):
        for name, val in pairs:
            if C.ws(val):
                label(name, C.clen(val), None)
                st.code(val, language=None)

# --------------------------------------------------------------- sidebar
with st.sidebar:
    st.subheader("Settings")
    vendor = st.radio("Account", ["Seller — 5 bullets", "Vendor — 10 bullets"], index=0)
    maxb = 10 if vendor.startswith("Vendor") else 5
    media = st.checkbox("Media category (200-character titles)", value=False)
    lim = C.TITLE_LIMIT_MEDIA if media else C.TITLE_LIMIT
    st.caption(f"Title limit in use: **{lim} characters**")
    st.markdown("---")
    st.caption("**Field limits**  \nTitle 75 · Highlights 125 · Bullets 150–200 each, "
               "1000 total · Search terms 249 bytes")

tabs = st.tabs(["Build a listing", "Improve a listing", "Listing images",
                "Keyword research", "Rules"])

# ================================================================ BUILD
with tabs[0]:
    st.markdown("### Product details")
    st.caption("Five fields build the title: brand, then the attribute that qualifies the product, "
               "then the product type, then the differentiator and size. Output updates as you type.")

    def clear_build():
        for k in ("b_brand","b_type","b_a1","b_a2","b_size","b_use","b_feat"):
            st.session_state[k] = ""

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown('<div class="lbl"><b>Brand name</b></div>', unsafe_allow_html=True)
        brand = st.text_input("brand", key="b_brand", label_visibility="collapsed",
                              placeholder="Rider")
        st.markdown('<div class="lbl"><b>Product type</b></div>', unsafe_allow_html=True)
        ptype = st.text_input("ptype", key="b_type", label_visibility="collapsed",
                              placeholder="Scooter Helmet")
    with c2:
        st.markdown('<div class="lbl"><b>Attribute 1</b></div>', unsafe_allow_html=True)
        a1 = st.text_input("a1", key="b_a1", label_visibility="collapsed",
                           placeholder="ABS Shell — material, line or model")
        st.markdown('<div class="lbl"><b>Attribute 2</b></div>', unsafe_allow_html=True)
        a2 = st.text_input("a2", key="b_a2", label_visibility="collapsed",
                           placeholder="Matte Black — colour or differentiator")
    with c3:
        st.markdown('<div class="lbl"><b>Size</b></div>', unsafe_allow_html=True)
        size = st.text_input("size", key="b_size", label_visibility="collapsed",
                             placeholder="3/4 or Pack of 2")
        st.markdown('<div class="lbl"><b>Used for</b></div>', unsafe_allow_html=True)
        use = st.text_input("use", key="b_use", label_visibility="collapsed",
                            placeholder="for scooters and skateboards")

    st.markdown('<div class="lbl"><b>Features — one per line, or paste a paragraph</b></div>',
                unsafe_allow_html=True)
    feat_raw = st.text_area("feat", key="b_feat", height=140, label_visibility="collapsed",
        placeholder="11 vents keep air moving over the head\nAdjustable dial fit 54 to 58 cm\n"
                    "Meets CPSC safety standard")
    st.button("Clear all boxes", key="b_clear", on_click=clear_build)

    feats, fmode = C.parse_bullets(feat_raw, maxb)
    if C.is_paragraph(feat_raw):
        feats = [f.split(": ", 1)[-1] for f in feats]
        st.caption(f"Paragraph detected and split into {len(feats)} feature points.")

    if C.ws(brand) and C.ws(ptype):
        facts = C.Facts(brand=brand, product_type=ptype, attr1=a1, attr2=a2, size=size,
                        use_case=use, features=feats)
        title = C.build_title(facts, media)
        high = C.build_highlights(facts, title)
        bullets = C.build_bullets(facts, maxb)

        au = [C.audit_title(title, brand, media), C.audit_highlights(high)]
        au += [C.audit_bullet(b, i + 1) for i, b in enumerate(bullets)]
        au.append(C.audit_bullets_total(bullets))

        st.markdown("---")
        scorecard(au)
        copy_out(title, high, bullets, key="b")
        st.session_state["listing"] = {"title": title, "high": high, "bullets": bullets,
                                       "brand": brand, "features": feats}
        with st.expander("Field-by-field check"):
            for a in au:
                label(a.field, a.count, a.limit, "bytes" if "term" in a.field.lower() else "characters")
                issues(a)
    else:
        st.info("Enter a brand name and a product type to see the listing.")

# ================================================================ IMPROVE
with tabs[1]:
    st.markdown("### Paste your current listing")
    st.caption("The raw title is mined for every feature it contains. Bullets can be pasted one "
               "per line or as a paragraph, and short ones are rebuilt to Amazon's length.")

    def clear_imp():
        for k in ("i_brand","i_title","i_bul","i_a1","i_a2","i_size"):
            st.session_state[k] = ""

    ic1, ic2 = st.columns([1, 2])
    with ic1:
        st.markdown('<div class="lbl"><b>Brand name</b></div>', unsafe_allow_html=True)
        ibrand = st.text_input("ib", key="i_brand", label_visibility="collapsed", placeholder="Rider")
    with ic2:
        st.markdown('<div class="lbl"><b>Current title</b></div>', unsafe_allow_html=True)
        iraw = st.text_area("it", key="i_title", height=80, label_visibility="collapsed",
                            placeholder="Rider ABS Scooter Helmet for Kids | 11 Vents | Pack of 2")
    if iraw:
        label("Length of what you pasted", C.clen(iraw), lim)

    mined = C.mine_title(iraw, ibrand) if C.ws(iraw) else None
    if mined:
        chips = [f"Type: {mined['product_type']}"] + \
                ([f"Size: {mined['size']}"] if mined["size"] else []) + \
                ([f"Pack: {mined['pack']}"] if mined["pack"] else []) + \
                [f"{len(mined['features'])} features found"]
        st.markdown("".join(f'<span class="chip ok">{C.esc(x)}</span>' for x in chips),
                    unsafe_allow_html=True)

    jc1, jc2, jc3 = st.columns(3)
    with jc1:
        st.markdown('<div class="lbl"><b>Attribute 1</b></div>', unsafe_allow_html=True)
        ia1 = st.text_input("ia1", key="i_a1", label_visibility="collapsed", placeholder="ABS Shell")
    with jc2:
        st.markdown('<div class="lbl"><b>Attribute 2</b></div>', unsafe_allow_html=True)
        ia2 = st.text_input("ia2", key="i_a2", label_visibility="collapsed", placeholder="Matte Black")
    with jc3:
        st.markdown('<div class="lbl"><b>Size</b></div>', unsafe_allow_html=True)
        isize = st.text_input("isz", key="i_size", label_visibility="collapsed",
                              placeholder=(mined or {}).get("pack") or (mined or {}).get("size") or "3/4")

    st.markdown('<div class="lbl"><b>Current bullets — one per line, a paragraph, or leave empty'
                '</b></div>', unsafe_allow_html=True)
    ibul = st.text_area("ibl", key="i_bul", height=150, label_visibility="collapsed",
                        placeholder="Vented shell\nAdjustable dial fit\nCPSC certified")
    st.button("Clear all boxes", key="i_clear", on_click=clear_imp)

    if mined and C.ws(iraw):
        facts = C.Facts(brand=ibrand, product_type=mined["product_type"],
                        attr1=ia1 or (mined["features"][0] if mined["features"] else ""),
                        attr2=ia2, size=isize or mined["pack"] or mined["size"],
                        features=mined["features"])
        title = C.build_title(facts, media)
        high = C.build_highlights(facts, title)

        pasted, bmode = C.parse_bullets(ibul, maxb)
        if pasted:
            used, uh = set(), set()
            bullets = [C.rewrite_bullet(b, mined["features"], used, uh) for b in pasted][:maxb]
            note = (f"Paragraph split into {len(bullets)} bullets and formatted."
                    if bmode == "paragraph" else
                    f"{len(bullets)} bullets reformatted and lengthened to Amazon's window.")
        else:
            bullets = C.build_bullets(facts, maxb)
            note = "No bullets supplied, so they were written from the title's features."

        au = [C.audit_title(title, ibrand, media), C.audit_highlights(high)]
        au += [C.audit_bullet(b, i + 1) for i, b in enumerate(bullets)]
        au.append(C.audit_bullets_total(bullets))

        st.markdown("---")
        scorecard(au)
        st.caption(note)
        copy_out(title, high, bullets, key="i")
        copy_raw([("Original title", iraw), ("Original bullets", ibul)], key="i")
        st.session_state["listing"] = {"title": title, "high": high, "bullets": bullets,
                                       "brand": ibrand, "features": mined["features"]}
        with st.expander("Field-by-field check"):
            for a in au:
                label(a.field, a.count, a.limit)
                issues(a)
    else:
        st.info("Paste a title to see the rebuilt listing.")

# ================================================================ KEYWORDS
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")
MARKETS = {"amazon.com (US)": "ATVPDKIKX0DER", "amazon.co.uk (UK)": "A1F83G8C2ARO7P",
           "amazon.de (DE)": "A1PA6795UKMFR9", "amazon.ca (CA)": "A2EUQ1WTGCTBG2",
           "amazon.in (IN)": "A21TJRUUN4KGV"}

def _get(url, timeout=6):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

def _google(seed):
    d = _get("https://suggestqueries.google.com/complete/search?client=firefox&q="
             + urllib.parse.quote(seed))
    return [str(x) for x in d[1]] if isinstance(d, list) and len(d) > 1 else []

def _amazon(seed, mid):
    d = _get("https://completion.amazon.com/api/2017/suggestions?mid=" + mid
             + "&alias=aps&limit=11&prefix=" + urllib.parse.quote(seed))
    return [s.get("value", "") for s in d.get("suggestions", []) if s.get("value")] \
        if isinstance(d, dict) else []

@st.cache_data(ttl=3600, show_spinner=False)
def fetch(seed, source, mid, expand):
    seed = C.ws(seed)
    if not seed: return [], "Enter a seed keyword."
    seeds = [seed] + ([f"{seed} {c}" for c in "abcdefghijklmnopqrstuvwxyz"] if expand else [])
    fn = (lambda s: _google(s)) if source == "Google" else (lambda s: _amazon(s, mid))
    rank, freq, disp, errs = {}, {}, {}, []
    def safe(s):
        try: return fn(s)
        except Exception as e: errs.append(str(e)); return []
    try:
        with ThreadPoolExecutor(max_workers=8) as p:
            for got in p.map(safe, seeds):
                for i, term in enumerate(got):
                    t = C.ws(term); k = t.lower()
                    if not t: continue
                    disp.setdefault(k, t); freq[k] = freq.get(k, 0) + 1
                    rank[k] = min(rank.get(k, 99), i)
    except Exception as e:
        return [], f"Could not reach {source}: {e}"
    if not disp:
        return [], (f"Could not reach {source} ({errs[0] if errs else 'no results'}). Suggestion "
                    "lookup needs outbound internet access, which some hosts block. Type your own "
                    "keywords below instead.")
    rows = [{"term": disp[k], "rank": rank[k], "freq": freq[k],
             "score": C.kw_score(rank[k], freq[k], source)} for k in disp]
    rows.sort(key=lambda r: (-r["score"], r["rank"]))
    return rows, ""

with tabs[3]:
    st.markdown("### Find keywords")
    k1, k2, k3 = st.columns([2, 1, 1])
    with k1:
        st.markdown('<div class="lbl"><b>Seed keyword</b></div>', unsafe_allow_html=True)
        seed = st.text_input("sd", key="k_seed", label_visibility="collapsed",
                             placeholder="kids scooter helmet")
    with k2:
        st.markdown('<div class="lbl"><b>Source</b></div>', unsafe_allow_html=True)
        src = st.selectbox("sr", ["Amazon", "Google"], label_visibility="collapsed")
    with k3:
        st.markdown('<div class="lbl"><b>Marketplace</b></div>', unsafe_allow_html=True)
        mkt = st.selectbox("mk", list(MARKETS), label_visibility="collapsed",
                           disabled=(src != "Amazon"))
    expand = st.checkbox("Expand A to Z for long-tail terms", value=False)
    if st.button("Fetch keywords", type="primary", key="k_go"):
        with st.spinner(f"Asking {src}…"):
            rows, err = fetch(seed, src, MARKETS[mkt], expand)
        st.session_state["k_rows"], st.session_state["k_err"] = rows, err
        st.session_state["k_t"] = [r["term"] for r in rows if r["score"] >= 70][:4]
        st.session_state["k_b"] = [r["term"] for r in rows if 45 <= r["score"] < 70][:6]
        st.session_state["k_s"] = [r["term"] for r in rows if r["score"] < 45][:25]

    if st.session_state.get("k_err"): st.warning(st.session_state["k_err"])
    rows = st.session_state.get("k_rows", [])

    legend = "".join(
        f'<span class="chip" style="background:{C.volume_colour(v)[0]};'
        f'color:{C.volume_colour(v)[1]};border-color:{C.volume_colour(v)[2]}">{lab}</span>'
        for v, lab in [(95, "Strongest"), (70, "Strong"), (50, "Medium"), (25, "Low"), (5, "Weakest")])
    st.markdown(f'<div style="background:#f7f9fc;border:1px solid #e7eaf3;border-radius:12px;'
                f'padding:11px 14px;margin:10px 0;font-size:12.5px;color:#3a4256">'
                f'<b>Colour key</b> &nbsp;{legend}<br><span style="color:#6b7391">Green is the '
                f'strongest signal, shading through amber to red as it weakens. This is a '
                f'<b>relevance proxy</b> from autocomplete position and how many searches surfaced '
                f'the term, not true search volume — no free source publishes that. Use Brand '
                f'Analytics or your Search Query Performance report for real volume.</span></div>',
                unsafe_allow_html=True)

    if rows:
        st.markdown("".join(
            f'<span class="chip" style="background:{C.volume_colour(r["score"])[0]};'
            f'color:{C.volume_colour(r["score"])[1]};border-color:{C.volume_colour(r["score"])[2]}">'
            f'{C.esc(r["term"])} <b>{r["score"]}</b></span>' for r in rows[:110]),
            unsafe_allow_html=True)

    st.markdown("### Send each keyword where it belongs")
    st.markdown('<div class="lbl"><b>Your own keywords — one per line</b></div>', unsafe_allow_html=True)
    manual = st.text_area("mn", key="k_man", height=90, label_visibility="collapsed")
    pool = list(dict.fromkeys([r["term"] for r in rows] + C.parse_lines(manual)
                              + st.session_state.get("k_t", []) + st.session_state.get("k_b", [])
                              + st.session_state.get("k_s", [])))
    a1_, a2_, a3_ = st.columns(3)
    with a1_:
        st.markdown('<div class="lbl"><b>Into the title</b></div>', unsafe_allow_html=True)
        sel_t = st.multiselect("st", pool, key="k_t", label_visibility="collapsed")
    with a2_:
        st.markdown('<div class="lbl"><b>Into the bullets</b></div>', unsafe_allow_html=True)
        sel_b = st.multiselect("sb", pool, key="k_b", label_visibility="collapsed")
    with a3_:
        st.markdown('<div class="lbl"><b>Into search terms</b></div>', unsafe_allow_html=True)
        sel_s = st.multiselect("ss", pool, key="k_s", label_visibility="collapsed")

    L = st.session_state.get("listing")
    if not L:
        st.info("Build or improve a listing first — it lands here automatically.")
    else:
        nt, alr, add, fail = C.force_into_title(L["title"], sel_t, L["brand"], lim, media)
        nb, balr, badd, bfail = C.force_into_bullets(L["bullets"], sel_b,
                                                     pool=L.get("features"), max_bullets=maxb)
        back = C.build_backend(sel_s, exclude_text=f'{nt} {L["high"]} {" ".join(nb)}',
                               brand=L["brand"])
        au = [C.audit_title(nt, L["brand"], media), C.audit_highlights(L["high"])]
        au += [C.audit_bullet(b, i + 1) for i, b in enumerate(nb)]
        au += [C.audit_bullets_total(nb), C.audit_backend(back["terms"])]
        st.markdown("---")
        scorecard(au)
        copy_out(nt, L["high"], nb, back["terms"], key="k")

        r1, r2 = st.columns(2)
        with r1:
            st.markdown("**Title keywords**")
            for lst, kind in [(alr, "ok"), (add, "ok"), (fail, "bad")]:
                for k in lst:
                    tag = "already there" if lst is alr else ("added" if lst is add else "would not fit")
                    st.markdown(f'<span class="chip {kind}">{C.esc(k)} — {tag}</span>',
                                unsafe_allow_html=True)
        with r2:
            st.markdown("**Bullet keywords**")
            for lst, kind in [(balr, "ok"), (badd, "ok"), (bfail, "bad")]:
                for k in lst:
                    tag = "already there" if lst is balr else ("added" if lst is badd else "did not fit")
                    st.markdown(f'<span class="chip {kind}">{C.esc(k)} — {tag}</span>',
                                unsafe_allow_html=True)

        with st.expander("What the search-term cleanup removed, and why"):
            st.markdown(
                f"- **Already visible in your title, highlights or bullets** "
                f"({len(back['dropped_visible'])}): `{', '.join(back['dropped_visible'][:30]) or 'none'}`\n"
                f"- **Repeats or plural forms** ({len(back['dropped_dupe'])}): "
                f"`{', '.join(back['dropped_dupe'][:30]) or 'none'}`\n"
                f"- **Stop words and filler** ({len(back['dropped_stop'])}): "
                f"`{', '.join(back['dropped_stop'][:30]) or 'none'}`\n"
                f"- **Beyond 249 bytes** ({len(back['overflow'])}): "
                f"`{', '.join(back['overflow'][:30]) or 'none'}`")
            st.caption("Unique single words, lowercase, separated by single spaces. No commas — "
                       "punctuation wastes bytes and breaks parsing. One byte over 249 and Amazon "
                       "ignores the entire field.")

# ================================================================ RULES
with tabs[4]:
    st.markdown("### The rules this tool enforces")
    st.markdown(f"""
**Title — {C.TITLE_LIMIT} characters**
`[Brand] + [Attribute 1] + [Product Type], [Attribute 2], [Size]`
Commas separate rather than brackets. Units are abbreviated (oz, lb, ct). The joining words
*for* and *with* are dropped to move keywords forward. No special characters outside a brand
name, no repeated words, no ALL-CAPS, no promotional claims. Media categories keep 200.

**Item Highlights — {C.HIGHLIGHT_LIMIT} characters**
`[Primary material or spec] ; [core differentiator or use case]`
Searchable, and shown under the title on mobile. Materials, specs and use cases only — no
pricing and no marketing fluff.

**Bullets — {C.BULLET_MIN} to {C.BULLET_MAX} characters each, {C.BULLETS_TOTAL_MAX} across all five**
`[ALL CAPS HEADER]: [benefit-first statement]; [supporting feature detail]`
Sentence fragments with no full stop. Clauses separated by semicolons. Numbers one to nine
spelled out unless they are a measurement or model number, and always a space between a
number and its unit. No bullet may begin or end on a conjunction.

**Backend search terms — {C.BACKEND_BYTES} bytes**
Unique single words, all lowercase, separated by single spaces. No commas or punctuation.
Nothing repeated from the title, highlights, bullets or brand, since Amazon indexes the whole
listing as one entity. Plurals are dropped because the algorithm handles them. Bytes are not
characters: accented and non-Latin letters cost two to four bytes each, and a single byte over
the limit causes Amazon to ignore every term in the field.
""")
    st.caption("Reflects Amazon's title update of 27 July 2026 and the current Seller Central "
               "style guidance. Some categories, notably Pet Supplies and Apparel, cap titles "
               "shorter than the global limit — confirm yours in Seller Central.")

# ================================================================ IMAGES
with tabs[2]:
    st.markdown("### Listing images")
    st.caption("Upload your product photo and the gallery is built around it — main image on pure "
               "white, then the infographic slots. Everything is 2000 x 2000 sRGB JPEG with "
               "Amazon's file names.")

    with st.expander("What an SEO-friendly image set needs", expanded=False):
        for slot, name, why in IMG.SLOT_PLAN:
            tag = "MAIN" if slot == 0 else f"PT{slot:02d}"
            st.markdown(f"**{tag} — {name}.** {why}")
        st.caption("Amazon recommends at least six images plus a video. Most listings allow nine, "
                   "and seven show by default on desktop.")

    up = st.file_uploader("Product photo on a plain background", type=["jpg", "jpeg", "png", "webp"],
                          key="img_main")
    extra = st.file_uploader("More angles, optional — used for the grid",
                             type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True,
                             key="img_extra")
    lifestyle_bg = st.file_uploader("Lifestyle background photo, optional",
                                    type=["jpg", "jpeg", "png", "webp"], key="img_bg")
    st.caption("The tool composites your product and lays out the type. It does not invent "
               "photographic scenery, so a lifestyle shot needs a background photo from you.")

    L = st.session_state.get("listing", {})
    g1, g2 = st.columns(2)
    with g1:
        st.markdown('<div class="lbl"><b>ASIN or SKU for the file names</b></div>', unsafe_allow_html=True)
        asin = st.text_input("as", key="img_asin", label_visibility="collapsed", placeholder="B0XXXXXXXX")
        st.markdown('<div class="lbl"><b>Headline</b></div>', unsafe_allow_html=True)
        hl = st.text_input("hl", key="img_hl", label_visibility="collapsed", placeholder="Ready for")
        st.markdown('<div class="lbl"><b>Headline accent, shown in red</b></div>', unsafe_allow_html=True)
        acc = st.text_input("ac", key="img_ac", label_visibility="collapsed", placeholder="any road")
    with g2:
        st.markdown('<div class="lbl"><b>Sub-line</b></div>', unsafe_allow_html=True)
        sub = st.text_area("sb", key="img_sb", height=76, label_visibility="collapsed",
                           placeholder="Real carbon fibre keeps weight down and cuts neck fatigue")
        st.markdown('<div class="lbl"><b>Certifications — one per line, "name | detail"</b></div>',
                    unsafe_allow_html=True)
        certs = st.text_area("cf", key="img_cf", height=76, label_visibility="collapsed",
                             placeholder="D.O.T. FMVSS 218 | Certified\nECE 22R06 | Certified")

    default_feats = "\n".join(
        f'{b.split(":")[0].title()} | {b.split(": ",1)[-1].split(";")[0]}'
        for b in (L.get("bullets") or [])[:6]) if L.get("bullets") else ""
    st.markdown('<div class="lbl"><b>Feature callouts — one per line, "title | description"</b></div>',
                unsafe_allow_html=True)
    feats_raw = st.text_area("fc", key="img_fc", height=130, label_visibility="collapsed",
                             value=default_feats,
                             placeholder="Aerodynamic design | Reduces wind resistance\n"
                                         "Optimal airflow | Top and rear vents circulate air")
    if L.get("bullets") and default_feats:
        st.caption("Pre-filled from the listing you built. Edit freely.")

    def split_pairs(txt, fallback=""):
        out = []
        for line in C.parse_lines(txt):
            a, _, b = line.partition("|")
            out.append((C.ws(a), C.ws(b) or fallback))
        return out

    if up is None:
        st.info("Upload a product photo to build the gallery.")
    else:
        try:
            src = Image.open(up)
            others = [Image.open(f) for f in (extra or [])]
            bg = Image.open(lifestyle_bg) if lifestyle_bg else None
            built = []

            with st.spinner("Building the gallery…"):
                built.append(("Main — pure white", IMG.main_image(src), True))
                if C.ws(hl) or C.ws(acc):
                    built.append(("Hero benefit", IMG.hero(src, hl or "Built for", acc or "the ride",
                                                           sub), False))
                fpairs = split_pairs(feats_raw)
                if fpairs:
                    built.append(("Feature callouts",
                                  IMG.callouts(others[0] if others else src, fpairs,
                                               headline="Engineered in detail"), False))
                cpairs = split_pairs(certs, "Certified")
                if cpairs:
                    built.append(("Certification", IMG.badge_card(src, "Certified for", "safety",
                                                                  cpairs), False))
                if bg is not None:
                    built.append(("Lifestyle in use",
                                  IMG.hero(src, hl or "Ready for", acc or "any road", sub, bg=bg), False))
                if others:
                    built.append(("Angle grid", IMG.angle_grid([src] + others), False))

            st.markdown("---")
            files = []
            for i, (name, im, is_main) in enumerate(built):
                data = IMG.encode(im)
                fname = IMG.filename(asin, 0 if is_main else i)
                files.append((fname, data))
                st.markdown(f"#### {name}")
                st.markdown(f'<div class="lbl"><b>{fname}</b>'
                            f'<span class="ok">{im.size[0]} x {im.size[1]} · '
                            f'{len(data)/1024:.0f} KB</span></div>', unsafe_allow_html=True)
                st.image(im, use_container_width=True)
                for sev, msg in IMG.audit_image(im, is_main=is_main):
                    tag = {"error": "Fix", "warn": "Check", "ok": "OK"}[sev]
                    st.markdown(f'<div class="iss {sev}"><b>{tag}</b> &nbsp;{C.esc(msg)}</div>',
                                unsafe_allow_html=True)
                st.download_button(f"Download {fname}", data, fname, "image/jpeg", key=f"dlimg{i}")

            st.markdown("---")
            st.download_button("Download the whole gallery (.zip)", IMG.build_zip(files),
                               f"{IMG.safe_asin(asin)}_images.zip", "application/zip",
                               type="primary", key="dlzip")
            st.caption("Files are named to Amazon's convention — ASIN.MAIN.jpg then ASIN.PT01.jpg "
                       "and so on, with no spaces or dashes.")
        except Exception as e:
            st.error(f"Could not process that image: {e}")
