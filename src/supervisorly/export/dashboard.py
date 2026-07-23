"""Build the single self-contained dashboard HTML (D-033, D-046).

One file, no CDN, offline: the export JSON is inlined and vanilla JS renders a generic,
filterable table whose columns come from the field descriptors (D-038). The four states
render distinctly — a blank field is never conflated with "we looked, found nothing"
(D-022, D-037).

Two views over the same data:

* **Table** — every professor, every field, filterable by name/value.
* **Deadlines** ("what closes soon", D-061) — professors with a date-typed field, sorted
  soonest-first. A *projected / not-yet-published* deadline (an envelope whose confidence
  is inferred/unconfirmed/action_needed) is shown as a **watch date**, visually distinct
  from a firm, officially-quoted one — never presented as firm.

Clicking a professor (row or deadline card — keyboard-accessible) opens a **detail panel**
showing every field with its state, value, verbatim quote, source link, and confidence, so
every displayed fact is traceable (D-010).

(React/JSX vendoring per D-048 is a later refinement; this vanilla-JS build already meets
the DoD — self-contained, offline, four-state, filterable, deadline-aware, clickable — and
is trivially testable.)
"""

from __future__ import annotations

import json

_CSS = """
:root{--bg:#0c0d10;--surface:#15161a;--line:#282a31;--ink:#e9eaed;--muted:#8a8d96;
--accent:#d9a441;--val:#dff2e7;--absent:#8a8d96;--never:#5a5d66;--blocked:#e8bf6a;
--firm:#7bd88f;--watch:#e8bf6a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font-family:ui-sans-serif,system-ui,Segoe UI,Roboto,sans-serif;font-size:14px}
header{padding:20px 24px;border-bottom:1px solid var(--line)}
h1{margin:0;font-size:20px;letter-spacing:-.02em}
.meta{color:var(--muted);font-family:ui-monospace,Consolas,monospace;font-size:12px;margin-top:6px}
.controls{padding:14px 24px;display:flex;gap:10px;flex-wrap:wrap;align-items:center;
border-bottom:1px solid var(--line)}
input,button{background:var(--surface);color:var(--ink);border:1px solid var(--line);
border-radius:8px;padding:7px 11px;font:inherit}
button{cursor:pointer}button:hover{border-color:var(--accent);color:var(--accent)}
button.on{border-color:var(--accent);color:var(--accent)}
.wrap{overflow-x:auto;padding:0 8px}
table{border-collapse:collapse;width:100%;min-width:640px}
th,td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);vertical-align:top}
th{position:sticky;top:0;background:var(--bg);color:var(--muted);font-weight:600;
font-family:ui-monospace,Consolas,monospace;font-size:11px;letter-spacing:.04em}
tr.row{cursor:pointer}tr.row:hover td{background:var(--surface)}
tr.row:focus{outline:2px solid var(--accent);outline-offset:-2px}
.name{font-weight:650}
.s-value{color:var(--val)}
.s-searched_absent{color:var(--absent);font-style:italic}
.s-never_attempted{color:var(--never)}
.s-blocked{color:var(--blocked)}
.src{color:var(--muted);text-decoration:none;font-size:11px;margin-left:6px}
.src:hover{color:var(--accent)}
.empty{padding:40px 24px;color:var(--muted)}
.hidden{display:none}
/* deadline view */
.dl-list{padding:8px 16px;display:flex;flex-direction:column;gap:8px}
.dl-card{display:flex;gap:14px;align-items:baseline;padding:12px 14px;background:var(--surface);
border:1px solid var(--line);border-radius:10px;cursor:pointer}
.dl-card:hover{border-color:var(--accent)}.dl-card:focus{outline:2px solid var(--accent)}
.dl-date{font-family:ui-monospace,Consolas,monospace;font-size:13px;min-width:120px}
.badge{font-size:11px;padding:2px 8px;border-radius:999px;border:1px solid var(--line);
font-family:ui-monospace,Consolas,monospace}
.badge.firm{color:var(--firm);border-color:var(--firm)}
.badge.watch{color:var(--watch);border-color:var(--watch)}
/* detail panel */
.overlay{position:fixed;inset:0;background:rgba(0,0,0,.5)}
aside.detail{position:fixed;top:0;right:0;height:100%;width:min(440px,92vw);background:var(--surface);
border-left:1px solid var(--line);padding:20px 22px;overflow-y:auto;box-shadow:-8px 0 24px rgba(0,0,0,.4)}
aside.detail h2{margin:0 0 4px;font-size:18px}
.close{position:absolute;top:14px;right:16px}
.field{padding:12px 0;border-bottom:1px solid var(--line)}
.field .k{color:var(--muted);font-family:ui-monospace,Consolas,monospace;font-size:11px;
letter-spacing:.04em;text-transform:uppercase}
.field .v{margin-top:3px}
.field blockquote{margin:6px 0 0;padding-left:10px;border-left:2px solid var(--line);
color:var(--muted);font-size:13px}
"""

