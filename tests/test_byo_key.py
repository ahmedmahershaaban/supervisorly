"""P7 — the student's own model key: in their browser, on their quota, never on our server.

The stakes are higher than for our own key, not lower: this is somebody else's credential for
somebody else's billing account. So the promise the panel makes ("stays in this browser, sent
only to Google, never reaches our servers") is checked structurally here rather than trusted —
including against the **D-071 error beacon**, which posts error text to us and is the one path
by which a key could leak without anyone writing code to send it.

The acceptance criterion is behavioural: with a key set, `/api/expand` is **not called at
all**, and with a bad key the wizard continues on the student's literal words.
"""

from __future__ import annotations

import re

from supervisorly.export.webapp import build_webapp


def _js(html: str) -> str:
    return html.split("<script>")[-1].split("</script>")[0]


# ── the promise, enforced ─────────────────────────────────────────────────────
def test_the_key_never_enters_the_state_object():
    """`state` is what gets serialised into the plan we POST. A key placed there would reach
    our servers without anybody intending it to."""
    js = _js(build_webapp())
    assert "state.modelKey" not in js
    assert "state.apiKey" not in js
    # The booleans that DO live in state are outcomes, not the secret.
    assert "state.ownKeyUsed" in js and "state.ownKeyFailed" in js


def test_no_code_path_posts_the_key_to_our_origin():
    """P7-1.5, the load-bearing one."""
    js = _js(build_webapp())
    for ln in js.splitlines():
        if "keyLoad()" in ln or "KEY_STORE" in ln or "modelKey" in ln:
            assert "api(" not in ln, f"key reaches our API: {ln.strip()!r}"
            assert "/api/" not in ln, f"key reaches our API: {ln.strip()!r}"


def test_the_key_only_ever_travels_to_google():
    """Both places the key is used name a Google endpoint constant, never `api()`."""
    js = _js(build_webapp())
    for fn in ("function keyTest(", "function expandWithOwnKey("):
        body = js.split(fn, 1)[1].split("\n}", 1)[0]
        assert "GEMINI" in body, f"{fn} does not call a Google endpoint"
        assert "api(" not in body, f"{fn} routes the key through our API"


def test_the_error_beacon_cannot_carry_the_key():
    """D-071 posts error text to our servers. If a key reached a message, it would ride along."""
    js = _js(build_webapp())
    beacon = js.split("function report(", 1)[1].split("\n}", 1)[0]
    for banned in ("modelKey", "KEY_STORE", "keyLoad"):
        assert banned not in beacon, f"the beacon can reach {banned}"


def test_the_key_is_not_written_into_any_note_or_error_message():
    """P7-1.3 — never in an error message or a note. Every status string is a literal."""
    js = _js(build_webapp())
    for fn in ("function keyStatus(", "function renderKeyOutcome("):
        body = js.split(fn, 1)[1].split("\n}", 1)[0]
        assert "keyLoad()" not in body and "modelKey" not in body.replace(
            'getElementById("modelKey")', ""), f"{fn} could interpolate the key"


# ── the acceptance criterion ──────────────────────────────────────────────────
def test_with_a_key_the_server_expand_endpoint_is_not_called():
    """"With a key set, /api/expand is not called at all." The branch is explicit: the server
    path is only reachable when `keyLoad()` returned nothing."""
    js = _js(build_webapp())
    body = js.split("function expandField(", 1)[1].split("\n}", 1)[0]
    assert "if(!own) return expandFieldViaServer" in body, body
    # …and the own-key branch never mentions the server path.
    own_branch = body.split("if(!own) return expandFieldViaServer", 1)[1]
    assert "expandFieldViaServer" not in own_branch
    assert "/api/expand" not in own_branch


def test_the_server_path_still_exists_for_students_without_a_key():
    js = _js(build_webapp())
    assert "function expandFieldViaServer(" in js
    assert '/api/expand' in js, "the no-key path must still call the server"


def test_a_bad_key_falls_back_to_the_students_own_words():
    """P7-1.4: never a broken scan. A refused key returns `[f]` — the literal field."""
    js = _js(build_webapp())
    body = js.split("function expandField(", 1)[1].split("\n}", 1)[0]
    assert "return [f];" in body, "no fallback to the student's own words"
    assert "state.ownKeyFailed = true" in body


def test_every_google_failure_mode_falls_back_rather_than_throwing():
    """A non-2xx (refused / quota), an unparseable body, and a network or CORS error must all
    return null so the caller can fall back. Any of them throwing would break the click."""
    js = _js(build_webapp())
    body = js.split("function expandWithOwnKey(", 1)[1].split("\n}", 1)[0]
    assert "if(!r.ok) return null;" in body            # refused / quota-exhausted
    assert "if(!txt) return null;" in body             # unparseable / empty completion
    assert ".catch(function(){ return null; })" in body  # offline / CORS / anything


def test_the_student_is_told_which_happened():
    """A key that quietly did nothing is worse than no key: the student believes their quota
    was spent and that a model chose the phrasings."""
    prose = re.sub(r"\s+", " ", build_webapp())
    assert "did not work" in prose and "your own words instead" in prose
    assert "on your quota" in prose
    js = _js(build_webapp())
    assert "renderKeyOutcome();" in js, "the outcome must actually be rendered"


def test_the_outcome_line_is_announced_to_assistive_tech():
    """It appears after an async step, so a screen-reader user needs it announced."""
    html = build_webapp()
    block = html.split('id="keyOutcome"', 1)[1][:120]
    assert 'role="status"' in html.split('id="keyOutcome"')[0][-80:] or "aria-live" in block


def test_the_key_is_stored_separately_from_the_past_searches_list():
    """Two unrelated things in one storage key would make "forget this search" and "clear my
    key" able to destroy each other."""
    js = _js(build_webapp())
    assert 'KEY_STORE = "supervisorly.modelkey"' in js
    assert 'PAST_KEY = "supervisorly.past"' in js
