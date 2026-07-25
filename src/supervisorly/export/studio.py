"""Build the Scan Studio (D-067): ONE self-contained, offline HTML plan wizard in the
"Supervisorly Atlas — Living" design language (`design_handoff_supervisorly_atlas/`), under the
same rules as the dashboard (D-033/D-048) — no external requests, inline CSS/JS, named fonts with
system fallbacks (never imported), `prefers-reduced-motion` honoured, fully keyboard-operable.

The page consumes a ``map-field`` subject-map JSON (embedded via the same injection-safe
``_inline_json`` discipline as the dashboard — every ``<`` neutralised, U+2028/U+2029 escaped, so
hostile API strings can't break the data block) and walks the student through: intent, country,
universities + mode, a tri-state **checkbox subject tree** (domain -> field -> subfield -> topics;
checking a parent checks its descendants, partial selection shows indeterminate), named
professors, and a contact email. "Export plan" validates inline (never ``alert()``) and downloads
``supervisorly_plan.json`` via a Blob/anchor download — a static file cannot write to disk, so the
plan arrives as a browser download the user (or the agent) then feeds to
``supervisorly scan --plan supervisorly_plan.json``.
"""

from __future__ import annotations

import html as _html

from .dashboard import _inline_json

#: Intent choices offered by the wizard (a subset of the CLI's ``--intent`` choices) with short,
#: honest one-line labels. ``pre_phd`` is selected by default, matching the CLI default.
INTENTS = (
    ("pre_phd", "Pre-PhD / RA", "a research assistantship before a doctorate"),
    ("pre_master", "Pre-master's", "preparation before a master's degree"),
    ("master", "Master's", "a taught or research master's program"),
    ("phd", "PhD", "a doctoral position or studentship"),
    ("postdoc", "Postdoc", "a postdoctoral research position"),
    ("mentor", "Mentor", "guidance, not (yet) a formal position"),
)


def esc(s: object) -> str:
    """Escape an untrusted string for HTML interpolation (the Python-side half of the
    dashboard's ``esc()`` discipline — attribute-safe, so it is also safe inside quotes)."""
    return _html.escape("" if s is None else str(s), quote=True)


