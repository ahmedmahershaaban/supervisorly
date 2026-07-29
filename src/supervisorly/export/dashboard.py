"""Build the single self-contained dashboard HTML — in the "Supervisorly Atlas — Living" design
language (`design_handoff_supervisorly_atlas/`), still ONE offline file (D-033/D-048).

Bioluminescent art direction: the tissue-type palette + Space Grotesk / Space Mono (named with
faithful system fallbacks — **no external font**, so the file stays self-contained), the
sidebar/drawer shell, and the **glowing cells + curved animated filament** diagram engine. Three
views over the same export:

* **Table** — every professor, every field, filterable; four states rendered distinctly (D-022/046).
* **Deadlines** — projected dates shown as *watch* dates, never firm (D-061).
* **How it works** — a cells-and-filaments diagram (the engine "how diagrams appear"): glowing cell
  nodes + cubic-bezier filaments with animated light-packets, highlight-connected, resize-aware.

Clicking a professor opens a **cell drawer** with every field's value, verbatim quote, source link,
and confidence — every displayed fact traceable (D-010). No external resources; injection- and
URL-scheme-safe; `prefers-reduced-motion` disables all animation.
"""

from __future__ import annotations

import json

_CSS = r"""
:root{
  --void:#05070c; --panel-a:rgba(15,22,34,.7); --panel-b:rgba(6,9,15,.9);
  --sidebar:rgba(7,10,16,.72); --drawer:rgba(9,13,20,.98); --chip:rgba(10,14,22,.66);
  --line:#172233; --line2:#1a2434; --ink:#e9edf3; --ink2:#c1c8d6; --muted:#9aa2b4; --faint:#6a7488;
  --accent:#e8b24a; --accent2:#e8b24a; --teal:#43c9d6; --focus:#7fd6e0;
  --chartreuse:#79d06a; --coral:#f0839a; --violet:#b58cf0; --slate:#7d828e;
  --val:#dff2e7; --absent:#8a8d96; --never:#5a5d66; --blocked:#e8bf6a;
  --firm:#7bd88f; --watch:#e8bf6a;
  --sans:'Space Grotesk',ui-sans-serif,system-ui,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
  --mono:'Space Mono',ui-monospace,'Cascadia Code',Consolas,'Liberation Mono',monospace;
}
*{box-sizing:border-box}
body{margin:0;font-family:var(--sans);color:var(--ink);font-size:15px;line-height:1.6;
  background:var(--void);-webkit-font-smoothing:antialiased;
  background-image:
    radial-gradient(1100px 720px at 78% -8%, rgba(120,86,220,.14), transparent 60%),
    radial-gradient(1000px 700px at 6% 32%, rgba(41,150,168,.13), transparent 58%),
    radial-gradient(900px 900px at 96% 88%, rgba(228,160,70,.09), transparent 60%);
  background-attachment:fixed}
.scan{position:fixed;inset:0;pointer-events:none;z-index:0;
  background:radial-gradient(120% 120% at 50% 50%, transparent 58%, rgba(2,4,8,.78) 100%)}
.scan::after{content:"";position:absolute;left:0;right:0;height:120px;
  background:linear-gradient(180deg,transparent,rgba(127,214,224,.05),transparent);
  animation:omScan 11s linear infinite}
header{position:relative;z-index:1;padding:34px clamp(20px,4vw,56px) 18px;border-bottom:1px solid var(--line)}
.eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:.22em;text-transform:uppercase;color:var(--accent)}
h1{margin:.35em 0 .1em;font-weight:700;letter-spacing:-.02em;font-size:clamp(22px,3.4vw,32px)}
.meta{color:var(--faint);font-family:var(--mono);font-size:11.5px}
.controls{position:relative;z-index:1;display:flex;gap:10px;flex-wrap:wrap;align-items:center;
  padding:14px clamp(20px,4vw,56px);border-bottom:1px solid var(--line)}
input,button{font:inherit}
#q{flex:1;min-width:220px;background:var(--chip);color:var(--ink);border:1px solid var(--line);
  border-radius:10px;padding:9px 13px;font-family:var(--mono);font-size:13px}
.vbtn{background:var(--chip);color:var(--ink2);border:1px solid var(--line);border-radius:10px;
  padding:9px 14px;cursor:pointer;font-family:var(--mono);font-size:12.5px}
.vbtn:hover{border-color:var(--accent);color:var(--accent)}
.vbtn.on{border-color:var(--accent);color:var(--accent);background:rgba(232,178,74,.09)}
.count{font-family:var(--mono);font-size:11.5px;color:var(--faint)}
/* supervision-level filter chips (MI-4) */
.levels{position:relative;z-index:1;display:flex;gap:8px;flex-wrap:wrap;align-items:center;
  padding:11px clamp(20px,4vw,56px);border-bottom:1px solid var(--line)}
.lvl-lead{font-family:var(--mono);font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--faint);margin-right:2px}
.chip{background:var(--chip);color:var(--muted);border:1px solid var(--line);border-radius:999px;
  padding:5px 12px;cursor:pointer;font-family:var(--mono);font-size:12px}
.chip:hover{border-color:var(--teal);color:var(--ink2)}
.chip:focus-visible{outline:2px solid var(--focus);outline-offset:2px}
.chip.on{border-color:var(--teal);color:var(--teal);background:rgba(67,201,214,.10)}
.chip-n{opacity:.62;margin-left:3px}
.lvl-note{font-family:var(--mono);font-size:11px;color:var(--faint);flex:1 1 100%;padding-top:2px}
.wrap{position:relative;z-index:1;padding:14px clamp(16px,3vw,44px) 90px}
.hidden{display:none}
/* table */
table{border-collapse:collapse;width:100%;min-width:640px}
.tblwrap{overflow-x:auto;border:1px solid var(--line);border-radius:14px;
  background:radial-gradient(120% 140% at 50% 0%, var(--panel-a), var(--panel-b))}
th,td{text-align:left;padding:11px 14px;border-bottom:1px solid var(--line);vertical-align:top}
th{position:sticky;top:0;background:#0a0e15;color:var(--faint);font-family:var(--mono);
  font-size:10.5px;letter-spacing:.05em;text-transform:uppercase;font-weight:700}
tr.row{cursor:pointer}tr.row:hover td{background:rgba(127,214,224,.04)}
tr.row:focus{outline:2px solid var(--focus);outline-offset:-2px}
.name{font-weight:650}
.s-value{color:var(--val)} .s-searched_absent{color:var(--absent);font-style:italic}
.s-never_attempted{color:var(--never)} .s-blocked{color:var(--blocked)}
.src{color:var(--faint);text-decoration:none;font-size:11px;margin-left:6px}
.src:hover{color:var(--accent)}
.empty{padding:44px 20px;color:var(--muted)}
/* deadline */
.dl-list{display:flex;flex-direction:column;gap:9px}
.dl-card{display:flex;gap:14px;align-items:baseline;padding:12px 14px;cursor:pointer;
  background:var(--chip);border:1px solid var(--line);border-radius:12px}
.dl-card:hover{border-color:var(--accent)} .dl-card:focus{outline:2px solid var(--focus)}
.dl-date{font-family:var(--mono);font-size:13px;min-width:118px}
.badge{font-family:var(--mono);font-size:10.5px;padding:2px 9px;border-radius:999px;border:1px solid var(--line)}
.badge.firm{color:var(--firm);border-color:#3a6b48} .badge.watch{color:var(--watch);border-color:#7a6528}
.note{font-family:var(--mono);font-size:11px;color:var(--faint);padding:8px 4px}
/* phase ledger (CC-1) — what each phase attempted, reached and skipped, and why.
   It lives under the diagram because the diagram says what the engine DOES and this
   says what it did THIS TIME; a student reading one wants the other. */
.ledger{margin:26px auto 0;max-width:940px}
.ledger h2{font-family:var(--mono);font-size:11px;letter-spacing:.18em;text-transform:uppercase;
  color:var(--accent);font-weight:700;margin:0 0 10px}
.ledger table{min-width:0}
.ledger .tblwrap{overflow-x:auto}
.lg-num{font-family:var(--mono);font-size:12.5px;text-align:right;white-space:nowrap}
.lg-phase{font-family:var(--mono);font-size:12.5px;color:var(--teal);white-space:nowrap}
.lg-reason{color:var(--muted);font-size:13px}
.lg-zero{color:var(--never)}
.lg-skip{color:var(--blocked)}
/* professor modal — a centred dialog, not a side drawer: the panel now carries a profile,
   stats, links and a publication list, and 452px of edge-anchored column made that a
   scrolling ribbon on every screen size. */
.overlay{position:fixed;inset:0;background:rgba(3,5,9,.62);backdrop-filter:blur(3px);z-index:50}
.modal{position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);z-index:51;
  width:min(720px,94vw);max-height:88vh;overflow-y:auto;border-radius:14px;
  background:var(--drawer);border:1px solid var(--line2);padding:26px 28px;
  box-shadow:0 40px 120px -30px rgba(0,0,0,.95);animation:omModalIn .22s cubic-bezier(.2,.7,.2,1)}
@keyframes omModalIn{from{opacity:0;transform:translate(-50%,-46%) scale(.985)}
  to{opacity:1;transform:translate(-50%,-50%) scale(1)}}
@media (prefers-reduced-motion:reduce){.modal{animation:none}}
.modal h2{margin:.2em 0 .1em;font-size:24px;letter-spacing:-.01em}
.sect{margin-top:18px;padding-top:16px;border-top:1px solid var(--line2)}
.sect-h{font-family:var(--mono);font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;
  color:var(--faint);margin-bottom:10px}
.inst{color:var(--ink2);font-size:14.5px;margin-bottom:10px}
.stats{display:flex;flex-wrap:wrap;gap:8px}
.stat{font-family:var(--mono);font-size:11px;color:var(--muted);border:1px solid var(--line2);
  border-radius:999px;padding:4px 11px}
.stat b{color:var(--ink);font-size:12.5px}
.stat.match{border-color:var(--accent)}.stat.match b{color:var(--accent)}
.links{display:flex;flex-wrap:wrap;gap:14px;margin-top:12px}
.links a{color:var(--accent);text-decoration:none;font-size:13px}
.links a:hover{text-decoration:underline}
ol.works{margin:0;padding-left:18px;color:var(--ink2);font-size:13.5px}
ol.works li{margin:6px 0;line-height:1.45}
ol.works .yr{font-family:var(--mono);font-size:11px;color:var(--faint);margin-right:6px}
.why{margin-top:14px;padding:11px 13px;border:1px solid var(--line2);border-radius:9px;
  background:rgba(255,255,255,.02);color:var(--muted);font-size:13px;line-height:1.5}
/* the actions that turn "awaiting your browser" from an instruction into something to click */
.acts{margin-top:12px;display:flex;flex-wrap:wrap;gap:9px;align-items:center}
.act{display:inline-block;font-family:var(--mono);font-size:11.5px;letter-spacing:.02em;
  color:var(--accent);background:transparent;border:1px solid var(--accent);border-radius:8px;
  padding:7px 13px;cursor:pointer;text-decoration:none;line-height:1.2}
.act:hover{background:var(--accent);color:#0a0d14}
.acts .note{flex-basis:100%;margin-top:4px}
.close{position:absolute;top:16px;right:18px;background:transparent;border:1px solid var(--line2);
  color:var(--muted);border-radius:8px;padding:5px 10px;cursor:pointer;font-family:var(--mono);font-size:11px}
.close:hover{border-color:var(--accent);color:var(--accent)}
.field{padding:13px 0;border-bottom:1px solid var(--line)}
.field .k{font-family:var(--mono);font-size:10.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--faint)}
.field .v{margin-top:4px;color:var(--ink2)}
.field blockquote{margin:6px 0 0;padding-left:10px;border-left:2px solid var(--line2);color:var(--muted);font-size:13px}
/* ── diagram engine (cells + filaments) ── */
.stage{position:relative;width:100%;min-width:760px;aspect-ratio:1040/560;
  border:1px solid var(--line);border-radius:14px;overflow:hidden;
  background:radial-gradient(120% 140% at 50% 0%, var(--panel-a), var(--panel-b));
  box-shadow:0 40px 90px -50px rgba(0,0,0,.9), inset 0 1px 0 rgba(127,214,224,.04)}
.stagewrap{overflow-x:auto}
.om-overlay{position:absolute;inset:0;z-index:0;pointer-events:none}
.om-flt{animation:omFlow 1.5s linear infinite}
.cell{position:absolute;transform:translate(-50%,-50%);width:132px;display:flex;flex-direction:column;
  align-items:center;gap:7px;background:transparent;border:0;cursor:pointer;z-index:1;transition:.18s}
.cell:hover,.cell:focus{transform:translate(-50%,-50%) scale(1.08);z-index:6;outline:none}
.circle{position:relative;display:grid;place-items:center}
.halo{position:absolute;border-radius:50%;animation:omHalo 6s ease-in-out infinite}
.membrane{border-radius:50%;animation:omBreathe 6s ease-in-out infinite}
.nucleus{position:absolute;width:8px;height:8px;border-radius:50%}
.clabel{font-family:var(--sans);font-weight:600;font-size:12.5px;color:#eef1f6;text-align:center;max-width:132px}
.ctag{font-family:var(--mono);font-size:8.5px;letter-spacing:.18em}
.dcap{font-family:var(--mono);font-size:11px;color:var(--faint);padding:10px 4px 0}
@keyframes omBreathe{0%,100%{transform:scale(1)}50%{transform:scale(1.055)}}
@keyframes omHalo{0%,100%{opacity:.4;transform:scale(1)}50%{opacity:.82;transform:scale(1.16)}}
@keyframes omFlow{to{stroke-dashoffset:-24.2}}
@keyframes omScan{0%{transform:translateY(-120px)}100%{transform:translateY(110vh)}}
@keyframes omDrawerIn{from{opacity:0;transform:translateX(30px)}to{opacity:1;transform:translateX(0)}}
:focus-visible{outline:2px solid var(--focus);outline-offset:2px}
@media (prefers-reduced-motion:reduce){
  *{animation:none!important;transition:none!important}
  .cell:hover,.cell:focus{transform:translate(-50%,-50%)}
}
"""

