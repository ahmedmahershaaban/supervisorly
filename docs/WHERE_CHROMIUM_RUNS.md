# Where Chromium runs — the short version

There are **two different Chromiums** in this project and they have nothing to do with each
other. Mixing them up is the whole reason this page exists.

| | **A — the product's browser** | **B — the verification browser** |
|---|---|---|
| Where | inside the Cloud Run worker, in Google's datacentre | on your desktop, a window you can watch |
| Headless? | **yes**, headless | **no**, headful on purpose |
| Who starts it | the scan itself | you, by hand, before running the e2e script |
| Ships to students | **yes** | **no** — it is a test tool |
| When | during a scan, deep-dive phase only | only when someone verifies a deploy |

---

## A — the product's Chromium (the one students' scans use)

### Where it lives
Baked into the worker image by `firebase/Dockerfile.worker`:

```dockerfile
RUN pip install --no-cache-dir playwright==1.49.1 \
    && playwright install chromium
```

~400 MB with the system libraries Chromium needs. It is why the worker build is slower than
the Functions build.

### When it starts
**Once per scan**, not once per page — `src/supervisorly/pipeline.py`:

```python
renderer = render_mod.ChromiumRenderer(fetcher.robots_allows)   # one browser for the run
try:
    gaps = _process_targets(..., renderer=renderer)
finally:
    renderer.close()                    # never leak it — the container gets reused
```

In wizard terms: **nothing to do with steps 1–4.** It only exists after *Start scan*, and only
inside the phase the progress line calls **deep dive** (`deep_dive_progress`).

### When it actually renders a page
Almost never, and that is the design. Per professor:

```
1. plain HTTP fetch of the page
2. did it come back 200 and robots-allowed?         no  -> stop, honest "blocked"
3. does the text look like a login wall or a JS shell?
                                        no  -> DONE. Chromium is never touched.
                                        yes -> render it in Chromium
4. run the SAME wall detector on the rendered text
                                        still a wall -> it really was a wall.
                                                        Nothing was defeated; human rung.
                                        real content -> use it
```

That second check is the important one. Rendering a login page works perfectly — it is a real
page, just not the professor's — so without step 4 "render it" would quietly become "defeat
it", which D-039/D-043 forbid.

### Why it exists at all
A measured run had **52 of 52 professors blocked** because the only page on record was an
ORCID profile: public, robots-allowed, and a JavaScript application our HTTP reader cannot
execute. Not a wall. Our reader's limit.

### If Chromium is missing
Nothing breaks. `render()` reports itself unavailable, every page takes the path it took
before, the scan finishes. Slower is not the same as broken.

---

## B — the verification Chromium (how I check a deploy)

Not part of the product. `tools/e2e/record_flow.js` **attaches to a Chrome you started
yourself** — it does not launch one.

```powershell
# 1. start a Chrome with the debugging port open
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
    --remote-debugging-port=9222 --user-data-dir=C:\Temp\chrome-e2e about:blank

# 2. point the driver at the live site
$env:SV_EMAIL = "you@example.com"
node tools/e2e/record_flow.js "machine learning | natural language processing" C:\Temp\e2e-out
```

It then drives the real site the way a student would — types the email, ticks the intents,
expands the phrasings, picks topics, starts a real scan, waits for it, opens the dashboard,
opens a professor — and checks **63** things on the way, screenshotting each step.

Both prerequisites now name themselves if you forget: a missing `SV_EMAIL` and a missing
browser each print what to do instead of failing obscurely.

### Why headful and not headless
Because the point is to see it. A headless pass can be green while the page is visually
broken, and three real defects this week were only visible to something driving the real
thing:

- a topic cap the student met on the last click, with no way back
- a `409` that turned a healthy job into a dead end
- **"Copied ✓" for a copy that never happened** — the run pasted the word `music`, which was
  whatever had been on the clipboard beforehand

None of those were caught by 1,083 offline tests, because in each case the product reported an
outcome it had not checked.

---

## One-line answer

**Students' scans use a headless Chromium inside the worker, only during the deep-dive phase,
and only for a page that came back readable-but-unreadable. The Chrome window on your desktop
is mine, for verifying deploys, and never ships.**
