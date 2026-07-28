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
  await typeInto("#email", EMAIL);
  await typeInto("#country", "Egypt");               // country lives on STEP 1
  const country = await evalJs(`document.getElementById("country").value`);
  check("country accepted on step 1", country === "Egypt", country);
  await sleep(900); await shot("01-step1");
  await realClick("#toStep2");
  await waitFor(`!document.getElementById("s2").classList.contains("hidden")`, "step 2");

  // ── step 2 ──────────────────────────────────────────────────────────────
  await typeInto("#field", FIELD);
  await sleep(700); await shot("02-step2-field");
  await realClick("#understand");
  await waitFor(`document.querySelectorAll("input.topic").length > 0`, "topics", 240000);
  const nTopics = await evalJs(`document.querySelectorAll("input.topic").length`);
  check("Understand returned topics", nTopics > 0, nTopics + " offered");
  await sleep(1200); await shot("03-step3-topics");

  // ── step 3 ──────────────────────────────────────────────────────────────
  await evalJs(`Array.from(document.querySelectorAll("input.topic")).slice(0,8)
    .forEach(c=>{if(!c.checked){c.checked=true;c.dispatchEvent(new Event("change",{bubbles:true}));}})`);
  await sleep(800);
  const picked = await evalJs(`document.querySelectorAll("input.topic:checked").length`);
  check("topics selectable", picked > 0, picked + " selected");
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

  // ── the professor modal (the "side menu") ───────────────────────────────
  await realClick("tr.row");
  await sleep(1200);
  const modal = await evalJs(`(()=>{const m=document.querySelector(".modal"); if(!m) return null;
    return { name:(m.querySelector("h2")||{}).innerText||"",
             inst:(m.querySelector(".inst")||{}).innerText||"",
             stats:Array.from(m.querySelectorAll(".stat")).map(s=>s.innerText.replace(/\\s+/g," ")),
             links:Array.from(m.querySelectorAll(".links a")).map(a=>a.innerText),
             works:Array.from(m.querySelectorAll("ol.works li")).length,
             fields:Array.from(m.querySelectorAll(".field .k")).map(k=>k.innerText),
             why:(m.querySelector(".why")||{}).innerText||"",
             disclaimer:/not quote-verified evidence/.test(m.innerText) };})()`);
  check("professor modal opens on click", !!modal);
  if (modal) {
    check("modal shows a name", !!modal.name.trim(), modal.name.trim().slice(0, 40));
    check("modal shows registry stats", modal.stats.length > 0, JSON.stringify(modal.stats));
    check("modal lists recent publications", modal.works > 0, modal.works + " works");
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
      await realClick("[data-prompt]");
      await sleep(700);
      const label = await evalJs(`(document.querySelector('[data-prompt]')||{}).textContent||""`);
      check("Copy gives feedback that it worked", /copied/i.test(label), label.trim());
      const clip = await evalJs(`navigator.clipboard && navigator.clipboard.readText
          ? navigator.clipboard.readText().catch(()=>"") : ""`);
      if (clip) check("the copied text is the real D-043 prompt",
                      /Quote verbatim/.test(clip) && /searched_absent/.test(clip),
                      clip.slice(0, 60).replace(/\s+/g, " "));
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
