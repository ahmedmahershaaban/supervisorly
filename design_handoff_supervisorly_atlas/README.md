# Handoff: Supervisorly Atlas — Living

## Overview
An interactive, self-contained "system atlas" for **Supervisorly**, an AI-agent supervision platform that gates, verifies, escalates, and records every action an agent proposes. The atlas presents the platform as **8 connected diagrams ("specimens")** rendered in an original bioluminescent-organism art direction: every service is a glowing "cell," every connection a curved "filament" of light. It targets **engineers building on the system** — each node opens a detail drawer explaining its role and the design "laws" (ADRs) that govern it.

This is a reference/education artifact (an internal docs microsite), not a form-driven app. There is no backend and no persistence.

## About the Design Files
The files in this bundle are **design references created in HTML** — a working prototype showing the intended look, motion, and behavior. They are **not production code to copy directly**. The task is to **recreate this design in the target codebase's environment** (React, Vue, Svelte, etc.) using its established patterns, component library, and conventions. If no environment exists yet, pick the most appropriate stack — this design maps cleanly onto React + inline styles or CSS-in-JS, with one SVG layer per diagram.

The prototype is authored as a "Design Component" (a single streaming `.dc.html` file with a template + a `Component` logic class). **Ignore that authoring wrapper** — it is specific to the design tool. What matters is the rendered DOM, the styles, the data model, and the diagram-drawing logic, all documented below so you can reimplement from this README alone.

## Fidelity
**High-fidelity (hifi).** Final colors, typography, spacing, motion, and interactions are all specified. Recreate the UI pixel-accurately using the codebase's libraries. The one area with intentional latitude: the **node/cell positions** within each diagram are authored as percentage coordinates (documented per specimen below) — keep them, but they can be nudged for balance on unusual viewport ratios.

---

## Layout (page shell)

Three-zone shell over a fixed decorative background:

- **Fixed background (z-0, `pointer-events:none`)** — never scrolls:
  - Layer A: three radial-gradient "nebula" blooms + base color `#05070c`:
    `radial-gradient(1100px 720px at 78% -8%, rgba(120,86,220,.14), transparent 60%)`,
    `radial-gradient(1000px 700px at 6% 32%, rgba(41,150,168,.13), transparent 58%)`,
    `radial-gradient(900px 900px at 96% 88%, rgba(228,160,70,.09), transparent 60%)`.
  - Layer B: vignette `radial-gradient(120% 120% at 50% 50%, transparent 58%, rgba(2,4,8,.78) 100%)`.
  - Layer C (motion only): 3 blurred drifting orbs (`animation: omDrift 26s/34s/30s ease-in-out infinite`) + one vertical scan line sweeping top→bottom (`omScan 11s linear infinite`).
- **Left sidebar ("CATALOGUE")** — fixed, `width:300px`, full height, `background:rgba(7,10,16,.72)` + `backdrop-filter:blur(6px)`, `border-right:1px solid #121a27`, `padding:28px 24px 40px`, `z-index:40`, own scroll.
- **Main column** — `margin-left:300px`, `padding:0 clamp(28px,4vw,64px) 140px`, `max-width:1240px`, `z-index:1`.
- **Scroll progress bar** — fixed top, `height:2px`, width tracks scroll %, `background:linear-gradient(90deg,#6bc4d6,#b58cf0,#e8b24a)`, `box-shadow:0 0 12px rgba(127,214,224,.6)`, `z-index:60`.

### Responsive (breakpoint: viewport width < 900px)
- Sidebar becomes a **top drop-down panel** toggled by a `CATALOGUE` button in a fixed 54px top bar (`background:rgba(6,8,14,.92)` + blur). Panel slides via `transform: translateY(-118%) → translateY(0)`, `.28s ease`, with a dim backdrop.
- Main column: `margin-left:0; margin-top:54px; padding:0 18px 120px`.
- Diagrams keep a `min-width` and the panel scrolls horizontally (see Diagram stage).

