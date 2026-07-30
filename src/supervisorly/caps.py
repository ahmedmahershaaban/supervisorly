"""The §3.5 collection caps — **one definition, two enforcers.**

These bound what a single plan may ask for. They are our own product choice, not an API
limit, and they exist so one student cannot spend the shared budget on one scan (D-069).

They live here rather than in ``webapi`` because **the page and the server must agree on
the number**. When they disagree, the student meets the cap at the wrong moment: the
wizard let them check 49 topics with a counter that never mentioned a limit, and only the
final "Start scan" click said ``'resolved_topic_ids' must hold at most 25 topics (got 49)``
— a server error, two steps from the checkboxes that caused it, naming no way out. A cap
the student cannot see until the last click is a dead end, and D-069/D-070 forbid dead
ends. So ``export/webapp.py`` renders this number into the page and ``webapi.py`` enforces
it on the wire; neither may hardcode its own.

``webapi`` keeps the server-side check as defence in depth — a plan can arrive from a file
or a script that never ran the page.
"""

from __future__ import annotations

#: Serialized plan JSON size limit.
PLAN_MAX_BYTES = 64 * 1024

#: ``resolved_topic_ids`` per plan. A broad field genuinely maps to many topics — "Machine
#: Learning · NLP" across nine phrasings offered 111 — so 25 was stingy in a way students
#: hit routinely. The number is affordable because :data:`TOPIC_FILTER_CHUNK` keeps the
#: OpenAlex request shape unchanged; see that constant for what actually costs money.
MAX_TOPICS = 50

#: How many topic ids may ride in ONE OpenAlex ``topics.id:a|b|c`` OR-filter.
#:
#: This is deliberately **not** :data:`MAX_TOPICS`. OpenAlex documents a limit on OR-list
#: length and we have not measured it: the attempt hit `429 Insufficient budget … resets at
#: midnight UTC` — OpenAlex's free budget is **per caller**, and this workstation's was spent
#: on the day's spikes while production, on its own address, kept answering normally. So the
#: number stays unverified for a reason unrelated to the product. 25 is the width already
#: proven by every scan that has run; anything wider is untested. Chunking makes the cap
#: independent of that unknown: a 50-topic plan issues two 25-wide queries whose results are
#: merged, instead of one query nobody has confirmed the API will accept.
#:
#: The cost is one extra request per institution per chunk, and only for students who
#: deliberately choose more than 25 topics. If a measurement later shows a wider OR-list is
#: accepted, raising this halves those requests — that is the whole change.
TOPIC_FILTER_CHUNK = 25

#: Universities named in a plan.
MAX_UNIVERSITIES = 50

#: Named professors ("deep-dive these people directly").
MAX_TARGETS = 100

#: Shortlist size (professors read thoroughly) and institution scan width.
SHORTLIST_MIN, SHORTLIST_MAX = 1, 200
MAX_INSTITUTIONS_MIN, MAX_INSTITUTIONS_MAX = 1, 300

#: Free-text field length.
FIELD_MAX_CHARS = 200

#: Concurrent browser pages. Capped low on purpose: this is concurrency ACROSS hosts — one
#: host is always strictly serial (CC-3.3/CC-3.4) — and every page above it is a running
#: Chromium tab on somebody's machine. 8 saturates a laptop long before it saturates the
#: politeness budget, so a bigger number buys memory pressure, not speed.
CONCURRENCY_MIN, CONCURRENCY_MAX = 1, 8


def chunk_topics(topic_ids, size: int = TOPIC_FILTER_CHUNK) -> list[list[str]]:
    """Split topic ids into OR-filter-sized chunks. ``[]`` in, ``[]`` out (no filter)."""
    ids = [t for t in (topic_ids or []) if t]
    if not ids:
        return []
    step = max(1, int(size))
    return [ids[i:i + step] for i in range(0, len(ids), step)]
