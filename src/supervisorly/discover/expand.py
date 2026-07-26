"""Optional LLM query expansion for the subject-map search (D-068).

The deterministic layer stays LLM-free for *facts* (D-009). The one sanctioned exception:
this module may use an LLM to turn a student's raw phrasing ("NLP", "natural language
procssisng") into candidate *search strings* for the OpenAlex topics search — **queries,
never claims** (D-068). A wrong expansion yields zero topics; it can never mint a
professor, a deadline, or a recruiting status — every fact still passes the D-010 quote
gate.

Guardrails, all in code (D-068):

1. **Validated output.** The reply is parsed as JSON and reduced to a list of <= 8 short
   strings (<= 120 chars each, deduped case-insensitively, original query first);
   anything else is discarded — a malformed ENTRY is dropped, never the whole list.
2. **Fail-closed.** No key, any transport error, a non-200, a timeout, or an unparseable
   reply -> expansion is skipped and the raw query proceeds; nobody is ever blocked by a
   missing LLM. The failure is reported in a short ASCII ``note``, never raised.
3. **Server-side only.** The key comes from the ``api_key`` parameter or the
   ``SUPERVISORLY_EXPAND_KEY`` environment variable (server config) and is NEVER logged,
   returned, or included in ``note``; the model and base URL are module constants.
"""

from __future__ import annotations

import json
import os

from ..fetch.transport import TransportError

#: Server-side settings (D-068) — never request parameters a caller can smuggle in.
DEFAULT_BASE_URL = "https://api.kimi.com/coding/v1"
DEFAULT_MODEL = "kimi-for-coding"

#: Environment variable holding the expansion API key (server config, fail-closed).
ENV_KEY = "SUPERVISORLY_EXPAND_KEY"

#: D-068 output contract: <= 8 short strings, <= 120 chars each.
MAX_VARIANTS = 8
MAX_VARIANT_LEN = 120

_SYSTEM = (
    "You expand an academic research field into search strings for an academic "
    "subject-map search (OpenAlex topics). Reply with a JSON object of the form "
    '{"variants": [...]} holding up to 6 short English query variants: the canonical '
    "phrase, the acronym expansion (or the acronym, if the input is spelled out), "
    "synonyms, one broader term, and one narrower term. Output JSON only."
)


def post_json(url: str, payload: dict, headers: dict, *, timeout: float = 10.0):
    """Minimal POST helper — the ``fetch.transport`` seam is GET-only, so the expansion
    POST lives here (httpx lazily imported, offline use needs no dependency).

    Returns ``(status, text)``; a network/DNS failure raises ``TransportError`` and a
    timeout raises ``TransportError("timeout")`` so the caller can fail closed with an
    honest, key-free reason."""
    import httpx  # noqa: PLC0415 — intentional lazy import

    try:
        r = httpx.post(url, json=payload, headers=headers, timeout=timeout)
    except httpx.TimeoutException as exc:
        raise TransportError("timeout") from exc
    except httpx.HTTPError as exc:
        raise TransportError("transport error") from exc
    return r.status_code, r.text


def _closed(field: str, reason: str) -> dict:
    """Fail-closed result: the raw query proceeds, expansion silently skipped (D-068)."""
    return {"variants": [field], "expanded": False, "note": reason}


def _sanitize(field: str, raw) -> list[str]:
    """Reduce the parsed ``variants`` value to the D-068 contract: the original query
    first, then only strings — stripped, non-empty, <= 120 chars, deduped
    case-insensitively, capped at MAX_VARIANTS total. A malformed entry is discarded,
    never the whole list."""
    out = [field]
    seen = {field.casefold()}
    for v in raw:
        if not isinstance(v, str):
            continue
        v = v.strip()
        if not v or len(v) > MAX_VARIANT_LEN or v.casefold() in seen:
            continue
        seen.add(v.casefold())
        out.append(v)
        if len(out) >= MAX_VARIANTS:
            break
    return out


def expand_query(field: str, *, base_url: str | None = None, api_key: str | None = None,
                 model: str | None = None, timeout: float = 10.0,
                 transport=None) -> dict:
    """Expand ``field`` into up to 8 search-string variants (D-068).

    Sends ONE OpenAI-compatible chat completion to ``{base_url}/chat/completions``
    (JSON-mode reply ``{"variants": [...]}``) and returns
    ``{"variants": [...], "expanded": True, "note": ""}`` on success. Any failure — no
    API key, transport error, non-200, timeout, malformed JSON — fails CLOSED:
    ``{"variants": [field], "expanded": False, "note": "<short ascii reason>"}``. The
    key is never logged, returned, or included in ``note``.

    ``transport`` is the test seam: a callable ``(url, payload, headers, *, timeout) ->
    (status, text)`` with the same contract as ``post_json``; the default builds the
    httpx-backed helper, so cassette tests need neither network nor a real LLM.
    """
    q = (field or "").strip()
    key = api_key or os.environ.get(ENV_KEY)
    if not q:
        return _closed(field, "empty query")
    if not key:
        return _closed(q, "no api key")

    url = f"{(base_url or DEFAULT_BASE_URL).rstrip('/')}/chat/completions"
    payload = {
        "model": model or DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": f"Academic field: {q}"},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "max_tokens": 300,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    poster = transport if transport is not None else post_json
    try:
        status, text = poster(url, payload, headers, timeout=timeout)
    except TransportError as exc:
        return _closed(q, str(exc) if str(exc) == "timeout" else "transport error")
    if status != 200:
        return _closed(q, f"http {status}")
    try:
        data = json.loads(text)
        content = data["choices"][0]["message"]["content"]
        variants = json.loads(content)["variants"]
        if not isinstance(variants, list):
            raise ValueError("variants is not a list")
    except (ValueError, TypeError, KeyError, IndexError):
        return _closed(q, "malformed response")

    out = _sanitize(q, variants)
    if len(out) == 1:
        # parsed fine, but nothing usable survived validation — same honest skip
        return _closed(q, "no usable variants")
    return {"variants": out, "expanded": True, "note": ""}
