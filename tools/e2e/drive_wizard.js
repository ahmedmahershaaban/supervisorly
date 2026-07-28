/* Drive the real product in a REAL Chrome window, all five wizard steps, then open a
   professor and read the modal back. Usage: node drive.js "<field>" <outdir>

   Uses Input.dispatchMouseEvent for the clicks that matter rather than scripted .click():
   a scripted click is not a trusted gesture, and an earlier round of this work reported a
   working button as broken because of exactly that. */
const CDP_PORT = Number(process.env.CDP_PORT || 9222);
const FIELD = process.argv[2] || "law";
const OUT = process.argv[3] || ".";
const EMAIL = process.env.SV_EMAIL;
const fs = require("fs");
const path = require("path");

const sleep = ms => new Promise(r => setTimeout(r, ms));
let ws, id = 0; const pending = new Map();

async function connect() {
  const list = await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json();
  const page = list.find(t => t.type === "page");
  const WebSocket = require("ws");
  ws = new WebSocket(page.webSocketDebuggerUrl, { maxPayload: 256 * 1024 * 1024 });
  await new Promise(r => ws.on("open", r));
  ws.on("message", m => {
    const msg = JSON.parse(m);
    if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
  });
}
function send(method, params = {}) {
  const mid = ++id;
  return new Promise(res => { pending.set(mid, res); ws.send(JSON.stringify({ id: mid, method, params })); });
}
async function evalJs(expression) {
  const r = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
  if (r.result?.exceptionDetails) throw new Error(JSON.stringify(r.result.exceptionDetails).slice(0, 300));
  return r.result?.result?.value;
}
async function shot(name) {
  const r = await send("Page.captureScreenshot", { format: "png" });
  if (r.result?.data) {
    fs.writeFileSync(path.join(OUT, name + ".png"), Buffer.from(r.result.data, "base64"));
    console.log("   [shot]", name + ".png");
  }
}
/* A real, trusted click at the element's centre. */
async function realClick(sel) {
  const box = await evalJs(`(()=>{const e=document.querySelector(${JSON.stringify(sel)});
    if(!e) return null; e.scrollIntoView({block:"center"});
    const r=e.getBoundingClientRect(); return {x:r.x+r.width/2,y:r.y+r.height/2};})()`);
  if (!box) throw new Error("no element " + sel);
  for (const type of ["mousePressed", "mouseReleased"])
    await send("Input.dispatchMouseEvent", { type, x: box.x, y: box.y, button: "left", clickCount: 1 });
  await sleep(350);
}
async function typeInto(sel, text) {
  await evalJs(`(()=>{const e=document.querySelector(${JSON.stringify(sel)});e.focus();e.value="";})()`);
  for (const ch of text) await send("Input.insertText", { text: ch });
  await evalJs(`(()=>{const e=document.querySelector(${JSON.stringify(sel)});
    e.dispatchEvent(new Event("input",{bubbles:true}));e.dispatchEvent(new Event("change",{bubbles:true}));})()`);
  await sleep(150);
}
async function waitFor(js, label, timeoutMs = 300000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    if (await evalJs(`!!(${js})`)) return true;
    await sleep(2000);
  }
  throw new Error("timeout waiting for " + label);
}

(async () => {
  await connect();
  await send("Page.enable"); await send("Runtime.enable");
  console.log(`\n=== FIELD: ${FIELD} ===`);
  await send("Page.navigate", { url: "https://supervisorly.web.app/" });
  await sleep(3000);
  // The product deliberately REMEMBERS an unfinished job so a student never loses their
  // place, which means a second run does not start at step 1 — it restores the last one.
  // A fresh-visitor test has to actually be a fresh visitor.
  await evalJs(`(()=>{try{localStorage.clear();sessionStorage.clear();}catch(e){}})()`);
  await send("Page.navigate", { url: "https://supervisorly.web.app/" });
  await sleep(4000);
  const startStep = await evalJs(`["s1","s2","s3","s4","s5"].filter(function(s){
      var e=document.getElementById(s); return e && !e.classList.contains("hidden");}).join(",")`);
  console.log("   entry step:", startStep);

  // step 1 — email
  await typeInto("#email", EMAIL);
  await realClick("#toStep2");
  await waitFor(`!document.getElementById("s2").classList.contains("hidden")`, "step 2");

  // step 2 — field + Understand
  await typeInto("#field", FIELD);
  await shot("01-field-" + FIELD.replace(/\W+/g, "_"));
  await realClick("#understand");
  await waitFor(`document.querySelectorAll("input.topic").length > 0`, "topics", 180000);
  const nTopics = await evalJs(`document.querySelectorAll("input.topic").length`);
  console.log("   topics offered:", nTopics);
  await shot("02-topics-" + FIELD.replace(/\W+/g, "_"));

  // step 3 — select the first few topics
  await evalJs(`Array.from(document.querySelectorAll("input.topic")).slice(0,6)
      .forEach(c=>{if(!c.checked){c.checked=true;c.dispatchEvent(new Event("change",{bubbles:true}));}})`);
  await sleep(400);
  await realClick("#toStep4");
  await waitFor(`!document.getElementById("s4").classList.contains("hidden")`, "step 4");

  // step 4 — scope, then scan
  await evalJs(`(()=>{const c=document.getElementById("country");
     if(c){c.value="Egypt";c.dispatchEvent(new Event("input",{bubbles:true}));
           c.dispatchEvent(new Event("change",{bubbles:true}));}})()`);
  await shot("03-scope-" + FIELD.replace(/\W+/g, "_"));
  await realClick("#startScan");

  // step 5 — wait for the run
  await waitFor(`/ready|done|Done/.test(document.getElementById("phaseLine")?.textContent||"")
                 || !document.getElementById("openDash")?.classList.contains("hidden")`,
                "scan finish", 420000);
  const phase = await evalJs(`document.getElementById("phaseLine")?.textContent||""`);
  const jobId = await evalJs(`(document.body.innerText.match(/job id:\\s*([a-f0-9]{32})/)||[])[1]||""`);
  console.log("   phase:", phase.trim().slice(0, 80));
  console.log("   job  :", jobId);
  await shot("04-done-" + FIELD.replace(/\W+/g, "_"));

  fs.writeFileSync(path.join(OUT, "job-" + FIELD.replace(/\W+/g, "_") + ".txt"), jobId);
  console.log("RESULT_JOB=" + jobId);
  ws.close();
})().catch(e => { console.error("DRIVER FAILED:", e.message); process.exit(1); });
