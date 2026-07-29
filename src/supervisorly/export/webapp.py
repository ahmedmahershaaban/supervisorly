"""Build the Supervisorly web app (plan step 5, D-069): ONE dynamic HTML page in the
"Supervisorly Atlas — Living" design language — the Scan Studio's dynamic sibling.

Unlike the Studio (D-067) the page MAY ``fetch()`` the API (D-069(d)), but ships no other
external resource: no fonts/CDN/img/iframe, inline CSS/JS, ``prefers-reduced-motion``
honoured, fully keyboard-operable with visible focus, Escape closes transient UI. ALL
state lives in memory — nothing in localStorage/cookies (D-069: no client-side personal
data). The five-step wizard (§0 of docs/FIREBASE_WEB_PLAN.md):

1. **You** — email (required, format-checked inline), intent radio cards, country,
   universities chips + all/prioritise/only mode, optional ``max_institutions`` (1–300).
2. **Field** — free text + *Understand* → ``POST /api/expand`` (best-effort; any failure
   proceeds deterministically with the raw words + a small note), then one
   ``GET /api/map`` per variant, merged client-side by ``topic_id`` with ``found_by``
   tags (``/api/map`` takes a single ``field`` — see ``webapi.handle_subject_map``).
3. **Disambiguate** — the merged map as meaning clusters with the tri-state checkbox
   tree (the Studio's logic); nothing pre-checked; PARTIAL banner if any variant
   truncated; a live "N of M topics selected" counter; next needs ≥1 topic OR ≥1 named
   professor (last-comma format, like the Studio).
4. **Scope & scan** — institutions slider (1–300, default 25) + professors slider
   (1–200, default 40) with a live cost preview, a review card, and *Start scan* →
   ``POST /api/scan`` (button disabled immediately; 429 → the one-active-job message;
   200 ``existing: true`` → straight to progress, §3.3 idempotent start).
5. **Progress** — determinate bar (§4.1: discovery 0–30%, deep-dive 30–90% by i/k,
   scoring/export 90–100%; indeterminate pulse only before the first count), the §4.1
   plain-language phase line, elapsed timer, amber ``partial_warning`` notes, polling
   every 4 s, the §4.2 slow-state notice with three actions, cancel (graceful, §3.4)
   and resume buttons, "Open dashboard" → ``GET /api/result/<id>`` → ``window.open`` in
   a new tab, and the lost-contact recovery (job id + resume-by-id input).

``api_base`` is a BUILD-TIME trusted config string (the deploy step substitutes
``<API_BASE_URL>``) — it is injected as a plain JS string literal so the placeholder
passes through verbatim; it is never user data. Empty string = same-origin (local dev /
hosted rewrite).
"""

from __future__ import annotations

import json as _json

