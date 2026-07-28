/* Multi-subject sweep straight against the API: for each field, expand → map → scan → wait →
   read the export back and report whether the professor PROFILE actually arrived.
   Usage: node sweep.js */
const EMAIL = process.env.SV_EMAIL;
const BASE = "https://supervisorly.web.app";
const sleep = ms => new Promise(r => setTimeout(r, ms));
const fs = require("fs");

const SUBJECTS = [
  { label: "law",         field: "wills in law" },
  { label: "science",     field: "molecular biology" },
  { label: "sport",       field: "sports science and athletic performance" },
  { label: "engineering", field: "structural engineering" },
  { label: "medicine",    field: "cardiology" },
];

async function j(url, opts) { const r = await fetch(url, opts); const t = await r.text();
  try { return { s: r.status, b: JSON.parse(t) }; } catch { return { s: r.status, b: t }; } }

/* Do what the PAGE does, not a shortcut around it: expand the field into phrasings, map each
   phrasing, merge by topic_id (D-070). Mapping the raw field alone is what my first pass did
   and it silently sent an EMPTY topic filter — so "sport" and "medicine" searched the same
   unfiltered population and returned the same 1081 people. It also hid that "cardiology" maps
   to nothing on its own: OpenAlex has no topic by that name, which is precisely the case the
   expand step exists to rescue ("cardiovascular medicine", "heart diseases"). */
async function topicsFor(field) {
  const ex = await j(`${BASE}/api/expand`, { method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ field, email: EMAIL }) });
  const variants = (ex.s === 200 && ex.b.variants && ex.b.variants.length) ? ex.b.variants : [field];
  const seen = new Map();
  let mapped = 0;
  for (const v of variants) {
    const m = await j(`${BASE}/api/map?field=${encodeURIComponent(v)}&email=${encodeURIComponent(EMAIL)}`);
    if (m.s !== 200) continue;
    mapped++;
    for (const g of (m.b.groups || []))
      for (const t of (g.topics || [])) {
        const id = t.topic_id || t.id;
        if (id && !seen.has(id)) seen.set(id, t.display_name || t.name || id);
      }
  }
  const ids = [...seen.keys()];
  if (!ids.length) return { err: `no topics from ${variants.length} phrasings` };
  return { ids: ids.slice(0, 12), offered: ids.length, variants: variants.length, mapped,
           sample: [...seen.values()].slice(0, 3) };
}

(async () => {
  const summary = [];
  for (const s of SUBJECTS) {
    console.log(`\n=== ${s.label.toUpperCase()} — "${s.field}" ===`);
    const t = await topicsFor(s.field);
    if (t.err) { console.log("  map failed:", t.err); summary.push({ ...s, err: t.err }); continue; }
    console.log(`  ${t.variants} phrasings -> ${t.mapped} mapped -> ${t.offered} topics, using ${t.ids.length}`);
    console.log(`  e.g. topics: ${t.sample.join(" | ")}`);

    const start = await j(`${BASE}/api/scan`, { method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ email: EMAIL, shortlist: 12, max_institutions: 12, plan: {
        intent_kind: "phd", country: "Egypt", resolved_topic_ids: t.ids,
        field: s.field, university_mode: "all", universities: [] } }) });
    if (start.s !== 202 && start.s !== 200) { console.log("  scan refused:", start.s, JSON.stringify(start.b).slice(0,120));
      summary.push({ ...s, err: `scan ${start.s}` }); continue; }
    const job = start.b.job_id;
    console.log("  job:", job);

    let st = {};
    for (let i = 0; i < 40; i++) {
      st = (await j(`${BASE}/api/scan/${job}`)).b;
      if (["done", "failed", "cancelled"].includes(st.status)) break;
      await sleep(8000);
    }
    console.log("  status:", st.status, JSON.stringify(st.counts || {}));
    if (st.status !== "done") { summary.push({ ...s, job, err: "status " + st.status }); continue; }

    const html = await (await fetch(`${BASE}/api/result/${job}`, { redirect: "follow" })).text();
    const mm = html.match(/const\s+DATA\s*=\s*(\{[\s\S]*?\});/);
    if (!mm) { summary.push({ ...s, job, err: "no DATA in dashboard" }); continue; }
    const P = (JSON.parse(mm[1]).professors) || [];
    const withProfile = P.filter(p => p.profile);
    const withWorks   = P.filter(p => p.profile && p.profile.recent_works && p.profile.recent_works.length);
    const withInst    = P.filter(p => p.profile && p.profile.institutions && p.profile.institutions.length);
    const withCites   = P.filter(p => p.profile && p.profile.cited_by_count > 0);
    const modalReady  = html.includes('class="modal"') && html.includes("Recent publications");
    console.log(`  professors ${P.length} | profile ${withProfile.length} | institutions ${withInst.length}` +
                ` | citations ${withCites.length} | recent works ${withWorks.length} | modal markup ${modalReady}`);
    if (withWorks.length) {
      const ex = withWorks[0];
      console.log(`  e.g. ${ex.name}: ${ex.profile.works_count} works, ${ex.profile.cited_by_count} cites, ` +
                  `latest "${(ex.profile.recent_works[0]||{}).title||""}".slice`.slice(0,150));
    }
    // Who was actually surfaced — the check that the topic filter is doing something. Two
    // subjects returning the same top names means the filter was empty, which is exactly the
    // bug the first pass hid behind healthy-looking counts.
    const top = P.slice(0, 5).map(p => p.name);
    console.log("  top names:", JSON.stringify(top));
    summary.push({ ...s, job, professors: P.length, profile: withProfile.length,
                   inst: withInst.length, cites: withCites.length, works: withWorks.length,
                   modalReady, top });
  }
  fs.writeFileSync(process.argv[2] || "sweep.json", JSON.stringify(summary, null, 1));
  console.log("\n================ SUMMARY ================");
  for (const r of summary)
    console.log(` ${String(r.label).padEnd(12)} ${r.err ? "ERR " + r.err
      : `${r.professors} profs | ${r.works} with publications | ${r.cites} with citations`}`);
})();
