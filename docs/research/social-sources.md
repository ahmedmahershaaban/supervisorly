# Social & Personal Channels for Recruiting Signals — 2026 Assessment

**Project:** Supervisorly · **Scope:** Reading a professor's own social/personal channels for recruiting
signals ("recruiting PhD students for Fall 2027", "lab has an opening", "NOT taking students this cycle",
pre-doc/RA calls) using only public, non-login, non-ToS-violating surfaces where possible.

**Method note.** Every endpoint claim below is marked **VERIFIED** (I called it live from a sandbox on
2026-07-23 and report the actual status code / fields) or **DOC** (read from documentation / reputable
reporting). Empirical testing was done with plain `fetch()` and a browser User-Agent, no auth, no cookies —
exactly what the tool would have.

---

## Per-channel table

| # | Channel | Public unauth read in 2026? | Login / bot-wall? | ToS on automated access | Recruiting content it carries | **Verdict** |
|---|---------|------------------------------|-------------------|--------------------------|-------------------------------|-------------|
| 1 | **X / Twitter** | **No usable path.** Profile-timeline syndication is dead (empty). Single-tweet endpoints work but need a tweet ID you can't enumerate. Nitter dead/bot-walled. | Timeline reading requires login or paid API. Nitter instances 403/JS-challenge/502. | Scraping "in any form, for any purpose" prohibited w/o written consent; $15k/1M-post liquidated damages; aggressive enforcement since 2023 (DOC). | Pinned "recruiting" tweets, "my lab is hiring", "NOT taking students", RA/pre-doc calls, retweets of dept ads. High-value when present. | **Human-rung only** |
| 2 | **Bluesky** | **Yes — cleanest source.** `public.api.bsky.app` XRPC, no auth. | None. | Open AT Protocol; public AppView is *designed* for public-web read use. Dev guidelines bar bulk automated *interactions* (writes/follows/likes), not reads (DOC). | Same as X for academics who migrated there; growing academic presence. | **Tool-fetchable (public)** |
| 3 | **Mastodon / Fediverse** | **Yes**, per-instance public REST, no auth. | None (public statuses). Some instances `authorized_fetch` restricts federation, not the local REST read. | Per-instance; no blanket anti-scrape; rate-limited (~300 req/5min/IP observed). | Openings, "boosts" of dept calls, lab news; academics cluster on fediscience.org, mastodon.social, hci.social, etc. | **Tool-fetchable (public)** |
| 4 | **LinkedIn** | No — content is behind a login/bot wall. | Yes, hard. | User agreement bars scraping; hiQ settlement ($500k judgment, permanent injunction) shows public-data scraping still breaches the *contract* even where CFAA doesn't apply (DOC). | "We're hiring a PhD/postdoc", reposts of dept ads. | **Human-rung or skip** |
| 5 | **Professor's OWN site + linked pages** | **Yes — the single best source.** Plain public HTML the tool fetches directly. | None. | Site owner's own content; robots.txt should be honored but personal/lab sites rarely disallow. | **Where recruiting status appears most often, in plain prose.** openings pages, "joining my lab", prospective-students pages, group "News", pinned banners. | **Tool-fetchable (public)** |
| 6 | **GitHub** | **Yes** — REST API + raw READMEs, no auth (limited). | None; just a low unauth rate limit. | Public API, documented limits; scraping the *API* as intended is fine. | Profile/org/lab-repo READMEs sometimes carry "I'm recruiting" notes or PhD-advice docs. Secondary signal. | **Tool-fetchable (public)** |
| 7 | **Google Scholar** | No — `robots.txt` `Disallow: /scholar`. | Bot-wall + robots-disallowed. | Robots disallows crawling `/scholar`; no public API. | Rarely carries recruiting signal at all. | **Skip (human-rung at most)** |

---

## Channel deep-dives

### 1. X / Twitter — the important one, tested empirically

**Verdict: human-rung only.** There is no public, unauthenticated way for the tool to enumerate a given
professor's recent tweets in 2026. Details, all VERIFIED unless marked:

- **(a) Syndication `timeline/profile`** — `GET https://cdn.syndication.twimg.com/timeline/profile?screen_name=<handle>`
  → **HTTP 200 with a 0-byte body** (also with `&lang=en`, `&showReplies=true`, browser UA). **VERIFIED dead**
  for profile-timeline enumeration. This surface used to back embedded profile timelines; it no longer returns
  content.
- **(a) Single-tweet syndication `tweet-result`** — `GET https://cdn.syndication.twimg.com/tweet-result?id=<id>&token=<any>`
  → **HTTP 200 JSON** with `text`, `user.screen_name`, `created_at`, `favorite_count` (**VERIFIED** on id `20`).
  With **no** `token` param → returns `{}` (**VERIFIED**). Any non-empty token (e.g. `token=a`) works.
  **Fatal limitation:** it renders **one tweet whose numeric ID you already have.** There is no unauth way to
  *list* a user's tweet IDs, so this cannot discover a professor's recruiting tweet — it can only re-render a
  tweet you were already handed.
- **(a) oEmbed** — `GET https://publish.twitter.com/oembed?url=<...>`:
  - For a **profile URL** (`.../BarackObama`) → HTTP 200 but `html` is just an embed-widget stub
    (`<a class="twitter-timeline">Posts by …</a><script src="platform.x.com/widgets.js">`) — **no tweet text**
    (**VERIFIED**).
  - For a **single live tweet URL** → HTTP 200 with the tweet text inside `html` (**VERIFIED** on `jack/status/20`).
  - Same chicken-and-egg problem: you must already know the tweet URL.
- **(b) Guest-token / GraphQL public endpoints** — these exist and are what scraper libraries use, but reaching
  them requires minting a guest/bearer token and hitting internal GraphQL routes, which is exactly the
  "scraping … in any form" that X's ToS **prohibits without written consent** (DOC), with **$15,000 per
  1,000,000 posts** liquidated damages and active litigation against scrapers since 2023. **Do not recommend
  — ToS-violating.**
- **(c) Nitter and instances** — **VERIFIED all dead or bot-walled**: `nitter.net` → 200 empty (dead);
  `nitter.poast.org` → 403 "Verifying your browser" JS challenge; `nitter.privacyredirect.com` → 502;
  `xcancel.com` → 403 Forbidden (its `/rss` returns "This URL only works inside an RSS client");
  `nitter.tiekoetter.com` → "Making sure you're not a bot!" challenge; `lightbrd.com` → 403. **No instance
  returned tweets to a plain fetch.** Nitter is not a reliable tool surface in 2026.
- **(d) Official X API pricing (DOC, 2026)** — As of **6 Feb 2026** X replaced tiered plans with **pay-per-use**
  as the default for new developers. **No free read tier.** Post reads bill **~$0.005/read, hard-capped at 2M
  reads/month** (≈ $10,000/mo at the cap); beyond that requires an **Enterprise** contract (~$42,000+/mo).
  Legacy **Basic ($200/mo)** and **Pro ($5,000/mo)** are closed to new signups. **No tier is viable for a
  self-hosted, open-source, per-user tool.**

