# Goals — Supervisorly

The autonomous build goals for this project. Each is a self-contained `/goal` prompt: it builds,
self-tests, adversarially refines, clean-room-verifies, and only reports complete against a hard
Definition of Done. Newest work at the bottom.

| # | Goal | File | Status |
|---|------|------|--------|
| 1 | **Build + prove the offline engine** — deterministic collection, verified claims, four-state honesty, scoring, export/dashboard, human rung, ethics, cache/resume | [`docs/IMPLEMENTATION_GOAL.md`](IMPLEMENTATION_GOAL.md) | ✅ **Complete** — 140 tests green; see [`docs/COMPLETION_REPORT.md`](COMPLETION_REPORT.md) |
| 2 | **Ship the LIVE scan + Atlas front-end** — real ROR/OpenAlex discovery, students who joined, companies worked with, recruiting/social via the human rung, university + professor ranking, prioritise/only scope, scheduled re-scans, and the whole UI + diagrams recreated in the Atlas design language | [`docs/LIVE_IMPLEMENTATION_GOAL.md`](LIVE_IMPLEMENTATION_GOAL.md) | ✅ **Complete** — 253 tests green, adversarial audit closed (zero open findings), clean-room verified; see [`docs/LIVE_COMPLETION_REPORT.md`](LIVE_COMPLETION_REPORT.md) |

## Binding design reference (front-end & diagrams)

`design_handoff_supervisorly_atlas/` — the hifi **"Supervisorly Atlas — Living"** design language:

- `README.md` — the **binding spec**: bioluminescent tokens, the sidebar/drawer/lightbox shell, and
  the glowing **cells + curved animated filaments** diagram engine (how every diagram must appear).
- `Supervisorly Atlas - Living.dc.html` — the reference prototype + the diagram/decision **data** +
  final **copy** (port the data as-is; reimplement the runtime — never ship `.dc.html`/`support.js`).

Every UI and diagram Supervisorly ships follows this language, kept **self-contained and offline**
(D-033/D-048): self-hosted fonts, no CDN, no external request.

## How to start / resume a goal

Open a fresh session in this repo and point `/goal` at the file. Recommended: a dedicated branch so
the completed offline work on `build/v1` stays intact.

```text
# create the live branch first (once):
git switch -c build/live

# then, in Claude Code:
/goal [ this is your goal 'D:\AndroidStudioProjects\how_to_get_proffessor\docs\LIVE_IMPLEMENTATION_GOAL.md' ]
```

The goal is written to be **resumable**: if a session is interrupted or its context is reset, the
next session picks up from `docs/BUILD_LOG.md` + `git log` + the test suite and continues — it does
not restart from scratch, and does not stop until the Definition of Done is fully met.
