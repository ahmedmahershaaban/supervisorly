"""Subject-map stage (D-066): free-text field -> hierarchical OpenAlex topic map.

API-derived only (D-038) — the OpenAlex topics search endpoint returns topic objects that
carry their own ``subfield``/``field``/``domain`` hierarchy (each ``{id, display_name}``);
this module groups the hits domain -> field -> subfield, sorts topics by ``works_count``
descending, and caps the result HONESTLY: a cap hit or a mid-pagination failure records a
truncation marker (the same ``truncated_sources`` pattern as the OpenAlex client, D-037) so
a partial map is never presented as complete. An empty query or a genuine no-results page is
an honest empty map, never an error. The user multi-selects from this map; the selected IDs
become the plan's ``resolved_topic_ids``.

A genuine empty (200, zero results — NOT a failure) triggers deterministic query relaxation:
the topics ``search`` matches display names only, so a multi-word phrase can miss every topic
while its single words hit the right neighborhood (live-verified: "mechanistic
interpretability" -> 0 topics, "interpretability" -> the XAI neighborhood). The fallback
searches each query word on its own, unions the hits by topic id, and ranks by query-word
overlap then ``works_count``; the result then carries ``relaxed_from`` naming the original
query, so the broadening is always honest, never a silent substitution.
"""

from __future__ import annotations

import json
import re

from ..fetch.transport import Transport, TransportError
from .openalex import PER_PAGE, _short_id, topics_url

#: Bucket label for a topic whose hierarchy level is missing from the API object —
#: honest "we don't know", never a crash on a null ``domain``/``field``/``subfield``.
UNGROUPED = "ungrouped"

#: Minimum word length for a per-word relaxation search — a purely mechanical filter,
#: no stopword dictionary (D-038 stays clean).
MIN_WORD_LEN = 4


def _get_json(transport: Transport, url: str) -> dict | None:
    try:
        resp = transport.get(url)
    except TransportError:
        return None
    if resp.status != 200:
        return None
    try:
        return json.loads(resp.text)
    except ValueError:
        return None


def _level(topic: dict, name: str) -> str:
    return ((topic.get(name) or {}).get("display_name")) or UNGROUPED