#: Intent choices — the CLI's full ``PLAN_INTENT_KINDS`` enum (7), so every card the page
#: offers is accepted by ``POST /api/scan`` server-side validation.
INTENTS = (
    ("pre_phd", "Pre-PhD / RA", "a research assistantship before a doctorate"),
    ("pre_master", "Pre-master's", "preparation before a master's degree"),
    ("master", "Master's", "a taught or research master's program"),
    ("phd", "PhD", "a doctoral position or studentship"),
    ("postdoc", "Postdoc", "a postdoctoral research position"),
    ("mentor", "Mentor", "guidance, not (yet) a formal position"),
    ("training", "Training", "research training or skills development"),
)

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
header{position:relative;z-index:1;padding:82px clamp(20px,4vw,64px) 40px;
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
/* step rail */
.rail{display:flex;gap:8px;flex-wrap:wrap;margin:26px 0 0}
.ritem{font-family:var(--mono);font-size:11px;letter-spacing:.14em;color:var(--faint);
  border:1px solid var(--line);border-radius:999px;padding:6px 14px;background:var(--chip);
  cursor:pointer;text-transform:uppercase}
.ritem b{font-weight:400;margin-right:6px;color:inherit}
.ritem.on{color:var(--accent);border-color:rgba(232,178,74,.55);background:rgba(232,178,74,.08)}
.ritem.done{color:var(--teal);border-color:rgba(67,201,214,.35)}
.ritem:disabled{opacity:.45;cursor:default}
.step{margin-top:30px;padding:24px 26px 26px;border:1px solid var(--line);border-radius:14px;
  background:radial-gradient(120% 140% at 50% 0%, var(--panel-a), var(--panel-b));
  box-shadow:0 40px 90px -50px rgba(0,0,0,.9), inset 0 1px 0 rgba(127,214,224,.04)}
.step-head{display:flex;align-items:baseline;gap:12px;margin-bottom:6px}
.step-code{font-family:var(--mono);font-size:12px;letter-spacing:.2em;color:var(--accent)}
.step h2{margin:0;font-size:clamp(20px,2.6vw,26px);letter-spacing:-.015em}
.step .why{margin:.2em 0 1em;color:var(--muted);font-size:14.5px;max-width:62ch}
.hidden{display:none}
label{display:block}
input,textarea,button,select{font:inherit}
input[type=text],input[type=email],input[type=number],textarea{width:100%;
  background:var(--chip);color:var(--ink);border:1px solid var(--line);border-radius:10px;
  padding:10px 13px;font-family:var(--mono);font-size:13px}
input[type=text]:hover,input[type=email]:hover,input[type=number]:hover,textarea:hover{
  border-color:#223148}
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
/* the search plan: one collapsed row per field, with its phrasing count on the row */
.fplan{margin:18px 0 4px;border:1px solid var(--line2);border-radius:12px;overflow:hidden}
.fplan-h{padding:11px 14px;border-bottom:1px solid var(--line2);color:var(--muted);
  font-size:13px;background:rgba(255,255,255,.02)}
details.fp{border-bottom:1px solid var(--line)}
details.fp:last-child{border-bottom:0}
details.fp summary{list-style:none;cursor:pointer;padding:11px 14px;display:flex;
  align-items:center;gap:10px;justify-content:space-between}
details.fp summary::-webkit-details-marker{display:none}
details.fp summary::before{content:"▸";color:var(--faint);font-size:12px;margin-right:2px}
details.fp[open] summary::before{content:"▾"}
details.fp summary:hover{background:rgba(255,255,255,.03)}
.fp-name{font-weight:600;flex:1}
.fp-vars{padding:2px 14px 0}
.fp-add{padding:0 14px 12px}
.fp-add .fp-in{flex:1}
.chip-own{border-color:var(--accent);color:var(--accent)}
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
.btn:disabled{opacity:.5;cursor:default;box-shadow:none}
.btn.ghost{background:var(--chip);color:var(--ink2);border-color:var(--line)}
.btn.ghost:hover{border-color:var(--accent);color:var(--accent);box-shadow:none}
.btn.big{font-size:14px;padding:13px 26px}
.btnrow{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}
/* subject tree (meaning clusters) */
.trunc{border:1px solid rgba(232,178,74,.55);border-left:3px solid var(--accent);
  border-radius:10px;background:rgba(232,178,74,.08);color:#e8c987;padding:11px 14px;
  font-family:var(--mono);font-size:12px;margin-bottom:14px}
.note{border-left:3px solid var(--teal);border-radius:10px;background:rgba(67,201,214,.07);
  color:#aee3ea;padding:9px 13px;font-family:var(--mono);font-size:12px;margin:0 0 14px}
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
.wchip.fb{margin-left:0;color:var(--violet);border-color:rgba(181,140,240,.4);
  background:rgba(181,140,240,.07)}
.empty{padding:26px 8px;color:var(--muted)}
.selcount{font-family:var(--mono);font-size:12px;color:var(--teal);margin:10px 2px 0}
/* sliders + cost preview */
.sliderblock{margin:18px 0 6px}
.sliderblock label{font-size:14px;color:var(--ink2);margin-bottom:4px}
input[type=range]{width:100%;accent-color:var(--accent)}
.costline{font-family:var(--mono);font-size:13.5px;color:var(--accent);margin:14px 0 0}
.review{margin-top:18px;border:1px solid var(--line);border-radius:12px;background:var(--chip);
  padding:12px 16px}
.rrow{display:flex;gap:14px;padding:4px 0;border-bottom:1px solid rgba(23,34,51,.6)}
.rrow:last-child{border-bottom:0}
.rk{flex:none;width:190px;font-family:var(--mono);font-size:11px;color:var(--faint);
  text-transform:uppercase;letter-spacing:.12em;padding-top:3px}
.rv{font-size:13.5px;color:var(--ink2);word-break:break-word}
/* progress */
#barWrap{height:10px;border:1px solid var(--line);border-radius:999px;background:var(--chip);
  overflow:hidden;margin-top:8px}
#barFill{height:100%;width:0;border-radius:999px;
  background:linear-gradient(90deg,#6bc4d6,#b58cf0,#e8b24a);
  box-shadow:0 0 12px rgba(127,214,224,.5);transition:width .6s ease}
#barFill.pulse{width:35%;animation:barPulse 1.6s ease-in-out infinite}
#phaseLine{font-size:16px;color:var(--ink);margin:14px 0 2px}
.warnnote{border-left:3px solid var(--accent);border-radius:10px;
  background:rgba(232,178,74,.08);color:#e8c987;padding:9px 13px;font-family:var(--mono);
  font-size:12px;margin-top:10px}
.panelnote{border-radius:10px;padding:13px 16px;font-size:13.5px;margin-top:16px}
#slowPanel{border:1px solid rgba(232,178,74,.55);border-left:3px solid var(--accent);
  background:rgba(232,178,74,.08);color:#e8c987}
#lostPanel{border:1px solid rgba(240,131,154,.55);border-left:3px solid var(--coral);
  background:rgba(240,131,154,.07);color:#f0aebc}
.jobid{font-family:var(--mono);font-size:12px;color:var(--teal);word-break:break-all}
.err{display:none;color:var(--coral);font-family:var(--mono);font-size:11.5px;margin-top:8px}
.err.on{display:block}
.step.bad{border-color:rgba(240,131,154,.6)}
#toast{position:fixed;bottom:26px;left:50%;transform:translateX(-50%);z-index:70;
  background:var(--chip);border:1px solid var(--teal);color:var(--teal);border-radius:10px;
  padding:9px 18px;font-family:var(--mono);font-size:12px;display:none;
  box-shadow:0 0 24px rgba(67,201,214,.25)}
:focus-visible{outline:2px solid var(--focus);outline-offset:2px}
@keyframes omBreathe{0%,100%{transform:scale(1)}50%{transform:scale(1.055)}}
@keyframes omFlow{to{stroke-dashoffset:-24.2}}
@keyframes omScan{0%{transform:translateY(-120px)}100%{transform:translateY(110vh)}}
@keyframes barPulse{0%,100%{opacity:.45}50%{opacity:1}}
@media (prefers-reduced-motion:reduce){
  *{animation:none!important;transition:none!important}
  html{scroll-behavior:auto}
}
@media (max-width:720px){.hero-cells{display:none}.rk{width:120px}}
"""

_JS = r"""
/* the same esc() discipline as the dashboard/studio: every API string is untrusted.
   The single quote is escaped too (audit W8-F8): this file mixes single- and
   double-quoted attribute markup, so leaving ' unescaped meant the next esc()'d value
   dropped into a single-quoted attribute would be an XSS — a latent trap, not a hole
   we had to hit first. */
function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,c=>(
  {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}

/* ── D-071: browser-side error reporting ─────────────────────────────────────
   Errors ONLY. Nothing is sent on a healthy run: no page views, no session id, no timing,
   no identity. The two worst production bugs so far lived entirely in the browser and left
   no server trace at all — a finished scan claiming the user was offline, and an Open
   dashboard button that failed every time without ever sending a request. This is the
   narrowest thing that would have caught them.

   Capped at REPORT_MAX per page load so a render loop cannot beat on the endpoint, and
   every send is fire-and-forget: a failure to report must never become a second failure
   the student can see. The email and the plan are NEVER included — the server redacts
   anything email-shaped as a backstop, but the page simply does not send it. */
var REPORT_MAX = 6, reportsSent = 0;
function report(kind, message, extra){
  if(reportsSent >= REPORT_MAX) return;
  reportsSent++;
  try {
    var b = {kind: kind, message: String(message == null ? "" : message).slice(0, 500),
             ua: (navigator.userAgent || "").slice(0, 180)};
    if(state.jobId) b.job_id = state.jobId;
    if(state.phaseKey) b.phase = state.phaseKey;
    if(extra){ if(extra.where) b.where = String(extra.where).slice(0,200);
               if(typeof extra.status === "number") b.status = extra.status; }
    fetch(api("/api/clientlog"), {method:"POST", keepalive:true,
      headers:{"Content-Type":"application/json"}, body: JSON.stringify(b)})
      .catch(function(){});                       /* never surface a reporting failure */
  } catch(e){ /* reporting must not be able to break the page */ }
}
window.addEventListener("error", function(e){
  report("js_error", (e && e.message) || "script error",
         {where: (e && e.filename ? e.filename + ":" + e.lineno : "")});
});
window.addEventListener("unhandledrejection", function(e){
  var r = e && e.reason;
  report("unhandled_rejection", (r && (r.message || r)) || "unhandled rejection");
});

/* tuning constants (docs/FIREBASE_WEB_PLAN.md §4/§5) */
var POLL_MS = 4000;            /* status poll interval: every 4 s */
var LOST_AFTER_MS = 120000;    /* >2 min of consecutive poll errors -> lost-contact panel */
var REQ_TIMEOUT_MS = 45000;    /* cold-start-friendly timeout (§5.1) + one retry */
var SLOW_DISCOVERY_S = 300;    /* §4.2 soft expectation: discovery ~5 min */
var SLOW_PER10_S = 90;         /* §4.2 soft expectation: deep-dive ~1.5 min per 10 professors */
var SLOW_FACTOR = 1.5;         /* §4.2: past 1.5x the soft expectation -> calm slow notice */

/* ALL state lives in memory only — no browser storage, no cookies, ever (D-069:
   no client-side storage of plan/email; the unguessable job id is shown, not persisted). */
var state = {
  step: 1,
  /* `intents` is a LIST (MI-1) — several levels may be ticked. It mirrors the checked cards
     and its first element is what the derived `intent_kind` scalar becomes. */
  email: "", intents: ["pre_phd"], country: "", universities: [], uniMode: "all",
  field: "", fields: [], plan: [], variants: [], expansionOff: false, merged: null, topicTotal: 0,
  jobId: null, jobStart: 0, jobEnd: 0, lastOk: 0, watching: false,
  pollTimer: null, tickTimer: null, phaseKey: "", phaseEnter: 0, slowShown: false
};

function reducedMotion(){
  return !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion:reduce)").matches);
}
function fmtWorks(n){
  n = Number(n)||0;
  if(n>=1e6) return (n/1e6).toFixed(1).replace(/\.0$/,"")+"M works";
  if(n>=1e3) return (n/1e3).toFixed(1).replace(/\.0$/,"")+"k works";
  return n+" works";
}
function toast(msg){
  var t = document.getElementById("toast");
  t.textContent = msg; t.style.display = "block";
  clearTimeout(t._h); t._h = setTimeout(function(){ t.style.display="none"; }, 2600);
}
function showErr(id, msg){
  var e = document.getElementById(id);
  e.textContent = msg; e.classList.add("on");
  var step = e.closest(".step"); if(step) step.classList.add("bad");
  /* Every error the student is actually shown is reported (D-071). Reporting HERE rather
     than at each call site means a new error path cannot be added without it — the same
     reasoning that puts the quote gate and conflict detection at their choke points. */
  report("api_error", msg, {where: id});
}

/* What the student can hand over when something goes wrong — assembled locally, sent
   nowhere unless they choose to paste it. Contains no email and no plan. */
function diagnosticsText(){
  var lines = [
    "Supervisorly diagnostics",
    "when       : " + new Date().toISOString(),
    "job id     : " + (state.jobId || "(none)"),
    "step       : " + state.step,
    "phase      : " + (state.phaseKey || "(none)"),
    "last status: " + ((document.getElementById("phaseLine")||{}).textContent || ""),
    "error shown: " + ((document.getElementById("err-progress")||{}).textContent || "(none)"),
    "field      : " + (state.field || ""),
    "variants   : " + ((state.variants || []).join(" | ") || "(none)"),
    "topics     : " + (state.topicTotal || 0) + " offered",
    "online     : " + navigator.onLine,
    "page       : " + location.host,
    "browser    : " + (navigator.userAgent || "").slice(0, 180)
  ];
  return lines.join("\n");
}
function clearErrs(){
  document.querySelectorAll(".err").forEach(function(e){
    e.textContent=""; e.classList.remove("on"); });
  document.querySelectorAll(".step.bad").forEach(function(s){ s.classList.remove("bad"); });
}

/* ── API plumbing: the ONLY fetch() targets are the endpoint paths (D-069) ── */
function api(p){ return API_BASE + p; }
function fetchJson(url, opts, timeoutMs){
  return new Promise(function(resolve, reject){
    if(navigator.onLine === false){ reject({offline:true}); return; }
    var ctrl = new AbortController();
    var t = setTimeout(function(){ ctrl.abort(); }, timeoutMs || REQ_TIMEOUT_MS);
    opts = opts || {}; opts.signal = ctrl.signal;
    fetch(url, opts).then(function(resp){
      clearTimeout(t);
      return resp.json().catch(function(){ return {}; }).then(function(body){
        resolve({status: resp.status, body: body || {}});
      });
    }, function(err){ clearTimeout(t); reject(err); });
  });
}
/* 45 s timeout + one retry — a cold start (10–30 s, §5.1) must not kill the first try */
function withRetry(url, opts){
  return fetchJson(url, opts).then(null, function(){ return fetchJson(url, opts); });
}
function humanError(status, body, err){
  var msg = body && body.error ? String(body.error) : "";
  if(status === 503 || /source budget|midnight UTC/i.test(msg))
    /* OpenAlex itself 429'd: the honest midnight-UTC message (§5.2), never a fake empty */
    return msg || "OpenAlex's free daily budget is exhausted — it resets at midnight UTC. "+
                  "Nothing was lost; try again then.";
  /* Only claim the student is offline when they actually are. This used to fire on ANY
     rejection (`if(err || ...)`), so a request that merely timed out — a cold start
     overrunning REQ_TIMEOUT_MS, say — told a perfectly connected user they had no
     network. A wrong diagnosis is worse than a vague one: it sends them to check their
     wifi instead of pressing the button again. */
  if((err && err.offline) || navigator.onLine === false)
    return "you seem to be offline — nothing was lost; your place is kept. "+
           "Reconnect and try again.";
  if(err && (err.name === "AbortError" || err.aborted))
    return "that took longer than we allow for one request — nothing was lost; your "+
           "place is kept. Try again.";
  if(err)
    return "that request could not be completed — nothing was lost; your place is kept. "+
           "Try again.";
  if(status === 429) return msg || "too many requests — wait a little and try again.";
  if(status >= 500) return "something went wrong on our side — nothing was lost. "+
                          "Try again in a moment.";
  return msg || "something unexpected happened — nothing was lost. Try again.";
}

/* ── wizard shell ── */
function showStep(n){
  state.step = n;
  for(var i=1;i<=5;i++)
    document.getElementById("s"+i).classList.toggle("hidden", i!==n);
  document.querySelectorAll(".ritem").forEach(function(el){
    var s = Number(el.getAttribute("data-step"));
    el.classList.toggle("on", s===n);
    el.classList.toggle("done", s<n);
    el.disabled = (n===5 && s!==5);     /* a running/watched job keeps its step */
  });
  if(n===4) syncScope();
  window.scrollTo({top:0, behavior: reducedMotion()?"auto":"smooth"});
}

/* ── step 1: You ── */
function validEmail(v){ return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v); }
function renderChips(){
  var host = document.getElementById("uniChips");
  host.innerHTML = state.universities.map(function(u,i){
    return '<span class="chip">'+esc(u)+
      '<button type="button" data-uni="'+i+'" aria-label="remove '+esc(u)+'">×</button></span>';
  }).join("");
  host.querySelectorAll("button[data-uni]").forEach(function(b){
    b.addEventListener("click", function(){
      state.universities.splice(Number(b.getAttribute("data-uni")),1); renderChips(); });
  });
}
function addUniversity(){
  var inp = document.getElementById("uniInput"), v = inp.value.trim();
  if(v && state.universities.indexOf(v)<0){ state.universities.push(v); renderChips(); }
  inp.value = ""; inp.focus();
}
/* ── step 2: several fields, not one ──────────────────────────────────────────
   Most people work across more than one area, and being made to pick a single phrase first
   is the tool narrowing the search on the student's behalf before it has shown them
   anything. Each field is expanded and mapped independently and the topics are merged, so
   "ML" + "AI safety" produces the union of both literatures to choose from. MAX_FIELDS
   mirrors cli.PLAN_MAX_FIELDS: each field costs an expansion plus one map call per phrasing,
   so this is the §5.2 throttle budget of a single click as much as it is a payload cap. */