---

## Screens / Views

There is one scrolling page. Its logical views are: **Header**, **Sidebar (catalogue + legend)**, **8 Specimen sections**, **Cell drawer**, **Law drawer**, **Isolate lightbox**.

### Header (hero)
- `padding:82px 0 60px`.
- Eyebrow: `SUPERVISORLY · XENO-ATLAS · FIELD RECORD v2` — Space Mono, 12px, color `#e8b24a`, `letter-spacing:.24em`.
- H1: Space Grotesk 700, `clamp(33px,5.2vw,62px)`, `line-height:1.01`, `letter-spacing:-.02em`, `max-width:16ch`, `text-wrap:balance`. Copy: "A living map of the supervision organism."
- Sub-paragraph: 16.5px, `line-height:1.64`, color `#9aa2b4`, `max-width:66ch`, `text-wrap:pretty`.
- **Stat chips (4):** border `1px solid #17202f`, `background:rgba(10,14,22,.66)`, `radius:12px`, `padding:16px 22px 14px`, `min-width:124px`, each with a blurred colored glow blob in the corner. Number = Space Mono 700 30px in the stat color; label = Space Mono 10px `#6a7488` `letter-spacing:.15em`.
  - `SPECIMENS 08` (color `#e8b24a`), `CELLS 76` (`#43c9d6`), `FILAMENTS 82` (`#b58cf0`), `DESIGN LAWS 14` (`#79d06a`). (Counts are computed from data — verify against the data model below.)
- **Legend row** (mirrors sidebar): 6 small glowing dots + Space Mono tags.

### Sidebar
- Brand lockup: 34px golden glowing orb (`radial-gradient(circle at 38% 30%, rgba(232,178,74,.92), rgba(232,178,74,.12) 72%)`, border + outer/inner glow) + "Supervisorly" (Space Grotesk 700 16px) + `XENO-ATLAS · LIVE SPECIMEN` (Space Mono 9.5px `#5f6b80` `letter-spacing:.24em`).
- **CATALOGUE nav** — one button per specimen: 2-digit number (Space Mono 11px) + title (Space Grotesk 13.5px). Default color `#8b93a5`. **Active** (scroll-spy): text `#e8b24a`, `background:rgba(232,178,74,.09)`, `border-left:2px solid #e8b24a`, number `#e8b24a`.
- **TISSUE TYPES legend** — 6 rows: 15px glowing dot + label (12px `#b7bece`).
- Footer note (Space Mono 10px `#4b5468`) ending in `SIGNAL · NOMINAL` (`#7fd6e0`).
- Dividers: `height:1px; background:linear-gradient(90deg,#1a2436,transparent)`.

### Specimen section (×8, one per diagram)
Each section (`scroll-margin-top:80px`, `padding:60px 0 8px`) has:
- **Header row:** code `SPECIMEN 0N` (Space Mono 12px `#e8b24a` `.2em`) · 5px glowing amber dot · glyph e.g. `ξ-CONTEXT` (Space Mono 12px `#6a7488`). Then H2 (Space Grotesk 700, `clamp(24px,3vw,34px)`) + purpose line (15.5px `#9aa2b4`, `max-width:62ch`). Right-aligned **`ISOLATE ↗`** button (Space Mono 11px, border `1px solid #223148`, radius 8px; hover → text `#e8b24a`, border `#3a4a63`).
- **Diagram stage** (see below).
- **Caption** under stage: Space Mono 11px `#4b5468`, e.g. `GOVERNS · DR-001 DR-003 DR-013 · context.md`.

