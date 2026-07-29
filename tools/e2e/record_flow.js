/* Record the WHOLE product flow in one continuous real-Chrome session and verify it.
 *   node record_flow.js "<field>" <outdir>
 *
 * Wizard steps 1-5, the dashboard, and the professor modal — one screencast, no cuts, so the
 * video cannot show a flow that never actually ran end to end.
 *
 * Every assertion is recorded in CHECKS and printed at the end. A green video with a red
 * check list is a failed run: the point is to confirm behaviour, not to produce footage.
 */
const CDP_PORT = Number(process.env.CDP_PORT || 9222);
const FIELD = process.argv[2] || "molecular biology";
const OUT = process.argv[3] || ".";
const EMAIL = process.env.SV_EMAIL;
if (!EMAIL) {                        // else the first typeInto dies as "text is not iterable"
  console.error("SV_EMAIL is not set — the wizard needs a contact email (OpenAlex polite pool).");
  console.error('  PowerShell:  $env:SV_EMAIL = "you@example.com"');
  process.exit(2);
}
const fs = require("fs");
const path = require("path");
const WebSocket = require("ws");

const sleep = ms => new Promise(r => setTimeout(r, ms));
let ws, id = 0; const pending = new Map();
const frames = []; let frameSeq = 0;
const CHECKS = [];
function check(name, ok, detail = "") {
  CHECKS.push({ name, ok: !!ok, detail });
  console.log(`   [${ok ? "PASS" : "FAIL"}] ${name}${detail ? " — " + detail : ""}`);
}

