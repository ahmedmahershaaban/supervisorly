# Reusable prompt — "Design the Supervisorly Atlas"

Paste the block below into a fresh Claude session (one that can build artifacts). It is a
self-contained design brief: it tells Claude the identity, the structure, the interactivity,
and the hard constraints, so it regenerates an atlas in the same visual language without you
re-explaining. Swap the **CONTENT** section for whatever you want mapped.

Everything above the line is notes for you; everything below the line is the prompt.

---

Build a single self-contained, interactive HTML page — a **"design atlas"**: a set of
connected diagrams that explain a system, with a live index and clickable diagrams. Publish it
as an artifact.

## Visual identity — commit to it
- **Committed dark theme only.** Neutral charcoal grounds (around `#0c0d10` background,
  `#15161a` surfaces), **not** navy-blue. Do not add a light mode.
- **One warm accent: gold** (`#d9a441`, brighter `#ecc271`) for links, active nav, the brand
  mark, section codes, and the progress bar. The theme must not read as "blue."
- **Type:** a heavy system sans for headings (`ui-sans-serif, system-ui, …`), and a
  **monospace** face (`ui-monospace, "SF Mono", "JetBrains Mono", …`) for eyebrows, section
  codes, captions, and the legend — an engineering-notebook / blueprint feel. Do **not** link a
  web font (CSP blocks font CDNs and it will silently fall back); use system stacks only.
- **Feel:** technical blueprint. A faint survey-grid texture behind the hero (CSS repeating
  gradients), hairline rules, generous whitespace, tight heading tracking.
- Avoid the generic AI looks: no cream+serif, no purple gradient hero, no Inter-on-white, no
  emoji section markers, no everything-centered.

## Diagrams — the critical craft
- Use **Mermaid** (rendered natively in the artifact via `<pre class="mermaid">` blocks).
- **Theme every diagram dark** with a per-diagram `%%{init}%%` directive: dark panel
  background (`#16181d`), dark node fills (`#20232b`) with **light text** (`#e9eaed`), light
  edge lines (`#858994`), and `edgeLabelBackground` matching the panel so labels don't show a
  white box. Diagrams must look native to the dark page — never a bright white card.
- Use a **six-colour semantic scheme**, each a dark fill with light, colour-tinted text and a
  coloured border, applied via `classDef`: tool (slate/blue), verified (green), human (rose),
  data/orchestrator (gold), rule/gate (teal), skip (grey). Show these in a **legend**.
- Put each diagram in a bordered "printed-map" panel with a subtle shadow and its own
  `overflow-x:auto`.

## Layout & interaction
- **Fixed left sidebar:** brand, a numbered index of the maps, and the colour legend.
- **Scrollspy:** the index highlights the map you're currently viewing (IntersectionObserver).
- **Scroll-progress bar** across the top.
- **Click any diagram node** → open a slide-in **detail drawer** showing what that node is and
  which design decisions govern it. Clicking a decision reference opens its summary.
- **An "expand" affordance** on each diagram → open it full-size in a lightbox (Esc / click-away
  to close).
- Every section: a monospace **map code** (e.g. `MAP 04`), a title, a one-line purpose, the
  diagram, and a caption naming the documents/decisions that govern it.
- Smooth-scroll nav; respect `prefers-reduced-motion`; collapse the sidebar to a top bar on
  narrow screens; the page body must never scroll sideways.

## Hard constraints
- **Self-contained:** no external CSS/JS/fonts/images. Inline everything. A strict CSP blocks
  every external host.
- Data (stats, node info, decision summaries) lives in a **JS object** so the page is dynamic
  and easy to edit — not hardcoded in the markup.
- Accessible: visible keyboard focus, semantic buttons for interactive elements.

## CONTENT — replace this section
Map the following system as N connected diagrams (one per concern), in this reading order:
[…list your maps here — e.g. Context, Components, Pipeline, Data model, Rules… — each with a
one-line purpose and the nodes/edges it should contain. For each node that has extra meaning,
give a one-sentence description and the decision ids that govern it, so the detail drawer has
something to show.]

Return the finished page as an artifact.