### Cell drawer (right sheet)
Opens on cell click. Fixed right, `width:452px` (100% on mobile), `background:rgba(9,13,20,.98)`, `border-left:1px solid #1a2434`, `box-shadow:-40px 0 90px -40px rgba(0,0,0,.9)`, slides in via `omDrawerIn .24s cubic-bezier(.2,.7,.2,1)`. Dim + blurred backdrop behind (`rgba(3,5,9,.62)` + `blur(3px)`).
- Sticky header: `CELL DETAIL` label + `ESC ✕` close button.
- Body: glowing kind-colored dot + `KIND · SPECIMEN 0N`; H3 title (Space Grotesk 700 26px); "in {map title}" (13px `#6a7488`); description (15.5px `#c1c8d6`); then **GOVERNING LAWS** — clickable rows (`background:rgba(16,22,33,.7)`, border `1px solid #1c2739`, radius 10px; hover border `#e8b24a`) each showing `DR-0NN` (amber) + law title.

### Law drawer (same sheet, second view)
Reached by clicking a law row inside the cell drawer.
- `← BACK TO CELL` button.
- `DR-0NN` (amber 14px) + status pill (`ACCEPTED`, teal outline, radius 20px) + `RATIFIED YYYY-MM` (Space Mono 10px `#5f6b80`).
- H3 law title (Space Grotesk 700 23px).
- Summary paragraph (15.5px `#c1c8d6`).
- **TENSION** callout: `border-left:2px solid rgba(240,131,154,.55)`, coral label, body 14px `#a9b1c1` — the trade-off the decision accepts.
- **GOVERNS THESE CELLS** — reverse lookup: rows of `SP0N` + the cell names that carry this law, across all specimens.

### Isolate lightbox
Opens on `ISOLATE ↗`. Full-screen overlay `background:rgba(3,5,9,.92)`, centered card (`max-width:96vw; max-height:92vh`, radius 16px, radial panel bg, big drop shadow). Header: `SPECIMEN 0N · ξ-GLYPH` + title + `ESC ✕`. Body: the same diagram at a **larger stage** (`width:min(88vw,1400px); min-width:1120px`), scrollable, hover-highlight active.

---

## The diagram engine (the core of this design)

Each diagram is a **stage** with two stacked layers:

1. **SVG overlay** (`.om-overlay`, absolutely positioned, `inset:0`, `z-index:0`, `pointer-events:none`) — draws all edges ("filaments").
2. **Node buttons** (`z-index:1`) — absolutely positioned "cells," each a `<button>`.

### Stage box
- Inline stage: `position:relative; width:100%; min-width:860px; aspect-ratio:1040/616`.
- Lightbox stage: `width:min(88vw,1400px); min-width:1120px; aspect-ratio:1040/616`.
- The panel wrapping the stage: border `1px solid #172233`, radius 14px, `background:radial-gradient(120% 140% at 50% 0%, rgba(15,22,34,.7), rgba(6,9,15,.9))`, `overflow-x:auto`, shadow `0 40px 90px -50px rgba(0,0,0,.9), inset 0 1px 0 rgba(127,214,224,.04)`.

### Nodes ("cells")
Positioned by **percentage coordinates** `left:x%; top:y%; transform:translate(-50%,-50%)`, `width:132px`, a vertical flex stack (circle, label, tag), transparent button.
- **Circle** = 3 nested spans:
  - **halo** — `width/height = diameter × 1.85`, `radial-gradient(circle, rgba(kind,.34×glow), transparent 66%)`, `animation: omHalo 6s ease-in-out infinite` (staggered delay).
  - **body** — the membrane: `radial-gradient(circle at 38% 30%, rgba(kind,.62), rgba(kind,.1) 74%)`, `border:1.6px solid rgba(kind,.88)`, `box-shadow:0 0 {20×glow}px rgba(kind,.5×glow), inset 0 0 16px rgba(kind,.2)`, `animation: omBreathe 6s ease-in-out infinite` (staggered).
  - **nucleus** — centered 8px dot, `background:rgba(kind,.95)`, `box-shadow:0 0 10px kind`.