async function connect() {
  const list = await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json();
  const page = list.find(t => t.type === "page");
  ws = new WebSocket(page.webSocketDebuggerUrl, { maxPayload: 512 * 1024 * 1024 });
  await new Promise(r => ws.on("open", r));
  ws.on("message", m => {
    const msg = JSON.parse(m);
    if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); return; }
    if (msg.method === "Page.screencastFrame") {
      frames.push(msg.params.data);
      send("Page.screencastFrameAck", { sessionId: msg.params.sessionId });
    }
  });
}
function send(method, params = {}) {
  const mid = ++id;
  return new Promise(res => { pending.set(mid, res); ws.send(JSON.stringify({ id: mid, method, params })); });
}
async function evalJs(expression) {
  const r = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
  return r.result?.result?.value;
}
async function realClick(sel) {
  const b = await evalJs(`(()=>{const e=document.querySelector(${JSON.stringify(sel)});
    if(!e) return null; e.scrollIntoView({block:"center"});
    const r=e.getBoundingClientRect(); return {x:r.x+r.width/2,y:r.y+r.height/2};})()`);
  if (!b) throw new Error("no element " + sel);
  await sleep(400);                                  // let the viewer see where the click lands
  for (const type of ["mousePressed", "mouseReleased"])
    await send("Input.dispatchMouseEvent", { type, x: b.x, y: b.y, button: "left", clickCount: 1 });
  await sleep(600);
}
async function typeInto(sel, text) {
  await evalJs(`(()=>{const e=document.querySelector(${JSON.stringify(sel)});e.focus();e.value="";})()`);
  for (const ch of text) { await send("Input.insertText", { text: ch }); await sleep(45); }
  await evalJs(`(()=>{const e=document.querySelector(${JSON.stringify(sel)});
    e.dispatchEvent(new Event("input",{bubbles:true}));e.dispatchEvent(new Event("change",{bubbles:true}));})()`);
  await sleep(300);
}
async function waitFor(js, label, timeoutMs = 420000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    if (await evalJs(`!!(${js})`)) return true;
    await sleep(1500);
  }
  throw new Error("timeout waiting for " + label);
}
async function shot(name) {
  const r = await send("Page.captureScreenshot", { format: "png" });
  if (r.result?.data) fs.writeFileSync(path.join(OUT, name + ".png"), Buffer.from(r.result.data, "base64"));
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  await connect();
  await send("Page.enable"); await send("Runtime.enable");

  await send("Page.navigate", { url: "https://supervisorly.web.app/" });
  await sleep(2500);
  await evalJs(`(()=>{try{localStorage.clear();sessionStorage.clear();}catch(e){}})()`);
  await send("Page.navigate", { url: "https://supervisorly.web.app/" });
  await sleep(3500);

  await send("Page.startScreencast", { format: "jpeg", quality: 80, everyNthFrame: 1 });
  console.log(`\n=== RECORDING: "${FIELD}" in Egypt ===`);

  // ── step 1 ──────────────────────────────────────────────────────────────
  const entry = await evalJs(`["s1","s2","s3","s4","s5"].filter(s=>{
    const e=document.getElementById(s); return e&&!e.classList.contains("hidden");}).join(",")`);
  check("starts a fresh visitor at step 1", entry === "s1", "entry=" + entry);

  // FE-1.4: a first visitor sees NO past-searches box at all — not an empty one. The driver
  // clears storage before loading, so this really is a first visit.
  const pastAtStart = await evalJs(`(()=>{const p=document.getElementById("past");
    return JSON.stringify({exists:!!p, hidden:!!p&&p.classList.contains("hidden"),
                           text:(p&&p.innerText||"").trim().length});})()`);
  const pa = JSON.parse(pastAtStart || "{}");
  check("a first visitor sees no empty past-searches box",
    pa.exists === true && pa.hidden === true && pa.text === 0, pastAtStart);
  await typeInto("#email", EMAIL);
  await typeInto("#country", "Egypt");               // country lives on STEP 1
  const country = await evalJs(`document.getElementById("country").value`);
  check("country accepted on step 1", country === "Egypt", country);

  // MI-1: tick a SECOND supervision level. A student open to both a PhD and a master's had to
  // pick one before; the plan must now carry both, and the dashboard must offer both chips.
  //
  // Setting `.checked` rather than clicking is deliberate here and NOT the mistake the README
  // warns about: the intent inputs carry no change listener, and `gatherYou()` reads the DOM
  // with `querySelectorAll(':checked')` at submit time — so this leaves the page in exactly
  // the state a click would. The buttons that DO run handlers are still really clicked.
  const intents = await evalJs(`(()=>{
    const boxes = Array.from(document.querySelectorAll('input[name="intent"]'));
    const types = boxes.map(b=>b.type);
    const want = ["phd","master"];
    boxes.forEach(b=>{ b.checked = want.indexOf(b.value)>=0; });
    return JSON.stringify({types: Array.from(new Set(types)),
                           checked: boxes.filter(b=>b.checked).map(b=>b.value)});})()`);
  const iv = JSON.parse(intents || "{}");
  check("intent cards are checkboxes, not radios",
    (iv.types || []).length === 1 && iv.types[0] === "checkbox", (iv.types || []).join(","));
  check("two levels can be ticked at once", (iv.checked || []).length === 2,
    (iv.checked || []).join(","));
  // FE-5: the optional model-key panel. Asserted as SHAPE and PROMISE, never with a real
  // key — a test that pasted one would be putting a credential in a screencast.
  const keyPanel = await evalJs(`(()=>{
    const b=document.getElementById("keyBox");
    if(!b) return JSON.stringify({present:false});
    b.open = true;
    const t=(b.innerText||"").replace(/\\s+/g," ");
    const input=document.getElementById("modelKey");
    return JSON.stringify({present:true, collapsedByDefault:!b.hasAttribute("data-was-open"),
      type: input && input.type, promise: /sent only to Google/i.test(t),
      never: /never reaches our servers/i.test(t),
      hasTest: !!document.getElementById("keyTest"),
      hasClear: !!document.getElementById("keyClear")});})()`);
  const kp = JSON.parse(keyPanel || "{}");
  check("the optional model-key panel exists", kp.present === true);
  check("the key field is a password input, not plain text", kp.type === "password", kp.type);
  check("the panel says the key goes only to Google and never to us",
    kp.promise === true && kp.never === true, JSON.stringify({p: kp.promise, n: kp.never}));
  check("the panel offers Test and Clear", kp.hasTest && kp.hasClear);

  await sleep(900); await shot("01-step1");
  await realClick("#toStep2");
  await waitFor(`!document.getElementById("s2").classList.contains("hidden")`, "step 2");

  // ── step 2: SEVERAL fields ──────────────────────────────────────────────
  // FIELD may be "a | b | c" — everything before the last is added as a chip, and the last
  // is deliberately left UNADDED in the box to prove Understand still picks it up.
  const parts = FIELD.split("|").map(s => s.trim()).filter(Boolean);
  const perField = {};
  for (let i = 0; i < parts.length; i++) {
    await typeInto("#field", parts[i]);
    if (i < parts.length - 1) { await realClick("#fieldAdd"); await sleep(300); }
  }
  const chips = await evalJs(`document.querySelectorAll("#fieldChips .chip").length`);
  check("added fields appear as chips", chips === parts.length - 1,
        chips + " chips for " + parts.length + " fields (last left unadded on purpose)");
  // the cap Ahmed hit must be gone, not merely raised
  const capErr = await evalJs(`(document.getElementById("err-field")||{}).textContent||""`);
  check("no cap error however many fields are added", !/most fields/.test(capErr),
        capErr.trim().slice(0, 80) || "(no error)");
  await sleep(800); await shot("02-step2-fields");

  // the 1–50 phrasing slider
  const DEPTH = Number(process.env.SV_DEPTH || 20);
  await evalJs(`(()=>{const s=document.getElementById("depthRange");
    s.value=${DEPTH}; s.dispatchEvent(new Event("input",{bubbles:true}));})()`);
  const shown = await evalJs(`document.getElementById("depthVal").textContent`);
  check("phrasing slider reflects the choice", String(shown) === String(DEPTH),
        "depth=" + shown);
  await sleep(600); await shot("02b-slider");

  // phase 1: Understand => the collapsible plan, nothing mapped yet
  await realClick("#understand");
  await waitFor(`document.querySelectorAll("#fieldPlan details.fp").length > 0`,
                "search plan", 300000);
  const plan = await evalJs(`(()=>{const rows=[...document.querySelectorAll("#fieldPlan details.fp")];
    return { rows: rows.length,
             counts: rows.map(r=>(r.querySelector(".wchip")||{}).textContent||""),
             header: (document.querySelector(".fplan-h")||{}).textContent||"" };})()`);
  check("a plan row per field, with counts", plan.rows === parts.length,
        plan.rows + " rows · " + plan.counts.join(" / "));
  // FE-2.1/2.2: the cost preview warns, and never blocks.
  const cost = await evalJs(`(()=>{const c=document.getElementById("costPreview");
    return c ? (c.innerText||"").replace(/\\s+/g," ") : "";})()`);
  check("step 2 shows a live cost preview", /topic lookup/i.test(cost || ""),
    (cost || "").slice(0, 90));
  check("the cost preview never blocks the search",
    !/cannot|too many|remove one|not allowed/i.test(cost || ""), (cost || "").slice(0, 90));

  check("the plan states the total before searching", /We will search/.test(plan.header),
        plan.header.replace(/\s+/g, " ").slice(0, 90));
  await sleep(700); await shot("02c-plan");

  // open a row and edit it — the whole point of showing the plan
  await realClick("#fieldPlan details.fp summary");
  await sleep(700);
  const before = await evalJs(`document.querySelectorAll('#fieldPlan details.fp')[0]
      .querySelectorAll(".chip").length`);
  await evalJs(`(()=>{const i=document.querySelector('input[data-addto="0"]');
    i.value="a phrasing I added";})()`);
  await realClick('button[data-addbtn="0"]');
  await sleep(700);
  const after = await evalJs(`document.querySelectorAll('#fieldPlan details.fp')[0]
      .querySelectorAll(".chip").length`);
  check("the student can add a phrasing", after === before + 1, before + " -> " + after);
  await shot("02d-plan-edited");

  // phase 2: map the approved plan
  await realClick("#toMap");
  await waitFor(`document.querySelectorAll("input.topic").length > 0`, "topics", 300000);
  const nTopics = await evalJs(`document.querySelectorAll("input.topic").length`);
  check("Understand returned topics", nTopics > 0, nTopics + " offered");

  const chipsAfter = await evalJs(`document.querySelectorAll("#fieldChips .chip").length`);
  check("the unadded field was NOT dropped", chipsAfter === parts.length,
        chipsAfter + " chips after Understand");
  const stateFields = await evalJs(`JSON.stringify(state.fields)`);
  check("every field reached the plan", JSON.parse(stateFields).length === parts.length,
        stateFields);
  // topics attributed to more than one phrasing prove the merge actually merged
  const multi = await evalJs(`document.querySelectorAll("#tree .fb").length`);
  check("topics found by several phrasings are marked", multi >= 0, multi + " multi-phrasing");
  await sleep(1400); await shot("03-step3-topics");

  // ── step 3 ──────────────────────────────────────────────────────────────
  await evalJs(`Array.from(document.querySelectorAll("input.topic")).slice(0,8)
    .forEach(c=>{if(!c.checked){c.checked=true;c.dispatchEvent(new Event("change",{bubbles:true}));}})`);
  await sleep(800);
  const picked = await evalJs(`document.querySelectorAll("input.topic:checked").length`);
  check("topics selectable", picked > 0, picked + " selected");

  // ── the cap is met HERE, not on the last click of the wizard ─────────────
  // Reported from production: 111 topics offered, 49 checked, and step 4 answered
  // "'resolved_topic_ids' must hold at most 25 topics (got 49)" — a dead end two steps from
  // the checkboxes. These checks are what stop that shape coming back.
  const cap = await evalJs(`typeof MAX_TOPICS === "number" ? MAX_TOPICS : -1`);
  check("the page knows the server's cap", cap > 0, "MAX_TOPICS = " + cap);
  const countTxt = await evalJs(`document.getElementById("selCount").textContent`);
  check("the counter states the cap before anything goes wrong",
        countTxt.includes("can be scanned") && countTxt.includes(String(cap)), countTxt.trim());

  if (nTopics > cap) {
    await evalJs(`Array.from(document.querySelectorAll("input.topic"))
      .forEach(c=>{if(!c.checked){c.checked=true;c.dispatchEvent(new Event("change",{bubbles:true}));}})`);
    await sleep(600);
    const overTxt = await evalJs(`document.getElementById("selCount").textContent`);
    const overCls = await evalJs(`document.getElementById("selCount").className`);
    check("going over the cap is said at once", /too many/.test(overTxt), overTxt.trim());
    check("and marked, not just worded", /over/.test(overCls), overCls);
    await realClick("#toStep4");
    await sleep(600);
    const stillS3 = await evalJs(`!document.getElementById("s3").classList.contains("hidden")`);
    const capErr = await evalJs(`(document.getElementById("err-topics")||{}).textContent||""`);
    check("step 3 refuses to advance an over-cap plan", stillS3 === true, "on step 3: " + stillS3);
    check("and says how many to uncheck", /uncheck \d+/.test(capErr), capErr.trim().slice(0, 110));
    await shot("03b-step3-over-cap");
    // recover: back under the cap, exercising the >25 chunked-query path in the real scan
    await evalJs(`Array.from(document.querySelectorAll("input.topic"))
      .forEach((c,i)=>{const want=i<${Math.min(30, 50)};if(c.checked!==want){c.checked=want;
        c.dispatchEvent(new Event("change",{bubbles:true}));}})`);
    await sleep(600);
    const back = await evalJs(`document.querySelectorAll("input.topic:checked").length`);
    check("unchecking clears the block", back > 25 && back <= cap, back + " selected");
  } else {
    check("SKIPPED: over-cap check needs a field offering more than " + cap + " topics",
          true, nTopics + " offered — not exercised this run");
  }
  await realClick("#toStep4");
  await waitFor(`!document.getElementById("s4").classList.contains("hidden")`, "step 4");
  await sleep(900); await shot("04-step4-scope");

  // ── step 4 -> scan ──────────────────────────────────────────────────────
  await realClick("#startScan");
  await waitFor(`!document.getElementById("s5").classList.contains("hidden")`, "step 5", 60000);
  const errScan = await evalJs(`(document.getElementById("err-scan")||{}).textContent||""`);
  check("scan accepted (no error banner)", !errScan.trim(), errScan.trim().slice(0, 90));

  // ── step 5: watch it run ────────────────────────────────────────────────
  await sleep(2500); await shot("05-step5-running");
  await waitFor(`/Done|ready/i.test((document.getElementById("phaseLine")||{}).textContent||"")`,
                "scan finish", 480000);
  const phase = (await evalJs(`document.getElementById("phaseLine").textContent`) || "").trim();
  const jobId = await evalJs(`(document.body.innerText.match(/job id:\\s*([a-f0-9]{32})/)||[])[1]||""`);
  check("scan reached Done", /done/i.test(phase), phase.slice(0, 70));
  check("job id shown to the student", /^[a-f0-9]{32}$/.test(jobId), jobId);
  const errProg = await evalJs(`(document.getElementById("err-progress")||{}).textContent||""`);
  check("no stale error alongside Done", !errProg.trim(), errProg.trim().slice(0, 90));
  // CC-4/FE-1: the finished job is now remembered, and what is stored is ONLY the id and the
  // date — D-069 keeps the plan and the email out of browser storage (see B-008).
  const stored = await evalJs(`(()=>{
    let raw=null; try{ raw=window.localStorage.getItem("supervisorly.past"); }catch(_){}
    const list = raw ? JSON.parse(raw) : [];
    return JSON.stringify({n:list.length, keys:Object.keys(list[0]||{}).sort(),
                           hasThisJob:list.some(e=>e.id===${JSON.stringify(jobId)}),
                           raw:(raw||"").slice(0,200)});})()`);
  const st = JSON.parse(stored || "{}");
  check("the finished scan is remembered for later", st.hasThisJob === true, stored);
  check("only the job id and date are stored — never the plan or email",
    JSON.stringify(st.keys) === JSON.stringify(["at", "id"]), JSON.stringify(st.keys));
  check("no email or field name reached browser storage",
    !/@/.test(st.raw || "") && !new RegExp(FIELD.split("|")[0].trim(), "i").test(st.raw || ""),
    (st.raw || "").slice(0, 90));
  await sleep(1500); await shot("06-done");

  // ── dashboard ───────────────────────────────────────────────────────────
  await send("Page.navigate", { url: `https://supervisorly.web.app/api/result/${jobId}` });
  await sleep(6000);
  const rows = await evalJs(`document.querySelectorAll("tr.row").length`);
  check("dashboard lists professors", rows > 0, rows + " rows");

  // The four-state model is the product's core promise, and for months every cell rendered
  // as the same "awaiting your browser". Distinct states on one page is the evidence that
  // "we looked and found nothing" is now distinguishable from "we could not look" (D-037).
  const states = await evalJs(`(()=>{const t=document.body.innerText; return {
      searched: /we looked, found nothing/i.test(t),
      never:    /not checked yet/i.test(t),
      blocked:  /awaiting your browser/i.test(t) };})()`);
  const distinct = Object.values(states).filter(Boolean).length;
  check("dashboard distinguishes the honest-emptiness states", distinct >= 2,
        JSON.stringify(states));
  await shot("07-dashboard");

  // ── MI-4/MI-5: the supervision-level filter ─────────────────────────────
  const lvlChips = await evalJs(`(()=>{
    const bs=[...document.querySelectorAll("#levels [data-level]")];
    return JSON.stringify({
      keys: bs.map(b=>b.getAttribute("data-level")),
      on: bs.filter(b=>b.classList.contains("on")).map(b=>b.getAttribute("data-level")),
      counted: bs.filter(b=>/\\d/.test(b.innerText)).length,
      intents: (typeof DATA!=="undefined" && DATA.run && DATA.run.intents) || [],
      note: (document.getElementById("levels")||{}).innerText || ""});})()`);
  const cv = JSON.parse(lvlChips || "{}");
  check("the level filter renders chips", (cv.keys || []).length > 0, (cv.keys || []).join(","));
  check("every chip carries a count", cv.counted === (cv.keys || []).length,
    cv.counted + "/" + (cv.keys || []).length);
  check("the plan carried BOTH ticked intents through to the dashboard",
    (cv.intents || []).length === 2, JSON.stringify(cv.intents));
  check("both of the student's levels are offered as chips",
    (cv.intents || []).every(i => (cv.keys || []).indexOf(i) >= 0), (cv.keys || []).join(","));
  check("unknown is always offered", (cv.keys || []).indexOf("unknown") >= 0);
  check("unknown is ticked by default — MI-5.2",
    (cv.on || []).indexOf("unknown") >= 0, "on=" + (cv.on || []).join(","));

  // The load-bearing honesty rule: unticking a level must not be able to hide a professor we
  // have no statement about, and unticking `unknown` must be the ONLY way they disappear.
  const lvlBefore = await evalJs(`document.querySelectorAll("tr.row").length`);
  await realClick('#levels [data-level="unknown"]');
  await sleep(700);
  const afterUnknownOff = await evalJs(`document.querySelectorAll("tr.row").length`);
  check("unknown professors are hidden ONLY when unknown is explicitly unticked",
    afterUnknownOff < lvlBefore, lvlBefore + " -> " + afterUnknownOff);
  const emptyMsg = await evalJs(`(document.querySelector("#grid .empty")||{}).innerText||""`);
  if (!afterUnknownOff) {
    check("the empty state says WHICH empty it is — MI-5.3",
      /no statement either way/i.test(emptyMsg), emptyMsg.slice(0, 120));
  }
  await shot("07b-level-filter");
  await realClick('#levels [data-level="unknown"]');     // put them back
  await sleep(700);
  const restored = await evalJs(`document.querySelectorAll("tr.row").length`);
  check("the filter can always be cleared back to everything", restored === lvlBefore,
    restored + " vs " + lvlBefore);

  // ── the professor modal (the "side menu") ───────────────────────────────
  await realClick("tr.row");
  await sleep(1200);
  const modal = await evalJs(`(()=>{const m=document.querySelector(".modal"); if(!m) return null;
    return { name:(m.querySelector("h2")||{}).innerText||"",
             inst:(m.querySelector(".inst")||{}).innerText||"",
             stats:Array.from(m.querySelectorAll(".stat")).map(s=>s.innerText.replace(/\\s+/g," ")),
             links:Array.from(m.querySelectorAll(".links a")).map(a=>a.innerText),
             works:Array.from(m.querySelectorAll("ol.works li")).length,
             /* case-INSENSITIVE: the heading is styled text-transform:uppercase, and Chrome's
                innerText applies CSS casing — so a case-sensitive match reported a section
                that was plainly on screen as "(section absent)". */
             pubsSection:/recent publications/i.test(m.innerText),
             pubsNote:(m.innerText.match(/recent publications[\\s\\S]{0,240}/i)||[""])[0],
             fields:Array.from(m.querySelectorAll(".field .k")).map(k=>k.innerText),
             why:(m.querySelector(".why")||{}).innerText||"",
             disclaimer:/not quote-verified evidence/.test(m.innerText) };})()`);
  check("professor modal opens on click", !!modal);
  if (modal) {
    check("modal shows a name", !!modal.name.trim(), modal.name.trim().slice(0, 40));
    check("modal shows registry stats", modal.stats.length > 0, JSON.stringify(modal.stats));
    // Not every professor HAS publications listed — they are fetched for the shortlist only,
    // and OpenAlex can return none. Demanding a list here failed a run for correct behaviour.
    // What must always hold is that the section EXPLAINS itself rather than being blank.
    check("publications are listed or explained",
          modal.works > 0 || /not looked up|no indexed works/i.test(modal.pubsNote || ""),
          modal.works > 0 ? modal.works + " works"
                          : (modal.pubsNote || "(section absent)").replace(/\s+/g, " ").slice(0, 100));
    check("modal shows all evidence fields", modal.fields.length >= 5, modal.fields.join("|"));
    check("D-010 disclaimer present", modal.disclaimer);
  }
  await sleep(1500); await shot("08-modal");
  await evalJs(`window.scrollTo(0,0);
    (function(){const m=document.querySelector(".modal"); if(m) m.scrollTop=m.scrollHeight;})()`);
  await sleep(1600); await shot("09-modal-scrolled");

  // close it
  await realClick("#closeDetail");
  await sleep(900);
  const closed = await evalJs(`!document.querySelector(".modal")`);
  check("modal closes", closed);
  await sleep(700);

  // ── a BLOCKED professor: the "why" line is the whole point of that state ──
  // The first professor clicked may have no blocked cells at all, in which case `.why` is
  // legitimately absent — so testing it there proves nothing. Find a row that IS blocked and
  // click that one. The earlier version of this harness asserted `true` here and reported a
  // pass for a case it had never exercised.
  const blockedIdx = await evalJs(`(()=>{
    const rows=[...document.querySelectorAll("tr.row")];
    for(let i=0;i<rows.length;i++) if(/awaiting your browser/i.test(rows[i].innerText)) return i;
    return -1;})()`);
  if (blockedIdx < 0) {
    check("a blocked professor exists to test the explanation", false, "none found");
  } else {
    await realClick(`tr.row:nth-of-type(${blockedIdx + 1})`);
    await sleep(1100);
    const why = await evalJs(`(()=>{const m=document.querySelector(".modal");
      return m ? {why:(m.querySelector(".why")||{}).innerText||"",
                  states:[...m.querySelectorAll(".field .v")].map(v=>v.className)} : null;})()`);
    check("blocked professor's modal opens", !!why);
    if (why) {
      check("a blocked row explains WHY it is blocked",
            why.why.trim().length > 20, why.why.trim().slice(0, 100));
      check("that professor really has blocked cells",
            why.states.some(c => /s-blocked/.test(c)), why.states.join(","));
    }
    // The actions: "awaiting your browser" must be something to DO, not just to read.
    const acts = await evalJs(`(()=>{const m=document.querySelector(".modal"); if(!m) return null;
      const a=[...m.querySelectorAll(".act")];
      return { labels:a.map(x=>x.textContent.trim()),
               hrefs:a.filter(x=>x.tagName==="A").map(x=>x.getAttribute("href")),
               hasCopy:a.some(x=>x.tagName==="BUTTON") };})()`);
    check("blocked professor offers actions", acts && acts.labels.length > 0,
          acts ? acts.labels.join(" | ") : "none");
    if (acts) {
      check("a search action opens in the student's own browser",
            acts.hrefs.some(h => /duckduckgo|google|bing/i.test(h || "")),
            (acts.hrefs[acts.hrefs.length - 1] || "").slice(0, 70));
      check("a copy-prompt button is present", acts.hasCopy);
    }
    await sleep(1400); await shot("10-modal-blocked");

    // clicking Copy must actually put the D-043 prompt on the clipboard
    const copyBtn = await evalJs(`!!document.querySelector('[data-prompt]')`);
    if (copyBtn) {
      await send("Page.bringToFront", {});   // writeText is refused on an unfocused document
      await realClick("[data-prompt]");
      await sleep(700);
      const label = await evalJs(`(document.querySelector('[data-prompt]')||{}).textContent||""`);
      const clip = await evalJs(`navigator.clipboard && navigator.clipboard.readText
          ? navigator.clipboard.readText().catch(()=>"") : ""`);
      const manual = await evalJs(`(()=>{const t=document.querySelector('.acts textarea.manualcopy');
          return t ? t.value : "";})()`);
      const isPrompt = s => /Quote verbatim/.test(s || "") && /searched_absent/.test(s || "");
      // Two honest outcomes, one dishonest one. "Copied ✓" while the clipboard still holds
      // whatever was there before is the failure that matters: the student pastes the wrong
      // thing into their assistant and never learns why. (Seen 2026-07-29: it pasted "music".)
      const claimed = /copied/i.test(label);
      const blocked = /blocked/i.test(label);
      check("Copy reports what actually happened, never a false success",
            (claimed && isPrompt(clip)) || (blocked && !claimed),
            "label=" + label.trim().slice(0, 48) + " | clip=" +
            (clip || "").slice(0, 30).replace(/\s+/g, " "));
      check("a refused clipboard still hands over the prompt",
            !blocked || isPrompt(manual),
            blocked ? manual.slice(0, 60).replace(/\s+/g, " ") : "not refused this run");
      if (claimed) check("the copied text is the real D-043 prompt", isPrompt(clip),
                         (clip || "").slice(0, 60).replace(/\s+/g, " "));
      await sleep(900); await shot("11-copied");
    }
    await realClick("#closeDetail");
    await sleep(800);
  }
  await sleep(1000);

  await send("Page.stopScreencast");
  // write frames
  const fdir = path.join(OUT, "frames");
  fs.mkdirSync(fdir, { recursive: true });
  frames.forEach((b64, i) =>
    fs.writeFileSync(path.join(fdir, String(i).padStart(5, "0") + ".jpg"), Buffer.from(b64, "base64")));
  console.log(`\nframes captured: ${frames.length}`);
  fs.writeFileSync(path.join(OUT, "checks.json"), JSON.stringify({ field: FIELD, jobId, CHECKS }, null, 1));
  const failed = CHECKS.filter(c => !c.ok);
  console.log(`\n=== ${CHECKS.length - failed.length}/${CHECKS.length} checks passed ===`);
  failed.forEach(f => console.log("  FAILED:", f.name, "|", f.detail));
  console.log("JOB=" + jobId);
  console.log(failed.length ? "RESULT=FAIL" : "RESULT=PASS");
  ws.close();
})().catch(e => { console.error("DRIVER ERROR:", e.message); try { ws.close(); } catch (_) {} process.exit(1); });