function renderFieldChips(){
  var host = document.getElementById("fieldChips");
  host.innerHTML = state.fields.map(function(f,i){
    return '<span class="chip">'+esc(f)+
      '<button type="button" data-fld="'+i+'" aria-label="remove '+esc(f)+'">×</button></span>';
  }).join("");
  host.querySelectorAll("button[data-fld]").forEach(function(b){
    b.addEventListener("click", function(){
      state.fields.splice(Number(b.getAttribute("data-fld")),1); renderFieldChips(); });
  });
}
/* No cap. There was one (6) and it refused the student's input to solve a cost problem that
   belongs to the cost layer — someone working across eight areas is exactly who this is for.
   The limiters that remain are the §5.2 throttle and the fact that every phrasing is mapped
   in ONE request (B-001), so breadth costs one unit, not one per phrasing. */
function addField(){
  var inp = document.getElementById("field"), v = inp.value.trim();
  if(!v) return;
  /* case-insensitive, so "ML" and "ml" are not two searches of the same thing */
  var dup = state.fields.some(function(x){ return x.toLowerCase()===v.toLowerCase(); });
  if(!dup) state.fields.push(v);
  inp.value = ""; inp.focus(); renderFieldChips();
}
/* Everything the student meant: the chips PLUS whatever is still sitting unadded in the box.
   Forgetting to press "+ add" before Understand is the obvious mistake, and silently
   dropping that text would search for something they did not ask for. */
function gatherFields(){
  var typed = (document.getElementById("field").value||"").trim();
  var all = state.fields.slice();
  if(typed && !all.some(function(x){ return x.toLowerCase()===typed.toLowerCase(); }))
    all.push(typed);
  return all;
}
/* How many phrasings to ask the expander for, PER field (step 2's slider, 1–50). The model
   is told to return fewer rather than pad, so a narrow field yields a short honest list at
   any setting — the number is a ceiling, never a quota. */
function variantDepth(){
  var el = document.getElementById("depthRange");
  return el ? Number(el.value)||8 : 8;
}
function gatherYou(){
  state.email = document.getElementById("email").value.trim();
  /* An ARRAY now (MI-1). No fallback default: an empty tick list is reported at step 1
     rather than quietly becoming "pre_phd" — silently searching for something the student
     did not ask for is worse than making them tick a box. */
  state.intents = Array.prototype.map.call(
    document.querySelectorAll('input[name="intent"]:checked'),
    function(r){ return r.value; });
  state.country = document.getElementById("country").value.trim();
  var m = document.querySelector('input[name="uniMode"]:checked');
  state.uniMode = m ? m.value : "all";
}
function step1Next(){
  clearErrs();
  gatherYou();
  if(!validEmail(state.email)){
    showErr("err-email",
      "a valid email is required — it joins the OpenAlex polite pool and is never shown "+
      "on any page the tool fetches.");
    document.getElementById("email").focus();
    return;
  }
  if(!state.intents.length){
    showErr("err-intent",
      "tick at least one thing you are looking for on this step — you can tick several "+
      "(a PhD and a pre-PhD position, say) and filter the results by level afterwards.");
    var first = document.querySelector('input[name="intent"]');
    if(first) first.focus();
    return;
  }
  showStep(2);
}

