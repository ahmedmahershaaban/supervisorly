/* Convert the guide PNGs to WebP data URIs using Chrome's own canvas encoder.
   No image library needed. Writes a JSON map {filename: dataURI} for the HTML builder. */
const { spawn } = require("child_process");
const http = require("http");
const fs = require("fs");
const path = require("path");
const WebSocket = require("ws");

const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const PORT = 9488;
const [SRC, OUTJSON, PROFILE, QUALITY] = process.argv.slice(2);

const get = (p) => new Promise((res, rej) => {
  http.get({ host: "127.0.0.1", port: PORT, path: p }, r => {
    let b = ""; r.on("data", d => b += d); r.on("end", () => res(JSON.parse(b)));
  }).on("error", rej);
});
const sleep = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  const chrome = spawn(CHROME, ["--headless=new", "--disable-gpu", "--no-sandbox",
    `--remote-debugging-port=${PORT}`, "--user-data-dir=" + PROFILE, "about:blank"],
    { stdio: "ignore" });
  let t = null;
  for (let i = 0; i < 60 && !t; i++) {
    await sleep(500);
    try { t = (await get("/json/list")).filter(x => x.type === "page"); } catch {}
  }
  if (!t?.length) { console.log("ATTACH_FAILED"); chrome.kill(); return; }
  const ws = new WebSocket(t[0].webSocketDebuggerUrl, { maxPayload: 512 * 1024 * 1024 });
  let id = 0; const pend = new Map();
  const send = (m, p) => new Promise(r => { const i = ++id; pend.set(i, r);
    ws.send(JSON.stringify({ id: i, method: m, params: p })); });
  ws.on("message", m => { const d = JSON.parse(m);
    if (d.id && pend.has(d.id)) { pend.get(d.id)(d.result); pend.delete(d.id); } });
  await new Promise(r => ws.on("open", r));
  await send("Runtime.enable");

  const files = fs.readdirSync(SRC).filter(f => f.endsWith(".png")).sort();
  const out = {};
  let before = 0, after = 0;
  for (const f of files) {
    const png = fs.readFileSync(path.join(SRC, f));
    before += png.length;
    const src = "data:image/png;base64," + png.toString("base64");
    const r = await send("Runtime.evaluate", {
      awaitPromise: true, returnByValue: true,
      expression: `new Promise(function(res){
        var im = new Image();
        im.onload = function(){
          var c = document.createElement('canvas');
          c.width = im.naturalWidth; c.height = im.naturalHeight;
          c.getContext('2d').drawImage(im, 0, 0);
          res(c.toDataURL('image/webp', ${QUALITY}));
        };
        im.onerror = function(){ res(""); };
        im.src = ${JSON.stringify(src)};
      })`,
    });
    const uri = r?.result?.value || "";
    if (!uri.startsWith("data:image/webp")) { console.log(`  !! ${f} conversion failed`); continue; }
    out[f] = uri;
    const kb = Math.round(uri.length * 0.75 / 1024);
    after += uri.length * 0.75;
    console.log(`  ${f.padEnd(36)} ${String(Math.round(png.length/1024)).padStart(4)} KB -> ${String(kb).padStart(3)} KB webp`);
  }
  fs.writeFileSync(OUTJSON, JSON.stringify(out));
  console.log(`\n  total ${Math.round(before/1024)} KB -> ${Math.round(after/1024)} KB ` +
              `(${Math.round(100 - after/before*100)}% smaller)`);
  ws.close(); chrome.kill();
})();