_CSS = r"""
:root{
  --void:#05070c; --panel-a:rgba(15,22,34,.7); --panel-b:rgba(6,9,15,.9);
  --chip:rgba(10,14,22,.66); --line:#172233; --line2:#1a2434;
  --ink:#e9edf3; --ink2:#c1c8d6; --muted:#9aa2b4; --faint:#6a7488; --dim:#4b5468;
  --accent:#e8b24a; --teal:#43c9d6; --focus:#7fd6e0;
  --chartreuse:#79d06a; --coral:#f0839a; --violet:#b58cf0; --slate:#7d828e;
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
#progress{position:fixed;top:0;left:0;height:2px;width:0;z-index:60;
  background:linear-gradient(90deg,#6bc4d6,#b58cf0,#e8b24a);
  box-shadow:0 0 12px rgba(127,214,224,.6)}
header{position:relative;z-index:1;padding:82px clamp(20px,4vw,64px) 48px;
  border-bottom:1px solid var(--line);overflow:hidden}
.eyebrow{font-family:var(--mono);font-size:12px;letter-spacing:.24em;text-transform:uppercase;
  color:var(--accent)}
h1{margin:.35em 0 .3em;font-weight:700;font-size:clamp(30px,4.6vw,54px);line-height:1.04;
  letter-spacing:-.02em;max-width:18ch}
.sub{color:var(--muted);font-size:16.5px;line-height:1.64;max-width:66ch}
.hero-cells{position:absolute;right:clamp(8px,3vw,48px);top:38px;width:300px;height:190px;
  opacity:.85;pointer-events:none}
.om-flt{animation:omFlow 1.5s linear infinite}
.breathe{animation:omBreathe 6s ease-in-out infinite;transform-origin:center;transform-box:fill-box}
main{position:relative;z-index:1;max-width:920px;margin:0 auto;
  padding:26px clamp(18px,3vw,44px) 140px}
.step{margin-top:44px;padding:24px 26px 26px;border:1px solid var(--line);border-radius:14px;
  background:radial-gradient(120% 140% at 50% 0%, var(--panel-a), var(--panel-b));
  box-shadow:0 40px 90px -50px rgba(0,0,0,.9), inset 0 1px 0 rgba(127,214,224,.04)}
.step-head{display:flex;align-items:baseline;gap:12px;margin-bottom:6px}
.step-code{font-family:var(--mono);font-size:12px;letter-spacing:.2em;color:var(--accent)}
.step h2{margin:0;font-size:clamp(20px,2.6vw,26px);letter-spacing:-.015em}
.step .why{margin:.2em 0 1em;color:var(--muted);font-size:14.5px;max-width:62ch}
.hidden{display:none}
label{display:block}
input,textarea,button{font:inherit}
input[type=text],input[type=email],textarea{width:100%;background:var(--chip);color:var(--ink);
  border:1px solid var(--line);border-radius:10px;padding:10px 13px;font-family:var(--mono);
  font-size:13px}
input[type=text]:hover,textarea:hover{border-color:#223148}
textarea{min-height:96px;resize:vertical}
.hint{font-family:var(--mono);font-size:11px;color:var(--faint);margin-top:6px}
/* intent radio cards */
.rcards{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:10px}
.rcard{cursor:pointer;border:1px solid var(--line);border-radius:12px;padding:14px 16px;
  background:var(--chip);transition:border-color .18s, box-shadow .18s}
.rcard:hover{border-color:#2a3a55;box-shadow:0 0 18px rgba(127,214,224,.08)}
.rcard:has(input:checked){border-color:var(--accent);background:rgba(232,178,74,.07);
  box-shadow:0 0 22px rgba(232,178,74,.14)}
.rcard input{position:absolute;opacity:0;pointer-events:none}
/* the input is invisible, so the :focus-visible ring must be painted on the card itself
   (WCAG 2.4.7 — Tab-ing into the intent group shows where focus landed) */
.rcard:has(input:focus-visible){outline:2px solid var(--focus);outline-offset:2px}
.rc-t{font-weight:650;font-size:14.5px}
.rc-d{color:var(--muted);font-size:12.5px;margin-top:2px}
/* university chips */
.urow{display:flex;gap:8px;margin-bottom:10px}
.urow input{flex:1}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:4px 0 14px}
.chip{display:inline-flex;align-items:center;gap:8px;border:1px solid var(--line);
  border-radius:12px;background:var(--chip);padding:5px 8px 5px 12px;font-family:var(--mono);
  font-size:12.5px;color:var(--ink2);box-shadow:0 0 14px rgba(67,201,214,.06)}
.chip button{background:transparent;border:0;color:var(--faint);cursor:pointer;
  font-family:var(--mono);font-size:13px;padding:0 4px;border-radius:6px}
.chip button:hover{color:var(--coral)}
.modes{display:flex;gap:14px;flex-wrap:wrap}
.mlabel{display:inline-flex;align-items:center;gap:8px;font-family:var(--mono);font-size:12.5px;
  color:var(--ink2);cursor:pointer;border:1px solid var(--line);border-radius:10px;
  padding:7px 12px;background:var(--chip)}
.mlabel:has(input:checked){border-color:var(--teal);color:var(--teal);
  background:rgba(67,201,214,.08)}
.mlabel input{accent-color:var(--teal)}
.btn{background:rgba(232,178,74,.12);color:var(--accent);border:1px solid rgba(232,178,74,.5);
  border-radius:10px;padding:9px 16px;cursor:pointer;font-family:var(--mono);font-size:12.5px;
  letter-spacing:.06em}
.btn:hover{background:rgba(232,178,74,.2);box-shadow:0 0 18px rgba(232,178,74,.2)}
.btn.ghost{background:var(--chip);color:var(--ink2);border-color:var(--line)}
.btn.ghost:hover{border-color:var(--accent);color:var(--accent);box-shadow:none}
.btn.big{font-size:14px;padding:13px 26px}
/* subject tree */
.trunc{border:1px solid rgba(232,178,74,.55);border-left:3px solid var(--accent);
  border-radius:10px;background:rgba(232,178,74,.08);color:#e8c987;padding:11px 14px;
  font-family:var(--mono);font-size:12px;margin-bottom:14px}
#tree{max-height:520px;overflow-y:auto;border:1px solid var(--line);border-radius:12px;
  background:var(--chip);padding:12px 16px}
#tree ul{list-style:none;margin:0;padding-left:22px}
#tree>ul{padding-left:2px}
.trow{display:flex;align-items:center;gap:9px;padding:5px 6px;border-radius:8px;cursor:pointer}
.trow:hover{background:rgba(127,214,224,.05)}
.trow input{accent-color:var(--accent);width:15px;height:15px;flex:none}
.tdom{font-weight:700;color:var(--ink);letter-spacing:.01em}
.tfld{font-weight:600;color:var(--ink2)}
.tsub{color:var(--muted);font-size:13.5px}
.topic-row .tname{color:var(--ink2);font-size:14px}
.wchip{margin-left:auto;font-family:var(--mono);font-size:10.5px;color:var(--teal);
  border:1px solid rgba(67,201,214,.4);border-radius:999px;padding:1px 9px;flex:none;
  background:rgba(67,201,214,.07)}
.empty{padding:26px 8px;color:var(--muted)}
/* inline errors + done panel */
.err{display:none;color:var(--coral);font-family:var(--mono);font-size:11.5px;margin-top:8px}
.err.on{display:block}
.step.bad{border-color:rgba(240,131,154,.6)}
#done{margin-top:18px}
.code{position:relative;background:#080b12;border:1px solid var(--line2);border-radius:10px;
  padding:13px 16px;font-family:var(--mono);font-size:13px;color:#aee3ea;overflow-x:auto;
  white-space:nowrap}
.copy{position:absolute;top:8px;right:8px;background:var(--chip);border:1px solid var(--line2);
  color:var(--muted);border-radius:8px;padding:4px 10px;cursor:pointer;font-family:var(--mono);
  font-size:11px}
.copy:hover{color:var(--accent);border-color:var(--accent)}
#toast{position:fixed;bottom:26px;left:50%;transform:translateX(-50%);z-index:70;
  background:var(--chip);border:1px solid var(--teal);color:var(--teal);border-radius:10px;
  padding:9px 18px;font-family:var(--mono);font-size:12px;display:none;
  box-shadow:0 0 24px rgba(67,201,214,.25)}
:focus-visible{outline:2px solid var(--focus);outline-offset:2px}
@keyframes omBreathe{0%,100%{transform:scale(1)}50%{transform:scale(1.055)}}
@keyframes omFlow{to{stroke-dashoffset:-24.2}}
@keyframes omScan{0%{transform:translateY(-120px)}100%{transform:translateY(110vh)}}
@media (prefers-reduced-motion:reduce){
  *{animation:none!important;transition:none!important}
  html{scroll-behavior:auto}
}
@media (max-width:720px){.hero-cells{display:none}}
"""

