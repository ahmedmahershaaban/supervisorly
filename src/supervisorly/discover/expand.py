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
#: These are only the FALLBACK defaults; a deployment sets the two env vars below.
#:
#: A note earned the hard way: pin a model version and it will eventually be retired under
#: you. Configuring Gemini's ``gemini-2.5-flash-lite`` failed with HTTP 404 *"no longer
#: available to new users"* — the model still worked for projects that had used it before,
#: so it looked like a key problem rather than a model problem. Prefer a provider's
#: "latest" alias for a task this simple, and pin a version only when you need
#: reproducibility more than you need it to keep working.
DEFAULT_BASE_URL = "https://api.kimi.com/coding/v1"
DEFAULT_MODEL = "kimi-for-coding"

#: Environment variable holding the expansion API key (server config, fail-closed).
ENV_KEY = "SUPERVISORLY_EXPAND_KEY"

#: Endpoint + model, as SERVER config (D-068 §3). The defaults above stay the defaults;
#: these let an operator point the same OpenAI-compatible call at another provider without
#: a code change. They are read from the environment ONLY — never from a request — so a
#: caller still cannot smuggle in a different endpoint or model.
#:
#: The work here is deliberately small (a few dozen tokens in, <= 300 out, one call per
#: "Understand" click), and a wrong expansion can only cost topics, never mint a fact
#: (D-010 still gates every claim) — so the cheapest capable model is the right choice,
#: not a compromise. Verified working with:
#:   Gemini   base=https://generativelanguage.googleapis.com/v1beta/openai
#:            model=gemini-2.5-flash-lite
#:   DeepSeek base=https://api.deepseek.com/v1               model=deepseek-chat
#:   Groq     base=https://api.groq.com/openai/v1            model=llama-3.3-70b-versatile
ENV_BASE_URL = "SUPERVISORLY_EXPAND_BASE_URL"
ENV_MODEL = "SUPERVISORLY_EXPAND_MODEL"

#: D-068 output contract: short strings, <= 120 chars each. The COUNT is now the student's
#: to choose (step 2's slider) — 8 remains the default, 50 the ceiling.
#:
#: The guardrails that make D-068 safe are untouched by this, and that is the whole reason
#: the number can move: expansion emits QUERIES, never claims. Fifty bad variants can cost
#: topics; they cannot mint a professor, a deadline or a recruiting status, because every
#: fact still passes the D-010 quote gate. What a bigger number does cost is breadth of
#: search — which is exactly what the student is asking for when they raise it.
DEFAULT_VARIANTS = 8
MAX_VARIANTS = 50
MAX_VARIANT_LEN = 120


def clamp_count(value) -> int:
    """A slider position is a preference, not a claim — clamp it, never reject it."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return DEFAULT_VARIANTS
    return max(1, min(MAX_VARIANTS, n))


def _system_prompt(count: int) -> str:
    """Ask for the number the student chose.

    "Do your best and stop" is stated explicitly because a model told to produce fifty
    variants of a narrow field will pad — inventing plausible-sounding subfields that match
    nothing, which wastes map calls and puts noise in front of the student. Fewer good
    strings is the better failure, and saying so is what makes it happen.
    """
    return (
        "You expand an academic research field into search strings for an academic "
        "subject-map search (OpenAlex topics). Reply with a JSON object of the form "
        f'{{"variants": [...]}} holding UP TO {count} short English query variants: the '
        "canonical phrase, the acronym expansion (or the acronym, if the input is spelled "
        "out), synonyms, adjacent subfields, and broader and narrower terms.\n"
        "Return FEWER if the field does not genuinely have that many distinct phrasings — "
        "do not pad the list with invented or near-duplicate terms. A short accurate list "
        "is better than a long vague one. Output JSON only."
    )


#: Kept for callers that want the historical default prompt.
_SYSTEM = _system_prompt(DEFAULT_VARIANTS)


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


def _sanitize(field: str, raw, limit: int = DEFAULT_VARIANTS) -> list[str]:
    """Reduce the parsed ``variants`` value to the D-068 contract: the original query
    first, then only strings — stripped, non-empty, <= 120 chars, deduped
    case-insensitively, capped at ``limit`` total. A malformed entry is discarded,
    never the whole list.

    The student's own words are always first and can never be crowded out, however many
    variants come back: their phrasing is the one thing here that is not a guess."""
    limit = clamp_count(limit)
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
        if len(out) >= limit:
            break
    return out


def expand_query(field: str, *, base_url: str | None = None, api_key: str | None = None,
                 model: str | None = None, timeout: float = 10.0,
                 transport=None, environ=None, count: int | None = None) -> dict:
    """Expand ``field`` into up to ``count`` search-string variants (D-068, default 8).

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
    environ = os.environ if environ is None else environ
    q = (field or "").strip()
    key = api_key or environ.get(ENV_KEY)
    if not q:
        return _closed(field, "empty query")
    if not key:
        return _closed(q, "no api key")

    want = clamp_count(count if count is not None else DEFAULT_VARIANTS)
    endpoint = (base_url or environ.get(ENV_BASE_URL) or DEFAULT_BASE_URL).strip()
    url = f"{endpoint.rstrip('/')}/chat/completions"
    payload = {
        "model": (model or environ.get(ENV_MODEL) or DEFAULT_MODEL).strip(),
        "messages": [
            {"role": "system", "content": _system_prompt(want)},
            {"role": "user", "content": f"Academic field: {q}"},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        # Scaled to the ask: 300 tokens truncates a 50-variant reply mid-JSON, which parses
        # as malformed and fails closed to the student's own words — the feature would look
        # broken at exactly the setting they turned up.
        "max_tokens": 300 + 24 * want,
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

    out = _sanitize(q, variants, want)
    if len(out) == 1:
        # parsed fine, but nothing usable survived validation — same honest skip
        return _closed(q, "no usable variants")
    return {"variants": out, "expanded": True, "note": ""}