/* ── step 2: Field — Understand (expand best-effort, then one /api/map per variant) ── */
function setFieldStatus(msg){
  var el = document.getElementById("fieldStatus");
  el.textContent = msg;
  el.classList.toggle("hidden", !msg);
}
function expandField(f, count){
  return withRetry(api("/api/expand"), {method:"POST",
    headers:{"Content-Type":"application/json"},
    body: JSON.stringify({field:f, count: count||8})})
    .then(function(r){
      if(r.status===200 && r.body && Array.isArray(r.body.variants) && r.body.variants.length){
        if(r.body.expanded === false) state.expansionOff = true;
        /* No client-side truncation: the server already clamped to what was asked for, and
           slicing again here would silently discard phrasings the student paid for with the
           slider. */
        return r.body.variants;
      }
      /* expansion unavailable -> deterministic fallback: the student's words directly */
      state.expansionOff = true; return [f];
    }, function(){
      state.expansionOff = true; return [f];   /* any failure: proceed deterministically */
    });
}
/* Every phrasing in ONE request (B-001). The page used to call /api/map once per phrasing
   and merge here, to keep a single failing phrasing from failing the click — the server now
   reports `failed_queries`, so that honesty survives while the whole click costs one unit of
   the 30/hour budget instead of one per phrasing. With the step-2 slider asking for up to 50
   phrasings per field, per-phrasing calls would 429 on first use. */
function mapMany(variants){
  return withRetry(api("/api/map"), {method:"POST",
    headers:{"Content-Type":"application/json"},
    body: JSON.stringify({queries: variants, email: state.email})})
    .then(function(r){
      if(r.status===200 && r.body && Array.isArray(r.body.groups))
        return {ok:true, map:r.body};
      return {ok:false, status:r.status, error:(r.body && r.body.error)||""};
    }, function(e){ return {ok:false, status:0, error:"", err:e}; });
}
/* client-side multi-query merge: /api/map takes ONE field, so the page calls it per
   variant and merges here — topics dedupe by topic_id, found_by tags the variant(s)
   that surfaced each topic, identically-shaped groups (domain/field/subfield) merge. */
function mergeMaps(results){
  var byId = {}, order = [];
  results.forEach(function(r){
    var groups = (r.map && r.map.groups) || [];
    groups.forEach(function(g){
      if(!g) return;
      var topics = Array.isArray(g.topics) ? g.topics : [];
      topics.forEach(function(t){
        if(!t || !t.topic_id) return;      /* no id -> skipped, never a brick */
        var id = String(t.topic_id);
        if(!byId[id]){
          byId[id] = {domain:String(g.domain||"ungrouped"),
                      field:String(g.field||"ungrouped"),
                      subfield:String(g.subfield||"ungrouped"),
                      topic:{topic_id:id, name:String(t.name||id),
                             works_count:Number(t.works_count)||0, found_by:[r.variant]}};
          order.push(id);
        } else {
          var fb = byId[id].topic.found_by;
          if(fb.indexOf(r.variant)<0 && fb.length<8) fb.push(r.variant);
        }
      });
    });
  });
  var gmap = {}, gorder = [];
  order.forEach(function(id){
    var e = byId[id], key = e.domain+""+e.field+""+e.subfield;
    if(!gmap[key]){ gmap[key] = {domain:e.domain, field:e.field, subfield:e.subfield,
                                 topics:[]}; gorder.push(key); }
    gmap[key].topics.push(e.topic);
  });
  return {queries: results.map(function(r){ return r.variant; }),
          groups: gorder.map(function(k){ return gmap[k]; }),
          truncated: results.some(function(r){ return !!(r.map && r.map.truncated); })};
}
/* ── the search plan: what we will actually look for, before we look ──────────
   One collapsed row per field the student named, with the phrasing COUNT on the row. Open
   it and every phrasing is listed and editable — remove one that is wrong for their sense of
   the word, add one the model missed. This is the last moment before the search is defined,
   and it is the student's to correct: the expansion is a guess about their words, and a
   guess they cannot see is one they cannot fix. */
function renderFieldPlan(){
  var host = document.getElementById("fieldPlan");
  if(!state.plan || !state.plan.length){ host.classList.add("hidden"); host.innerHTML=""; return; }
  var total = state.plan.reduce(function(n,e){ return n + e.variants.length; }, 0);
  host.innerHTML =
    '<div class="fplan-h">We will search <b>'+total+'</b> phrasing'+(total===1?"":"s")+
    ' across <b>'+state.plan.length+'</b> field'+(state.plan.length===1?"":"s")+
    ' — open any field to change what it looks for.</div>'+
    state.plan.map(function(e,i){
      return '<details class="fp" data-fp="'+i+'"'+(e.open?" open":"")+'>'+
        '<summary><span class="fp-name">'+esc(e.field)+'</span>'+
        '<span class="wchip">'+e.variants.length+' phrasing'+
        (e.variants.length===1?"":"s")+'</span></summary>'+
        '<div class="chips fp-vars">'+
          e.variants.map(function(v,j){
            var own = (v.toLowerCase()===e.field.toLowerCase());
            return '<span class="chip'+(own?" chip-own":"")+'">'+esc(v)+
              (own ? '' : '<button type="button" data-rmv="'+i+':'+j+
                          '" aria-label="remove '+esc(v)+'">×</button>')+'</span>';
          }).join('')+
        '</div>'+
        '<div class="urow fp-add">'+
          '<input type="text" class="fp-in" data-addto="'+i+'" '+
            'placeholder="add a phrasing for '+esc(e.field)+'">'+
          '<button type="button" class="btn ghost" data-addbtn="'+i+'">+ add</button>'+
        '</div></details>';
    }).join('');
  host.classList.remove("hidden");
  /* keep a row's open/closed state across re-renders, or editing one snaps it shut */
  host.querySelectorAll("details.fp").forEach(function(d){
    d.addEventListener("toggle", function(){
      var e = state.plan[Number(d.getAttribute("data-fp"))];
      if(e) e.open = d.open;
    });
  });
  host.querySelectorAll("button[data-rmv]").forEach(function(b){
    b.addEventListener("click", function(){
      var p = b.getAttribute("data-rmv").split(":");
      state.plan[Number(p[0])].variants.splice(Number(p[1]),1);
      renderFieldPlan();
    });
  });
  function addTo(i, inp){
    var v = (inp.value||"").trim(); if(!v) return;
    var e = state.plan[i];
    if(!e.variants.some(function(x){ return x.toLowerCase()===v.toLowerCase(); }))
      e.variants.push(v);
    e.open = true; inp.value = ""; renderFieldPlan();
    var again = document.querySelector('input[data-addto="'+i+'"]'); if(again) again.focus();
  }
  host.querySelectorAll("button[data-addbtn]").forEach(function(b){
    b.addEventListener("click", function(){
      var i = Number(b.getAttribute("data-addbtn"));
      addTo(i, document.querySelector('input[data-addto="'+i+'"]'));
    });
  });
  host.querySelectorAll("input[data-addto]").forEach(function(inp){
    inp.addEventListener("keydown", function(ev){
      if(ev.key==="Enter"){ ev.preventDefault(); addTo(Number(inp.getAttribute("data-addto")), inp); }
    });
  });
}

/* Phase 1 of step 2: expand every field and SHOW the plan. Nothing is mapped yet. */
function understand(){
  clearErrs();
  var fields = gatherFields();
  if(!fields.length){
    showErr("err-field","describe your field first — a few words are enough."); return; }
  var btn = document.getElementById("understand");
  btn.disabled = true;
  state.fields = fields;
  renderFieldChips();
  document.getElementById("field").value = "";
  /* `field` stays a single readable string for every existing consumer (the plan, the run
     header, the worker log); `fields` is the real list. Derived, never a second source of
     truth. */
  state.field = fields.join(" · ");
  var depth = variantDepth();
  setFieldStatus(fields.length>1
    ? "Understanding "+fields.length+" fields… (a cold start can take 10–30 s)"
    : "Understanding your field… (a cold start can take 10–30 s — warming up…)");
  /* Expand each field independently. One field failing to expand costs THAT field its
     synonyms and nothing else — it falls back to the student's own words (D-068). */
  Promise.all(fields.map(function(f){
    return expandField(f, depth).then(function(vs){ return {field:f, variants:vs&&vs.length?vs:[f]}; },
                                      function(){ return {field:f, variants:[f]}; });
  })).then(function(perField){
    btn.disabled = false;
    setFieldStatus("");
    state.plan = perField.map(function(e){ return {field:e.field, variants:e.variants, open:false}; });
    renderFieldPlan();
    document.getElementById("expNote").classList.toggle("hidden", !state.expansionOff);
    document.getElementById("toMap").classList.remove("hidden");
  });
}

