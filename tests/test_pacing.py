"""B2: social pacing as deterministic code (D-065). Interval jitter, session caps,
abort-latch, reset, fail-closed corruption handling, and the CLI exit-code contract.
No wall-clock sleeping — ``now`` and the jitter source are injected."""

import json
import random

from supervisorly.cli import main
from supervisorly.ethics import pacing


def _state_file(tmp_path):
    return tmp_path / "pacing_state.json"


# ── classification (suffix match, subdomains included) ────────────────────────
def test_classification_by_suffix_including_subdomains():
    assert pacing.classify("x.com") == "social"
    assert pacing.classify("mobile.twitter.com") == "social"
    assert pacing.classify("www.linkedin.com") == "social"
    assert pacing.classify("scholar.google.com") == "scholar"
    assert pacing.classify("scholar.google.co.uk") == "scholar"
    assert pacing.classify("Twitter.COM") == "social"        # case-insensitive
    assert pacing.classify("notx.com") is None               # not a suffix trick
    assert pacing.classify("example.edu") is None


def test_non_social_host_is_a_noop(tmp_path):
    res = pacing.check("example.edu", state_path=_state_file(tmp_path))
    assert res == {"allowed": True, "wait_seconds": 0, "reason": "ok"}
    assert not _state_file(tmp_path).exists()     # nothing recorded for default hosts


# ── intervals + jitter ────────────────────────────────────────────────────────
def test_first_visit_is_allowed_and_recorded(tmp_path):
    res = pacing.check("x.com", now=1000.0, state_path=_state_file(tmp_path),
                       rng=random.Random(0))
    assert res == {"allowed": True, "wait_seconds": 0, "reason": "ok"}
    state = json.loads(_state_file(tmp_path).read_text(encoding="utf-8"))
    assert state["hosts"]["x.com"]["count"] == 1
    assert state["hosts"]["x.com"]["last_fetch_epoch"] == 1000.0


def test_immediate_second_visit_is_denied_with_wait_in_the_interval(tmp_path):
    rng = random.Random(0)
    pacing.check("x.com", now=1000.0, state_path=_state_file(tmp_path), rng=rng)
    res = pacing.check("x.com", now=1000.0, state_path=_state_file(tmp_path), rng=rng)
    assert res["allowed"] is False and res["reason"] == "min-interval"
    assert 45 <= res["wait_seconds"] <= 120        # social interval (D-065)


def test_visit_after_the_interval_is_allowed(tmp_path):
    rng = random.Random(0)
    pacing.check("x.com", now=1000.0, state_path=_state_file(tmp_path), rng=rng)
    res = pacing.check("x.com", now=1000.0 + 200.0, state_path=_state_file(tmp_path),
                       rng=rng)
    assert res == {"allowed": True, "wait_seconds": 0, "reason": "ok"}


def test_scholar_interval_uses_its_own_range(tmp_path):
    rng = random.Random(0)
    pacing.check("scholar.google.com", now=0.0, state_path=_state_file(tmp_path), rng=rng)
    res = pacing.check("scholar.google.com", now=0.0, state_path=_state_file(tmp_path),
                       rng=rng)
    assert res["allowed"] is False and 60 <= res["wait_seconds"] <= 180


# ── session caps ──────────────────────────────────────────────────────────────
def test_social_session_cap_denies_after_15_pages(tmp_path):
    rng = random.Random(0)
    now = 1000.0
    for i in range(15):
        now += 200.0                               # always past any jittered interval
        res = pacing.check("x.com", now=now, state_path=_state_file(tmp_path), rng=rng)
        assert res["allowed"] is True, f"page {i + 1} unexpectedly denied"
    res = pacing.check("x.com", now=now + 200.0, state_path=_state_file(tmp_path), rng=rng)
    assert res["allowed"] is False and "session-cap" in res["reason"]


def test_scholar_cap_is_5(tmp_path):
    rng = random.Random(0)
    now = 0.0
    for _ in range(5):
        now += 300.0
        assert pacing.check("scholar.google.com", now=now,
                            state_path=_state_file(tmp_path), rng=rng)["allowed"] is True
    assert pacing.check("scholar.google.com", now=now + 300.0,
                        state_path=_state_file(tmp_path), rng=rng)["allowed"] is False


# ── abort-on-challenge latch + reset ──────────────────────────────────────────
def test_abort_latches_and_the_reason_surfaces(tmp_path):
    pacing.abort("x.com", "captcha shown", state_path=_state_file(tmp_path))
    res = pacing.check("x.com", state_path=_state_file(tmp_path))
    assert res["allowed"] is False and "captcha shown" in res["reason"]
    # latched: still denied far in the future — never retry harder
    res = pacing.check("x.com", now=10 ** 12, state_path=_state_file(tmp_path))
    assert res["allowed"] is False


def test_reset_clears_one_host_or_all(tmp_path):
    state = _state_file(tmp_path)
    pacing.abort("x.com", "soft-block", state_path=state)
    pacing.abort("www.linkedin.com", "login redirect", state_path=state)

    pacing.reset("x.com", state_path=state)
    assert pacing.check("x.com", state_path=state, rng=random.Random(0))["allowed"] is True
    assert pacing.check("www.linkedin.com", state_path=state)["allowed"] is False

    pacing.reset(state_path=state)               # all hosts
    assert pacing.check("www.linkedin.com", state_path=state,
                        rng=random.Random(0))["allowed"] is True


# ── corruption fails closed ───────────────────────────────────────────────────
def test_corrupt_state_file_denies_fail_closed(tmp_path):
    state = _state_file(tmp_path)
    state.write_text("{not json", encoding="utf-8")
    res = pacing.check("x.com", state_path=state)
    assert res["allowed"] is False and "state-corrupt" in res["reason"]


def test_structurally_invalid_state_denies_fail_closed(tmp_path):
    state = _state_file(tmp_path)
    state.write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
    assert pacing.check("x.com", state_path=state)["allowed"] is False


def test_missing_state_file_is_a_fresh_start_not_corruption(tmp_path):
    res = pacing.check("x.com", state_path=_state_file(tmp_path), rng=random.Random(0))
    assert res["allowed"] is True


# ── CLI: pace ─────────────────────────────────────────────────────────────────
def test_cli_pace_allow_then_deny_exit_codes(tmp_path, capsys):
    state = str(_state_file(tmp_path))
    assert main(["pace", "--host", "x.com", "--state", state]) == 0
    out = capsys.readouterr().out
    assert out.startswith("ALLOW host=x.com wait=0s reason=ok")
    out.encode("ascii")

    assert main(["pace", "--host", "x.com", "--state", state]) == 3
    out = capsys.readouterr().out
    assert out.startswith("DENY host=x.com") and "reason=min-interval" in out


def test_cli_pace_non_social_host_allows(tmp_path, capsys):
    assert main(["pace", "--host", "example.edu",
                 "--state", str(_state_file(tmp_path))]) == 0
    assert "ALLOW" in capsys.readouterr().out


def test_cli_pace_abort_and_reset(tmp_path, capsys):
    state = str(_state_file(tmp_path))
    assert main(["pace", "--host", "x.com", "--abort", "captcha shown",
                 "--state", state]) == 0
    assert "ABORTED host=x.com" in capsys.readouterr().out
    assert main(["pace", "--host", "x.com", "--state", state]) == 3
    assert "captcha shown" in capsys.readouterr().out

    assert main(["pace", "--reset", "x.com", "--state", state]) == 0
    assert "RESET host=x.com" in capsys.readouterr().out
    assert main(["pace", "--host", "x.com", "--state", state]) == 0   # fresh again
