/* Open a finished dashboard in the real browser, click a professor, and read the modal back.
   Usage: node modal.js <jobId> <label> <outdir> */
const CDP_PORT = Number(process.env.CDP_PORT || 9222);
const JOB = process.argv[2], LABEL = process.argv[3] || "run", OUT = process.argv[4] || ".";
const fs = require("fs"), path = require("path");
const sleep = ms => new Promise(r => setTimeout(r, ms));
let ws, id = 0; const pending = new Map();

async function connect() {
  const list = await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json();
  const page = list.find(t => t.type === "page");
  const WebSocket = require("ws");
  ws = new WebSocket(page.webSocketDebuggerUrl, { maxPayload: 256 * 1024 * 1024 });
  await new Promise(r => ws.on("open", r));
  ws.on("message", m => { const msg = JSON.parse(m);
    if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); } });
}
const send = (method, params = {}) => { const mid = ++id;
  return new Promise(res => { pending.set(mid, res); ws.send(JSON.stringify({ id: mid, method, params })); }); };
async function evalJs(e) {
  const r = await send("Runtime.evaluate", { expression: e, returnByValue: true, awaitPromise: true });
  return r.result?.result?.value;
}
async function shot(name) {
  const r = await send("Page.captureScreenshot", { format: "png" });
  if (r.result?.data) { fs.writeFileSync(path.join(OUT, name + ".png"), Buffer.from(r.result.data, "base64"));
    console.log("   [shot]", name + ".png"); }
}
async function realClick(sel) {
  const b = await evalJs(`(()=>{const e=document.querySelector(${JSON.stringify(sel)});
    if(!e) return null; e.scrollIntoView({block:"center"});
    const r=e.getBoundingClientRect(); return {x:r.x+r.width/2,y:r.y+r.height/2};})()`);
  if (!b) throw new Error("no element " + sel);
  for (const type of ["mousePressed", "mouseReleased"])
    await send("Input.dispatchMouseEvent", { type, x: b.x, y: b.y, button: "left", clickCount: 1 });
  await sleep(500);
}

(async () => {
  await connect(); await send("Page.enable"); await send("Runtime.enable");
  await send("Page.navigate", { url: `https://supervisorly.web.app/api/result/${JOB}` });
  await sleep(5000);
  const n = await evalJs(`document.querySelectorAll("tr.row").length`);
  console.log(`   dashboard rows: ${n}`);
  if (!n) { console.log("   NO ROWS"); ws.close(); return; }
  await shot(`10-dash-${LABEL}`);

  await realClick("tr.row");                       // a real click on the first professor
  const open = await evalJs(`!!document.querySelector(".modal")`);
  console.log("   modal opened:", open);
  if (!open) { await shot(`11-nomodal-${LABEL}`); ws.close(); process.exit(2); }
  await shot(`11-modal-${LABEL}`);

  const info = await evalJs(`(()=>{const m=document.querySelector(".modal");
    return {
      name: m.querySelector("h2")?.innerText||"",
      inst: m.querySelector(".inst")?.innerText||"",
      stats: Array.from(m.querySelectorAll(".stat")).map(s=>s.innerText.replace(/\\s+/g," ")),
      links: Array.from(m.querySelectorAll(".links a")).map(a=>a.innerText),
      works: Array.from(m.querySelectorAll("ol.works li")).slice(0,4).map(l=>l.innerText.replace(/\\s+/g," ")),
      why:  m.querySelector(".why")?.innerText||"",
      disclaimer: /not quote-verified evidence/.test(m.innerText),
    };})()`);
  console.log("   name  :", info.name);
  console.log("   inst  :", info.inst);
  console.log("   stats :", JSON.stringify(info.stats));
  console.log("   links :", JSON.stringify(info.links));
  console.log("   works :", info.works.length, info.works.slice(0,2));
  console.log("   why   :", (info.why||"").slice(0,110));
  console.log("   D-010 disclaimer present:", info.disclaimer);
  fs.writeFileSync(path.join(OUT, `modal-${LABEL}.json`), JSON.stringify(info, null, 1));
  ws.close();
})().catch(e => { console.error("MODAL FAILED:", e.message); process.exit(1); });