- **Diameter by kind (px):** core `76`, tool/verified/human/rule `62`, skip `52` (radii 38/31/26 ×2).
- **Label** — Space Grotesk 600 12.5px `#eef1f6`, centered, `max-width:132px`, `text-wrap:balance`.
- **Tag** — Space Mono 8.5px in the kind color, `letter-spacing:.18em` (e.g. `CORE`, `TOOL`).
- **Hover / focus:** `transform: translate(-50%,-50%) scale(1.08)`, `filter: brightness(1.12) drop-shadow(0 0 16px rgba(kind,.55))`, `z-index:6`.

### Edges ("filaments") — computed in JS, drawn as SVG
For each edge `[from, to, label]`, at paint time (after layout, on mount/resize/font-load/lightbox-open):
1. Read stage `clientWidth/Height`; convert each node's `x%,y%` to px; use its radius `r`.
2. Compute a unit vector from→to. Start point `P0` sits `r+4` px out from the source center; end point `P3` sits `r+7` px short of the target center (so the line meets the membrane, not the middle).
3. Build a **cubic bezier** bowed perpendicular to the straight line. Offset = `clamp(dist×0.16, 16, 64)`, sign chosen deterministically per edge (`hash(from+to) % 2`) so parallel edges bow opposite ways and don't overlap. Control points at 32% and 68% along, displaced by the perpendicular × offset.
4. Emit **4 stacked SVG elements per edge**, all in the source-node's kind color:
   - wide soft glow: `stroke-width:8, opacity:.11, stroke-linecap:round`
   - thin base line: `stroke-width:1.3, opacity:.42`
   - **animated light-packets:** `stroke-width:2.4, opacity:.92, stroke-dasharray:"0.1 12"`, class `om-flt` = `@keyframes omFlow { to { stroke-dashoffset:-24.2 } } 1.5s linear infinite` — reads as dots crawling toward the target.
   - **arrowhead:** a small filled polygon at `P3` oriented along the curve's end tangent.
5. If labels enabled and the edge has a label: a rounded pill at the curve midpoint — `rect rx:10.5, fill:#080b12, stroke:rgba(kind,.35)`, text Space Mono 11px `#aeb6c6`.
6. Wrap each edge's elements in `<g data-edge="from|to">` for highlight toggling.

**Recreation note:** in a component framework, compute these paths in a layout effect (after refs/measure) and re-run on resize, font load, and when the lightbox opens. Keep the node coordinates as data; derive all geometry. `viewBox` = `0 0 W H` matching the stage px size.

### Highlight-connected (hover / focus a cell)
On cell `mouseenter`/`focus`, within that stage only:
- Build adjacency from the edge list (undirected).
- Set every non-neighbor node to `opacity:.2; filter:saturate(.55)`; keep the hovered node + direct neighbors at full.
- Every edge NOT touching the node → `opacity:.07`; touching edges stay lit.
- On `mouseleave`/`blur`, clear all inline overrides. Transitions: nodes `.18s`, edge groups `.18s`.

### Scroll-spy
`IntersectionObserver` with `rootMargin:'-42% 0px -52% 0px'` on each specimen section → sets the active sidebar nav item (see active styles above).

---

## Interactions & Behavior

- **Sidebar nav click** → smooth-scroll to that specimen (`scroll-margin-top` handles offset; JS scrolls to `top - 22` desktop / `- 70` mobile). On mobile, closes the panel.
- **Cell click** → open Cell drawer for that node; close sidebar panel on mobile.
- **Law row click** (in Cell drawer) → switch drawer to Law view (`view:'decision'`).
- **← BACK TO CELL** → return to Cell view (same node).
- **`ISOLATE ↗`** → open lightbox for that specimen.
- **Close:** `ESC ✕` buttons, backdrop click, and **Escape key** (Escape closes lightbox first, else drawer).
- **Cell hover/focus** → highlight-connected (above). Keyboard focus triggers the same, so it's operable without a mouse.
- **Scroll** → progress bar width + scroll-spy active nav.
- **Motion:** halos pulse (`omHalo`), membranes breathe (`omBreathe`), filaments flow (`omFlow`), background orbs drift + scan line sweeps. All staggered by a per-node hash so nothing pulses in lockstep.
- **`prefers-reduced-motion: reduce`** → all animations disabled, smooth-scroll off (a global CSS override sets `animation:none` + near-zero transitions; the JS also passes `behavior:'auto'` to scroll).