_JS = r"""
const stateLabel = {searched_absent:"— we looked, found nothing",
  never_attempted:"· not checked yet", blocked:"⏳ awaiting your browser"};
const FIRM_CONF = {quoted_official:1, derived:1};   // only these read as firm (D-061)
const KIND = {tool:"#43c9d6", verified:"#79d06a", human:"#f0839a", core:"#e8b24a",
  rule:"#b58cf0", skip:"#7d828e"};
function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,c=>(
  {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));}
function safeUrl(u){return (typeof u==="string" && /^https?:\/\//i.test(u.trim())) ? u : null;}
function srcLink(u){var s=safeUrl(u);
  if(s) return ' <a class="src" href="'+esc(s)+'" target="_blank" rel="noopener">source ↗</a>';
  return u ? ' <span class="src" title="non-web source">source (non-web)</span>' : '';}
function dateKey(v){var t=Date.parse(v);return isNaN(t)?Infinity:t;}
function dateFields(){return DATA.fields.filter(function(f){return f.datatype==="date";});}
function isFirm(env){return !!(env && FIRM_CONF[env.confidence]);}
function isWatch(env){return !isFirm(env);}
function idBadge(p){
  // named-target identity honesty label (D-010): verified needs no badge — a badge marks
  // the two states where the OpenAlex match was NOT confirmed against an affiliation.
  var r=p.identity_resolution;
  if(r==="unverified") return ' <span class="badge watch" title="affiliation given but no OpenAlex hit matched it">identity unverified</span>';
  if(r==="unchecked") return ' <span class="badge watch" title="no affiliation given — identity not checked">identity unchecked</span>';
  return '';
}
function cell(env){
  if(!env) return '<span class="s-never_attempted">'+stateLabel.never_attempted+'</span>';
  if(env.state==="value") return '<span class="s-value">'+esc(env.value)+'</span>'+srcLink(env.source_url);
  return '<span class="s-'+env.state+'">'+(stateLabel[env.state]||env.state)+'</span>';
}
/* ── MI-4/MI-5: filter by supervision level ────────────────────────────────────
   The vocabulary is the fixed enum shared with extract/llm_claims.SUPERVISION_LEVELS and
   cli.PLAN_INTENT_KINDS — "I want a PhD supervisor" and "this person takes PhD students"
   were deliberately designed to be the same seven words, so no translation layer exists
   here and none may be added. A page saying "research assistant" maps to a level because a
   model read the sentence (P5/MI-3), never because a synonym table shipped (D-038). */
const LEVELS = ["training","pre_master","pre_phd","mentor","master","phd","postdoc"];
const LEVEL_LABEL = {training:"training", pre_master:"pre-master's", pre_phd:"pre-PhD",
  mentor:"mentor", master:"master's", phd:"PhD", postdoc:"postdoc", unknown:"unknown"};
const UNKNOWN = "unknown";
var levelSel = null;             // Set of ticked chips; built on first render

function levelsOf(p){
  /* MI-5.1: no `supervises` claim means UNKNOWN, never "no". We did not find a statement;
     that is not the same as the person not taking students at that level. Any non-`value`
     state — searched_absent, blocked, never_attempted — is equally unknown here. */
  var env = p.fields && p.fields.supervises;
  if(!env || env.state !== "value" || !env.value) return [];
  return String(env.value).split(",").map(function(s){return s.trim().toLowerCase();})
    .filter(function(s){return LEVELS.indexOf(s) >= 0;});
}
function levelCounts(){
  var c = {unknown:0};
  LEVELS.forEach(function(l){c[l]=0;});
  DATA.professors.forEach(function(p){
    var ls = levelsOf(p);
    if(!ls.length){ c.unknown++; return; }
    ls.forEach(function(l){c[l]++;});      // a professor stating two levels counts in both
  });
  return c;
}
function chipKeys(counts){
  /* Every level anyone actually states, plus every level the STUDENT asked for (so their own
     choice is always visible and untickable even when nothing matched it yet), plus unknown
     — which is always offered, because before P5 ships it is the only truthful answer for
     everyone and a filter with no way back to "show me everything" is a trap. */
  var want = (DATA.run && DATA.run.intents) || [];
  return LEVELS.filter(function(l){return counts[l] > 0 || want.indexOf(l) >= 0;})
    .concat([UNKNOWN]);
}
function initLevelSel(){
  if(levelSel) return;
  var want = (DATA.run && DATA.run.intents) || [];
  /* MI-4.2 + MI-5.2: pre-tick what the student asked for — AND unknown, always. A student
     filtering to "phd" must not silently lose the professors we simply have no statement
     about, which today is nearly all of them. */
  levelSel = new Set(want.filter(function(l){return LEVELS.indexOf(l) >= 0;}));
  levelSel.add(UNKNOWN);
  if(levelSel.size === 1){
    // no usable intents came through: default to everything rather than to unknown alone,
    // which would look like a broken filter hiding real rows.
    LEVELS.forEach(function(l){levelSel.add(l);});
  }
}
function matchesLevel(p){
  initLevelSel();
  var ls = levelsOf(p);
  if(!ls.length) return levelSel.has(UNKNOWN);
  return ls.some(function(l){return levelSel.has(l);});
}
function renderChips(){
  initLevelSel();
  var counts = levelCounts(), keys = chipKeys(counts);
  var el = document.getElementById("levels");
  if(!el) return;
  // One real level plus unknown means nothing has been stated by anyone — say so instead of
  // rendering a filter that appears to do nothing.
  var stated = keys.filter(function(k){return k !== UNKNOWN && counts[k] > 0;}).length;
  el.innerHTML =
    '<span class="lvl-lead">Supervises</span>' +
    keys.map(function(k){
      return '<button class="chip'+(levelSel.has(k)?" on":"")+'" data-level="'+esc(k)+'" '+
        'aria-pressed="'+(levelSel.has(k)?"true":"false")+'">'+
        esc(LEVEL_LABEL[k]||k)+' <span class="chip-n">'+counts[k]+'</span></button>';
    }).join("") +
    (stated ? "" : '<span class="lvl-note">No professor has stated a level yet — every row '+
      'is “unknown”, which is why that is the only chip with a count.</span>');
}
function filtered(){
  var q=(document.getElementById("q").value||"").toLowerCase();
  // The two filters COMPOSE (MI-4.5): text narrows, level narrows, neither resets the other.
  return DATA.professors.filter(function(p){
    if(!matchesLevel(p)) return false;
    if(!q) return true;
    return (p.name||"").toLowerCase().indexOf(q)>=0 ||
      Object.values(p.fields).some(function(e){return e && e.state==="value" &&
        String(e.value||"").toLowerCase().indexOf(q)>=0;});
  });
}
function emptyStateMessage(){
  /* MI-5.3: say WHICH empty this is. "No results" over a hidden pile of unknowns is the
     failure mode this whole section exists to prevent. */
  initLevelSel();
  var counts = levelCounts();
  var picked = LEVELS.filter(function(l){return levelSel.has(l);});
  if(!levelSel.has(UNKNOWN) && counts.unknown > 0){
    return "No professor is confirmed to supervise at " +
      (picked.length ? "this level" : "any ticked level") + ". " + counts.unknown +
      " have no statement either way — tick “unknown” to see them.";
  }
  return "No professors to show — " + ((DATA.run && DATA.run.coverage) ||
    "this search returned nothing.");
}
function renderTable(){
  var profs=filtered();
  var cols=DATA.fields.filter(function(f){return f.kind!=="score-input";});
  var html='<div class="tblwrap"><table><thead><tr><th>Professor</th>'+
    cols.map(function(f){return '<th>'+esc(f.label)+'</th>';}).join('')+'</tr></thead><tbody>';
  profs.forEach(function(p){
    html+='<tr class="row" tabindex="0" role="button" data-id="'+esc(p.id)+'">'+
      '<td class="name">'+esc(p.name||p.id)+idBadge(p)+'</td>'+
      cols.map(function(f){return '<td>'+cell(p.fields[f.id])+'</td>';}).join('')+'</tr>';
  });
  html+='</tbody></table></div>';
  document.getElementById("grid").innerHTML= profs.length ? html :
    '<div class="empty">'+(DATA.professors.length? esc(emptyStateMessage())
      : 'No professors to show — '+esc((DATA.run&&DATA.run.coverage)||'this search returned nothing.'))+'</div>';
}
function renderDeadlines(){
  var dfs=dateFields(), rows=[];
  filtered().forEach(function(p){dfs.forEach(function(f){var e=p.fields[f.id];
    if(e&&e.state==="value"&&e.value) rows.push({p:p,f:f,env:e,when:String(e.value)});});});
  rows.sort(function(a,b){return dateKey(a.when) - dateKey(b.when);});   // soonest first
  var host=document.getElementById("deadlines");
  if(!dfs.length||!rows.length){host.innerHTML='<div class="empty">No deadline-shaped data was collected.</div>';return;}
  host.innerHTML='<div class="dl-list">'+rows.map(function(r){
    var badge=isFirm(r.env)?'<span class="badge firm">firm</span>':'<span class="badge watch">watch · projected</span>';
    return '<div class="dl-card" tabindex="0" role="button" data-id="'+esc(r.p.id)+'">'+
      '<span class="dl-date">'+esc(r.when)+'</span><span class="name">'+esc(r.p.name||r.p.id)+'</span>'+
      '<span class="count">'+esc(r.f.label)+'</span>'+badge+'</div>';}).join('')+'</div>'+
    '<div class="note">Watch dates are projected from past cycles — not published deadlines. Always confirm on the official page.</div>';
}
function num(n){ return (typeof n==="number"&&isFinite(n)) ? n.toLocaleString() : "—"; }

/* Why a row can be blocked, in the student's words. The dashboard used to say only
   "awaiting your browser", which reads as "your turn" even when the tool never found a page
   to hand over. page_url_kind is what makes the difference sayable (D-037). */
function whyBlocked(pr){
  if(!pr) return "";
  if(!pr.page_url) return "No personal page was found for this professor in any public registry, so there was nothing to read. A search by name in your own browser is the next step.";
  if(pr.page_url_kind==="orcid") return "The only page on record is an ORCID profile, which loads its content with JavaScript — the reader cannot see it, and the registry lists no other page. Opening it yourself works.";
  return "The page we found refused an automated reader, or returned nothing usable. Opening it in your own browser is the next step.";
}

/* The registry facts the scan already collected. Kept visually and structurally apart from
   the evidence fields below it: this block never carries a quote because it is not a claim
   about recruiting, and presenting it as one would defeat the point of the quote gate. */
function profileHtml(p){
  var pr=p.profile; if(!pr) return "";
  var chips=[];
  if(pr.works_count)     chips.push('<span class="stat"><b>'+num(pr.works_count)+'</b> works</span>');
  if(pr.cited_by_count)  chips.push('<span class="stat"><b>'+num(pr.cited_by_count)+'</b> citations</span>');
  if(pr.topics_total)    chips.push('<span class="stat"><b>'+num(pr.topics_total)+'</b> topics</span>');
  if(pr.topic_overlap)   chips.push('<span class="stat match"><b>'+num(pr.topic_overlap)+'</b> matching yours</span>');
  var links=[];
  if(pr.orcid)        links.push('<a href="'+esc(pr.orcid)+'" target="_blank" rel="noopener noreferrer">ORCID ↗</a>');
  if(pr.openalex_id)  links.push('<a href="'+esc(pr.openalex_id)+'" target="_blank" rel="noopener noreferrer">OpenAlex ↗</a>');
  if(pr.page_url)     links.push('<a href="'+esc(pr.page_url)+'" target="_blank" rel="noopener noreferrer">Their page ↗</a>');
  /* An empty publication list next to "4 works" reads as a bug unless the page says which
     it is. Three honest cases, never a silent gap. */
  var works="";
  if(pr.recent_works&&pr.recent_works.length){
    works='<div class="sect"><div class="sect-h">Recent publications</div><ol class="works">'+
      pr.recent_works.map(function(w){
        return '<li><span class="yr">'+esc(w.year||"—")+'</span> '+esc(w.title||"")+'</li>';
      }).join('')+'</ol><div class="note">From OpenAlex, newest first — an activity and recency signal, not a full bibliography.</div></div>';
  } else if(pr.works_checked){
    works='<div class="sect"><div class="sect-h">Recent publications</div>'+
      '<div class="note">We asked OpenAlex and it returned no indexed works for this person — '+
      'the count above comes from their author record, which can be ahead of the index.</div></div>';
  } else if(pr.works_count){
    works='<div class="sect"><div class="sect-h">Recent publications</div>'+
      '<div class="note">Not looked up — publications are fetched only for the professors in '+
      'the deep-dive shortlist, and this one was outside it. The '+num(pr.works_count)+
      ' above is from their author record.</div></div>';
  }
  return '<div class="sect">'+
      (pr.institutions&&pr.institutions.length?'<div class="inst">'+esc(pr.institutions.join(" · "))+'</div>':'')+
      (chips.length?'<div class="stats">'+chips.join('')+'</div>':'')+
      (links.length?'<div class="links">'+links.join('')+'</div>':'')+
      '<div class="note">Registry facts from OpenAlex/ROR — not quote-verified evidence; the fields below are.</div>'+
    '</div>'+works;
}

/* "Awaiting your browser" used to be an instruction with nothing to click — a terminal state
   that is a dead end, which is exactly what D-070 says must never happen. These are the three
   things a person can actually do, best lead first.

   All three run in the STUDENT's browser and their own session. That is the human rung as
   designed (D-043/D-044): a person reading a page they can already reach is a different act
   from a datacentre rendering it at scale, and nothing here asks the tool to defeat anything. */
function searchUrl(p){
  var bits=[p.name||""];
  var inst=(p.profile&&p.profile.institutions)||[];
  if(inst.length) bits.push(inst[0]);
  return "https://duckduckgo.com/?q="+encodeURIComponent(bits.join(" ")+" faculty page");
}
function actionsHtml(p){
  var pr=p.profile||{}, b=[];
  if(pr.page_url)
    b.push('<a class="act" href="'+esc(pr.page_url)+'" target="_blank" rel="noopener noreferrer">Open the page we found ↗</a>');
  b.push('<a class="act" href="'+esc(searchUrl(p))+'" target="_blank" rel="noopener noreferrer">Search for their page ↗</a>');
  if(pr.human_prompt)
    b.push('<button type="button" class="act" data-prompt="'+esc(p.id)+'">Copy research prompt</button>');
  return '<div class="acts">'+b.join('')+
    '<div class="note">The prompt is ready to paste into Claude for Chrome (or any assistant you '+
    'use). It asks for a verbatim quote and a source URL per field, and says plainly that '+
    '“found nothing” is a valid answer — so what comes back can be checked, not just believed.</div></div>';
}
function copyPrompt(id){
  var p=DATA.professors.find(function(x){return x.id===id;});
  if(!p||!p.profile||!p.profile.human_prompt) return;
  var txt=p.profile.human_prompt;
  var done=function(){ var el=document.querySelector('[data-prompt="'+id+'"]');
    if(el){ var o=el.textContent; el.textContent="Copied ✓"; setTimeout(function(){el.textContent=o;},1600);} };
  if(navigator.clipboard&&navigator.clipboard.writeText){
    navigator.clipboard.writeText(txt).then(done,function(){fallbackCopyText(txt);done();});
  } else { fallbackCopyText(txt); done(); }
}
/* Clipboard API needs a secure context and a permission the file:// dashboard may not have —
   a downloaded dashboard opened from disk is a normal way to read this, so it must still work. */
function fallbackCopyText(txt){
  var ta=document.createElement("textarea");
  ta.value=txt; ta.setAttribute("readonly",""); ta.style.position="fixed"; ta.style.left="-9999px";
  document.body.appendChild(ta); ta.select();
  try{ document.execCommand("copy"); }catch(e){}
  document.body.removeChild(ta);
}

function openDetail(id){
  var p=DATA.professors.find(function(x){return x.id===id;}); if(!p) return;
  var anyBlocked=false;
  var body=DATA.fields.map(function(f){
    var env=p.fields[f.id]||{state:"never_attempted"}, v;
    if(env.state==="value"){
      v='<div class="v s-value">'+esc(env.value)+'</div>'+
        (env.quote?'<blockquote>“'+esc(env.quote)+'”</blockquote>':'')+srcLink(env.source_url)+
        (env.confidence?' <span class="count">'+esc(env.confidence)+(isWatch(env)?' · watch':'')+'</span>':'');
    } else {
      if(env.state==="blocked") anyBlocked=true;
      v='<div class="v s-'+env.state+'">'+(stateLabel[env.state]||env.state)+'</div>';
    }
    return '<div class="field"><div class="k">'+esc(f.label)+'</div>'+v+'</div>';
  }).join('');
  var why=anyBlocked?'<div class="why">'+esc(whyBlocked(p.profile))+'</div>'+actionsHtml(p):'';
  document.getElementById("panel").innerHTML=
    '<div class="overlay" id="overlay"></div>'+
    '<div class="modal" role="dialog" aria-modal="true" aria-label="Professor detail">'+
      '<button class="close" id="closeDetail">ESC ✕</button>'+
      '<div class="eyebrow">Professor</div>'+
      '<h2>'+esc(p.name||p.id)+idBadge(p)+'</h2><div class="meta">'+esc(p.id)+'</div>'+
      profileHtml(p)+
      '<div class="sect"><div class="sect-h">What the scan verified</div>'+body+why+'</div>'+
    '</div>';
  document.getElementById("panel").classList.remove("hidden");
  document.getElementById("closeDetail").onclick=closeDetail;
  document.getElementById("overlay").onclick=closeDetail;
  var cp=document.querySelector('[data-prompt]');
  if(cp) cp.onclick=function(){copyPrompt(cp.getAttribute("data-prompt"));};
  document.getElementById("closeDetail").focus();
}
function closeDetail(){var pn=document.getElementById("panel");pn.classList.add("hidden");pn.innerHTML="";}

/* ── the diagram engine: glowing cells + curved animated filaments ── */
var SPEC={ title:"How Supervisorly works — plan → discover → verify → rank → dashboard",
  caption:"GOVERNS · public-source ladder · quote-verified claims · browser tier (your session) for the walled, MD rung as fallback",
  nodes:[
    ["plan","Search plan","core",11,50],["discover","Discover (ROR + OpenAlex)","tool",30,26],
    ["fetch","Fetch public pages","tool",30,74],["verify","Verify quote in snapshot","verified",53,50],
    ["browser","Browser tier (your session)","human",53,80],["human","MD human rung (fallback)","human",74,90],
    ["score","Score & rank","rule",74,30],
    ["dash","Dashboard","core",91,55]],
  edges:[["plan","discover","intent"],["discover","fetch","targets"],["fetch","verify","snapshot"],
    ["verify","score","claims"],["score","dash","ranked"],["fetch","browser","robots/login wall"],
    ["browser","verify","ingest-page snapshot"],["browser","human","on challenge"],
    ["human","verify","pasted MD"]] };
function diam(kind){return kind==="core"?76:(kind==="skip"?52:62);}
function drawDiagram(){
  var stage=document.getElementById("stage"); if(!stage) return;
  var W=stage.clientWidth, H=stage.clientHeight;
  var pos={}; SPEC.nodes.forEach(function(n){pos[n[0]]={x:n[3]/100*W,y:n[4]/100*H,r:diam(n[2])/2};});
  var svg='<svg class="om-overlay" viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="none">';
  SPEC.edges.forEach(function(e){
    var a=pos[e[0]], b=pos[e[1]], col=KIND[nodeKind(e[0])];
    var dx=b.x-a.x, dy=b.y-a.y, d=Math.hypot(dx,dy)||1, ux=dx/d, uy=dy/d;
    var x0=a.x+ux*(a.r+4), y0=a.y+uy*(a.r+4), x3=b.x-ux*(b.r+7), y3=b.y-uy*(b.r+7);
    var off=Math.max(16,Math.min(64,d*0.16)) * ((hash(e[0]+e[1])%2)?1:-1);
    var px=-uy*off, py=ux*off;
    var c1x=x0+(x3-x0)*.32+px, c1y=y0+(y3-y0)*.32+py, c2x=x0+(x3-x0)*.68+px, c2y=y0+(y3-y0)*.68+py;
    var path='M'+x0+' '+y0+' C'+c1x+' '+c1y+' '+c2x+' '+c2y+' '+x3+' '+y3;
    svg+='<g data-edge="'+e[0]+'|'+e[1]+'">'+
      '<path d="'+path+'" fill="none" stroke="'+col+'" stroke-width="8" opacity=".11" stroke-linecap="round"/>'+
      '<path d="'+path+'" fill="none" stroke="'+col+'" stroke-width="1.3" opacity=".42"/>'+
      '<path class="om-flt" d="'+path+'" fill="none" stroke="'+col+'" stroke-width="2.4" opacity=".92" stroke-dasharray="0.1 12"/>'+
      arrow(x3,y3,c2x,c2y,col)+'</g>';
  });
  svg+='</svg>';
  var cells=SPEC.nodes.map(function(n){
    var col=KIND[n[2]], dd=diam(n[2]);
    return '<button class="cell" tabindex="0" data-node="'+n[0]+'" style="left:'+n[3]+'%;top:'+n[4]+'%">'+
      '<span class="circle" style="width:'+dd+'px;height:'+dd+'px">'+
        '<span class="halo" style="width:'+(dd*1.85)+'px;height:'+(dd*1.85)+'px;background:radial-gradient(circle,'+rgba(col,.34)+',transparent 66%)"></span>'+
        '<span class="membrane" style="width:'+dd+'px;height:'+dd+'px;background:radial-gradient(circle at 38% 30%,'+rgba(col,.62)+','+rgba(col,.1)+' 74%);border:1.6px solid '+rgba(col,.88)+';box-shadow:0 0 20px '+rgba(col,.5)+',inset 0 0 16px '+rgba(col,.2)+'"></span>'+
        '<span class="nucleus" style="background:'+rgba(col,.95)+';box-shadow:0 0 10px '+col+'"></span>'+
      '</span><span class="clabel">'+esc(n[1])+'</span>'+
      '<span class="ctag" style="color:'+col+'">'+n[2].toUpperCase()+'</span></button>';
  }).join('');
  stage.innerHTML=svg+cells;
  stage.querySelectorAll(".cell").forEach(function(c){
    c.addEventListener("mouseenter",function(){hl(c.getAttribute("data-node"));});
    c.addEventListener("focus",function(){hl(c.getAttribute("data-node"));});
    c.addEventListener("mouseleave",clearHl); c.addEventListener("blur",clearHl);
  });
}
function nodeKind(id){var n=SPEC.nodes.find(function(x){return x[0]===id;});return n?n[2]:"core";}
function rgba(hex,a){var n=parseInt(hex.slice(1),16);return 'rgba('+((n>>16)&255)+','+((n>>8)&255)+','+(n&255)+','+a+')';}
function hash(s){var h=0;for(var i=0;i<s.length;i++)h=(h*31+s.charCodeAt(i))>>>0;return h;}
function arrow(x,y,cx,cy,col){var a=Math.atan2(y-cy,x-cx),s=6;
  return '<polygon points="'+x+','+y+' '+(x-s*Math.cos(a-0.5))+','+(y-s*Math.sin(a-0.5))+' '+(x-s*Math.cos(a+0.5))+','+(y-s*Math.sin(a+0.5))+'" fill="'+col+'"/>';}
function hl(id){
  var adj={}; SPEC.edges.forEach(function(e){if(e[0]===id)adj[e[1]]=1;if(e[1]===id)adj[e[0]]=1;});
  document.querySelectorAll("#stage .cell").forEach(function(c){var k=c.getAttribute("data-node");
    var on=(k===id||adj[k]); c.style.opacity=on?"1":".2"; c.style.filter=on?"":"saturate(.55)";});
  document.querySelectorAll("#stage g[data-edge]").forEach(function(g){var e=g.getAttribute("data-edge").split("|");
    g.style.opacity=(e[0]===id||e[1]===id)?"1":".07";});
}
function clearHl(){
  document.querySelectorAll("#stage .cell").forEach(function(c){c.style.opacity="";c.style.filter="";});
  document.querySelectorAll("#stage g[data-edge]").forEach(function(g){g.style.opacity="";});
}
function renderLedger(){
  // CC-1. The honesty rule this panel exists for: a phase that reached NOTHING still
  // gets a row, with its reason. Rendering only the phases that found something would
  // reproduce exactly the silence the ledger was built to end.
  var rows=(DATA.run&&DATA.run.ledger)||[];
  var el=document.getElementById("ledger");
  if(!el) return;
  if(!rows.length){
    // Distinguish "no phase recorded anything" from "phases ran and found nothing" —
    // the four-state honesty rule applied to the ledger itself.
    el.innerHTML='<h2>What each phase did</h2><div class="note">No phase recorded a '+
      'ledger row for this run. That means the phases did not report, not that they '+
      'found nothing.</div>';
    return;
  }
  var html='<h2>What each phase did</h2><div class="tblwrap"><table><thead><tr>'+
    '<th>Phase</th><th>Attempted</th><th>Reached</th><th>Skipped</th><th>Why</th>'+
    '<th>Time</th></tr></thead><tbody>';
  rows.forEach(function(r){
    var reached=Number(r.reached||0), skipped=Number(r.skipped||0);
    html+='<tr>'+
      '<td class="lg-phase">'+esc(r.phase)+'</td>'+
      '<td class="lg-num">'+esc(Number(r.attempted||0))+'</td>'+
      '<td class="lg-num'+(reached?'':' lg-zero')+'">'+esc(reached)+'</td>'+
      '<td class="lg-num'+(skipped?' lg-skip':'')+'">'+esc(skipped)+'</td>'+
      '<td class="lg-reason">'+esc(r.reason||(skipped?'':'—'))+'</td>'+
      '<td class="lg-num">'+esc((Number(r.seconds||0)).toFixed(1))+'s'+
        (Number(r.tokens||0)?' · '+esc(r.tokens)+' tok':'')+'</td>'+
      '</tr>';
  });
  el.innerHTML=html+'</tbody></table></div>';
}
function setView(v){
  document.getElementById("grid").classList.toggle("hidden",v!=="table");
  document.getElementById("deadlines").classList.toggle("hidden",v!=="deadlines");
  document.getElementById("how").classList.toggle("hidden",v!=="how");
  [["vTable","table"],["vDeadlines","deadlines"],["vHow","how"]].forEach(function(p){
    document.getElementById(p[0]).classList.toggle("on",v===p[1]);});
  if(v==="how") drawDiagram();
}
function render(){renderChips();renderTable();renderDeadlines();renderLedger();
  document.getElementById("count").textContent=filtered().length+" / "+DATA.professors.length+" professors";}
function onLevelChip(e){
  var b = e.target.closest("[data-level]");
  if(!b) return;
  initLevelSel();
  var k = b.getAttribute("data-level");
  // Untickable to zero on purpose: "nothing selected" is a state the student chose, and the
  // empty message explains it. Silently re-ticking would override their instruction.
  if(levelSel.has(k)) levelSel.delete(k); else levelSel.add(k);
  render();
}
function onId(e,keyb){var el=e.target.closest("[data-id]");
  if(el&&(!keyb||e.key==="Enter"||e.key===" ")){if(keyb)e.preventDefault();openDetail(el.getAttribute("data-id"));}}
document.addEventListener("DOMContentLoaded",function(){
  document.getElementById("q").addEventListener("input",render);
  document.getElementById("levels").addEventListener("click",onLevelChip);
  document.getElementById("vTable").addEventListener("click",function(){setView("table");});
  document.getElementById("vDeadlines").addEventListener("click",function(){setView("deadlines");});
  document.getElementById("vHow").addEventListener("click",function(){setView("how");});
  document.body.addEventListener("click",function(e){onId(e,false);});
  document.body.addEventListener("keydown",function(e){if(e.key==="Escape")return closeDetail();onId(e,true);});
  window.addEventListener("resize",function(){if(!document.getElementById("how").classList.contains("hidden"))drawDiagram();});
  render(); setView("table");
});
"""


