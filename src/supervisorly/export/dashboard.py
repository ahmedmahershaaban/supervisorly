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
/* cell drawer */
.overlay{position:fixed;inset:0;background:rgba(3,5,9,.62);backdrop-filter:blur(3px);z-index:50}
aside.detail{position:fixed;top:0;right:0;height:100%;width:min(452px,94vw);z-index:51;
  background:var(--drawer);border-left:1px solid var(--line2);padding:22px 24px;overflow-y:auto;
  box-shadow:-40px 0 90px -40px rgba(0,0,0,.9);animation:omDrawerIn .24s cubic-bezier(.2,.7,.2,1)}
aside.detail h2{margin:.2em 0 .1em;font-size:24px;letter-spacing:-.01em}
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
function filtered(){
  var q=(document.getElementById("q").value||"").toLowerCase();
  return DATA.professors.filter(function(p){
    if(!q) return true;
    return (p.name||"").toLowerCase().indexOf(q)>=0 ||
      Object.values(p.fields).some(function(e){return e && e.state==="value" &&
        String(e.value||"").toLowerCase().indexOf(q)>=0;});
  });
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
    '<div class="empty">'+(DATA.professors.length? 'No professors match. Try clearing the filter.'
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
function openDetail(id){
  var p=DATA.professors.find(function(x){return x.id===id;}); if(!p) return;
  var body=DATA.fields.map(function(f){
    var env=p.fields[f.id]||{state:"never_attempted"}, v;
    if(env.state==="value"){
      v='<div class="v s-value">'+esc(env.value)+'</div>'+
        (env.quote?'<blockquote>“'+esc(env.quote)+'”</blockquote>':'')+srcLink(env.source_url)+
        (env.confidence?' <span class="count">'+esc(env.confidence)+(isWatch(env)?' · watch':'')+'</span>':'');
    } else { v='<div class="v s-'+env.state+'">'+(stateLabel[env.state]||env.state)+'</div>'; }
    return '<div class="field"><div class="k">'+esc(f.label)+'</div>'+v+'</div>';
  }).join('');
  document.getElementById("panel").innerHTML=
    '<div class="overlay" id="overlay"></div><aside class="detail"><button class="close" id="closeDetail">ESC ✕</button>'+
    '<div class="eyebrow">Cell detail</div><h2>'+esc(p.name||p.id)+idBadge(p)+'</h2><div class="meta">'+esc(p.id)+'</div>'+body+'</aside>';
  document.getElementById("panel").classList.remove("hidden");
  document.getElementById("closeDetail").onclick=closeDetail;
  document.getElementById("overlay").onclick=closeDetail;
}
function closeDetail(){var pn=document.getElementById("panel");pn.classList.add("hidden");pn.innerHTML="";}

/* ── the diagram engine: glowing cells + curved animated filaments ── */
var SPEC={ title:"How Supervisorly works — plan → discover → verify → rank → dashboard",
  caption:"GOVERNS · public-source ladder · quote-verified claims · human rung for the walled",
  nodes:[
    ["plan","Search plan","core",11,50],["discover","Discover (ROR + OpenAlex)","tool",30,26],
    ["fetch","Fetch public pages","tool",30,74],["verify","Verify quote in snapshot","verified",53,50],
    ["human","Human rung (walled)","human",53,90],["score","Score & rank","rule",74,30],
    ["dash","Dashboard","core",91,55]],
  edges:[["plan","discover","intent"],["discover","fetch","targets"],["fetch","verify","snapshot"],
    ["verify","score","claims"],["score","dash","ranked"],["fetch","human","robots/login wall"],
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
function setView(v){
  document.getElementById("grid").classList.toggle("hidden",v!=="table");
  document.getElementById("deadlines").classList.toggle("hidden",v!=="deadlines");
  document.getElementById("how").classList.toggle("hidden",v!=="how");
  [["vTable","table"],["vDeadlines","deadlines"],["vHow","how"]].forEach(function(p){
    document.getElementById(p[0]).classList.toggle("on",v===p[1]);});
  if(v==="how") drawDiagram();
}
function render(){renderTable();renderDeadlines();
  document.getElementById("count").textContent=filtered().length+" / "+DATA.professors.length+" professors";}
function onId(e,keyb){var el=e.target.closest("[data-id]");
  if(el&&(!keyb||e.key==="Enter"||e.key===" ")){if(keyb)e.preventDefault();openDetail(el.getAttribute("data-id"));}}
document.addEventListener("DOMContentLoaded",function(){
  document.getElementById("q").addEventListener("input",render);
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
<div class="wrap">
  <div id="grid"></div>
  <div id="deadlines" class="hidden"></div>
  <div id="how" class="hidden">
    <div class="stagewrap"><div class="stage" id="stage"></div></div>
    <div class="dcap">GOVERNS · public-source ladder · quote-verified claims · human rung for the walled</div>
  </div>
</div>
<div id="panel" class="hidden"></div>
<script>const DATA = {data};</script>
<script>{_JS}</script>
</body></html>
"""
