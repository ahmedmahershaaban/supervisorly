"""Subject-map stage (D-066): free-text field -> hierarchical OpenAlex topic map.

API-derived only (D-038) — the OpenAlex topics search endpoint returns topic objects that
carry their own ``subfield``/``field``/``domain`` hierarchy (each ``{id, display_name}``);
this module groups the hits domain -> field -> subfield, sorts topics by ``works_count``
descending, and caps the result HONESTLY: a cap hit or a mid-pagination failure records a
truncation marker (the same ``truncated_sources`` pattern as the OpenAlex client, D-037) so
a partial map is never presented as complete. An empty query or a genuine no-results page is
an honest empty map, never an error. The user multi-selects from this map; the selected IDs
become the plan's ``resolved_topic_ids``.
"""

from __future__ import annotations

import json

from ..fetch.transport import Transport, TransportError
from .openalex import PER_PAGE, _short_id, topics_url

#: Bucket label for a topic whose hierarchy level is missing from the API object —
#: honest "we don't know", never a crash on a null ``domain``/``field``/``subfield``.
UNGROUPED = "ungrouped"


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


def subject_map(query: str, transport: Transport, *, email: str | None = None,
                key: str | None = None, max_results: int = 25) -> dict:
    """Map a free-text field to a grouped subject map:

    ``{"query", "groups": [{domain, field, subfield,
    topics: [{topic_id, name, works_count}]}], "truncated", "truncated_sources"}``.

    Topics are sorted by ``works_count`` descending and capped at ``max_results``; groups
    follow their top topic's rank. ``truncated`` (+ a ``topics@<query>`` marker) is set when
    the cap cut off existing results or a page fetch failed mid-pagination — PARTIAL, never
    a false "complete" (D-037). Empty query / no results -> honest empty ``groups``.
    """
    result: dict = {"query": query, "groups": [], "truncated": False,
                    "truncated_sources": []}
    q = (query or "").strip()
    if not q or max_results <= 0:
        return result                                   # honest empty, never an error

    topics: list[dict] = []
    truncated = False
    page = 1
    max_pages = max(1, -(-max_results // PER_PAGE))     # ceil(max_results / PER_PAGE)
    while page <= max_pages:
        data = _get_json(transport, topics_url(q, email, key, page=page))
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
    if len(topics) > max_results:
        truncated = True            # the cap itself cut off results that existed

    topics = sorted(topics, key=lambda t: int(t.get("works_count") or 0),
                    reverse=True)[:max_results]
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
    if truncated:
        result["truncated_sources"] = [f"topics@{q}"]
    return result