_JS = r"""
const stateLabel = {searched_absent:"— we looked, found nothing",
  never_attempted:"· not checked yet", blocked:"⏳ awaiting your browser"};
const WATCH_CONF = {inferred:1, unconfirmed:1, action_needed:1};  // projected, not firm (D-061)
function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,c=>(
  {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));}
function dateFields(){return DATA.fields.filter(function(f){return f.datatype==="date";});}
function isWatch(env){return !!(env && WATCH_CONF[env.confidence]);}
function cell(env){
  if(!env) return '<span class="s-never_attempted">'+stateLabel.never_attempted+'</span>';
  if(env.state==="value"){
    var src = env.source_url ? ' <a class="src" href="'+esc(env.source_url)+'" target="_blank" rel="noopener">source</a>' : '';
    return '<span class="s-value">'+esc(env.value)+'</span>'+src;
  }
  return '<span class="s-'+env.state+'">'+(stateLabel[env.state]||env.state)+'</span>';
}
function filtered(){
  var q = (document.getElementById("q").value||"").toLowerCase();
  return DATA.professors.filter(function(p){
    if(!q) return true;
    return (p.name||"").toLowerCase().indexOf(q)>=0 ||
      Object.values(p.fields).some(function(e){return e && e.state==="value" &&
        String(e.value||"").toLowerCase().indexOf(q)>=0;});
  });
}
function renderTable(){
  var profs = filtered();
  var cols = DATA.fields.filter(function(f){return f.kind!=="score-input";});
  var html = '<table><thead><tr><th>Professor</th>' +
    cols.map(function(f){return '<th>'+esc(f.label)+'</th>';}).join('') +
    '</tr></thead><tbody>';
  profs.forEach(function(p){
    html += '<tr class="row" tabindex="0" role="button" data-id="'+esc(p.id)+'">'+
      '<td class="name">'+esc(p.name||p.id)+'</td>' +
      cols.map(function(f){return '<td>'+cell(p.fields[f.id])+'</td>';}).join('') + '</tr>';
  });
  html += '</tbody></table>';
  document.getElementById("grid").innerHTML =
    profs.length ? html : '<div class="empty">'+
    (DATA.professors.length ? 'No professors match. Try clearing the filter.'
      : 'No professors to show — '+
        esc((DATA.run && DATA.run.coverage) || 'this search returned nothing.'))+'</div>';
}
function renderDeadlines(){
  var dfs = dateFields();
  var rows = [];
  filtered().forEach(function(p){
    dfs.forEach(function(f){
      var env = p.fields[f.id];
      if(env && env.state==="value" && env.value){
        rows.push({p:p, f:f, env:env, when:String(env.value)});
      }
    });
  });
  rows.sort(function(a,b){return a.when < b.when ? -1 : a.when > b.when ? 1 : 0;});  // soonest first
  var host = document.getElementById("deadlines");
  if(!dfs.length || !rows.length){
    host.innerHTML = '<div class="empty">No deadline-shaped data was collected for this search.</div>';
    return;
  }
  host.innerHTML = '<div class="dl-list">'+rows.map(function(r){
    var watch = isWatch(r.env);
    var badge = watch ? '<span class="badge watch">watch · projected</span>'
                      : '<span class="badge firm">firm</span>';
    return '<div class="dl-card" tabindex="0" role="button" data-id="'+esc(r.p.id)+'">'+
      '<span class="dl-date">'+esc(r.when)+'</span>'+
      '<span class="name">'+esc(r.p.name||r.p.id)+'</span>'+
      '<span class="meta">'+esc(r.f.label)+'</span>'+badge+'</div>';
  }).join('')+'</div>'+
  '<div class="meta" style="padding:6px 18px">Watch dates are projected from past cycles — not published deadlines. Always confirm on the official page.</div>';
}
function openDetail(id){
  var p = DATA.professors.find(function(x){return x.id===id;});
  if(!p) return;
  var body = DATA.fields.map(function(f){
    var env = p.fields[f.id] || {state:"never_attempted"};
    var v;
    if(env.state==="value"){
      v = '<div class="v s-value">'+esc(env.value)+'</div>'+
          (env.quote? '<blockquote>“'+esc(env.quote)+'”</blockquote>':'')+
          (env.source_url? '<a class="src" href="'+esc(env.source_url)+'" target="_blank" rel="noopener">source</a>':'')+
          (env.confidence? ' <span class="meta">'+esc(env.confidence)+(isWatch(env)?' · watch':'')+'</span>':'');
    } else {
      v = '<div class="v s-'+env.state+'">'+(stateLabel[env.state]||env.state)+'</div>';
    }
    return '<div class="field"><div class="k">'+esc(f.label)+'</div>'+v+'</div>';
  }).join('');
  document.getElementById("panel").innerHTML =
    '<button class="close" id="closeDetail">close</button>'+
    '<aside class="detail"><h2>'+esc(p.name||p.id)+'</h2>'+
    '<div class="meta">'+esc(p.id)+'</div>'+body+'</aside>'+
    '<div class="overlay" id="overlay"></div>';
  document.getElementById("panel").classList.remove("hidden");
  document.getElementById("closeDetail").onclick = closeDetail;
  document.getElementById("overlay").onclick = closeDetail;
}
function closeDetail(){
  var panel = document.getElementById("panel");
  panel.classList.add("hidden"); panel.innerHTML = "";
}
function setView(v){
  document.getElementById("grid").classList.toggle("hidden", v!=="table");
  document.getElementById("deadlines").classList.toggle("hidden", v!=="deadlines");
  document.getElementById("vTable").classList.toggle("on", v==="table");
  document.getElementById("vDeadlines").classList.toggle("on", v==="deadlines");
}
function render(){
  renderTable(); renderDeadlines();
  document.getElementById("count").textContent =
    filtered().length+" / "+DATA.professors.length+" professors";
}
function onClickId(e){
  var el = e.target.closest("[data-id]");
  if(el) openDetail(el.getAttribute("data-id"));
}
function onKeyId(e){
  if(e.key!=="Enter" && e.key!==" ") return;
  var el = e.target.closest("[data-id]");
  if(el){ e.preventDefault(); openDetail(el.getAttribute("data-id")); }
}
document.addEventListener("DOMContentLoaded", function(){
  document.getElementById("q").addEventListener("input", render);
  document.getElementById("vTable").addEventListener("click", function(){setView("table");});
  document.getElementById("vDeadlines").addEventListener("click", function(){setView("deadlines");});
  document.body.addEventListener("click", onClickId);
  document.body.addEventListener("keydown", function(e){
    if(e.key==="Escape") return closeDetail();
    onKeyId(e);
  });
  render(); setView("table");
});
"""


def build_dashboard(export_obj: dict) -> str:
    """Return a complete, self-contained HTML document rendering ``export_obj``."""
    # Inline the data safely: neutralise any '</script>' inside string values.
    data = json.dumps(export_obj, ensure_ascii=False).replace("</", "<\\/")
    run = export_obj.get("run", {})
    meta = (f"run {run.get('run_id', '?')} · {run.get('status', '?')} · "
            f"generated {export_obj.get('generated_at', '?')}")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Supervisorly — results</title>
<style>{_CSS}</style></head>
<body>
<header><h1>Supervisorly</h1><div class="meta">{meta}</div></header>
<div class="controls">
  <input id="q" placeholder="filter by name or any value…" style="min-width:260px">
  <button id="vTable" class="on">Table</button>
  <button id="vDeadlines">Deadlines</button>
  <span class="meta" id="count"></span>
</div>
<div class="wrap"><div id="grid"></div><div id="deadlines" class="hidden"></div></div>
<div id="panel" class="hidden"></div>
<script>const DATA = {data};</script>
<script>{_JS}</script>
</body></html>
"""