_JS = r"""
/* the same esc() discipline as the dashboard: every API string is untrusted */
function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,c=>(
  {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));}
var universities = [];

function fmtWorks(n){
  n = Number(n)||0;
  if(n>=1e6) return (n/1e6).toFixed(1).replace(/\.0$/,"")+"M works";
  if(n>=1e3) return (n/1e3).toFixed(1).replace(/\.0$/,"")+"k works";
  return n+" works";
}

/* ── subject tree: domain -> field -> subfield -> topics, tri-state parents ── */
function buildTree(){
  var host = document.getElementById("tree");
  var groups = (DATA && DATA.groups) || [];
  if(!groups.length){
    host.innerHTML = '<div class="empty">This subject map is empty — no topics were returned. '+
      'You can still export a plan that names professors directly.</div>';
    return;
  }
  var byDom = {}, domOrder = [];
  groups.forEach(function(g){
    var d = String(g.domain||"ungrouped"), f = String(g.field||"ungrouped");
    if(!byDom[d]){ byDom[d] = {order:[], fields:{}}; domOrder.push(d); }
    if(!byDom[d].fields[f]){ byDom[d].fields[f] = []; byDom[d].order.push(f); }
    byDom[d].fields[f].push(g);
  });
  var html = "<ul>";
  domOrder.forEach(function(d){
    html += '<li><label class="trow"><input type="checkbox" class="tparent">'+
      '<span class="tname tdom">'+esc(d)+'</span></label><ul>';
    byDom[d].order.forEach(function(f){
      html += '<li><label class="trow"><input type="checkbox" class="tparent">'+
        '<span class="tname tfld">'+esc(f)+'</span></label><ul>';
      byDom[d].fields[f].forEach(function(g){
        html += '<li><label class="trow"><input type="checkbox" class="tparent">'+
          '<span class="tname tsub">'+esc(g.subfield)+'</span></label><ul>';
        /* belt and braces: a malformed entry is skipped, never allowed to brick the page */
        var topics = Array.isArray(g.topics) ? g.topics : [];
        topics.forEach(function(t){
          if(!t || !t.topic_id) return;    /* no id -> no checkbox ("" would dilute topic_match) */
          html += '<li><label class="trow topic-row">'+
            '<input type="checkbox" class="topic" value="'+esc(t.topic_id)+'">'+
            '<span class="tname">'+esc(t.name)+'</span>'+
            '<span class="wchip">'+esc(fmtWorks(t.works_count))+'</span></label></li>';
        });
        html += "</ul></li>";
      });
      html += "</ul></li>";
    });
    html += "</ul></li>";
  });
  host.innerHTML = html + "</ul>";
  host.addEventListener("change", function(e){
    var box = e.target;
    if(box.classList.contains("tparent")){
      /* checking a parent checks every descendant topic (and the reverse) */
      box.closest("li").querySelectorAll("input.topic").forEach(function(k){
        k.checked = box.checked; });
    }
    refreshTree();
  });
}
/* recompute every parent from its descendants: checked / unchecked / indeterminate */
function refreshTree(){
  document.querySelectorAll("#tree input.tparent").forEach(function(p){
    var kids = p.closest("li").querySelectorAll("input.topic");
    var n = 0;
    kids.forEach(function(k){ if(k.checked) n++; });
    p.checked = kids.length>0 && n===kids.length;
    p.indeterminate = n>0 && n<kids.length;
  });
}

/* ── university chips ── */
function renderChips(){
  var host = document.getElementById("uniChips");
  host.innerHTML = universities.map(function(u,i){
    return '<span class="chip">'+esc(u)+
      '<button type="button" data-uni="'+i+'" aria-label="remove '+esc(u)+'">×</button></span>';
  }).join("");
  host.querySelectorAll("button[data-uni]").forEach(function(b){
    b.addEventListener("click", function(){
      universities.splice(Number(b.getAttribute("data-uni")),1); renderChips(); });
  });
}
function addUniversity(){
  var inp = document.getElementById("uniInput"), v = inp.value.trim();
  if(v && universities.indexOf(v)<0){ universities.push(v); renderChips(); }
  inp.value = ""; inp.focus();
}

/* ── plan build + validate + export ── */
function parseProfs(text){
  var out = [];
  String(text||"").split("\n").forEach(function(line){
    line = line.trim();
    if(!line) return;
    /* affiliation = after the LAST comma, so "Name, Jr., MIT" and "Last, First, MIT" parse */
    var i = line.lastIndexOf(",");
    var name = (i<0 ? line : line.slice(0,i)).trim();
    if(!name) return;
    var aff = (i<0 ? "" : line.slice(i+1)).trim();
    out.push(aff ? {name:name, affiliation:aff} : {name:name});
  });
  return out;
}
function checkedTopics(){
  var ids = [];
  document.querySelectorAll("#tree input.topic:checked").forEach(function(b){
    if(b.value) ids.push(b.value); });
  return ids;
}
function buildPlan(){
  var intent = document.querySelector('input[name="intent"]:checked');
  var mode = document.querySelector('input[name="uniMode"]:checked');
  return {
    intent_kind: intent ? intent.value : "pre_phd",
    country: document.getElementById("country").value.trim(),
    field: (DATA && DATA.query) || "",
    resolved_topic_ids: checkedTopics(),
    university_mode: mode ? mode.value : "all",
    universities: universities.slice(),
    targets: parseProfs(document.getElementById("profs").value),
    email: document.getElementById("email").value.trim()
  };
}
function showErr(step, id, msg){
  var e = document.getElementById(id);
  e.textContent = msg; e.classList.add("on");
  document.getElementById(step).classList.add("bad");
}
function clearErrs(){
  document.querySelectorAll(".err").forEach(function(e){
    e.textContent=""; e.classList.remove("on"); });
  document.querySelectorAll(".step.bad").forEach(function(s){ s.classList.remove("bad"); });
}
function exportPlan(){
  clearErrs();
  var plan = buildPlan(), bad = null;
  if(!plan.country && !plan.targets.length){
    showErr("step-country","err-country",
      "give a country OR name at least one professor below.");
    showErr("step-profs","err-profs",
      "name at least one professor OR give a country above.");
    bad = bad || "country";
  }
  if(!plan.targets.length && !plan.resolved_topic_ids.length){
    showErr("step-topics","err-topics",
      "check at least one topic (or name professors directly instead).");
    bad = bad || "tree";
  }
  if(!plan.email){
    showErr("step-email","err-email",
      "an email is required for live scans — it goes to the OpenAlex polite pool.");
    bad = bad || "email";
  }
  if(bad){
    var el = document.getElementById(bad==="tree" ? "tree" : bad);
    if(el && el.focus) el.focus();
    return;
  }
  /* a static file cannot write to disk — deliver the plan as a browser download */
  var blob = new Blob([JSON.stringify(plan,null,2)+"\n"], {type:"application/json"});
  var a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "supervisorly_plan.json";
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(function(){ URL.revokeObjectURL(a.href); }, 4000);
  document.getElementById("done").classList.remove("hidden");
  /* CSS can't cancel JS-driven motion — honour reduced-motion explicitly (D-048) */
  var _rm = window.matchMedia && window.matchMedia("(prefers-reduced-motion:reduce)").matches;
  document.getElementById("done").scrollIntoView({behavior:_rm?"auto":"smooth", block:"nearest"});
}
function copyCmd(){
  var cmd = document.getElementById("nextcmd").textContent;
  function ok(){ toast("copied to clipboard"); }
  if(navigator.clipboard && navigator.clipboard.writeText){
    navigator.clipboard.writeText(cmd).then(ok, function(){ fallbackCopy(cmd); ok(); });
  } else { fallbackCopy(cmd); ok(); }
}
function fallbackCopy(text){
  var ta = document.createElement("textarea");
  ta.value = text; ta.style.position="fixed"; ta.style.opacity="0";
  document.body.appendChild(ta); ta.select();
  try{ document.execCommand("copy"); }catch(_){}
  ta.remove();
}
function toast(msg){
  var t = document.getElementById("toast");
  t.textContent = msg; t.style.display = "block";
  clearTimeout(t._h); t._h = setTimeout(function(){ t.style.display="none"; }, 2200);
}

document.addEventListener("DOMContentLoaded", function(){
  /* wire every control FIRST — a bad tree below can then never take down the page */
  var d = (DATA && DATA.defaults) || {};
  if(d.country) document.getElementById("country").value = d.country;
  if(d.email) document.getElementById("email").value = d.email;
  if(d.intent_kind){
    /* intent_kind is validated against INTENTS at build time; the try/catch is belt and
       braces so a hostile value can never escape init via a malformed selector */
    var r = null;
    try { r = document.querySelector('input[name="intent"][value="'+d.intent_kind+'"]'); }
    catch(_){}
    if(r) r.checked = true;
  }
  if(Array.isArray(d.universities)){ universities = d.universities.slice(); }
  renderChips();
  document.getElementById("uniAdd").addEventListener("click", addUniversity);
  document.getElementById("uniInput").addEventListener("keydown", function(e){
    if(e.key==="Enter"){ e.preventDefault(); addUniversity(); } });
  document.getElementById("export").addEventListener("click", exportPlan);
  document.getElementById("copybtn").addEventListener("click", copyCmd);
  window.addEventListener("scroll", function(){
    var h = document.documentElement;
    var p = h.scrollTop / Math.max(1, h.scrollHeight - h.clientHeight);
    document.getElementById("progress").style.width = (p*100)+"%";
  });
  /* Escape closes any transient UI */
  document.addEventListener("keydown", function(e){
    if(e.key==="Escape"){
      document.getElementById("toast").style.display = "none";
      document.getElementById("done").classList.add("hidden");
    }
  });
  /* build the tree LAST, inside a guard: a malformed map renders an honest note instead
     of throwing before the wiring above exists */
  try { buildTree(); }
  catch(e){
    document.getElementById("tree").innerHTML =
      '<div class="empty">This subject map could not be rendered — its entries are '+
      'malformed. You can still export a plan that names professors directly.</div>';
  }
});
"""


