"""Build docs/USER_GUIDE.html — one self-contained page, generated FROM USER_GUIDE.md.

Single source of truth on purpose: the Markdown is authored, the HTML is derived, so the
two cannot drift. Screenshots are inlined as WebP data URIs, so the file works offline,
survives being emailed, and ships no external request — the same rule the product itself
follows (D-048 / D-069).

## Regenerating after editing docs/USER_GUIDE.md

    node tools/png_to_webp.js docs/guide images.json <chrome-profile-dir> 0.86
    python tools/build_user_guide.py images.json

`png_to_webp.js` uses Chrome's own canvas encoder rather than an image library — the repo
has no image dependency and does not need one for this. It shrinks the screenshots ~89%
(3.3 MB of PNG to ~380 KB of WebP), which is what keeps the single-file page under 600 KB
instead of 4.4 MB.

`tests/test_user_guide_html.py` fails if the HTML falls behind the Markdown, so forgetting
this step is caught rather than shipped.

The Markdown deliberately stays the readable source: it renders on GitHub, diffs cleanly,
and is what a human edits. The HTML is the shareable artifact.
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(r"D:\AndroidStudioProjects\how_to_get_proffessor")
MD = ROOT / "docs" / "USER_GUIDE.md"
OUT = ROOT / "docs" / "USER_GUIDE.html"
IMAGES = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))

# ── inline formatting ────────────────────────────────────────────────────────
def inline(s: str) -> str:
    out, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c == "`":                                        # code span, wins over all
            j = s.find("`", i + 1)
            if j == -1:
                out.append(html.escape(c)); i += 1; continue
            out.append("<code>" + html.escape(s[i + 1:j]) + "</code>"); i = j + 1; continue
        m = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", s[i:])    # image (handled by block too)
        if m:
            out.append(img_tag(m.group(2), m.group(1))); i += m.end(); continue
        m = re.match(r"<(https?://[^>\s]+)>", s[i:])        # autolink <https://…>
        if m:
            u = html.escape(m.group(1))
            out.append(f'<a href="{u}" target="_blank" rel="noopener">{u}</a>')
            i += m.end(); continue
        m = re.match(r"\[([^\]]+)\]\(([^)]+)\)", s[i:])     # link
        if m:
            href = m.group(2)
            ext = ' target="_blank" rel="noopener"' if href.startswith("http") else ""
            out.append(f'<a href="{html.escape(href)}"{ext}>{inline(m.group(1))}</a>')
            i += m.end(); continue
        if s.startswith("**", i):
            j = s.find("**", i + 2)
            if j != -1:
                out.append("<strong>" + inline(s[i + 2:j]) + "</strong>"); i = j + 2; continue
        if c == "*":
            j = s.find("*", i + 1)
            if j != -1 and j > i + 1:
                out.append("<em>" + inline(s[i + 1:j]) + "</em>"); i = j + 1; continue
        out.append(html.escape(c)); i += 1
    return "".join(out)


def img_tag(src: str, alt: str) -> str:
    name = src.split("/")[-1]
    uri = IMAGES.get(name)
    if not uri:
        return f'<span class="missing">[missing image: {html.escape(name)}]</span>'
    return (f'<figure class="shot"><img src="{uri}" alt="{html.escape(alt)}" loading="lazy">'
            f'<figcaption>{html.escape(alt)} <span class="zoom">click to enlarge</span>'
            f'</figcaption></figure>')


def plain(text: str) -> str:
    """Markdown stripped to bare words — for the sidebar, where `**bold**` and `code`
    markers would otherwise show up literally."""
    t = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", t)
    t = t.replace("`", "")
    return re.sub(r"\s+", " ", t).strip()


def slugify(text: str) -> str:
    t = re.sub(r"<[^>]+>", "", text)
    t = re.sub(r"[^\w\s-]", "", t.lower())
    return re.sub(r"[\s]+", "-", t).strip("-")


# ── block parsing ────────────────────────────────────────────────────────────
def build(md: str) -> tuple[str, list[tuple[int, str, str]]]:
    lines = md.split("\n")
    out, toc = [], []
    i, n = 0, len(lines)
    while i < n:
        ln = lines[i]

        if ln.startswith("```"):                                    # fenced code
            lang = ln[3:].strip()
            i += 1
            buf = []
            while i < n and not lines[i].startswith("```"):
                buf.append(lines[i]); i += 1
            i += 1
            out.append(f'<pre class="code" data-lang="{html.escape(lang)}"><code>'
                       + html.escape("\n".join(buf)) + "</code></pre>")
            continue

        if re.match(r"^\s*(---|\*\*\*)\s*$", ln):
            out.append("<hr>"); i += 1; continue

        m = re.match(r"^(#{1,6})\s+(.*)$", ln)                      # heading
        if m:
            lvl, text = len(m.group(1)), m.group(2).strip()
            sid = slugify(text)
            if lvl in (2, 3):
                toc.append((lvl, text, sid))
            out.append(f'<h{lvl} id="{sid}">{inline(text)}'
                       f'<a class="anchor" href="#{sid}" aria-label="link">#</a></h{lvl}>')
            i += 1; continue

        if ln.startswith(">"):                                      # blockquote
            buf = []
            while i < n and lines[i].startswith(">"):
                buf.append(lines[i].lstrip(">").strip()); i += 1
            inner, _ = build("\n".join(buf))
            out.append(f'<blockquote>{inner}</blockquote>'); continue

        if ln.lstrip().startswith("|") and i + 1 < n and re.match(r"^\s*\|[\s:\-|]+\|\s*$", lines[i + 1]):
            head = [c.strip() for c in ln.strip().strip("|").split("|")]
            i += 2
            rows = []
            while i < n and lines[i].lstrip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            th = "".join(f"<th>{inline(c)}</th>" for c in head)
            tb = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>"
                         for r in rows)
            out.append(f'<div class="tw"><table><thead><tr>{th}</tr></thead>'
                       f"<tbody>{tb}</tbody></table></div>")
            continue

        m = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", ln)             # list
        if m:
            ordered = bool(re.match(r"\d+\.", m.group(2)))
            items, base = [], len(m.group(1))
            while i < n:
                mm = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", lines[i])
                if not mm or len(mm.group(1)) < base:
                    if lines[i].strip() and not lines[i].lstrip().startswith(("|", "#", ">", "```")) \
                       and items and lines[i].startswith(" "):
                        items[-1] += " " + lines[i].strip(); i += 1; continue
                    break
                items.append(mm.group(3)); i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{inline(x)}</li>" for x in items) + f"</{tag}>")
            continue

        if not ln.strip():
            i += 1; continue

        buf = []                                                    # paragraph
        while i < n and lines[i].strip() and not re.match(
                r"^(#{1,6}\s|\s*\||>|```|\s*([-*]|\d+\.)\s|\s*---\s*$)", lines[i]):
            buf.append(lines[i]); i += 1
        para = " ".join(buf).strip()
        if para:
            mimg = re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)", para)
            out.append(img_tag(mimg.group(2), mimg.group(1)) if mimg
                       else f"<p>{inline(para)}</p>")
    return "\n".join(out), toc


CSS = """
*{box-sizing:border-box}
:root{--bg:#0f1115;--panel:#161920;--panel2:#1b1f28;--ink:#e9eaed;--soft:#b6bac4;
--muted:#878c99;--line:#262b36;--indigo:#7fa6ee;--amber:#e0b25f;--green:#5fd39a;
--violet:#a98ae8;--rose:#e58197;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.68 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
-webkit-font-smoothing:antialiased}
.hero{padding:64px 32px 40px;border-bottom:1px solid var(--line);
background:radial-gradient(1100px 380px at 12% -10%,#1d2440 0%,transparent 62%),var(--bg)}
.hero .eyebrow{font:600 12px/1 var(--mono);letter-spacing:.18em;color:var(--amber);
text-transform:uppercase;margin-bottom:18px}
.hero h1{margin:0 0 14px;font-size:clamp(30px,4.4vw,50px);line-height:1.08;letter-spacing:-.02em}
.hero p{margin:0;max-width:76ch;color:var(--soft);font-size:17px}
.hero .live{display:inline-flex;align-items:center;gap:9px;margin-top:22px;padding:9px 16px;
border:1px solid #2f6b4d;border-radius:999px;background:#10251b;color:#8ce0b4;
font:600 14px/1 var(--mono);text-decoration:none}
.hero .live .dot{width:8px;height:8px;border-radius:50%;background:#4ade80;
box-shadow:0 0 0 4px rgba(74,222,128,.16)}
.shell{display:grid;grid-template-columns:290px minmax(0,1fr);gap:44px;
max-width:1500px;margin:0 auto;padding:40px 32px 96px}
.toc{position:sticky;top:24px;align-self:start;max-height:calc(100vh - 48px);overflow:auto;
border:1px solid var(--line);border-radius:14px;background:var(--panel);padding:18px}
.toc .lbl{font:600 11px/1 var(--mono);letter-spacing:.16em;color:var(--muted);
text-transform:uppercase;margin-bottom:12px}
.toc a{display:block;padding:6px 10px;border-radius:8px;color:var(--soft);
text-decoration:none;font-size:13.5px;border-left:2px solid transparent}
.toc a:hover{background:#1e2330;color:var(--ink)}
.toc a.l3{padding-left:22px;font-size:12.5px;color:var(--muted)}
.toc a.on{color:var(--ink);background:#1e2330;border-left-color:var(--amber)}
main{min-width:0;max-width:96ch}
h1,h2,h3,h4{line-height:1.22;letter-spacing:-.01em}
main>h1{font-size:32px;margin:8px 0 18px}
h2{font-size:25px;margin:52px 0 16px;padding-top:14px;border-top:1px solid var(--line)}
h3{font-size:19px;margin:32px 0 12px;color:#dfe3ea}
h4{font-size:16px;margin:22px 0 8px;color:var(--soft)}
.anchor{margin-left:10px;color:#39404f;text-decoration:none;font-weight:400;
opacity:0;transition:opacity .12s}
h2:hover .anchor,h3:hover .anchor{opacity:1}
p{margin:0 0 15px;color:#dcdfe6}
a{color:var(--indigo)}a:hover{color:#a9c4f5}
strong{color:#fff}
code{font:13.5px/1.5 var(--mono);background:#1c2028;border:1px solid #2a303c;
border-radius:5px;padding:1.5px 6px;color:#cfe0ff}
pre.code{position:relative;background:#12151b;border:1px solid var(--line);border-radius:12px;
padding:18px 18px 16px;overflow-x:auto;margin:0 0 20px}
pre.code code{background:none;border:0;padding:0;color:#d5dae4;font-size:13px;line-height:1.62}
pre.code[data-lang]:not([data-lang=""])::after{content:attr(data-lang);position:absolute;
top:9px;right:12px;font:600 10px/1 var(--mono);letter-spacing:.12em;text-transform:uppercase;
color:#4d5666}
ul,ol{margin:0 0 16px;padding-left:22px}li{margin:5px 0;color:#dcdfe6}
blockquote{margin:0 0 20px;padding:14px 18px;border-left:3px solid var(--amber);
background:#1b1a14;border-radius:0 10px 10px 0;color:#efe2c4}
blockquote p:last-child{margin-bottom:0}
blockquote code{background:#241f16;border-color:#3c3career}
hr{border:0;border-top:1px solid var(--line);margin:34px 0}
.tw{overflow-x:auto;margin:0 0 22px;border:1px solid var(--line);border-radius:12px}
table{border-collapse:collapse;width:100%;font-size:14px}
th{text-align:left;padding:11px 14px;background:#191d26;color:var(--soft);
font:600 11.5px/1.4 var(--mono);letter-spacing:.07em;text-transform:uppercase;
border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:11px 14px;border-bottom:1px solid #1f2530;vertical-align:top;color:#d7dae2}
tbody tr:last-child td{border-bottom:0}
tbody tr:hover td{background:#171b23}
figure.shot{margin:0 0 26px}
figure.shot img{display:block;width:100%;border:1px solid var(--line);border-radius:14px;
cursor:zoom-in;background:#0b0d11}
figcaption{margin-top:9px;font-size:12.5px;color:var(--muted);display:flex;
justify-content:space-between;gap:14px}
.zoom{font:11px/1 var(--mono);color:#4f5765;white-space:nowrap}
.missing{color:var(--rose);font:12px var(--mono)}
#lb{position:fixed;inset:0;background:rgba(6,8,11,.94);display:none;place-items:center;
z-index:50;padding:28px;cursor:zoom-out}
#lb.on{display:grid}
#lb img{max-width:100%;max-height:100%;border-radius:12px;border:1px solid #2c3342}
footer{max-width:1500px;margin:0 auto;padding:26px 32px 60px;color:var(--muted);
font-size:13px;border-top:1px solid var(--line)}
@media(max-width:1080px){.shell{grid-template-columns:1fr;gap:24px}
.toc{position:static;max-height:none}}
@media print{.toc,#lb,.hero .live{display:none}body{background:#fff;color:#111}
main{max-width:none}figure.shot img{border-color:#ccc}}
"""

JS = """
(function(){
  var lb=document.getElementById('lb'),lbi=lb.querySelector('img');
  document.querySelectorAll('figure.shot img').forEach(function(im){
    im.addEventListener('click',function(){lbi.src=im.src;lb.classList.add('on');});
  });
  lb.addEventListener('click',function(){lb.classList.remove('on');lbi.src='';});
  document.addEventListener('keydown',function(e){
    if(e.key==='Escape'){lb.classList.remove('on');lbi.src='';}});
  var links=[].slice.call(document.querySelectorAll('.toc a'));
  var map={};links.forEach(function(a){map[a.getAttribute('href').slice(1)]=a;});
  var heads=[].slice.call(document.querySelectorAll('h2[id],h3[id]'));
  var obs=new IntersectionObserver(function(es){
    es.forEach(function(en){
      if(!en.isIntersecting)return;
      links.forEach(function(a){a.classList.remove('on');});
      var a=map[en.target.id];if(a)a.classList.add('on');
    });
  },{rootMargin:'-12% 0px -80% 0px',threshold:0});
  heads.forEach(function(h){obs.observe(h);});
})();
"""


def main() -> int:
    md = MD.read_text(encoding="utf-8")
    # the md's own Contents list is replaced by the sidebar
    md = re.sub(r"^## Contents\n(?:.*\n)*?(?=^---$)", "", md, flags=re.M)
    body, toc = build(md)
    # stripping the Contents section can leave its two separators adjacent
    body = re.sub(r"(?:<hr>\s*){2,}", "<hr>\n", body)

    nav = "".join(
        f'<a class="{"l3" if lvl == 3 else "l2"}" href="#{sid}">'
        f'{html.escape(plain(re.sub(r"^\\d+ · ", "", txt)))}</a>'
        for lvl, txt, sid in toc)

    doc = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Supervisorly — the complete user guide</title>
<meta name="description" content="Every step of Supervisorly, from opening the page to a
finished dashboard: what is called, what comes back, the limits, and what can go wrong.">
<style>{CSS}</style>
</head><body>
<header class="hero">
  <div class="eyebrow">Supervisorly · user guide</div>
  <h1>From a blank page to a supervisor shortlist.</h1>
  <p>Every step of the product, with real screenshots — and at each one, exactly what the
  page calls, what comes back, what the limits are, and what can go wrong. Nothing here is
  aspirational: it is read from the code and captured from the live deployment.</p>
  <a class="live" href="https://supervisorly.web.app" target="_blank" rel="noopener">
    <span class="dot"></span> supervisorly.web.app — live</a>
</header>
<div class="shell">
  <aside class="toc"><div class="lbl">Contents</div>{nav}</aside>
  <main>{body}</main>
</div>
<footer>Generated from <code>docs/USER_GUIDE.md</code> — the Markdown is the source, this page
is derived, so the two cannot drift. Self-contained: screenshots are embedded, no external
request is made. If the product and this guide disagree, the product is right.</footer>
<div id="lb"><img alt="enlarged screenshot"></div>
<script>{JS}</script>
</body></html>"""

    OUT.write_text(doc, encoding="utf-8")
    kb = OUT.stat().st_size / 1024
    print(f"wrote {OUT.relative_to(ROOT)}  {kb:,.0f} KB  "
          f"({len(IMAGES)} images embedded, {len(toc)} nav entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