### Tweakable options (were exposed as props; wire to config/props/context)
- **Living motion** (boolean, default true) — master switch for cell/filament/background animation.
- **Filament labels** (boolean, default true) — show/hide edge label pills.
- **Bioluminescence** (range 20–120%, default 70) — scales halo alpha and body glow radius/opacity (`glow = value/70`).

---

## State Management
Minimal UI state (no data fetching):
- `drawer` — `null | { mapId, nodeId, view:'node'|'decision', decisionId? }`.
- `lightbox` — `null | mapId`.
- `sidebarOpen` — boolean (mobile panel).
- `vw` — viewport width (drives the <900 responsive branch); update on resize.
- Derived, not stored: active nav (from IntersectionObserver), highlight state (inline DOM styles cleared on leave).
- Escape/resize/scroll listeners registered on mount, removed on unmount. Repaint diagrams on: mount, resize, font-ready, and lightbox open.

---

## Design Tokens

### Color — surfaces & text
| Token | Hex |
|---|---|
| Base void | `#05070c` |
| Panel bg (radial from) | `rgba(15,22,34,.7)` |
| Panel bg (radial to) | `rgba(6,9,15,.9)` |
| Sidebar bg | `rgba(7,10,16,.72)` (+ blur 6px) |
| Drawer bg | `rgba(9,13,20,.98)` |
| Card/chip bg | `rgba(10,14,22,.66)` |
| Hairline border | `#172233` / `#131a28` / `#1a2434` |
| Text primary | `#e9edf3` / `#eef1f6` |
| Text body | `#c1c8d6` |
| Text muted | `#9aa2b4` |
| Text faint | `#6a7488` / `#5f6b80` / `#4b5468` |

### Color — cell "tissue types" (kind → hex)
| Kind | Meaning | Hex | Tag |
|---|---|---|---|
| `tool` | Connector — external tool | `#43c9d6` (teal) | TOOL |
| `verified` | Verifier — automated check | `#79d06a` (chartreuse) | CHECK |
| `human` | Human node — in the loop | `#f0839a` (coral) | HUMAN |
| `data` | Core — orchestrator / data | `#e8b24a` (amber) | CORE |
| `rule` | Gate — rule / decision | `#b58cf0` (violet) | GATE |
| `skip` | Dormant — skipped / bypassed | `#7d828e` (slate) | SKIP |

Cell fills/glows are these hexes at varying alpha (see node spec). Amber `#e8b24a` doubles as the global accent (eyebrows, codes, active nav, hover). Coral `#f0839a` marks the TENSION callout. Teal `#7fd6e0` is the focus-ring / "signal nominal" color.

### Typography
- **Display / UI:** `'Space Grotesk'` (weights 400–700). Google Fonts.
- **Mono / labels / codes:** `'Space Mono'` (400/700). Google Fonts.
- **Body fallback:** `'Helvetica Neue', Helvetica, Arial, sans-serif`.
- Import: `https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Space+Mono:wght@400;700&display=swap`
- Scale: H1 `clamp(33px,5.2vw,62px)/1.01/-.02em`; H2 `clamp(24px,3vw,34px)/1.08/-.015em`; drawer H3 23–26px; body 15.5–16.5px/1.62–1.66; labels/codes 8.5–12px with wide tracking (`.14em`–`.24em`).

### Radius & shadow
- Radius: cards/chips 12px, panels/stage 14px, lightbox 16px, drawer rows 10px, status pill 20px, cells 50%.
- Key shadows: stage `0 40px 90px -50px rgba(0,0,0,.9), inset 0 1px 0 rgba(127,214,224,.04)`; drawer `-40px 0 90px -40px rgba(0,0,0,.9)`; lightbox `0 60px 150px -40px #000`; progress glow `0 0 12px rgba(127,214,224,.6)`.

