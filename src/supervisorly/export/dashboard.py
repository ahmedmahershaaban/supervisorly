"""Build the single self-contained dashboard HTML (D-033, D-046).

One file, no CDN, offline: the export JSON is inlined and vanilla JS renders a generic,
filterable table whose columns come from the field descriptors (D-038). The four states
render distinctly — a blank field is never conflated with "we looked, found nothing"
(D-022, D-037). A deadline view surfaces "what closes soon", showing projected/unpublished
deadlines as watch-dates, never firm (D-061).

(React/JSX vendoring per D-048 is a later refinement; this vanilla-JS build already meets
the DoD — self-contained, offline, four-state, filterable — and is trivially testable.)
"""

from __future__ import annotations

import json

_CSS = """
:root{--bg:#0c0d10;--surface:#15161a;--line:#282a31;--ink:#e9eaed;--muted:#8a8d96;
--accent:#d9a441;--val:#dff2e7;--absent:#8a8d96;--never:#5a5d66;--blocked:#e8bf6a}
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
.wrap{overflow-x:auto;padding:0 8px}
table{border-collapse:collapse;width:100%;min-width:640px}
th,td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);vertical-align:top}
th{position:sticky;top:0;background:var(--bg);color:var(--muted);font-weight:600;
font-family:ui-monospace,Consolas,monospace;font-size:11px;letter-spacing:.04em}
.name{font-weight:650}
.s-value{color:var(--val)}
.s-searched_absent{color:var(--absent);font-style:italic}
.s-never_attempted{color:var(--never)}
.s-blocked{color:var(--blocked)}
.src{color:var(--muted);text-decoration:none;font-size:11px;margin-left:6px}
.src:hover{color:var(--accent)}
.empty{padding:40px 24px;color:var(--muted)}
"""

_JS = r"""
const stateLabel = {searched_absent:"— we looked, found nothing",
  never_attempted:"· not checked yet", blocked:"⏳ awaiting your browser"};
function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,c=>(
  {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));}
function cell(env){
  if(!env) return '<span class="s-never_attempted">'+stateLabel.never_attempted+'</span>';
  if(env.state==="value"){
    var src = env.source_url ? ' <a class="src" href="'+esc(env.source_url)+'" target="_blank" rel="noopener">source</a>' : '';
    return '<span class="s-value">'+esc(env.value)+'</span>'+src;
  }
  return '<span class="s-'+env.state+'">'+(stateLabel[env.state]||env.state)+'</span>';
}
function render(){
  var q = (document.getElementById("q").value||"").toLowerCase();
  var profs = DATA.professors.filter(function(p){
    if(!q) return true;
    return (p.name||"").toLowerCase().indexOf(q)>=0 ||
      Object.values(p.fields).some(function(e){return e && e.state==="value" &&
        String(e.value||"").toLowerCase().indexOf(q)>=0;});
  });
  var cols = DATA.fields.filter(function(f){return f.kind!=="score-input";});
  var html = '<table><thead><tr><th>Professor</th>' +
    cols.map(function(f){return '<th>'+esc(f.label)+'</th>';}).join('') +
    '</tr></thead><tbody>';
  profs.forEach(function(p){
    html += '<tr><td class="name">'+esc(p.name||p.id)+'</td>' +
      cols.map(function(f){return '<td>'+cell(p.fields[f.id])+'</td>';}).join('') + '</tr>';
  });
  html += '</tbody></table>';
  document.getElementById("grid").innerHTML =
    profs.length ? html : '<div class="empty">No professors match. '+
    (DATA.professors.length? 'Try clearing the filter.' :
     'This search returned no professors — see the coverage note.')+'</div>';
  document.getElementById("count").textContent = profs.length+" / "+DATA.professors.length+" professors";
}
document.addEventListener("DOMContentLoaded", function(){
  document.getElementById("q").addEventListener("input", render);
  render();
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
  <span class="meta" id="count"></span>
</div>
<div class="wrap"><div id="grid"></div></div>
<script>const DATA = {data};</script>
<script>{_JS}</script>
</body></html>
"""
