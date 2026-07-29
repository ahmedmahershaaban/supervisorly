"""The one network call ``llm_claims`` deliberately does not make.

``llm_claims`` is pure: prompt in, proposals out, no transport, no key, no retries — which is
what lets its whole contract be tested with no network (D-011/D-063). Something still has to
carry the prompt to a model, and this is it: a factory that turns environment configuration
into a ``complete(prompt) -> str`` callable of exactly the shape ``llm_claims.propose`` wants.

**It is the same seam as ``discover/expand.py``, on purpose.** Same OpenAI-compatible
``/chat/completions`` shape, same ``post_json`` helper, same fail-closed discipline, and the
same "any provider with an OpenAI-compatible endpoint" story. Two different ways to call a
model would be two different places to leak a key and two different fallback behaviours.

**Fail-closed is the default, not a branch** (D-068): no key configured means
``completer_from_env`` returns ``None``, the caller never asks a model anything, and the scan
runs on the deterministic extractors exactly as it does today. A timeout, a non-200, or a
malformed body raises inside ``complete``, and ``llm_claims.propose`` already treats any
exception as an empty proposal list. **Nobody's search dies because a model was unavailable.**

**The key never leaves this module.** It is read from the environment, put in an
``Authorization`` header, and never returned, logged, or written into an error message — the
same rule ``expand.py`` follows, and the reason failures here say "http 401" and not why.
"""

from __future__ import annotations

import json
import os

from ..discover.expand import DEFAULT_BASE_URL, TransportError, post_json

#: Its own key, deliberately not shared with ``expand.py``'s. The two calls have very
#: different shapes — one asks for a handful of search strings, the other reads whole pages —
#: so an operator who wants a cheap model for query expansion and a stronger one for reading
#: can say so, and one that wants neither turns both off independently.
ENV_KEY = "SUPERVISORLY_EXTRACT_KEY"
ENV_BASE_URL = "SUPERVISORLY_EXTRACT_BASE_URL"
ENV_MODEL = "SUPERVISORLY_EXTRACT_MODEL"

DEFAULT_MODEL = "kimi-k2-0905-preview"

#: A page's worth of reasoning, not a conversation. ``llm_claims`` caps the page it sends at
#: ``MAX_PAGE_CHARS`` and asks for at most ``MAX_PROPOSALS`` (field, value, quote) triples;
#: this is sized for that reply plus the quotes, which are the bulky part.
MAX_TOKENS = 1_500

#: Reading a page is slower than naming eight search variants, so this is not expand's 10s.
DEFAULT_TIMEOUT = 30.0


def completer_from_env(environ=None, *, transport=None, timeout: float = DEFAULT_TIMEOUT):
    """Build ``complete(prompt) -> str``, or ``None`` when no key is configured.

    ``None`` is the honest answer to "can this run read pages with a model" and the caller is
    expected to branch on it once, at the top, rather than discovering the absence per page.

    ``transport`` is the test seam — the same ``(url, payload, headers, *, timeout) ->
    (status, text)`` contract ``expand.expand_query`` uses.
    """
    environ = os.environ if environ is None else environ
    key = (environ.get(ENV_KEY) or "").strip()
    if not key:
        return None
    endpoint = (environ.get(ENV_BASE_URL) or DEFAULT_BASE_URL).strip().rstrip("/")
    model = (environ.get(ENV_MODEL) or DEFAULT_MODEL).strip()
    url = f"{endpoint}/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    poster = transport if transport is not None else post_json

    def complete(prompt: str) -> str:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            # Reading, not writing: the answer is quotes copied off a page, and a model that
            # gets creative here produces quotes that fail the gate and vanish anyway.
            "temperature": 0.0,
            "max_tokens": MAX_TOKENS,
        }
        try:
            status, text = poster(url, payload, headers, timeout=timeout)
        except TransportError as exc:
            raise RuntimeError(str(exc) if str(exc) == "timeout" else "transport error") from None
        if status != 200:
            raise RuntimeError(f"http {status}")     # never the key, never the body
        return json.loads(text)["choices"][0]["message"]["content"]

    return complete
