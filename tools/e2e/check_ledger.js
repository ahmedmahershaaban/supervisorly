/* CC-1 — open a finished dashboard, switch to "How it works", and read the phase ledger back.
   Usage: node check_ledger.js <jobId> <outdir>

   The point is the acceptance criterion, not the screenshot: a phase that reached NOTHING must
   still be on the page, with its reason. A panel that renders only the productive phases would
   pass a "does it render" test and still be the silence CC-1 exists to remove.
*/
const CDP_PORT = Number(process.env.CDP_PORT || 9222);
const JOB = process.argv[2], OUT = process.argv[3] || ".";
const fs = require("fs"), path = require("path");
const sleep = ms => new Promise(r => setTimeout(r, ms));
let ws, id = 0; const pending = new Map();
const CHECKS = [];
function check(name, ok, detail = "") {
  CHECKS.push({ name, ok: !!ok, detail });
  console.log(`   [${ok ? "PASS" : "FAIL"}] ${name}${detail ? " — " + detail : ""}`);
}

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
  if (r.result?.data) {
    fs.writeFileSync(path.join(OUT, name + ".png"), Buffer.from(r.result.data, "base64"));
    console.log("   [shot]", name + ".png");
  }
}
async function realClick(sel) {
  // Never element.click(): a scripted click is not a trusted gesture and once reported a
  // working button as broken (tools/e2e/README.md).
  const b = await evalJs(`(()=>{const e=document.querySelector(${JSON.stringify(sel)});
    if(!e) return null; e.scrollIntoView({block:"center"});
    const r=e.getBoundingClientRect();
    const x=r.x+r.width/2, y=r.y+r.height/2;
    const hit=document.elementFromPoint(x,y);
    return {x, y, hittable: !!hit && (hit===e || e.contains(hit))};})()`);
  if (!b) throw new Error("no element " + sel);
  if (!b.hittable) throw new Error(`${sel} is covered at its centre — a click would hit something else`);
  // A mouseMoved first: a press that arrives with no prior pointer position over the target
  // is dropped in some window states, which looks exactly like a broken button.
  await send("Input.dispatchMouseEvent", { type: "mouseMoved", x: b.x, y: b.y });
  for (const type of ["mousePressed", "mouseReleased"])
    await send("Input.dispatchMouseEvent", { type, x: b.x, y: b.y, button: "left", clickCount: 1 });
  await sleep(600);
}

(async () => {
  await connect(); await send("Page.enable"); await send("Runtime.enable");
  // Input events go to the FOCUSED target. Without this the clicks are accepted by CDP and
  // silently do nothing whenever another tab is frontmost — which is exactly how this script
  // first "proved" the panel while screenshotting the table view.
  await send("Page.bringToFront");
  await send("Page.navigate", { url: `https://supervisorly.web.app/api/result/${JOB}` });
  await sleep(6000);

  // Bare `DATA`, not `window.DATA`: the dashboard declares it as a top-level `const` in a
  // classic script, which binds in script scope and never lands on `window`. The first
  // version of this check read `window.DATA`, got undefined, and reported a working ledger
  // as missing — the same false alarm the README warns about for scripted clicks.
  const ledgerData = await evalJs(
    `JSON.stringify((typeof DATA!=="undefined"&&DATA.run&&DATA.run.ledger)||[])`);
  const rows = JSON.parse(ledgerData || "[]");
  check("the export carries a phase ledger", rows.length > 0, `${rows.length} rows`);
  console.log("   ledger:", JSON.stringify(rows.map(r =>
    ({ p: r.phase, a: r.attempted, r: r.reached, s: r.skipped }))));

  await realClick("#vHow");
  await sleep(1200);          // the view switch also redraws the diagram; let it settle
  // If synthetic input was dropped (it is, when the window is not the OS-focused one), fall
  // back to the page's OWN view switcher and SAY SO. Screenshotting the table view while
  // claiming to show the ledger is the failure this branch exists to prevent.
  let switchedBy = "click";
  if (await evalJs(`document.getElementById("how").classList.contains("hidden")`)) {
    switchedBy = "setView()";
    await evalJs(`setView("how")`);
    await sleep(900);
    console.log("   [note] synthetic click was dropped by the window; used the page's own "
                + "setView(\"how\") instead. This checks the PANEL, not the button.");
  }
  // NOT innerText: for an element that is not being rendered, innerText falls back to
  // textContent, so a hidden panel reads exactly like a shown one. Ask the layout instead.
  const box = await evalJs(`(()=>{const e=document.getElementById("ledger");
    if(!e) return null; const r=e.getBoundingClientRect();
    return {h:Math.round(r.height), w:Math.round(r.width), rendered:!!e.offsetParent};})()`);
  check("the ledger panel is actually rendered, not just present in the DOM",
    !!(box && box.rendered && box.h > 0), JSON.stringify(box));

  const text = await evalJs(`document.getElementById("ledger").innerText`);
  check("the panel is titled", /What each phase did/i.test(text || ""));

  // The acceptance criterion: zero-reach phases are PRESENT, with a reason.
  const zeroReach = rows.filter(r => Number(r.reached) === 0);
  const named = zeroReach.filter(r => (text || "").includes(r.phase));
  check("every zero-reach phase is on the page", zeroReach.length > 0 && named.length === zeroReach.length,
    `${named.length}/${zeroReach.length} shown: ${zeroReach.map(r => r.phase).join(",")}`);
  const reasons = zeroReach.filter(r => r.reason && (text || "").includes(r.reason.slice(0, 25)));
  check("each of those carries its reason", reasons.length === zeroReach.length,
    `${reasons.length}/${zeroReach.length}`);

  // FLAG-2 in production: the off phase explains itself and names the variable.
  check("an off phase names PHASES so it can be turned on", /PHASES=/.test(text || ""),
    (text || "").split("\n").find(l => /PHASES=/.test(l)) || "not found");

  // Assert the view state AT CAPTURE TIME. A screenshot taken on the assumption that a click
  // landed is how a green image ends up documenting the wrong panel.
  const view = await evalJs(`(()=>({
    how: !document.getElementById("how").classList.contains("hidden"),
    grid: !document.getElementById("grid").classList.contains("hidden"),
    onBtn: (document.querySelector(".vbtn.on")||{}).id || null}))()`);
  check("the How-it-works view is the active one at capture time",
    view && view.how && !view.grid, JSON.stringify(view) + ` (switched by ${switchedBy})`);
  await evalJs(`document.getElementById("ledger").scrollIntoView({block:"center"})`);
  await sleep(500);
  await shot("20-ledger-panel");

  const failed = CHECKS.filter(c => !c.ok);
  console.log(`\n=== ${CHECKS.length - failed.length}/${CHECKS.length} checks passed ===`);
  console.log("RESULT=" + (failed.length ? "FAIL" : "PASS"));
  ws.close();
  process.exit(failed.length ? 1 : 0);
})().catch(e => { console.error("ERROR", e); process.exit(3); });
