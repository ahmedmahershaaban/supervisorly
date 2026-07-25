/*
 * page_extract.js — Supervisorly in-page main-text extractor (D-064, D-065).
 *
 * USAGE (chrome-devtools-mcp, host-portable):
 *   1. Navigate the browser to the page (after `supervisorly pace` allows it).
 *   2. Call the MCP `evaluate_script` tool with this whole file as the function
 *      body — the file IS a single callable: `(opts) => Promise<{title, finalUrl, text}>`.
 *        - default (static page):        evaluate with no args (or `{}`)
 *        - scroll mode (social, D-065):  evaluate with args `[{"scroll": true}]`
 *   3. Save ONLY the returned `text` to a staging file (e.g. browser_staging/page.txt)
 *      and run `supervisorly ingest-page --url <finalUrl> --file <staging file>`.
 *   Raw HTML/DOM never leaves the page; the agent handles paths and byte counts only.
 *
 * The extraction mirrors src/supervisorly/fetch/normalize.py `main_text`:
 * the same boilerplate tags are skipped and whitespace is collapsed the same way,
 * so a browser snapshot is interchangeable with a fetcher snapshot (the D-010
 * quote gate runs unchanged). Plain ES2019 — no imports, no dependencies.
 *
 * The 60 KiB text cap (CONFIG.MAX_TEXT_BYTES) is enforced HERE, in-page — the Python
 * side accepts the staged text as-is. tests/test_browser_rung.py pins this constant.
 */
(opts) => {
  "use strict";

  var CONFIG = {
    MAX_TEXT_BYTES: 61440,          // 60 * 1024 — the ingest cap (D-064); test-pinned
    TRUNCATION_MARKER: "\n[truncated]",
    // scroll mode (D-065): human-like, jittered, capped — never a fixed metronome
    SCROLL_STEPS_MIN: 4,
    SCROLL_STEPS_MAX: 10,
    SCROLL_PAUSE_MIN_MS: 1000,
    SCROLL_PAUSE_MAX_MS: 3000,
    SCROLL_SETTLE_MS: 1500          // extra wait after the last step for lazy content
  };

  // Same boilerplate set as normalize.py _SKIP_TAGS — keep the two in sync.
  var SKIP_TAGS = {
    script: 1, style: 1, noscript: 1, nav: 1, footer: 1, header: 1,
    aside: 1, form: 1, svg: 1, button: 1, template: 1
  };

  function randInt(min, max) {   // inclusive, per-call jitter (never a metronome)
    return min + Math.floor(Math.random() * (max - min + 1));
  }

  function sleep(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
  }

  function isHidden(el) {
    if (el.hidden) { return true; }
    var cs = window.getComputedStyle(el);
    return cs.display === "none" || cs.visibility === "hidden";
  }

  function underSkipped(node) {
    for (var el = node.parentElement; el; el = el.parentElement) {
      var tag = el.tagName.toLowerCase();
      if (SKIP_TAGS[tag] || isHidden(el)) { return true; }
    }
    return false;
  }

  // Mirror of normalize.main_text: text outside boilerplate, whitespace collapsed,
  // one space between pieces. Dates and numbers are KEPT (quotes are verified
  // against this text — a recruiting quote may contain a deadline).
  function extractText() {
    var walker = document.createTreeWalker(
      document.body || document.documentElement,
      NodeFilter.SHOW_TEXT,
      {
        acceptNode: function (node) {
          if (!node.nodeValue || !/\S/.test(node.nodeValue)) {
            return NodeFilter.FILTER_REJECT;
          }
          return underSkipped(node) ? NodeFilter.FILTER_REJECT
                                    : NodeFilter.FILTER_ACCEPT;
        }
      }
    );
    var parts = [];
    var n;
    while ((n = walker.nextNode())) { parts.push(n.nodeValue); }
    return parts.join(" ").replace(/\s+/g, " ").trim();
  }

  function byteLength(s) {   // UTF-8 byte length (the cap is in bytes, not chars)
    if (typeof TextEncoder !== "undefined") { return new TextEncoder().encode(s).length; }
    return unescape(encodeURIComponent(s)).length;
  }

  // Cap at ~MAX_TEXT_BYTES of UTF-8, cut at a word boundary, marker appended.
  function capText(text) {
    if (byteLength(text) <= CONFIG.MAX_TEXT_BYTES) { return text; }
    var lo = 0;
    var hi = text.length;
    while (lo < hi) {   // binary search the char index that fits the byte cap
      var mid = (lo + hi + 1) >> 1;
      if (byteLength(text.slice(0, mid)) <= CONFIG.MAX_TEXT_BYTES) { lo = mid; }
      else { hi = mid - 1; }
    }
    var cut = text.slice(0, lo);
    var lastSpace = cut.lastIndexOf(" ");
    if (lastSpace > 0) { cut = cut.slice(0, lastSpace); }   // word boundary
    return cut + CONFIG.TRUNCATION_MARKER;
  }

  function result(text) {
    return { title: document.title || "", finalUrl: location.href, text: text };
  }

  // D-065 scroll mode: 4-10 incremental steps with randomised 1-3 s pauses, then a
  // settle wait for lazy-loaded content, THEN extract. Human-like and capped.
  async function scrollAndSettle() {
    var steps = randInt(CONFIG.SCROLL_STEPS_MIN, CONFIG.SCROLL_STEPS_MAX);
    for (var i = 0; i < steps; i++) {
      window.scrollBy(0, Math.max(200, Math.floor(window.innerHeight * 0.8)));
      await sleep(randInt(CONFIG.SCROLL_PAUSE_MIN_MS, CONFIG.SCROLL_PAUSE_MAX_MS));
    }
    window.scrollTo(0, 0);   // settle from the top so the read order is stable
    await sleep(CONFIG.SCROLL_SETTLE_MS);
  }

  return (async function () {
    if (opts && opts.scroll) { await scrollAndSettle(); }
    return result(capText(extractText()));
  })();
}
