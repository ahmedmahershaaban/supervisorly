"""B2: social pacing as deterministic code (D-065). Interval jitter, session caps,
abort-latch, reset, fail-closed corruption handling, and the CLI exit-code contract.
No wall-clock sleeping — ``now`` and the jitter source are injected."""

import json
import math
import random
from pathlib import Path

import pytest

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


# ── F4: classify() normalises framing syntax; hostile lookalikes stay None ────
def test_classify_normalises_scheme_port_and_trailing_dot():
    for host in ("x.com:443", "x.com.", "mobile.twitter.com.", "twitter.com:443",
                 "linkedin.com:8080", "https://x.com/user", "HTTPS://X.COM/u",
                 "http://user:pass@x.com/p"):
        assert pacing.classify(host) == "social", host
    assert pacing.classify("linkedin.com.cn") == "social"     # legit ccTLD variant
    assert pacing.classify("scholar.google.com.") == "scholar"
    assert pacing.classify("scholar.google.ca:443") == "scholar"


def test_classify_hostile_lookalikes_stay_unpaced():
    for host in ("evilx.com", "x.com.evil.com", "twitter.com.evil.co", "notx.com",
                 "linkedin.com.evil.com", "scholar.google.com.evil.com"):
        assert pacing.classify(host) is None, host


def test_abort_latch_applies_to_formatted_host_forms_end_to_end(tmp_path):
    state = str(_state_file(tmp_path))
    pacing.abort("x.com", "captcha shown", state_path=state)
    assert main(["pace", "--host", "x.com:443", "--state", state]) == 3
    assert main(["pace", "--host", "https://x.com/u", "--state", state]) == 3


# ── F5: the jittered interval is pinned at fetch-record time, never re-rolled ─
def test_wait_is_pinned_at_fetch_time_and_identical_on_repoll(tmp_path):
    state = _state_file(tmp_path)
    interval = random.Random(7).uniform(*pacing.POLICY["social"]["interval"])
    pacing.check("x.com", now=1000.0, state_path=state, rng=random.Random(7))
    saved = json.loads(state.read_text(encoding="utf-8"))["hosts"]["x.com"]
    assert saved["next_allowed_epoch"] == pytest.approx(1000.0 + interval)

    # a re-poll with a DIFFERENT rng sees the stored target, not a fresh draw
    res = pacing.check("x.com", now=1000.0, state_path=state, rng=random.Random(999))
    assert res["allowed"] is False and res["reason"] == "min-interval"
    assert res["wait_seconds"] == math.ceil(interval)     # stored target minus elapsed
    again = pacing.check("x.com", now=1000.0, state_path=state, rng=random.Random(1))
    assert again["wait_seconds"] == res["wait_seconds"]   # same instant, same wait


def test_waits_decrease_monotonically_and_sleeping_the_printed_wait_allows(tmp_path):
    state = _state_file(tmp_path)
    pacing.check("x.com", now=1000.0, state_path=state, rng=random.Random(0))
    waits, t = [], 1000.0
    while True:
        res = pacing.check("x.com", now=t, state_path=state, rng=random.Random(1))
        if res["allowed"]:
            break
        waits.append(res["wait_seconds"])
        t += 10.0
    assert len(waits) > 2
    assert all(b < a for a, b in zip(waits, waits[1:]))    # strictly decreasing

    # the SKILL protocol: sleep exactly the printed wait, re-check → ALLOW
    res = pacing.check("x.com", now=5000.0, state_path=state, rng=random.Random(2))
    # (state was reset by the loop above ending in an ALLOW at time t — re-pin)
    if not res["allowed"]:
        follow = pacing.check("x.com", now=5000.0 + res["wait_seconds"],
                              state_path=state, rng=random.Random(2))
        assert follow["allowed"] is True


def test_sleeping_exactly_the_first_printed_wait_allows(tmp_path):
    state = _state_file(tmp_path)
    pacing.check("x.com", now=0.0, state_path=state, rng=random.Random(3))
    res = pacing.check("x.com", now=0.0, state_path=state, rng=random.Random(4))
    assert res["allowed"] is False
    follow = pacing.check("x.com", now=0.0 + res["wait_seconds"], state_path=state,
                          rng=random.Random(5))
    assert follow["allowed"] is True


def test_legacy_entry_without_a_pinned_interval_still_paces(tmp_path):
    """State files written before interval pinning lack next_allowed_epoch — they
    fall back to a fresh draw from last_fetch_epoch (and are NOT 'state-corrupt')."""
    state = _state_file(tmp_path)
    state.write_text(json.dumps({"hosts": {"x.com": {
        "count": 1, "last_fetch_epoch": 1000.0,
        "aborted": False, "abort_reason": None}}}), encoding="utf-8")
    res = pacing.check("x.com", now=1000.0, state_path=state, rng=random.Random(0))
    assert res["allowed"] is False and res["reason"] == "min-interval"
    assert 45 <= res["wait_seconds"] <= 120