/* Phase 2 of step 2: map the plan the student approved. Every phrasing goes in ONE request
   (B-001) — per-phrasing calls would spend 50 units of a 30/hour budget on one click. */
function mapPlan(){
  clearErrs();
  var variants = [], seen = {};
  (state.plan||[]).forEach(function(e){
    e.variants.forEach(function(v){
      var k = String(v).toLowerCase();
      if(!seen[k]){ seen[k]=1; variants.push(v); }
    });
  });
  if(!variants.length){ showErr("err-field","nothing to search for — add a field first."); return; }
  var btn = document.getElementById("toMap");
  btn.disabled = true;
  state.variants = variants;
  setFieldStatus("Mapping "+variants.length+" phrasing"+
    (variants.length>1?"s":"")+" to the subject index…");
  mapMany(variants).then(function(r){
    btn.disabled = false;
    setFieldStatus("");
    if(!r.ok){
      showErr("err-field", humanError(r.status, {error:r.error}, r.err));
      return;
    }
    state.merged = r.map;
    state.variants = (r.map.queries||variants);
    /* build the tree inside a guard: a malformed map renders an honest note, never a brick */
    try { buildTree(); }
    catch(e){
      document.getElementById("tree").innerHTML = '<div class="empty">The subject map '+
        'could not be rendered — its entries are malformed. You can still go on by naming '+
        'professors directly below.</div>';
    }
    document.getElementById("partialBanner").classList.toggle("hidden", !state.merged.truncated);
    document.getElementById("expNote").classList.toggle("hidden", !state.expansionOff);
    /* The server now reports WHICH phrasings failed, so the honest note that used to come
       from counting per-phrasing responses survives the move to one request (B-001). */
    var failed = (state.merged.failed_queries)||[];
    var dn = document.getElementById("dropNote");
    if(failed.length){
      dn.textContent = failed.length+" phrasing"+(failed.length>1?"s":"")+
        " could not be mapped — continuing with the rest.";
      dn.classList.remove("hidden");
    } else dn.classList.add("hidden");
    updateCount();
    showStep(3);
  });
}