def build_studio(subject_map: dict, *, defaults: dict | None = None) -> str:
    """Return the complete, self-contained Scan Studio HTML document for ``subject_map``.

    ``subject_map`` is the ``map-field`` JSON shape (``{"query", "groups", "truncated", ...}``);
    anything that is not a well-formed map renders as an honest empty tree, never a crash.
    ``defaults`` may prefill ``country`` / ``email`` / ``universities`` / ``intent_kind``.
    """
    smap = subject_map if isinstance(subject_map, dict) else {}
    groups = smap.get("groups")
    defaults = dict(defaults or {})
    intent = defaults.get("intent_kind")
    if intent is not None and intent not in {key for key, _, _ in INTENTS}:
        intent = "pre_phd"      # unknown/hostile intent falls back, never reaches a selector
    data = {
        "query": str(smap.get("query") or ""),
        # sanitize: only dict groups survive; topics is always a list of dicts whose
        # topic_id is truthy (a missing id would export "" and dilute topic_match)
        "groups": [
            {**g, "topics": [t for t in g.get("topics") if isinstance(t, dict) and t.get("topic_id")]
             if isinstance(g.get("topics"), list) else []}
            for g in groups if isinstance(g, dict)
        ] if isinstance(groups, list) else [],
        "truncated": bool(smap.get("truncated")),
        "defaults": {k: (intent if k == "intent_kind" else v)
                     for k, v in defaults.items()
                     if k in ("country", "email", "universities", "intent_kind")},
    }
    payload = _inline_json(data)

    trunc_banner = ""
    if data["truncated"]:
        # D-037 honesty: a capped map is PARTIAL, never presented as complete
        trunc_banner = (
            '<div class="trunc" role="note">PARTIAL MAP — the API returned more topics than '
            'shown; this map is partial, not complete. Narrow the query with '
            '<b>map-field</b> for the rest, or pick from what is here.</div>')

    intent_cards = "".join(
        f'<label class="rcard"><input type="radio" name="intent" value="{esc(key)}"'
        f'{" checked" if key == "pre_phd" else ""}>'
        f'<span class="rc-t">{esc(title)}</span>'
        f'<span class="rc-d">{esc(desc)}</span></label>'
        for key, title, desc in INTENTS)

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Supervisorly — Scan Studio</title>
<style>{_CSS}</style></head>
<body>
<div class="scan" aria-hidden="true"></div>
<div id="progress" aria-hidden="true"></div>
<header>
  <svg class="hero-cells" viewBox="0 0 300 190" aria-hidden="true">
    <path class="om-flt" d="M60 60 C 110 20, 150 30, 195 55" fill="none" stroke="#43c9d6"
      stroke-width="1.3" opacity=".42" stroke-dasharray="0.1 12"/>
    <path class="om-flt" d="M70 130 C 120 160, 160 150, 205 118" fill="none" stroke="#b58cf0"
      stroke-width="1.3" opacity=".42" stroke-dasharray="0.1 12"/>
    <path d="M60 60 C 110 20, 150 30, 195 55" fill="none" stroke="#43c9d6" stroke-width="8"
      opacity=".08" stroke-linecap="round"/>
    <path d="M70 130 C 120 160, 160 150, 205 118" fill="none" stroke="#b58cf0" stroke-width="8"
      opacity=".08" stroke-linecap="round"/>
    <g class="breathe"><circle cx="52" cy="62" r="30" fill="rgba(232,178,74,.12)"/>
      <circle cx="52" cy="62" r="16" fill="rgba(232,178,74,.28)" stroke="#e8b24a"
      stroke-width="1.4"/><circle cx="52" cy="62" r="4" fill="#e8b24a"/></g>
    <g class="breathe"><circle cx="212" cy="58" r="26" fill="rgba(67,201,214,.10)"/>
      <circle cx="212" cy="58" r="13" fill="rgba(67,201,214,.26)" stroke="#43c9d6"
      stroke-width="1.4"/><circle cx="212" cy="58" r="3.5" fill="#43c9d6"/></g>
    <g class="breathe"><circle cx="62" cy="132" r="22" fill="rgba(121,208,106,.10)"/>
      <circle cx="62" cy="132" r="11" fill="rgba(121,208,106,.24)" stroke="#79d06a"
      stroke-width="1.4"/><circle cx="62" cy="132" r="3" fill="#79d06a"/></g>
    <g class="breathe"><circle cx="222" cy="120" r="20" fill="rgba(181,140,240,.10)"/>
      <circle cx="222" cy="120" r="10" fill="rgba(181,140,240,.24)" stroke="#b58cf0"
      stroke-width="1.4"/><circle cx="222" cy="120" r="3" fill="#b58cf0"/></g>
  </svg>
  <div class="eyebrow">Supervisorly · Scan Studio</div>
  <h1>Plan your supervisor search.</h1>
  <p class="sub">Say what you're looking for and where, keep the subject-map topics that fit,
    optionally name professors directly, and export a plan — then one command runs the live,
    quote-verified scan. Subject map for: <b>{esc(data["query"]) or "—"}</b></p>