### Keyframes
- `omBreathe` — scale 1 → 1.055 → 1, 6s.
- `omHalo` — opacity .4→.82, scale 1→1.16 (translate-centered), 6s.
- `omFlow` — `stroke-dashoffset: 0 → -24.2`, 1.5s linear (light-packets).
- `omDrift` — translate wander, 26/30/34s.
- `omScan` — translateY -10vh → 110vh, 11s.
- `omDrawerIn` — translateX 30px+fade, .24s. `omFade` — opacity, .18–.2s.

### Layout constants
Sidebar 300px; main max-width 1240px; drawer 452px; mobile bar 54px; breakpoint 900px; stage aspect 1040/616, min-width 860 (inline) / 1120 (lightbox).

---

## Data model (drives everything — port this verbatim)

Two structures. Reproduce them as typed data in your codebase; the UI is a pure function of them.

### `DECISIONS` — 14 design laws (ADRs), keyed `DR-001`…`DR-014`
Each: `{ title, date (YYYY-MM), status ('ACCEPTED'), summary, tension }`. Full text is in the design file (`Supervisorly Atlas - Living.dc.html`, `DECISIONS = {…}` in the logic class). Titles: DR-001 Fail-closed gating · DR-002 Append-only ledger · DR-003 Control/data-plane split · DR-004 Risk-scored auto-skip · DR-005 Review SLA with fallback · DR-006 Sandboxed dry-run · DR-007 Idempotency keys · DR-008 Least-privilege connectors · DR-009 Escalation ladder · DR-010 Transitions are events · DR-011 Deterministic replay · DR-012 Redaction before storage · DR-013 Signed action envelopes · DR-014 Two-key execution.

### `maps` — 8 specimens
Each specimen: `{ id, code ('SPECIMEN 0N'), glyph ('ξ-…'), title, purpose, caption, nodes[], edges[] }`.
- **node** = `[id, label, kind, x%, y%, description, [decisionIds]]`.
- **edge** = `[fromId, toId, label]`.
The 8: `context` (ξ-CONTEXT), `components` (ξ-ANATOMY), `pipeline` (ξ-CURRENT), `data` (ξ-STRUCTURE), `rules` (ξ-LAW), `roles` (ξ-HANDS), `lifecycle` (ξ-PULSE), `observability` (ξ-SENSE). Node/edge/coordinate details and copy are all in the design file's `raw = […]` array — port it as-is; every string is final.

**Reverse lookup** (Law drawer "GOVERNS THESE CELLS"): for a given `DR-0NN`, scan all specimens for nodes whose decision list includes it, group the node labels by specimen code. Compute at render.

---

## Assets
**None external.** No images or icon fonts. All visuals are CSS gradients, box-shadows, and runtime-generated SVG. The only third-party dependency is the two Google Fonts (Space Grotesk, Space Mono) — self-host or import per your codebase's convention. There is one glyph-y motif (`ξ` + word) used purely as text.

## Files
- `Supervisorly Atlas - Living.dc.html` — **the design being handed off** (the bioluminescent "Living" version; the file the user selected). Contains the full template, the `Component` logic class (diagram engine, drawers, scroll-spy), and the `raw`/`DECISIONS` data.
- `Supervisorly Atlas.dc.html` — *(in the project, not required for this handoff)* an earlier "dark blueprint" version of the same content (rectangular nodes on a grid, straight connectors). Useful only if you want to compare art directions; the Living version supersedes it.

> Note on the `.dc.html` format: these open in a browser but are authored for a specific design tool (a `<x-dc>` template + a `Component` class, assembled by `support.js`). Read them as reference for DOM structure, styles, the diagram math, and the data — **do not** try to ship the `.dc.html`/`support.js` runtime. Reimplement in your framework.