/* ── step 3: Disambiguate — meaning clusters + tri-state tree (the Studio's logic) ── */
function buildTree(){
  var host = document.getElementById("tree");
  var groups = (state.merged && state.merged.groups) || [];
  state.topicTotal = 0;
  if(!groups.length){
    host.innerHTML = '<div class="empty">The subject map came back empty — no topics '+
      'matched. You can still go on by naming professors directly below.</div>';
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
        var topics = Array.isArray(g.topics) ? g.topics : [];
        topics.forEach(function(t){
          if(!t || !t.topic_id) return;
          state.topicTotal++;
          var fb = (Array.isArray(t.found_by) && t.found_by.length>1) ?
            '<span class="wchip fb" title="found by: '+esc(t.found_by.join(", "))+'">'+
            esc(t.found_by.length+" phrasings")+'</span>' : "";
          html += '<li><label class="trow topic-row">'+
            '<input type="checkbox" class="topic" value="'+esc(t.topic_id)+'">'+
            '<span class="tname">'+esc(t.name)+'</span>'+fb+
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
    updateCount();
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
function updateCount(){
  var n = document.querySelectorAll("#tree input.topic:checked").length;
  document.getElementById("selCount").textContent =
    n+" of "+state.topicTotal+" topics selected";
}
function checkedTopics(){
  var ids = [];
  document.querySelectorAll("#tree input.topic:checked").forEach(function(b){
    if(b.value) ids.push(b.value); });
  return ids;
}
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
function step3Next(){
  clearErrs();
  if(!checkedTopics().length &&
     !parseProfs(document.getElementById("profs").value).length){
    showErr("err-topics",
      "check at least one topic, or name at least one professor below.");
    document.getElementById("tree").focus();
    return;
  }
  showStep(4);
}

/* ── step 4: Scope & scan — sliders, live cost preview, review, idempotent start ── */
function syncScope(){
  var raw = document.getElementById("maxInst").value;
  var n = parseInt(raw, 10);
  if(!isNaN(n))
    document.getElementById("instRange").value = String(Math.max(1, Math.min(300, n)));
  updatePreview();
}
/* §4.3 estimate: discovery 2–5 min + 1.5 min per 10 professors, rendered as a range */
function costEstimate(shortlist){
  var lo = Math.max(1, Math.round(2 + 1.5*shortlist/10));
  var hi = Math.max(lo, Math.round(5 + 1.5*shortlist/10));
  return lo+"–"+hi+" minutes";
}
function updatePreview(){
  var i = Number(document.getElementById("instRange").value);
  var s = Number(document.getElementById("profRange").value);
  document.getElementById("instVal").textContent = i;
  document.getElementById("profVal").textContent = s;
  document.getElementById("costPreview").textContent =
    "≈ "+i+" institutions + "+s+" professors ≈ "+costEstimate(s);
  buildReview();
}
function intentLabel(){
  /* Every ticked level, in card order — the review step must show what will actually be
     searched, not the first of several. */
  var labels = Array.prototype.map.call(
    document.querySelectorAll('input[name="intent"]:checked'),
    function(r){ return r.getAttribute("data-label") || r.value; });
  return labels.length ? labels.join(" · ") : "—";
}
function buildReview(){
  var unis = state.universities;
  var rows = [
    ["email", state.email],
    ["intent", intentLabel()],
    ["country", state.country || "— (no country filter)"],
    ["universities", unis.length ? unis.join(", ")+" ("+state.uniMode+")" : "—"],
    ["topics", String(checkedTopics().length)],
    ["named professors",
      String(parseProfs(document.getElementById("profs").value).length)],
    ["institutions to scan", document.getElementById("instRange").value],
    ["professors to deep-dive", document.getElementById("profRange").value]
  ];
  document.getElementById("review").innerHTML = rows.map(function(r){
    return '<div class="rrow"><span class="rk">'+esc(r[0])+'</span>'+
           '<span class="rv">'+esc(r[1])+'</span></div>';
  }).join("");
}
function startScan(){
  var btn = document.getElementById("startScan");
  /* double-click safe: the button disables instantly AND the server is idempotent
     (§3.3 — a duplicate submit returns the EXISTING job id) */
  btn.disabled = true;
  clearErrs();
  var plan = {
    /* The list is the truth, the scalar is derived — the same rule `fields`/`field` follows.
       Both travel so an older reader keeps working; the server re-derives the scalar anyway,
       so the two can never drift apart in the stored plan. */
    intent_kinds: state.intents.slice(),
    intent_kind: state.intents[0],
    country: state.country,
    resolved_topic_ids: checkedTopics(),
    field: state.field,
    /* The list is the truth; `field` above is its readable join. Both travel so an older
       reader keeps working and a newer one can tell "ML · AI safety" from a field actually
       named that. */
    fields: state.fields.slice(),
    university_mode: state.uniMode,
    universities: state.universities.slice(),
    targets: parseProfs(document.getElementById("profs").value),
    email: state.email
  };
  fetchJson(api("/api/scan"), {method:"POST",
    headers:{"Content-Type":"application/json"},
    body: JSON.stringify({email: state.email, plan: plan,
      shortlist: Number(document.getElementById("profRange").value),
      max_institutions: Number(document.getElementById("instRange").value)})})
  .then(function(r){
    if((r.status===202 || r.status===200) && r.body && r.body.job_id){
      /* 200 existing:true = a double-click/refresh — jump straight to progress */
      state.jobId = String(r.body.job_id);
      beginWatching();
      showStep(5);
    } else if(r.status===429){
      btn.disabled = false;
      showErr("err-scan", (r.body && r.body.error) ||
        "you already have an active scan job — wait for it to finish, or cancel it and "+
        "start again.");
    } else {
      btn.disabled = false;
      showErr("err-scan", humanError(r.status, r.body));
    }
  }, function(e){
    btn.disabled = false;
    showErr("err-scan", humanError(0, null, e));
  });
}

/* ── step 5: Progress — §4.1 bar + phase line, §4.2 slow state, cancel/resume ── */
/* bar math: discovery 0–30%, deep-dive 30–90% (by i/k), scoring/export 90–100%.
   Indeterminate pulse ONLY before the first count arrives (never a faked percentage). */
function barPercent(status, phase, counts){
  if(status==="done") return 100;
  var c = counts || {};
  if(phase==="scoring") return 92;
  if(phase==="exported") return 96;
  if(c.deep_dive_total){
    var i = Math.min(Number(c.deep_dive_done)||0, c.deep_dive_total);
    return Math.min(90, Math.round(30 + 60*i/c.deep_dive_total));
  }
  if(c.targets!=null) return 30;
  return null;
}
/* the §4.1 plain-language phase table, verbatim */
function phaseText(phase, data){
  var d = Array.isArray(data) ? data : [];
  switch(phase){
    case "expanding": return "Understanding your field…";
    case "map_ready": return "Found "+(d[0]!=null?d[0]:"…")+" topic areas for you to pick from.";
    case "discovering": return "Finding universities and researchers in "+
      (d[0]||"your country")+"…";
    case "enumerated": return "Found "+d[0]+" researchers across "+d[1]+
      " institutions — picking the best matches.";
    case "deep_dive_start": return "Reading the pages of the top "+d[0]+" matches…";
    case "deep_dive_progress": return "Reading professor pages — "+d[0]+" of "+d[1]+"…";
    case "gap_fill": return d[0]+" pages need the slower path — filling what we can…";
    case "scoring": return "Ranking researchers and universities…";
    case "exported": return "Building your dashboard…";
  }
  return "";
}
function setBar(pct){
  var fill = document.getElementById("barFill");
  if(pct==null){ fill.classList.add("pulse"); }
  else { fill.classList.remove("pulse"); fill.style.width = pct+"%"; }
}
function phaseGroup(phase){
  if(phase==="expanding"||phase==="map_ready"||phase==="discovering"||
     phase==="enumerated") return "discovery";
  if(phase==="deep_dive_start"||phase==="deep_dive_progress"||phase==="gap_fill")
    return "deep";
  return "";
}
function hideSlow(){ document.getElementById("slowPanel").classList.add("hidden"); }
function showSlow(){ document.getElementById("slowPanel").classList.remove("hidden"); }
/* §4.2: track the phase-enter time client-side; past 1.5x the soft expectation, show the
   calm notice with three first-class actions — never a spinner with no explanation. */
function checkSlow(phase, counts){
  var g = phaseGroup(phase);
  if(!g) return;
  if(g!==state.phaseKey){
    state.phaseKey = g; state.phaseEnter = Date.now(); state.slowShown = false;
    hideSlow();
  }
  if(state.slowShown) return;
  var soft = SLOW_DISCOVERY_S;
  if(g==="deep"){
    var k = Number(counts.deep_dive_total) ||
            Number(document.getElementById("profRange").value) || 40;
    soft = SLOW_PER10_S * (k/10);
  }
  if((Date.now()-state.phaseEnter)/1000 > SLOW_FACTOR*soft){
    state.slowShown = true;
    showSlow();
  }
}
function renderStatus(b){
  /* A fresh status from the server supersedes any earlier transient error. Without this a
     click that timed out (cancel, resume, open) left its red banner on screen, so a
     finished scan showed "Done — your dashboard is ready" and "you seem to be offline"
     at the same time — two contradictory claims, one of them stale. The server's current
     state is the truthful one; clear the older complaint. */
  var ep = document.getElementById("err-progress");
  if(ep && ep.textContent){ ep.textContent = ""; ep.classList.remove("on"); }
  var counts = b.counts || {};
  var prog = Array.isArray(b.progress) ? b.progress : [];
  var last = prog.length ? prog[prog.length-1] : null;
  var phase = last && last.phase ? last.phase : b.phase;
  var data = last ? (last.data || []) : [];
  /* bar */
  setBar(barPercent(b.status, phase, counts));
  /* phase line */
  var line;
  if(b.status==="done") line = "Done — your dashboard is ready.";
  else if(b.status==="failed") line = "Stopped — "+(b.error || "something went wrong.")+
    " Nothing is lost: resume continues where it left off.";
  else if(b.status==="cancelled") line = "Cancelled — everything gathered is kept. "+
    "Resume continues where it left off.";
  else if(b.status==="cancelling") line =
    "Stopping after the current page — keeping everything gathered…";
  else if(b.status==="queued") line = "Queued — a worker will pick your scan up shortly…";
  else line = phaseText(phase, data) || "Working…";
  document.getElementById("phaseLine").textContent = line;
  /* inline amber notes for partial_warning entries (D-037 honesty) */
  var warns = Array.isArray(b.warnings) ? b.warnings : [];
  document.getElementById("warnList").innerHTML = warns.map(function(w){
    return '<div class="warnnote">PARTIAL — '+esc(w)+'</div>';
  }).join("");
  /* terminal states: stop polling, show the honest next action (never a dead end) */
  if(b.status==="done"){
    stopPolling();
    state.jobEnd = Date.now();
    setBar(100);
    document.getElementById("cancelBtn").classList.add("hidden");
    document.getElementById("openDash").classList.remove("hidden");
    hideSlow();
  } else if(b.status==="failed" || b.status==="cancelled"){
    stopPolling();
    state.jobEnd = Date.now();
    document.getElementById("cancelBtn").classList.add("hidden");
    document.getElementById("resumeBtn").classList.remove("hidden");
    hideSlow();
  } else {
    checkSlow(phase, counts);
  }
}
function poll(){
  if(!state.jobId) return;
  fetchJson(api("/api/scan/"+state.jobId)).then(function(r){
    if(r.status===200 && r.body && r.body.status){
      state.lastOk = Date.now();
      hideLost();
      renderStatus(r.body);
    } else pollError();
  }, function(){ pollError(); });
}
function pollError(){
  if(Date.now()-state.lastOk > LOST_AFTER_MS) showLost();
}
function beginPolling(){
  stopPolling();
  state.watching = true;
  state.lastOk = Date.now();
  poll();
  state.pollTimer = setInterval(poll, POLL_MS);
  if(!state.tickTimer) state.tickTimer = setInterval(tick, 1000);
}
function stopPolling(){
  state.watching = false;
  if(state.pollTimer){ clearInterval(state.pollTimer); state.pollTimer = null; }
}
function beginWatching(){
  state.jobStart = Date.now(); state.jobEnd = 0;
  state.phaseKey = ""; state.slowShown = false;
  hideSlow(); hideLost();
  setBar(null);
  document.getElementById("phaseLine").textContent =
    "Queued — a worker will pick your scan up shortly…";
  document.getElementById("warnList").innerHTML = "";
  document.getElementById("jobNote").innerHTML =
    "job id: <span class='jobid'>"+esc(state.jobId)+"</span> — keep it; it is the key to "+
    "your scan (unguessable, never listed).";
  document.getElementById("cancelBtn").classList.remove("hidden");
  document.getElementById("resumeBtn").classList.add("hidden");
  document.getElementById("openDash").classList.add("hidden");
  beginPolling();
}
function tick(){
  if(state.jobStart){
    var end = state.jobEnd || Date.now();
    var s = Math.max(0, Math.floor((end-state.jobStart)/1000));
    var mm = String(Math.floor(s/60)).padStart(2,"0"), ss = String(s%60).padStart(2,"0");
    document.getElementById("elapsed").textContent = "elapsed "+mm+":"+ss;
  }
  if(state.watching && Date.now()-state.lastOk > LOST_AFTER_MS) showLost();
}
function cancelScan(){
  if(!state.jobId) return;
  fetchJson(api("/api/scan/"+state.jobId+"/cancel"), {method:"POST",
    headers:{"Content-Type":"application/json"}, body:"{}"})
  .then(function(r){
    if(r.status===202){
      document.getElementById("phaseLine").textContent =
        "Stopping after the current page — keeping everything gathered…";
      hideSlow();
    } else showErr("err-progress", humanError(r.status, r.body));
  }, function(e){ showErr("err-progress", humanError(0, null, e)); });
}
function resumeScan(){
  if(!state.jobId) return;
  fetchJson(api("/api/scan/"+state.jobId+"/resume"), {method:"POST",
    headers:{"Content-Type":"application/json"}, body:"{}"})
  .then(function(r){
    if(r.status===202){
      clearErrs();
      document.getElementById("resumeBtn").classList.add("hidden");
      document.getElementById("cancelBtn").classList.remove("hidden");
      document.getElementById("phaseLine").textContent =
        "Queued — resuming where the scan left off…";
      state.jobEnd = 0; state.phaseKey = ""; state.slowShown = false;
      beginPolling();
    } else showErr("err-progress", humanError(r.status, r.body));
  }, function(e){ showErr("err-progress", humanError(0, null, e)); });
}
function openDashboard(){
  if(!state.jobId) return;
  /* NAVIGATE — never fetch. /api/result answers 302 to a short-lived signed URL on a
     DIFFERENT origin (the private results bucket). A fetch follows that redirect and is
     then blocked by CORS, so the button could never work on the hosted deployment: it
     always ended in "that request could not be completed". JS cannot read the redirect
     target either — with redirect:"manual" the response is an opaqueredirect whose
     Location header is unreadable by design. A top-level navigation follows the redirect
     natively, with no CORS involved.

     It also has to happen SYNCHRONOUSLY inside the click handler: window.open after an
     await has lost the user-gesture context and popup blockers eat it.

     The dashboard opens in a NEW TAB, never iframed (CSP/sandbox conflicts). */
  window.open(api("/api/result/"+encodeURIComponent(state.jobId)), "_blank", "noopener");
}
/* polling resilience: >2 min of consecutive poll errors -> the lost-contact panel.
   The job id is the access token, so the student can re-attach from anywhere. */
function showLost(){
  document.getElementById("lostJobId").textContent = state.jobId || "";
  document.getElementById("lostPanel").classList.remove("hidden");
}
function hideLost(){ document.getElementById("lostPanel").classList.add("hidden"); }
function resumeById(){
  var v = document.getElementById("resumeId").value.trim();
  if(!v) return;
  state.jobId = v;
  hideLost();
  state.jobStart = Date.now(); state.jobEnd = 0;
  state.phaseKey = ""; state.slowShown = false;
  document.getElementById("jobNote").innerHTML =
    "job id: <span class='jobid'>"+esc(state.jobId)+"</span>";
  document.getElementById("cancelBtn").classList.remove("hidden");
  beginPolling();
}

document.addEventListener("DOMContentLoaded", function(){
  /* wire every control FIRST — a failing API call can then never take down the page */
  renderChips();
  document.getElementById("email").addEventListener("input", function(e){
    var v = e.target.value.trim();
    var err = document.getElementById("err-email");
    if(v && !validEmail(v)){ err.textContent = "that does not look like an email yet.";
      err.classList.add("on"); }
    else { err.textContent = ""; err.classList.remove("on"); }
  });
  document.getElementById("toStep2").addEventListener("click", step1Next);
  document.getElementById("uniAdd").addEventListener("click", addUniversity);
  document.getElementById("uniInput").addEventListener("keydown", function(e){
    if(e.key==="Enter"){ e.preventDefault(); addUniversity(); } });
  document.getElementById("understand").addEventListener("click", understand);
  document.getElementById("fieldAdd").addEventListener("click", addField);
  document.getElementById("toMap").addEventListener("click", mapPlan);
  document.getElementById("depthRange").addEventListener("input", function(){
    document.getElementById("depthVal").textContent = variantDepth();
  });
  /* Enter ADDS the field rather than submitting: with a multi-value input, submitting on the
     first Enter would make a second field unreachable from the keyboard. Understand is the
     explicit button, as it already was. */
  document.getElementById("field").addEventListener("keydown", function(e){
    if(e.key==="Enter"){ e.preventDefault(); addField(); } });
  document.getElementById("back2").addEventListener("click", function(){ showStep(1); });
  document.getElementById("toStep4").addEventListener("click", step3Next);
  document.getElementById("back3").addEventListener("click", function(){ showStep(2); });
  document.getElementById("instRange").addEventListener("input", updatePreview);
  document.getElementById("profRange").addEventListener("input", updatePreview);
  document.getElementById("startScan").addEventListener("click", startScan);
  document.getElementById("back4").addEventListener("click", function(){ showStep(3); });
  document.getElementById("cancelBtn").addEventListener("click", cancelScan);
  document.getElementById("resumeBtn").addEventListener("click", resumeScan);
  document.getElementById("openDash").addEventListener("click", openDashboard);
  document.getElementById("copyDiag").addEventListener("click", function(){
    var txt = diagnosticsText();
    var done = function(){ toast("diagnostics copied — paste them when reporting"); };
    if(navigator.clipboard && navigator.clipboard.writeText){
      navigator.clipboard.writeText(txt).then(done, function(){ fallbackCopy(txt, done); });
    } else fallbackCopy(txt, done);
    /* the student asked for this, so the same detail goes to the log too — the one place
       a report is deliberately BOTH local and sent (D-071) */
    report("diagnostics", "student copied diagnostics", {where: "copyDiag"});
  });
  function fallbackCopy(txt, done){
    var ta = document.createElement("textarea");
    ta.value = txt; ta.setAttribute("readonly", "");
    ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); done(); }
    catch(e){ toast("could not copy — select the text manually"); }
    document.body.removeChild(ta);
  }
  document.getElementById("resumeIdBtn").addEventListener("click", resumeById);
  document.getElementById("resumeId").addEventListener("keydown", function(e){
    if(e.key==="Enter"){ e.preventDefault(); resumeById(); } });
  document.getElementById("slowWait").addEventListener("click", function(){
    state.slowShown = true; hideSlow(); });
  document.getElementById("slowPause").addEventListener("click", function(){
    hideSlow(); cancelScan();
    toast("pausing — press resume when you're back; everything gathered is kept"); });
  document.getElementById("slowCancel").addEventListener("click", function(){
    hideSlow(); cancelScan(); });
  document.querySelectorAll(".ritem").forEach(function(b){
    b.addEventListener("click", function(){
      var n = Number(b.getAttribute("data-step"));
      if(n < state.step && n>=1 && state.step!==5) showStep(n);
    });
  });
  /* Escape closes any transient UI */
  document.addEventListener("keydown", function(e){
    if(e.key==="Escape"){
      document.getElementById("toast").style.display = "none";
      if(state.slowShown) hideSlow();
    }
  });
});
"""


def build_webapp(*, api_base: str = "") -> str:
    """Return the complete Supervisorly web-app HTML document.

    ``api_base`` is the Functions base URL injected at deploy time (the
    ``<API_BASE_URL>`` placeholder passes through verbatim; ``""`` = same-origin for
    local dev / hosted rewrite). It is build-time trusted config, never user data, and
    is the ONLY value interpolated raw into the JS — everything from the API goes
    through the page's ``esc()`` discipline.
    """
    # a plain JSON string literal (NOT _inline_json): the deploy placeholder must survive
    # verbatim for substitution; api_base is trusted build-time config by contract
    api_literal = _json.dumps(str(api_base))

    # MI-1: checkboxes, not radios. A student is rarely after exactly one thing — someone open
    # to a PhD, a pre-PhD post and a master's had to pick one and hide the rest. The card
    # styling is unchanged on purpose: this is the same control answering a better question.
    intent_cards = "".join(
        f'<label class="rcard"><input type="checkbox" name="intent" value="{key}"'
        f' data-label="{title}"{" checked" if key == "pre_phd" else ""}>'
        f'<span class="rc-t">{title}</span>'
        f'<span class="rc-d">{desc}</span></label>'
        for key, title, desc in INTENTS)

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Supervisorly — Find your supervisor</title>
<style>{_CSS}</style></head>
<body>
<div class="scan" aria-hidden="true"></div>
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
  <div class="eyebrow">Supervisorly · Web Scan</div>
  <h1>Find your supervisor, live.</h1>
  <p class="sub">Five steps, no command line: say who you are, describe your field, keep the
    meanings you meant, choose how big the search is, and watch it run — with an honest
    progress bar and a safe exit at every point. No account; nothing is stored in your
    browser.</p>
</header>
<main>
  <nav class="rail" aria-label="steps">
    <button type="button" class="ritem on" data-step="1"><b>01</b>You</button>
    <button type="button" class="ritem" data-step="2"><b>02</b>Field</button>
    <button type="button" class="ritem" data-step="3"><b>03</b>Disambiguate</button>
    <button type="button" class="ritem" data-step="4"><b>04</b>Scope &amp; scan</button>
    <button type="button" class="ritem" data-step="5"><b>05</b>Progress</button>
  </nav>

  <section class="step" id="s1">
    <div class="step-head"><span class="step-code">STEP 01</span><h2>You</h2></div>
    <p class="why">Who to contact and what you're looking for. The email is required — it
      identifies you to the OpenAlex polite pool and is never shown on any page the tool
      fetches.</p>
    <label for="email">Contact email</label>
    <input type="email" id="email" placeholder="you@university.edu" autocomplete="email">
    <div class="err" id="err-email" role="alert"></div>
    <p class="why" style="margin-top:18px">Intent — it gates how candidates are scored.</p>
    <div class="rcards" role="group" aria-label="what you are looking for — tick every level you would consider">{intent_cards}</div>
    <div class="err hidden" id="err-intent"></div>
    <p class="why" style="margin-top:18px">Country (name or ISO code) — where the
      country-wide search runs.</p>
    <input type="text" id="country" placeholder="e.g. Canada or CA">
    <p class="why" style="margin-top:18px">Universities <span style="color:var(--faint);
      font-weight:400">(optional)</span> — add institutions, then choose how the search
      treats them.</p>
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
    <p class="why" style="margin-top:18px">Institutions cap <span style="color:var(--faint);
      font-weight:400">(optional)</span> — you can fine-tune this on the scope step.</p>
    <input type="number" id="maxInst" min="1" max="300" step="1"
      placeholder="optional — max institutions (1–300)">
    <div class="btnrow"><button type="button" class="btn big" id="toStep2">Next: your field →</button></div>
  </section>

  <section class="step hidden" id="s2">
    <div class="step-head"><span class="step-code">STEP 02</span><h2>Field</h2></div>
    <p class="why">A few words in your own phrasing — "NLP", "mechanistic interpretability",
      "causal ML". Add <b>as many as you like</b>: most people work across more than one, and
      "ML", "AI safety" and "NLP" are three doors into overlapping literatures. Each one is
      expanded (best-effort) and mapped to the OpenAlex subject index, and the results are
      merged into one set of meanings to choose from. If smart expansion is unavailable, your
      words are used directly — never a fake result.</p>
    <label for="field">Your field(s), in your words</label>
    <div class="urow">
      <input type="text" id="field" placeholder="e.g. machine learning">
      <button type="button" class="btn ghost" id="fieldAdd">+ add</button>
    </div>
    <div class="chips" id="fieldChips"></div>
    <div class="sliderblock" style="margin-top:18px">
      <label for="depthRange">Related phrasings to look for, per field — synonyms, acronyms,
        adjacent subfields</label>
      <input type="range" id="depthRange" min="1" max="50" value="8" step="1">
      <div class="hint"><span id="depthVal">8</span> per field · wider finds more meanings;
        a narrow field simply returns fewer, never padding</div>
    </div>
    <div class="err" id="err-field" role="alert"></div>
    <div id="fieldPlan" class="fplan hidden"></div>
    <p class="note hidden" id="fieldStatus" role="status"></p>
    <div class="btnrow">
      <button type="button" class="btn ghost" id="back2">← back</button>
      <button type="button" class="btn big" id="understand">Understand →</button>
      <button type="button" class="btn big hidden" id="toMap">Map these meanings →</button>
    </div>
  </section>

  <section class="step hidden" id="s3">
    <div class="step-head"><span class="step-code">STEP 03</span><h2>Disambiguate</h2></div>
    <p class="why">These are the meanings we found, grouped as meaning clusters — nothing is
      pre-checked; check the ones you mean. The tool presents senses, never guesses.</p>
    <div class="trunc hidden" id="partialBanner" role="note">PARTIAL MAP — the API returned
      more topics than shown; this map is partial, not complete. Narrow your wording for
      the rest, or pick from what is here.</div>
    <p class="note hidden" id="expNote">smart expansion is off — using your words directly.</p>
    <p class="note hidden" id="dropNote"></p>
    <div id="tree" tabindex="0"></div>
    <div class="selcount" id="selCount" role="status">0 of 0 topics selected</div>
    <div class="err" id="err-topics" role="alert"></div>
    <p class="why" style="margin-top:18px">Named professors <span style="color:var(--faint);
      font-weight:400">(optional)</span> — deep-dive specific people directly, one per line:
      <span style="font-family:var(--mono)">Name, Affiliation (optional)</span> — the
      affiliation is everything after the last comma, so
      <span style="font-family:var(--mono)">King, Jr., MIT</span> parses correctly.</p>
    <textarea id="profs" placeholder="Ada Maple, McGill University&#10;Grace Hopper"></textarea>
    <div class="btnrow">
      <button type="button" class="btn ghost" id="back3">← back</button>
      <button type="button" class="btn big" id="toStep4">Next: scope &amp; scan →</button>
    </div>
  </section>

  <section class="step hidden" id="s4">
    <div class="step-head"><span class="step-code">STEP 04</span><h2>Scope &amp; scan</h2></div>
    <p class="why">How big the search is. The caps protect the shared budget; the defaults
      protect your afternoon; the choice is yours.</p>
    <div class="sliderblock">
      <label for="instRange">Universities to scan — the top N institutions in the country,
        ranked by relevance</label>
      <input type="range" id="instRange" min="1" max="300" value="25" step="1">
      <div class="hint"><span id="instVal">25</span> institutions · smaller is faster and cheaper</div>
    </div>
    <div class="sliderblock">
      <label for="profRange">Professors to deep-dive — we read the pages of the best N
        matches thoroughly; the rest stay listed, unchecked</label>
      <input type="range" id="profRange" min="1" max="200" value="40" step="1">
      <div class="hint"><span id="profVal">40</span> professors</div>
    </div>
    <p class="costline" id="costPreview">≈ 25 institutions + 40 professors ≈ 8–11 minutes</p>
    <div class="review" id="review" aria-label="review"></div>
    <div class="err" id="err-scan" role="alert"></div>
    <div class="btnrow">
      <button type="button" class="btn ghost" id="back4">← back</button>
      <button type="button" class="btn big" id="startScan">Start scan →</button>
    </div>
  </section>

  <section class="step hidden" id="s5">
    <div class="step-head"><span class="step-code">STEP 05</span><h2>Progress</h2></div>
    <div id="barWrap" role="progressbar" aria-label="scan progress"><div id="barFill"></div></div>
    <p id="phaseLine" role="status">Queued…</p>
    <div class="hint" id="elapsed">elapsed 00:00</div>
    <div class="hint" id="jobNote"></div>
    <div id="warnList"></div>
    <div class="panelnote hidden" id="slowPanel" role="note">
      This is taking longer than usual — the source sites are slow today. You can keep
      waiting, or pause and resume later, or cancel and keep what we have.
      <div class="btnrow">
        <button type="button" class="btn ghost" id="slowWait">keep waiting</button>
        <button type="button" class="btn ghost" id="slowPause">pause &amp; resume later</button>
        <button type="button" class="btn ghost" id="slowCancel">cancel &amp; keep what we have</button>
      </div>
    </div>
    <div class="panelnote hidden" id="lostPanel" role="alert">
      Lost contact with the server — your scan keeps running; nothing is lost. Your job id
      is <span class="jobid" id="lostJobId"></span>; paste it later to resume watching.
      <div class="urow" style="margin-top:10px">
        <input type="text" id="resumeId" placeholder="paste a job id to resume watching">
        <button type="button" class="btn ghost" id="resumeIdBtn">resume watching</button>
      </div>
    </div>
    <div class="err" id="err-progress" role="alert"></div>
    <div class="btnrow">
      <button type="button" class="btn ghost" id="cancelBtn">Cancel scan</button>
      <button type="button" class="btn hidden" id="resumeBtn">Resume scan</button>
      <button type="button" class="btn big hidden" id="openDash">Open dashboard ↗</button>
      <button type="button" class="btn ghost" id="copyDiag">Copy diagnostics</button>
    </div>
    <div class="hint">cancel stops after the current page and keeps everything gathered —
      resume continues where it left off. The dashboard opens in a new tab.
      <b>Copy diagnostics</b> puts what happened on your clipboard — job id, phase and any
      error, with no email and no results — so you can paste it when reporting a problem.
      Nothing is sent by pressing it.</div>
  </section>
</main>
<div id="toast" role="status"></div>
<script>const API_BASE = {api_literal};
{_JS}</script>
</body></html>
"""