def _fetch_topics(transport: Transport, query: str, email: str | None, key: str | None,
                  max_results: int) -> tuple[list[dict], bool]:
    """Paginate the topics search for ``query``; return ``(topics, truncated)``.

    ``truncated`` is set when a page fetch failed (transport / non-200 / bad JSON) or the
    page cap was hit with a full last page — PARTIAL, never a false "complete" (D-037).
    """
    topics: list[dict] = []
    truncated = False
    page = 1
    max_pages = max(1, -(-max_results // PER_PAGE))     # ceil(max_results / PER_PAGE)
    while page <= max_pages:
        data = _get_json(transport, topics_url(query, email, key, page=page))
        if data is None:
            # transport / non-200 / bad JSON: first page -> we know nothing; mid-pagination ->
            # the unfetched pages are unknown. Either way PARTIAL, not a false "complete".
            truncated = True
            break
        results = data.get("results") or []
        topics.extend(results)
        if len(results) < PER_PAGE:                     # natural end of the listing
            break
        page += 1
    else:
        truncated = True            # page cap hit with a full last page — more results existed
    return topics, truncated


def _relax_words(query: str) -> list[str]:
    """Per-word fallback queries: unique words of >= MIN_WORD_LEN chars, deduped
    case-insensitively, in first-appearance order — mechanical only (D-038)."""
    seen: set[str] = set()
    words: list[str] = []
    for w in query.split():
        k = w.casefold()
        if len(w) >= MIN_WORD_LEN and k not in seen:
            seen.add(k)
            words.append(w)
    return words


def _topic_matches(topic: dict, word: str) -> bool:
    """True if ``word`` appears in the topic's display name OR its OpenAlex keywords
    (case-insensitive, word-boundary). Keywords matter: the canonical topic for a niche
    phrase often names itself differently ("Explainable Artificial Intelligence (XAI)"
    carries the keyword "Machine Learning Interpretability"), so a name-only match ranks
    off-target mega-topics above it."""
    haystack = " ".join(
        [topic.get("display_name") or ""] + [k for k in (topic.get("keywords") or []) if k])
    return bool(haystack.strip()) and bool(
        re.search(rf"\b{re.escape(word)}\b", haystack, re.IGNORECASE))


def _word_overlap(topic: dict, words: list[str]) -> int:
    """How many of the original query words match the topic (see ``_topic_matches``)."""
    return sum(1 for w in words if _topic_matches(topic, w))


def _overlap_score(topic: dict, words: list[str], idf: dict[str, float]) -> float:
    """Distinctiveness-weighted overlap: each matched word contributes its idf —
    1 / (1 + total hits for that word's own search). A rare word ("causal") outweighs
    generic ones ("machine", "learning") whose searches flood the topic index, so the
    distinctive half of a query ranks above the generic half instead of being outvoted
    one-word-each."""
    return sum(idf.get(w.casefold(), 1.0) for w in words if _topic_matches(topic, w))


def subject_map(query: str, transport: Transport, *, email: str | None = None,
                key: str | None = None, max_results: int = 25) -> dict:
    """Map a free-text field to a grouped subject map:

    ``{"query", "groups": [{domain, field, subfield,
    topics: [{topic_id, name, works_count}]}], "truncated", "truncated_sources"}``.

    Topics are sorted by ``works_count`` descending and capped at ``max_results``; groups
    follow their top topic's rank. ``truncated`` (+ a ``topics@<query>`` marker) is set when
    the cap cut off existing results or a page fetch failed mid-pagination — PARTIAL, never
    a false "complete" (D-037). Empty query / no results -> honest empty ``groups``.

    A GENUINE empty (200, zero results — never a failure) relaxes the query: each query
    word is searched individually, the hits are unioned by topic id and ranked by a
    distinctiveness-weighted overlap (each matched word weighs 1/(1+its own API hit
    count), so a rare word outranks generic ones) then ``works_count``; the result
    then carries ``relaxed_from: <original query>``. A word search that FAILS keeps the
    partial union and is marked PARTIAL with a ``topics@<word>`` marker, exactly like a
    direct-path page failure. Relaxation finding nothing is the same honest empty as a
    direct miss (no ``relaxed_from``); a failure on the original query never relaxes.
    """
    result: dict = {"query": query, "groups": [], "truncated": False,
                    "truncated_sources": []}
    q = (query or "").strip()
    if not q or max_results <= 0:
        return result                                   # honest empty, never an error

    truncated_sources: list[str] = []
    topics, truncated = _fetch_topics(transport, q, email, key, max_results)
    if truncated:
        truncated_sources.append(f"topics@{q}")

    if not topics and not truncated:
        # genuine empty -> deterministic per-word relaxation (failures don't relax: the
        # direct failure path above returns PARTIAL without ever reaching this branch)
        words = _relax_words(q)
        by_id: dict[str, dict] = {}
        idf: dict[str, float] = {}
        for w in words:
            data = _get_json(transport, topics_url(w, email, key))
            if data is None:
                # a relaxed search failed: keep the partial union, mark it PARTIAL naming
                # the failing word-query — same failure class as the direct path (D-037)
                truncated = True
                truncated_sources.append(f"topics@{w}")
                continue
            # distinctiveness of this word = inverse of its own hit count (missing meta
            # -> 1.0, so every word weighs the same — the word-count ranking falls back)
            total = int(((data.get("meta") or {}).get("count")) or 0)
            idf[w.casefold()] = 1.0 / (1.0 + total)
            for t in data.get("results") or []:
                if t.get("id"):
                    by_id.setdefault(t["id"], t)        # union, deduped by topic id
        if by_id:
            result["relaxed_from"] = q
            topics = sorted(by_id.values(),
                            key=lambda t: (-_overlap_score(t, words, idf),
                                           -int(t.get("works_count") or 0)))
    else:
        topics = sorted(topics, key=lambda t: int(t.get("works_count") or 0),
                        reverse=True)

    if len(topics) > max_results:
        truncated = True            # the cap itself cut off results that existed
        marker = f"topics@{q}"
        if marker not in truncated_sources:
            truncated_sources.append(marker)

    topics = topics[:max_results]
    groups: dict[tuple[str, str, str], dict] = {}
    for t in topics:
        gkey = (_level(t, "domain"), _level(t, "field"), _level(t, "subfield"))
        group = groups.setdefault(gkey, {"domain": gkey[0], "field": gkey[1],
                                         "subfield": gkey[2], "topics": []})
        group["topics"].append({"topic_id": _short_id(t.get("id")),
                                "name": t.get("display_name"),
                                "works_count": int(t.get("works_count") or 0)})
    # topics were globally sorted, so first-appearance order ranks groups by their top topic
    result["groups"] = list(groups.values())
    result["truncated"] = truncated
    result["truncated_sources"] = truncated_sources
    return result


#: Input cap for ``subject_map_multi`` — matches the D-068 expansion contract (<= 8).
MAX_QUERIES = 8


def subject_map_multi(queries: list[str], transport: Transport, *,
                      email: str | None = None, key: str | None = None,
                      max_results: int = 25) -> dict:
    """Map several query variants (e.g. a D-068 expansion) to ONE merged subject map.

    NOT CURRENTLY WIRED IN (D-070). The shipped web page does this merge in the browser
    instead — it calls ``/api/map`` once per phrasing so that ONE failing phrasing does
    not fail the whole click, which this function cannot express: a failing variant here
    would either vanish silently or take the entire call down. Kept, not deleted, as the
    server-side counterpart to migrate to if the per-phrasing throttle cost ever bites;
    the trigger and the migration are written up in ``docs/BLOCKERS.md`` B-001.

    Runs ``subject_map`` per unique variant (stripped, deduped case-insensitively, input
    capped at MAX_QUERIES) and merges the results: topics are deduped by ``topic_id``
    keeping the BEST (lowest) rank position across variants, each topic is tagged
    ``found_by`` with the variant string(s) that surfaced it (capped at 8), and the
    domain -> field -> subfield clustering is the SAME as a single-query map — variants
    never merge or rewrite clusters. ``truncated`` is set when ANY variant truncated,
    with the union of every variant's ``truncated_sources`` (each marker already names
    its variant, D-037). A variant that returns an honest empty contributes nothing —
    never an error. The result carries ``queries`` naming the variants actually run.
    """
    seen: set[str] = set()
    unique: list[str] = []
    for q in queries or []:
        q = (q or "").strip()
        if q and q.casefold() not in seen:
            seen.add(q.casefold())
            unique.append(q)
    unique = unique[:MAX_QUERIES]

    merged: dict[str, dict] = {}        # topic_id -> {rank, gkey, topic}
    truncated = False
    truncated_sources: list[str] = []
    for q in unique:
        smap = subject_map(q, transport, email=email, key=key, max_results=max_results)
        truncated = truncated or smap["truncated"]
        for marker in smap["truncated_sources"]:
            if marker not in truncated_sources:
                truncated_sources.append(marker)
        rank = 0
        for g in smap["groups"]:
            gkey = (g["domain"], g["field"], g["subfield"])
            for t in g["topics"]:
                entry = merged.get(t["topic_id"])
                if entry is None:
                    merged[t["topic_id"]] = {
                        "rank": rank, "gkey": gkey,
                        "topic": {**t, "found_by": [q]}}
                else:
                    entry["rank"] = min(entry["rank"], rank)   # best rank across variants
                    found = entry["topic"]["found_by"]
                    if q not in found and len(found) < MAX_QUERIES:
                        found.append(q)
                rank += 1

    groups: dict[tuple[str, str, str], dict] = {}
    for entry in sorted(merged.values(), key=lambda e: e["rank"]):
        gkey = entry["gkey"]
        group = groups.setdefault(gkey, {"domain": gkey[0], "field": gkey[1],
                                         "subfield": gkey[2], "topics": []})
        group["topics"].append(entry["topic"])
    # sorted by best rank, so first-appearance order ranks groups by their top topic
    return {"queries": unique, "groups": list(groups.values()),
            "truncated": truncated, "truncated_sources": truncated_sources}
