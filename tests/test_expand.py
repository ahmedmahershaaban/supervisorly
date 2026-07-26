"""D-068 — optional LLM query expansion: validated output (queries, never claims),
fail-closed on every failure class, and the API key never leaks into a return value.
No live network, no real LLM — a fake transport stands in for the POST seam."""

import json

from supervisorly.discover import expand
from supervisorly.fetch.transport import TransportError

KEY = "sk-test-secret-key"
URL = "https://api.kimi.com/coding/v1/chat/completions"


def _reply(variants):
    """An OpenAI-compatible chat-completion body wrapping a JSON-mode variants reply."""
    return json.dumps({"choices": [{"message": {"content": json.dumps(
        {"variants": variants})}}]})


def _fake(status=200, text="", seen=None):
    def transport(url, payload, headers, *, timeout):
        if seen is not None:
            seen.update({"url": url, "payload": payload, "headers": headers,
                         "timeout": timeout})
        return status, text
    return transport


def test_expand_success_returns_variants_with_the_original_first():
    seen = {}
    r = expand.expand_query("NLP", api_key=KEY,
                            transport=_fake(200, _reply([
                                "natural language processing", "computational linguistics"]),
                                seen))
    assert r == {"variants": ["NLP", "natural language processing",
                              "computational linguistics"],
                 "expanded": True, "note": ""}
    # one OpenAI-compatible JSON-mode POST to the default endpoint, model a constant
    assert seen["url"] == URL
    assert seen["payload"]["model"] == "kimi-for-coding"
    assert seen["payload"]["response_format"] == {"type": "json_object"}
    assert seen["headers"]["Authorization"] == f"Bearer {KEY}"


def test_expand_sanitizes_variants():
    variants = [
        "causal inference", "Causal Inference",      # case-insensitive dupe -> dropped
        "  ", 42, None,                               # empties / non-strings -> dropped
        "x" * 121,                                    # over-long -> dropped, not truncated
        "nlp",                                        # dupe of the original -> dropped
        " causal ml ",                                # stripped
        "v1", "v2", "v3", "v4", "v5", "v6", "v7",     # over the 8-total cap -> cut
    ]
    r = expand.expand_query("NLP", api_key=KEY, transport=_fake(200, _reply(variants)))
    assert r["expanded"] is True and r["note"] == ""
    assert r["variants"] == ["NLP", "causal inference", "causal ml",
                             "v1", "v2", "v3", "v4", "v5"]   # original first, cap 8


def test_expand_all_entries_invalid_is_an_honest_skip_not_an_error():
    r = expand.expand_query("NLP", api_key=KEY,
                            transport=_fake(200, _reply([42, "", "x" * 121])))
    assert r == {"variants": ["NLP"], "expanded": False, "note": "no usable variants"}


def test_expand_without_a_key_fails_closed_and_never_calls_the_transport(monkeypatch):
    monkeypatch.delenv(expand.ENV_KEY, raising=False)

    def bomb(url, payload, headers, *, timeout):
        raise AssertionError("transport must not be called without a key")

    r = expand.expand_query("NLP", transport=bomb)
    assert r == {"variants": ["NLP"], "expanded": False, "note": "no api key"}


def test_expand_reads_the_key_from_the_environment(monkeypatch):
    monkeypatch.setenv(expand.ENV_KEY, KEY)
    seen = {}
    r = expand.expand_query("NLP", transport=_fake(200, _reply(["nlp v2"]), seen))
    assert r["expanded"] is True
    assert seen["headers"]["Authorization"] == f"Bearer {KEY}"


def test_expand_fails_closed_on_non_200_timeout_and_transport_error():
    r = expand.expand_query("NLP", api_key=KEY, transport=_fake(429, "slow down"))
    assert r["expanded"] is False and r["variants"] == ["NLP"] and r["note"] == "http 429"

    def timed_out(url, payload, headers, *, timeout):
        raise TransportError("timeout")

    r = expand.expand_query("NLP", api_key=KEY, transport=timed_out)
    assert r["expanded"] is False and r["note"] == "timeout"

    def dead(url, payload, headers, *, timeout):
        raise TransportError("dns")

    r = expand.expand_query("NLP", api_key=KEY, transport=dead)
    assert r["expanded"] is False and r["note"] == "transport error"


def test_expand_fails_closed_on_malformed_replies():
    for body in ("not json at all",
                 json.dumps({"choices": []}),                       # no choice
                 json.dumps({"choices": [{"message": {"content": "not json"}}]}),
                 _reply("a string, not a list"),                    # variants not a list
                 json.dumps({"choices": [{"message": {"content": "{}"}}]})):
        r = expand.expand_query("NLP", api_key=KEY, transport=_fake(200, body))
        assert r == {"variants": ["NLP"], "expanded": False, "note": "malformed response"}


def test_expand_base_url_and_model_are_server_side_settings():
    seen = {}
    expand.expand_query("NLP", api_key=KEY, base_url="https://llm.example/v2/",
                        model="other-model",
                        transport=_fake(200, _reply(["x"]), seen))
    # a trailing slash on the base URL never doubles the path separator
    assert seen["url"] == "https://llm.example/v2/chat/completions"
    assert seen["payload"]["model"] == "other-model"


def test_expand_never_leaks_the_key():
    bodies = [_reply(["natural language processing"]), _reply(None), "garbage"]
    for body in bodies:
        r = expand.expand_query("NLP", api_key=KEY, transport=_fake(200, body))
        assert KEY not in json.dumps(r)
    for bad in (_fake(500, KEY), _fake(200, KEY)):   # even when the SERVER echoes it back
        r = expand.expand_query("NLP", api_key=KEY, transport=bad)
        assert r["note"] and KEY not in json.dumps(r)
    # every note is a short ASCII reason (console-safe, cp1252 convention)
    for transport in (_fake(500, "x"), _fake(200, "x")):
        r = expand.expand_query("NLP", api_key=KEY, transport=transport)
        assert r["note"].isascii() and len(r["note"]) <= 40
