/* Read the live page's step-5 state out of the already-open Chrome (CDP 9222).
 * Used when a recorded run times out and the question is "did the scan finish, or hang?" */
const WebSocket = require("ws");
const PORT = Number(process.env.CDP_PORT || 9222);

(async () => {
  const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
  const t = list.find(x => x.type === "page" && /supervisorly/.test(x.url || ""));
  if (!t) { console.log("no supervisorly page open"); process.exit(1); }
  const ws = new WebSocket(t.webSocketDebuggerUrl, { perMessageDeflate: false });
  await new Promise(r => ws.on("open", r));
  let id = 0;
  const evalJs = expr => new Promise((res, rej) => {
    const mid = ++id;
    const on = raw => {
      const m = JSON.parse(raw);
      if (m.id !== mid) return;
      ws.off("message", on);
      if (m.error) return rej(new Error(m.error.message));
      res(m.result && m.result.result && m.result.result.value);
    };
    ws.on("message", on);
    ws.send(JSON.stringify({ id: mid, method: "Runtime.evaluate",
                             params: { expression: expr, returnByValue: true } }));
  });
  const out = await evalJs(`JSON.stringify({
    step: ["s1","s2","s3","s4","s5"].filter(s=>{const e=document.getElementById(s);
             return e && !e.classList.contains("hidden");}).join(","),
    phase: (document.getElementById("phaseLine")||{}).textContent || "",
    job: (document.body.innerText.match(/job id:\\s*([a-f0-9]{32})/)||[])[1] || "",
    err: (document.getElementById("err-progress")||{}).textContent || ""
  })`);
  console.log(out);
  ws.close();
})().catch(e => { console.error("PEEK ERROR:", e.message); process.exit(1); });