</header>
<main>
  <section class="step" id="step-intent">
    <div class="step-head"><span class="step-code">STEP 01</span><h2>What are you looking for?</h2></div>
    <p class="why">The intent gates how candidates are scored.</p>
    <div class="rcards" role="radiogroup" aria-label="intent">{intent_cards}</div>
  </section>

  <section class="step" id="step-country">
    <div class="step-head"><span class="step-code">STEP 02</span><h2>Country</h2></div>
    <p class="why">Where the country-wide search runs — a name or an ISO code.</p>
    <input type="text" id="country" placeholder="e.g. Canada or CA" tabindex="0">
    <div class="err" id="err-country" role="alert"></div>
  </section>

  <section class="step" id="step-unis">
    <div class="step-head"><span class="step-code">STEP 03</span><h2>Universities <span style="color:var(--faint);font-weight:400">(optional)</span></h2></div>
    <p class="why">Add institutions, then choose how the search treats them.</p>
    <div class="urow">
      <input type="text" id="uniInput" placeholder="e.g. McGill University">
      <button type="button" class="btn ghost" id="uniAdd">+ add</button>
    </div>
    <div class="chips" id="uniChips"></div>
    <div class="modes" role="radiogroup" aria-label="university mode">
      <label class="mlabel"><input type="radio" name="uniMode" value="all" checked> all — search everywhere, these included</label>
      <label class="mlabel"><input type="radio" name="uniMode" value="prioritise"> prioritise — rank these first</label>
      <label class="mlabel"><input type="radio" name="uniMode" value="only"> only — restrict to these</label>
    </div>
  </section>

  <section class="step" id="step-topics">
    <div class="step-head"><span class="step-code">STEP 04</span><h2>Keep the topics that fit</h2></div>
    <p class="why">This map came from the OpenAlex topics API (never a hardcoded list). Check a
      group to keep all its topics; check individual topics to fine-tune.</p>
    {trunc_banner}
    <div id="tree" tabindex="0"></div>
    <div class="err" id="err-topics" role="alert"></div>
  </section>

  <section class="step" id="step-profs">
    <div class="step-head"><span class="step-code">STEP 05</span><h2>Named professors <span style="color:var(--faint);font-weight:400">(optional)</span></h2></div>
    <p class="why">Deep-dive specific people directly, one per line: <span style="font-family:var(--mono)">Name, Affiliation (optional)</span> — the affiliation is everything after the last comma, so <span style="font-family:var(--mono)">King, Jr., MIT</span> parses correctly.</p>
    <textarea id="profs" placeholder="Ada Maple, McGill University&#10;Grace Hopper"></textarea>
    <div class="err" id="err-profs" role="alert"></div>
  </section>

  <section class="step" id="step-email">
    <div class="step-head"><span class="step-code">STEP 06</span><h2>Contact email</h2></div>
    <p class="why">Required for live scans — it identifies you to the OpenAlex polite pool. It is
      never shown on any page the tool fetches.</p>
    <input type="email" id="email" placeholder="you@university.edu">
    <div class="err" id="err-email" role="alert"></div>
  </section>

  <section class="step" id="step-export">
    <div class="step-head"><span class="step-code">STEP 07</span><h2>Export plan</h2></div>
    <p class="why">Downloads <b>supervisorly_plan.json</b> (a static page can't write to disk, so
      it arrives as a browser download), then run the scan — yourself, or ask the agent to run it.</p>
    <button type="button" class="btn big" id="export">Export plan ↓</button>
    <div id="done" class="hidden">
      <p class="why" style="margin-top:16px">Plan downloaded. Next command:</p>
      <div class="code"><span id="nextcmd">supervisorly scan --plan supervisorly_plan.json --out output/live.html</span><button type="button" class="copy" id="copybtn">copy</button></div>
      <div class="hint">The agent can run this for you — the plan already carries your email and targets.</div>
    </div>
  </section>
</main>
<div id="toast" role="status"></div>
<script>const DATA = {payload};
{_JS}</script>
</body></html>
"""