# ── F6: no lost updates — atomic saves, merge-on-save for abort and check ──────
def test_abort_latch_survives_a_concurrent_stale_check_save(tmp_path):
    """The audit interleave: B loads, A aborts + saves, B's fetch-record lands after.
    check records via a fresh-load merge, so its save never carries a stale latch."""
    state = _state_file(tmp_path)
    pacing.check("x.com", now=100.0, state_path=state, rng=random.Random(0))
    pacing.abort("x.com", "captcha shown", state_path=state)          # A lands first
    # B (which had loaded before A's abort and decided ALLOW) records its fetch
    assert pacing._record_fetch(state, "x.com", 200.0, 260.0) is True
    saved = json.loads(state.read_text(encoding="utf-8"))["hosts"]["x.com"]
    assert saved["aborted"] is True and saved["abort_reason"] == "captcha shown"
    assert saved["count"] == 2                          # B's fetch still accounted
    res = pacing.check("x.com", now=10 ** 9, state_path=state)
    assert res["allowed"] is False and "captcha shown" in res["reason"]


def test_concurrent_checks_on_different_hosts_both_land(tmp_path):
    """B loaded before A's save; B's record merges only its own host entry, so A's
    host is not clobbered."""
    state = _state_file(tmp_path)
    pacing._load(state)                                  # B loads (empty)
    pacing.check("x.com", now=100.0, state_path=state, rng=random.Random(0))   # A
    assert pacing._record_fetch(state, "www.linkedin.com", 100.0, 200.0) is True
    saved = json.loads(state.read_text(encoding="utf-8"))["hosts"]
    assert saved["x.com"]["count"] == 1
    assert saved["www.linkedin.com"]["count"] == 1


def test_atomic_save_leaves_no_temp_file(tmp_path):
    state = _state_file(tmp_path)
    pacing.check("x.com", now=100.0, state_path=state, rng=random.Random(0))
    pacing.abort("www.linkedin.com", "soft-block", state_path=state)
    assert state.exists()
    assert list(tmp_path.glob("*.tmp")) == []


# ── F7: the default state path is anchored to the user's home, not the CWD ────
def test_default_state_path_lives_under_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    res = pacing.check("x.com", now=1000.0, rng=random.Random(0))
    assert res["allowed"] is True
    assert (tmp_path / ".supervisorly" / "pacing_state.json").exists()


def test_caps_and_latches_do_not_depend_on_the_cwd(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    for d in ("cwd1", "cwd2"):
        (tmp_path / d).mkdir()
    monkeypatch.chdir(tmp_path / "cwd1")
    pacing.check("x.com", now=1000.0, rng=random.Random(0))
    monkeypatch.chdir(tmp_path / "cwd2")                 # same host, fresh CWD
    res = pacing.check("x.com", now=1000.0, rng=random.Random(0))
    assert res["allowed"] is False and res["reason"] == "min-interval"


# ── F8: semantically broken state entries fail closed (DENY state-corrupt) ─────
@pytest.mark.parametrize("entry", [
    {"count": 1, "last_fetch_epoch": "yesterday", "aborted": False,
     "abort_reason": None},                                          # string epoch
    {"count": 1, "last_fetch_epoch": 0.0},                           # missing 'aborted'
    {"count": "3", "last_fetch_epoch": 0.0, "aborted": False,
     "abort_reason": None},                                          # string count
])
def test_broken_state_entry_fails_closed_without_a_traceback(tmp_path, entry):
    state = _state_file(tmp_path)
    state.write_text(json.dumps({"hosts": {"x.com": entry}}), encoding="utf-8")
    res = pacing.check("x.com", state_path=state, rng=random.Random(0))
    assert res["allowed"] is False and "state-corrupt" in res["reason"]


def test_cli_pace_broken_state_entry_exits_3(tmp_path, capsys):
    state = _state_file(tmp_path)
    state.write_text(json.dumps({"hosts": {"x.com": {
        "count": 1, "last_fetch_epoch": "yesterday", "aborted": False,
        "abort_reason": None}}}), encoding="utf-8")
    rc = main(["pace", "--host", "x.com", "--state", str(state)])
    assert rc == 3
    out = capsys.readouterr()
    assert out.out.startswith("DENY host=x.com") and "state-corrupt" in out.out
    assert out.err == ""                                # no traceback
