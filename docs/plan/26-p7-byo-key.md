# P7 — Bring your own model key

> ## STATUS, 2026-07-29 — **P7-1 built.** UI (FE-5) + browser-side expansion on the student's key.
>
> **[FE-5](30-frontend.md#fe-5--optional-model-key-x--the-ui-half-of-p7) is live** at
> `web-v22`: a collapsed "Use my own model key (optional)" panel on step 1, a password input,
> "Test key" (one cheap call **straight to Google**, never proxied through us), and one-click
> Clear.
>
> **P7's security rules are already enforced structurally**, not merely promised — the key
> never enters `state` (which is what gets serialised into a plan); tests assert that no line
> touching the key mentions `api(` or `/api/`, that the POSTed plan carries no key-shaped
> field, and that the **D-071 error beacon cannot reach it** (that beacon posts error text to
> our servers and is the real leak path). Browser→Gemini CORS was re-confirmed working.
>
> **P7-1.2 is now done too:** with a key set, `expandField` calls Gemini **directly from the
> browser** and `/api/expand` is not called at all; without one, the server path runs
> unchanged. Both branches return the same shape (a bare array of phrasings), so neither can
> become the special case nobody tests.
>
> **Failing closed is the part that got the most care.** A refused key, an exhausted quota, an
> unparseable completion, a CORS or offline failure — every one returns `null` and the caller
> falls back to the student's literal words. And the student is **told which happened**: a key
> that quietly did nothing is worse than no key, because they would believe their quota was
> spent and that a model chose the phrasings.

---

← [`README.md`](README.md) · [`00-invariants.md`](00-invariants.md)

**Size: S · Risk: low.** Independent of the harvest chain — can be built in parallel.
No spike needed; the one open risk was tested and closed.

## Why this exists

Each student supplies their own Gemini key. That removes the model budget from our side
entirely, which is what makes wide expansion and P5 affordable at any scale.

## The safe shape — and it is verified

**The browser calls Gemini directly. The key never reaches our server.**

Tested against the real endpoint on 2026-07-29 rather than assumed:

```
OPTIONS preflight               → 200
access-control-allow-origin     → https://supervisorly.web.app   (echoes our origin)
access-control-allow-methods    → …POST…
access-control-allow-headers    → content-type, x-goog-api-key
POST with a bad key             → 400, and the CORS header is still present
```

So a page can call Gemini directly. **A key posted to us is a key we are then responsible
for** — for logs, for Firestore, for support, for breach. Not holding it is the whole point.

---

## P7-1 · Key in the page, never on the server `[x]`

**Files**: `src/supervisorly/export/webapp.py`, `tests/test_byo_key.py` *(new)*

- [x] P7-1.1 Optional key field on step 1, stored in `localStorage` **only**
- [x] P7-1.2 Expansion calls Gemini **directly from the browser** when a key is present;
      falls back to the server path when it is not
- [x] P7-1.3 The key is **never** sent to our API, never logged, never placed in an error
      message or a `note` — the existing D-068 rule, applied to a key we do not own, which
      raises the stakes rather than lowering them
- [x] P7-1.4 Invalid / revoked / quota-exhausted → **fail closed to the student's own words**,
      with a clear message. Never a broken scan
- [x] P7-1.5 Tests: **no code path posts the key to our origin**, and the D-071 error beacon
      cannot carry it

**Acceptance** — with a key set, `/api/expand` is not called at all and the phrasings still
arrive. With an invalid key, the wizard continues using the student's literal words.
**Both pinned as tests** (`tests/test_byo_key.py`), the first by asserting the server path is
reachable only from the `if(!own)` branch.

**Done, 2026-07-29.** Notes for whoever touches this next:

- **The key is never in `state`.** `state` is what becomes the plan we POST, so a key placed
  there would reach our servers with nobody having written a line to send it. Only two
  booleans — `ownKeyUsed` / `ownKeyFailed` — travel there.
- **Both expansion branches return the same shape** (a bare array of phrasings). A different
  shape for the own-key path would make it the branch nobody tests.
- **Every Google failure mode returns `null`** — non-2xx (refused / quota), unparseable
  completion, and a `.catch` for offline/CORS. Any of them throwing would break the click,
  and P7's whole promise is that a bad key costs a *narrower* search, never a broken one.
- **The student is told which happened.** A key that quietly did nothing is worse than no key:
  they would believe their quota was spent and that a model chose the phrasings.
- The key has its **own** storage key, separate from the past-searches list, so "forget this
  search" and "clear my key" cannot destroy one another.

**Review** `[R]`

---

## Front-end surface

The UI half is **FE-5** in [`30-frontend.md`](30-frontend.md) — a collapsed "Use my own model
key (optional)" panel, a plain statement of where the key goes, a "Test key" button, and
one-click clearing.

---

## Edge cases

| case | handling |
|---|---|
| CORS blocked | **Closed by measurement** — it is not. If Google ever changes this, the property is lost and the design must change rather than quietly proxying through us |
| Invalid or revoked key | Fail closed to the student's own words |
| Quota exhausted mid-scan | Partial results, honestly labelled; the deterministic layer completes regardless |
| Key leaking into logs or errors | Never logged, echoed, or included in a note — asserted by test |
| Student pastes a key with whitespace or quotes | Trim and validate shape before use; a clear message beats a silent 400 |

## Later

The plan restricts this to Gemini because the Gemini path is already implemented and verified.
Model choice per student is a later decision, not part of P7.