**Conclusion on X:** not tool-fetchable, not even "best-effort" — the free surfaces cannot enumerate a
timeline, the paid API is priced out, ToS forbids the scraping routes, and Nitter is gone. X recruiting signal
must be retrieved on the **human rung** (student's own logged-in session).

### 2. Bluesky — VERIFIED, cleanest social source. Confirmed.

Public AppView at `https://public.api.bsky.app`, **no auth, no key**. Working calls (all **VERIFIED**, HTTP 200):

- Resolve handle → DID:
  `GET https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle?handle=<handle>`
  → `{ "did": "did:plc:…" }`.
- Author feed (recent posts):
  `GET https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed?actor=<handle-or-did>&limit=<n>`
  → `feed[]`, each `feed[i].post` has `uri, cid, author, record, indexedAt, likeCount, repostCount, replyCount`;
  the post **text** is at `feed[i].post.record.text`, timestamp at `record.createdAt`. `actor` accepts the raw
  handle, so the resolve step is optional.
- Profile / bio:
  `GET https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile?actor=<handle>`
  → includes `description` (bio), `displayName`, `pinnedPost`, counts. The **bio and pinned post** are prime
  recruiting-signal fields.

**Rate limits (DOC, docs.bsky.app):** the public AppView is cached and documented as having "generous"
limits with a request to contact them if you hit them; the underlying PDS/entryway caps overall requests at
**3,000 per 5 minutes per IP**. No rate-limit headers were present on public AppView responses in testing.
**ToS/guidelines (DOC):** open AT Protocol, public data explicitly intended for public-web read use;
developer guidelines restrict **bulk automated *interactions*** (writes, mass follow/like), **not reads.**
Reading author feeds is squarely in-bounds. **Confirmed: cleanest social source.**

### 3. Mastodon / Fediverse — VERIFIED, per-instance.

Per-instance public REST, **no auth** (all **VERIFIED** on `mastodon.social`, HTTP 200):

- `GET https://<instance>/api/v1/accounts/lookup?acct=<username>` → account object with `id`, `note` (bio, HTML).
- `GET https://<instance>/api/v1/accounts/<id>/statuses?limit=<n>` → array; each status has `content` (HTML),
  `url` (public permalink), `created_at`, `tags`, `visibility`.
- Rate-limit headers observed: `x-ratelimit-limit: 300`, `x-ratelimit-remaining`, `x-ratelimit-reset`
  (≈ **300 requests / 5-min window per IP**, VERIFIED).
- **Per-instance nature confirmed:** `GET https://fediscience.org/api/v1/instance` → 200 (`FediScience.org`,
  v4.5.13). You must first know the professor's home instance (from their handle `@user@instance`) and query
  *that* host. Some instances enable `authorized_fetch`, which restricts server-to-server federation but does
  **not** block the local public REST read of public statuses. Academics cluster on fediscience.org,
  mastodon.social, hci.social, and university-run instances. **Tool-fetchable, rate-limited, per-instance.**

### 4. LinkedIn — legal/ToS posture (DOC).

**Verdict: not tool-fetchable; human-rung or skip.** The nuance from **hiQ Labs v. LinkedIn** matters and cuts
against scraping even though it started as a "scraping is legal" case:

- The Ninth Circuit (2019, reaffirmed Apr 2022 after Supreme Court remand) held the **CFAA does not** bar
  automated collection of **publicly accessible** data — i.e., scraping public pages is not "unauthorized
  access" under that criminal statute.
- **But** the case ended (Dec 2022 stipulated judgment) with a **$500,000 judgment against hiQ**, an
  admission of liability for **breach of contract** (violating LinkedIn's user agreement), **CFAA** liability
  for using **fake accounts to reach password-protected pages**, plus **trespass to chattels** and
  **misappropriation**, and a **permanent injunction** forcing hiQ to stop scraping and delete the data.
- **Takeaway for Supervisorly:** even public LinkedIn scraping breaches LinkedIn's **contract** (the User
  Agreement expressly forbids it), and virtually all useful profile/post content sits **behind a login wall**
  anyway. Automating this from the tool is both bot-walled and contract-violating. Route to the **human rung**
  (student reads their own logged-in LinkedIn) or **skip**.

### 5. The professor's OWN site + linked pages — tool-fetchable, highest signal density.

**Verdict: tool-fetchable (public), and this is where recruiting status appears in plain text more than
anywhere else.** These are ordinary public HTML pages the tool fetches directly (honor `robots.txt`; personal
and lab sites rarely disallow). Emphasis: **actively pursue these** — a professor who is recruiting almost
always says so on their own homepage, lab site, or a dedicated page. Conventions worth probing:

- **Dedicated openings pages:** `/openings`, `openings.html`, `/joining`, `/join`, `/prospective-students`,
  `/prospective`, `/students`, `/positions`, `/vacancies`, `/hiring`, `/opportunities`.
- **Lab / group sites:** `/group`, `/lab`, `/team`, `/people`, and their **"News"** / "Announcements" section
  (recruiting cycle notes land here, often dated).
- **Homepage banners:** a pinned/top banner such as *"I am recruiting N PhD students for Fall 2027"* or
  *"I am not taking new students in 2026–27."* Parse the top-of-page block specifically.
- **Personal blog / Medium:** "Prospective students — read this first" posts, admissions-advice posts.
- **ORCID biography field:** ORCID's public API exposes the free-text bio, which sometimes carries a recruiting
  note (DOC — public ORCID record API, no auth for public fields).
- **Google Sites / Notion / group mailing-list pages:** public HTML; fetch as-is.
- **Aggregators:** a **CS/field faculty homepage** linked from the department directory is the canonical entry;
  follow its outbound links to the pages above.

### 6. GitHub — tool-fetchable (VERIFIED limits).

- **Rate limits (VERIFIED via live `X-RateLimit-*` headers):** unauthenticated **core = 60 requests/hour**,
  **search = 10 requests/minute**. With a token, **5,000 requests/hour** (DOC — standard documented limit).
  Use a token if the tool has one; 60/hr unauth is enough for a handful of professors per hour.
- **Useful endpoints (VERIFIED):** `GET https://api.github.com/users/<login>` returns `bio`, `blog`, `name`
  unauthenticated. Profile README is the repo `<login>/<login>` → fetch
  `https://raw.githubusercontent.com/<login>/<login>/<HEAD>/README.md` (404 when the user has no profile repo —
  VERIFIED on `torvalds`, who has none; handle the 404 gracefully).
- **Recruiting content:** profile READMEs, org/lab pages, and PhD-advice / "prospective-students" repo READMEs
  occasionally carry recruiting notes. **Secondary** signal, but cheap to check and fully in-bounds.

### 7. Google Scholar — skip (human-rung at most).

`https://scholar.google.com/robots.txt` disallows `/scholar`; there is no public API and the pages are
bot-walled. **Confirmed: do not scrape.** It rarely carries recruiting signal anyway (it's citation data), so
the practical verdict is **skip** for recruiting purposes; if ever needed, human-rung only.

---

## Cross-cutting answers

### A. Which channels can the tool read directly and cleanly in 2026? (ranked, verified)

1. **Professor's own site + linked pages** (homepage, openings/joining/prospective pages, lab "News", pinned
   banners) — plain HTML, **highest recruiting-signal density**, fully tool-fetchable. *(Primary target.)*
2. **Bluesky** — `public.api.bsky.app` XRPC, no auth, clean fields (`record.text`, bio, pinned post). *(VERIFIED;
   cleanest social API.)*
3. **Mastodon / Fediverse** — per-instance public REST, no auth, ~300 req/5min/IP. *(VERIFIED; must know the
   home instance.)*
4. **GitHub** — REST API + raw READMEs; 60/hr unauth or 5,000/hr with token. *(VERIFIED limits; secondary
   signal.)*
5. **ORCID biography** (public record API) — minor, but a clean structured field worth a look.

### B. Which are human-rung-only, and what the generated Claude-for-Chrome prompt should ask for

Human rung = the student runs a prompt inside **Claude for Chrome in their own logged-in session** and returns
Markdown. The generated prompt should, for each channel, ask for **verbatim text + date + permalink + a
one-line intent label**, and explicitly instruct: *do not summarize away dates or negations; copy the exact
words.*

- **X / Twitter** — "Open the professor's X profile (@handle). Scroll the last ~30 posts and the **pinned**
  post. Return every post that mentions students, PhD/MS admissions, postdoc/RA/pre-doc positions, a lab
  opening, or *not* taking students. For each: **date, permalink, and the exact text.** Include reposts of
  department ads. If the pinned post is a recruiting notice, flag it."
- **LinkedIn** — "On the professor's LinkedIn profile, check **Activity → Posts** and the About section.
  Return any post about hiring PhD/postdoc/RA, lab openings, or admissions, with **date, permalink, exact
  text.**"
- **Google Scholar** — generally omit; if included, only for confirming identity/affiliation, not recruiting.

The prompt is **generated per professor** (handles/URLs filled in) and asks the human to **paste back
Markdown**, which the tool then parses with the same signal-reading logic as Phase-1 channels.

### C. How to READ recruiting signal from a feed — generation strategy (never hardcode)

The corpus used a 5-bucket taxonomy — **recruiting/openings, application advice, what they value, current
research, mentorship** — but the **project rule is to GENERATE buckets/keywords per field + intent, not
hardcode them.** Strategy:

1. **Inputs:** the professor's **field/subfield** (e.g., "robotics", "computational biology", "medieval
   history") and the **student's need** (pre-PhD applicant vs. postdoc vs. RA/pre-doc vs. visiting).
2. **Generate an intent-scoped phrase set with the LLM.** Prompt the agent to expand each bucket into the
   phrasings a professor in *that field* actually uses for *that need* — e.g., for a pre-PhD applicant:
   "recruiting PhD students", "accepting students", "taking on a student", "openings in my group", "apply to
   our program", "join my lab"; for postdoc: "postdoc position", "funded postdoc", "seeking a postdoctoral
   researcher"; for RA/pre-doc: "pre-doctoral", "research assistant", "lab manager", "full-time RA". The set
   is **derived at runtime**, so field-specific jargon and program names surface without a static list.
3. **Scope by intent so buckets don't bleed.** A postdoc seeker should weight the postdoc phrasings and
   down-weight "apply to our PhD program"; a pre-PhD applicant does the reverse.
4. **Handle negation explicitly.** Detect and separately classify negated forms — "**not** taking new
   students", "no openings this year", "not recruiting", "unable to take on students" — as
   **negative recruiting signal**, which is *as valuable as* a positive one and must never be collapsed into
   the positive bucket by a naive keyword hit. Use a negation-aware pass (look for negators within the clause,
   not just the keyword).
5. **Resolve cycle-dating.** Extract the **cycle/year** attached to the claim — "for **2027**", "**Fall 2027**
   admissions", "**this** cycle", "**next** year" — and normalize it against **today's date** (2026-07-23).
   A "not this year" from a page last updated in 2024 is **stale**; a "recruiting for Fall 2027" seen in 2026
   is **current and high-value**. Always capture the **source timestamp** (page/post date) so freshness can be
   judged, and prefer the most recent dated statement when signals conflict.
6. **Output a normalized signal record** per hit: `{bucket, polarity (+/−), cycle/year, verbatim quote, source
   URL, source date, confidence}` — so downstream ranking can trust recency and polarity.

### D. The ethics / ToS bright line

**A human reading their own logged-in timeline in their own browser and copying public posts (Phase 3) is
categorically different from the tool scraping a login-walled or bot-walled endpoint.** The line:

- **Phase 3 (allowed):** a *person* uses *their own* authenticated session, in *their own* browser, to view
  content **they are already authorized to see**, and copies **publicly posted** text by hand (or via the
  Claude for Chrome extension acting as their agent). No credentials are shared with Supervisorly, no automated
  session is spun up against the platform, no bot-wall is defeated — it is ordinary human browsing. This is how
  every logged-in user already reads X/LinkedIn.
- **Over the line (never do from the tool):** minting guest/bearer tokens, driving headless/automated sessions
  against login- or bot-walled endpoints, using fake or shared accounts (the exact conduct that produced CFAA
  liability in hiQ), or otherwise circumventing an access control the platform put up. Its own **ToS forbids
  automated access**; that prohibition binds the tool, not a human reading their own feed.
- **Rule of thumb for Supervisorly:** the **tool** only ever touches **public, unauthenticated** surfaces
  (Bluesky public AppView, Mastodon public REST, GitHub API, ORCID, the professor's own HTML). Anything that
  needs a login, a token, or defeating a challenge is **delegated to the human rung**, where a real person
  acts within their own authorized session. The tool never holds platform credentials and never automates a
  logged-in session on the student's behalf against a site's wishes.

---

*Testing performed 2026-07-23 from an unauthenticated sandbox (plain `fetch`, browser UA). VERIFIED = called
live; DOC = documentation/reporting. Endpoints, limits, and ToS terms are not invented — where a number was
not directly observed it is labeled DOC, and uncertainty is stated inline.*