def _inline_json(obj: dict) -> str:
    """JSON for a <script> block, with every HTML-significant sequence neutralised: escape
    every '<' (so '</script>'/'<!--'/'<script' in a value can't break out) and the JS line
    separators U+2028/U+2029."""
    import json as _json
    return (_json.dumps(obj, ensure_ascii=False)
            .replace("<", "\\u003c")
            .replace(" ", "\\u2028")
            .replace(" ", "\\u2029"))


def build_dashboard(export_obj: dict) -> str:
    """Return a complete, self-contained HTML document rendering ``export_obj`` (Atlas language)."""
    # Inline the data safely: escape EVERY '<' (so no '</script>', '<!--' or '<script' in a value
    # can terminate/confuse the <script> block) plus the JS line separators U+2028/U+2029.
    data = _inline_json(export_obj)
    run = export_obj.get("run", {})
    meta = (f"run {run.get('run_id', '?')} · {run.get('status', '?')} · "
            f"generated {export_obj.get('generated_at', '?')}")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Supervisorly — results</title>
<style>{_CSS}</style></head>
<body>
<div class="scan" aria-hidden="true"></div>
<header>
  <div class="eyebrow">Supervisorly · Xeno-Atlas · Field record</div>
  <h1>A living map of your supervisor search.</h1>
  <div class="meta">{meta}</div>
</header>
<div class="controls">
  <input id="q" placeholder="filter by name or any value…">
  <button id="vTable" class="vbtn on">Table</button>
  <button id="vDeadlines" class="vbtn">Deadlines</button>
  <button id="vHow" class="vbtn">How it works</button>
  <span class="count" id="count"></span>
</div>
<div class="levels" id="levels"></div>
<div class="wrap">
  <div id="grid"></div>
  <div id="deadlines" class="hidden"></div>
  <div id="how" class="hidden">
    <div class="stagewrap"><div class="stage" id="stage"></div></div>
    <div class="dcap">GOVERNS · public-source ladder · quote-verified claims · browser tier (your session) for the walled, MD rung as fallback</div>
    <div id="ledger" class="ledger"></div>
  </div>
</div>
<div id="panel" class="hidden"></div>
<script>const DATA = {data};</script>
<script>{_JS}</script>
</body></html>
"""
