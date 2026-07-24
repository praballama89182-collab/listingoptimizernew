"""
Listing Studio — Amazon title, item highlights, bullets and search terms (2026 rules).
Rules engine lives in core.py. This file is presentation only.
"""
import json, re, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
import json
import streamlit as st
import streamlit.components.v1 as components
import core as C
import images as IMG
from PIL import Image

st.set_page_config(page_title="Listing Studio", page_icon="🛍️", layout="wide")

st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:wght@400;700&family=Archivo:wght@600;700;800&family=JetBrains+Mono:wght@500;700&display=swap');
.stApp{background:#fff}
html,body,[class*="css"]{font-family:'Atkinson Hyperlegible','Inter',system-ui,sans-serif;
 color:#0f1419;font-size:16px;line-height:1.55}
h1,h2,h3,h4,h5{font-family:'Archivo',sans-serif;color:#0b0f14;letter-spacing:-.015em}
.stMarkdown p,label,li{font-size:15.5px;color:#26303c}
.stCodeBlock code,pre code{font-family:'JetBrains Mono',monospace!important;font-size:15px!important;
 line-height:1.6!important;color:#0f1419!important}
.stCodeBlock{border:1px solid #d7dce4!important;border-radius:10px!important;background:#fbfcfe!important}
input,textarea{font-size:15.5px!important;color:#0f1419!important}
.block-container{padding-top:1.3rem;max-width:1380px}
.hero{background:linear-gradient(115deg,#ffe29a,#ff9a8b 38%,#ff6fa5 68%,#7b6cff);
 border-radius:18px;padding:20px 24px;margin-bottom:16px;box-shadow:0 10px 26px rgba(123,108,255,.2)}
.hero h1{font-size:25px;font-weight:800;margin:0;color:#20142e}
.hero p{margin:6px 0 0;font-size:13px;color:#3a2440;font-weight:500;max-width:840px}
.lbl{display:flex;justify-content:space-between;align-items:baseline;margin:14px 0 2px}
.lbl b{font-size:15px;font-weight:700;color:#0b0f14}
.lbl span{font-family:'JetBrains Mono',monospace;font-size:12.5px;font-weight:700;
 padding:3px 10px;border-radius:999px}
.ok{background:#dcfce7;color:#0b7a46;border:1px solid #86efac}
.warn{background:#fef3c7;color:#96690b;border:1px solid #fcd34d}
.bad{background:#ffe4e6;color:#b4143c;border:1px solid #fda4af}
.sc{display:flex;align-items:center;gap:18px;background:#fff;border:1px solid #e7eaf3;
 border-left:8px solid var(--c,#22c55e);border-radius:14px;padding:14px 20px;margin:8px 0 14px;
 box-shadow:0 4px 14px rgba(20,26,41,.06)}
.sc .n{font-family:'JetBrains Mono',monospace;font-size:38px;font-weight:700;line-height:1}
.sc .m{font-size:12.5px;color:#6b7391}
.iss{font-size:14px;padding:7px 12px;border-radius:9px;margin:4px 0;background:#f7f9fc;
 border-left:4px solid #cbd5e1;color:#3a4256}
.iss.error{background:#fff1f2;border-left-color:#f43f5e}
.iss.warn{background:#fffbeb;border-left-color:#f59e0b}
.iss.ok{background:#f0fdf4;border-left-color:#22c55e}
.chip{display:inline-block;font-size:12px;font-weight:600;padding:4px 10px;margin:3px;
 border-radius:999px;border:1px solid}
.stTabs [data-baseweb="tab-list"]{gap:6px}
[data-baseweb="tab"]{font-weight:700;font-family:'Archivo',sans-serif;font-size:16px}
div.stButton>button[kind="primary"]{background:#7b6cff;border:0;font-weight:700;border-radius:10px}
</style>""", unsafe_allow_html=True)

st.markdown('<div class="hero"><h1>Listing Studio</h1><p>Amazon title, item highlights, bullets '
 'and backend search terms, built to the 2026 rules. Everything updates as you type — there is no '
 'button to press.</p></div>', unsafe_allow_html=True)

# --------------------------------------------------------------- helpers
def cls(count, limit):
    return "bad" if count > limit else "warn" if count > limit * .9 else "ok"

def copy_button(text, key, caption=""):
    """Visible copy control above the box. st.code below keeps its own native
    copy icon as a fallback if the browser blocks the clipboard call."""
    payload = json.dumps(text or "")
    components.html(f"""
      <div style="display:flex;align-items:center;gap:10px;font-family:'Atkinson Hyperlegible',
                  system-ui,sans-serif">
        <button id="cb{key}" style="background:#7b6cff;color:#fff;border:0;border-radius:8px;
          padding:7px 16px;font-size:14px;font-weight:700;cursor:pointer">Copy</button>
        <span style="font-size:13px;color:#5b6472">{C.esc(caption)}</span>
      </div>
      <script>
        const t{key} = {payload};
        const b{key} = document.getElementById("cb{key}");
        b{key}.onclick = async () => {{
          try {{ await navigator.clipboard.writeText(t{key}); }}
          catch (e) {{
            const ta = document.createElement('textarea');
            ta.value = t{key}; ta.style.position='fixed'; ta.style.opacity='0';
            document.body.appendChild(ta); ta.select();
            try {{ document.execCommand('copy'); }} catch (err) {{}}
            document.body.removeChild(ta);
          }}
          b{key}.textContent = 'Copied'; b{key}.style.background = '#22c55e';
          setTimeout(() => {{ b{key}.textContent='Copy'; b{key}.style.background='#7b6cff'; }}, 1400);
        }};
      </script>""", height=44)


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
    label("Title", C.clen(title), C.TITLE_LIMIT)
    copy_button(title, f"t{key}"); st.code(title or "", language=None)

    label("Item Highlights", C.clen(high), C.HIGHLIGHT_LIMIT)
    copy_button(high, f"h{key}"); st.code(high or "", language=None)

    for i, b in enumerate(live, 1):
        label(f"Bullet {i}", C.clen(b), C.BULLET_MAX)
        copy_button(b, f"b{key}{i}"); st.code(b, language=None)

    label(f"All {len(live)} bullets, one per line",
          sum(C.clen(b) for b in live), C.BULLETS_TOTAL_MAX)
    copy_button("\n".join(live), f"all{key}", "one bullet per line")
    st.code("\n".join(live), language=None)

    if backend:
        label("Backend search terms", C.blen(backend), C.BACKEND_BYTES, "bytes")
        copy_button(backend, f"k{key}"); st.code(backend, language=None)
    if desc:
        label("Description", C.clen(desc), C.DESCRIPTION_LIMIT)
        copy_button(desc, f"d{key}"); st.code(desc, language=None)
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
                "AI generation", "Keyword research", "Rules"])

# ================================================================ BUILD
with tabs[0]:
    st.markdown("### Product details")
    st.caption("Fields are read in priority order. Whatever will not fit the 75-character title "
               "drops into Item Highlights, and whatever will not fit there becomes bullet "
               "material. Nothing is thrown away.")

    def clear_build():
        for k in ("f_brand","f_type","f_a1","f_a2","f_a3","f_a4","f_usp","f_size","f_use","f_feat"):
            st.session_state[k] = ""

    r1c1, r1c2, r1c3 = st.columns(3)
    with r1c1:
        st.markdown('<div class="lbl"><b>1 · Brand name</b></div>', unsafe_allow_html=True)
        brand = st.text_input("br", key="f_brand", label_visibility="collapsed", placeholder="Rider")
    with r1c2:
        st.markdown('<div class="lbl"><b>2 · Attribute 1 — the strongest qualifier</b></div>',
                    unsafe_allow_html=True)
        a1 = st.text_input("a1", key="f_a1", label_visibility="collapsed",
                           placeholder="Real Carbon Fibre")
    with r1c3:
        st.markdown('<div class="lbl"><b>3 · Product type</b></div>', unsafe_allow_html=True)
        ptype = st.text_input("pt", key="f_type", label_visibility="collapsed",
                              placeholder="Modular Motorcycle Helmet")

    r2c1, r2c2, r2c3 = st.columns(3)
    with r2c1:
        st.markdown('<div class="lbl"><b>4 · USP</b></div>', unsafe_allow_html=True)
        usp = st.text_input("up", key="f_usp", label_visibility="collapsed",
                            placeholder="1.48 kg Lightweight")
    with r2c2:
        st.markdown('<div class="lbl"><b>5 · Size or gender</b></div>', unsafe_allow_html=True)
        size = st.text_input("sz", key="f_size", label_visibility="collapsed",
                             placeholder="Medium, 500 ML or Men's")
    with r2c3:
        st.markdown('<div class="lbl"><b>6 · Attribute 2</b></div>', unsafe_allow_html=True)
        a2 = st.text_input("a2", key="f_a2", label_visibility="collapsed", placeholder="Dual Visor")

    r3c1, r3c2 = st.columns(2)
    with r3c1:
        st.markdown('<div class="lbl"><b>7 · Attribute 3</b></div>', unsafe_allow_html=True)
        a3 = st.text_input("a3", key="f_a3", label_visibility="collapsed",
                           placeholder="DOT and ECE Certified")
    with r3c2:
        st.markdown('<div class="lbl"><b>8 · Attribute 4</b></div>', unsafe_allow_html=True)
        a4 = st.text_input("a4", key="f_a4", label_visibility="collapsed",
                           placeholder="Flip Up Chin Bar")

    st.markdown('<div class="lbl"><b>Used for</b></div>', unsafe_allow_html=True)
    use = st.text_input("uc", key="f_use", label_visibility="collapsed",
                        placeholder="for touring and daily commuting")

    st.markdown('<div class="lbl"><b>Features — one per line, or paste a paragraph</b></div>',
                unsafe_allow_html=True)
    feat_raw = st.text_area("ft", key="f_feat", height=140, label_visibility="collapsed",
        placeholder="Superior Ventilation System: top and rear vents keep air moving\n"
                    "Retractable sun visor cuts glare without swapping shields\n"
                    "Quick release buckle opens with one hand")
    st.caption("Write your own ALL CAPS heading followed by a colon and it is kept as the bullet "
               "heading. Styled or bold pasted text is folded back to plain characters, since "
               "Amazon rejects those symbols.")
    st.button("Clear all boxes", key="f_clear", on_click=clear_build)

    feats, fmode = C.parse_bullets(feat_raw, maxb)
    if C.is_paragraph(feat_raw):
        feats = [x.split(": ", 1)[-1] for x in feats]
        st.caption(f"Paragraph detected and split into {len(feats)} feature points.")

    if C.ws(brand) and C.ws(ptype):
        facts = C.Facts(brand=brand, product_type=ptype, attr1=a1, attr2=a2, attr3=a3, attr4=a4,
                        usp=usp, size_gender=size, use_case=use, features=feats)
        res = C.compose(facts, media, max_bullets=maxb)
        title, high, bullets = res["title"], res["highlights"], res["bullets"]

        au = [C.audit_title(title, brand, media), C.audit_highlights(high)]
        au += [C.audit_bullet(b, i + 1) for i, b in enumerate(bullets)]
        au.append(C.audit_bullets_total(bullets))

        st.markdown("---")
        scorecard(au)

        h1, h2 = st.columns(2)
        with h1:
            st.markdown("**Moved down to Item Highlights**")
            st.markdown("".join(f'<span class="chip ok">{C.esc(x)}</span>'
                                for x in res["to_highlights"]) or "_nothing, it all fit the title_",
                        unsafe_allow_html=True)
        with h2:
            st.markdown("**Moved down to the bullets**")
            st.markdown("".join(f'<span class="chip warn">{C.esc(x)}</span>'
                                for x in res["to_bullets"]) or "_nothing left over_",
                        unsafe_allow_html=True)

        problems = {k: v for k, v in res["logic"].items() if v}
        if problems:
            for num, msgs in problems.items():
                for m in msgs:
                    st.markdown(f'<div class="iss error"><b>Bullet {num}</b> &nbsp;{C.esc(m)}</div>',
                                unsafe_allow_html=True)
        else:
            st.markdown('<div class="iss ok"><b>Checked</b> &nbsp;Every bullet has one heading, no '
                        'repeated clause, and no clause opening or closing on a conjunction.</div>',
                        unsafe_allow_html=True)

        copy_out(title, high, bullets, key="b")
        st.session_state["listing"] = {"title": title, "high": high, "bullets": bullets,
                                       "brand": brand, "features": feats}
        with st.expander("Field-by-field check"):
            for a in au:
                label(a.field, a.count, a.limit)
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
                        attr2=ia2, size_gender=isize or mined["pack"] or mined["size"],
                        features=mined["features"])
        _res = C.compose(facts, media, max_bullets=maxb)
        title, high = _res["title"], _res["highlights"]

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

with tabs[4]:
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
with tabs[5]:
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

with tabs[4]:
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
with tabs[5]:
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

# ================================================================ IMAGES
def _render_slot(i, src, extras, cfg_kind, bg, cfg):
    return IMG.render(cfg_kind, src, cfg, extras=extras, bg=bg)

def _show_gallery(built, asin, keyprefix):
    files = []
    for i, (name, im, is_main) in enumerate(built):
        data = IMG.encode(im)
        fname = IMG.filename(asin, 0 if is_main else i)
        files.append((fname, data))
        st.markdown(f"#### {i+1}. {name}")
        st.markdown(f'<div class="lbl"><b>{fname}</b><span class="ok">{im.size[0]} x {im.size[1]} '
                    f'· {len(data)/1024:.0f} KB</span></div>', unsafe_allow_html=True)
        st.image(im, use_container_width=True)
        for sev, msg in IMG.audit_image(im, is_main=is_main):
            tag = {"error": "Fix", "warn": "Check", "ok": "OK"}[sev]
            st.markdown(f'<div class="iss {sev}"><b>{tag}</b> &nbsp;{C.esc(msg)}</div>',
                        unsafe_allow_html=True)
        st.download_button(f"Download {fname}", data, fname, "image/jpeg",
                           key=f"{keyprefix}dl{i}")
    if files:
        st.markdown("---")
        st.download_button("Download the whole gallery (.zip)", IMG.build_zip(files),
                           f"{IMG.safe_asin(asin)}_images.zip", "application/zip",
                           type="primary", key=f"{keyprefix}zip")
        st.caption("Named to Amazon's convention: ASIN.MAIN.jpg, then ASIN.PT01.jpg and onward.")
    return files

def _pairs(txt, fallback=""):
    out = []
    for line in C.parse_lines(txt):
        a, _, b = line.partition("|")
        out.append((C.ws(a), C.ws(b) or fallback))
    return out

with tabs[2]:
    st.markdown("### Build each image yourself")
    st.caption("Add as many slots as you need. Every slot picks its own template, carries its own "
               "headline and callouts, and can take its own background photo.")

    up = st.file_uploader("Product photo on a plain background",
                          type=["jpg", "jpeg", "png", "webp"], key="m_main")
    extras_up = st.file_uploader("More angles, optional — used by the grid template",
                                 type=["jpg", "jpeg", "png", "webp"],
                                 accept_multiple_files=True, key="m_extra")
    st.markdown('<div class="lbl"><b>ASIN or SKU for the file names</b></div>', unsafe_allow_html=True)
    m_asin = st.text_input("ma", key="m_asin", label_visibility="collapsed",
                           placeholder="B0XXXXXXXX")
    n_slots = st.number_input("How many images", 1, 9, 5, key="m_n")

    tmpl_names = list(IMG.TEMPLATES.keys())
    defaults = ["Main — pure white", "Hero benefit", "Feature callouts",
                "Certification badges", "Spec or statistic", "Angle grid",
                "Hero benefit", "Feature callouts", "Spec or statistic"]
    slots = []
    for i in range(int(n_slots)):
        with st.expander(f"Image {i+1}", expanded=(i < 2)):
            kind_label = st.selectbox("Template", tmpl_names, key=f"m_k{i}",
                                      index=tmpl_names.index(defaults[i % len(defaults)]))
            kind = IMG.TEMPLATES[kind_label]
            bgf = None
            cfg = {}
            if kind != "main":
                c1, c2 = st.columns(2)
                with c1:
                    cfg["headline"] = st.text_input("Headline", key=f"m_h{i}",
                                                    placeholder="Ready for")
                with c2:
                    cfg["accent"] = st.text_input("Accent, shown in red", key=f"m_a{i}",
                                                  placeholder="any road")
                if kind in ("hero",):
                    cfg["subline"] = st.text_area("Sub-line", key=f"m_s{i}", height=70)
                if kind in ("callouts", "badge", "spec"):
                    cfg["items"] = _pairs(st.text_area(
                        "Callouts — one per line, \"title | description\"",
                        key=f"m_i{i}", height=110,
                        placeholder="Optimal airflow | Top and rear vents circulate air"))
                if kind == "spec":
                    s1, s2 = st.columns(2)
                    with s1: cfg["stat"] = st.text_input("Big number", key=f"m_n{i}b",
                                                         placeholder="1.48")
                    with s2: cfg["stat_label"] = st.text_input("Unit", key=f"m_u{i}",
                                                              placeholder="kg")
                if kind == "grid":
                    cfg["labels"] = C.parse_lines(st.text_area(
                        "Grid labels, one per line", key=f"m_g{i}", height=90,
                        placeholder="Front view\nSide view\nTop view\nAngled view")) or None
                bgf = st.file_uploader("Background photo for this image, optional",
                                       type=["jpg", "jpeg", "png", "webp"], key=f"m_bg{i}")
            slots.append((kind_label, kind, cfg, bgf))

    if up is None:
        st.info("Upload a product photo to start building.")
    else:
        try:
            src = Image.open(up)
            others = [Image.open(f) for f in (extras_up or [])]
            built = []
            with st.spinner("Rendering…"):
                for label_, kind, cfg, bgf in slots:
                    bg = Image.open(bgf) if bgf else None
                    built.append((label_, IMG.render(kind, src, cfg, extras=others, bg=bg),
                                  kind == "main"))
            st.markdown("---")
            _show_gallery(built, m_asin, "man")
        except Exception as e:
            st.error(f"Could not render: {e}")

# ================================================================ AI GENERATION
with tabs[3]:
    st.markdown("### Generate the set automatically")
    st.caption("Upload the product photo and a background, point it at your copy, and the whole "
               "gallery is planned and rendered in one pass. The plan reads your bullets, spots "
               "the certifications and the numbers, and assigns each to the slot it belongs in.")
    st.info("What this does and does not do: it composites your product, builds the graphics and "
            "lays out the type. It does not invent photographic scenery, so the lifestyle shot "
            "uses the background you upload.")

    a_up = st.file_uploader("Product photo on a plain background",
                            type=["jpg", "jpeg", "png", "webp"], key="a_main")
    a_bg = st.file_uploader("Background photo for the lifestyle and hero slots",
                            type=["jpg", "jpeg", "png", "webp"], key="a_bg")
    a_extra = st.file_uploader("More angles, optional", type=["jpg", "jpeg", "png", "webp"],
                               accept_multiple_files=True, key="a_extra")

    L = st.session_state.get("listing", {})
    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="lbl"><b>ASIN or SKU</b></div>', unsafe_allow_html=True)
        a_asin = st.text_input("aa", key="a_asin", label_visibility="collapsed",
                               placeholder="B0XXXXXXXX")
        st.markdown('<div class="lbl"><b>Title</b></div>', unsafe_allow_html=True)
        a_title = st.text_input("at", key="a_title", label_visibility="collapsed",
                                value=L.get("title", ""))
    with c2:
        st.markdown('<div class="lbl"><b>How many images</b></div>', unsafe_allow_html=True)
        a_n = st.slider("an", 5, 9, 6, key="a_n", label_visibility="collapsed")
        st.markdown('<div class="lbl"><b>Attributes, optional — "name | detail" per line</b></div>',
                    unsafe_allow_html=True)
        a_attrs = st.text_area("ax", key="a_attrs", height=88, label_visibility="collapsed",
                               placeholder="Real Carbon Fibre | keeps weight to 1.48 kg")

    st.markdown('<div class="lbl"><b>Bullets — paste them raw, one per line</b></div>',
                unsafe_allow_html=True)
    a_bul = st.text_area("ab", key="a_bul", height=150, label_visibility="collapsed",
                         value="\n".join(L.get("bullets", [])),
                         placeholder="SUPERIOR VENTILATION: top and rear vents keep air moving")
    if L.get("bullets"):
        st.caption("Pre-filled from the listing you built. Edit freely.")

    if a_up is None:
        st.info("Upload a product photo to generate the set.")
    else:
        try:
            src = Image.open(a_up)
            bg = Image.open(a_bg) if a_bg else None
            others = [Image.open(f) for f in (a_extra or [])]
            bullets = C.parse_lines(a_bul)
            attrs = C.parse_lines(a_attrs)
            plan = IMG.plan_from_copy(a_title, bullets, attrs, have_bg=bg is not None,
                                      n_extra=len(others), target=int(a_n))

            st.markdown("#### The plan")
            for i, p in enumerate(plan, 1):
                bits = p["cfg"].get("headline") or ""
                acc = p["cfg"].get("accent") or ""
                cnt = len(p["cfg"].get("items", []) or [])
                st.markdown(f'<span class="chip ok">{i}. {C.esc(p["name"])}'
                            f'{" — " + C.esc((bits + " " + acc).strip()) if bits else ""}'
                            f'{f" · {cnt} callouts" if cnt else ""}</span>', unsafe_allow_html=True)

            if not bullets and not attrs:
                st.warning("No bullets or attributes given, so the plan falls back to the title "
                           "alone. Paste your bullets for a much stronger set.")

            built = []
            with st.spinner("Rendering the gallery…"):
                for p in plan:
                    use_bg = bg if p.get("use_bg") else None
                    built.append((p["name"], IMG.render(p["kind"], src, p["cfg"],
                                                        extras=others, bg=use_bg),
                                  p["kind"] == "main"))
            st.markdown("---")
            _show_gallery(built, a_asin, "ai")
        except Exception as e:
            st.error(f"Could not generate: {e}")
