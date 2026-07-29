"""FLAG — shipping a half-finished phase safely.

Two properties, and they only work together:

1. A gated phase is **off by default**, so a deploy that forgets ``PHASES`` ships the
   branch's existing behaviour rather than a half-finished phase.
2. An off phase **says so** in the CC-1 ledger. This is the half that matters. The render
   rung once shipped and did nothing for two deploys because a separate change had quietly
   removed its input — nothing was broken enough to fail, so nothing said anything. A flag
   without a ledger row reproduces exactly that silence, deliberately.

And one boundary: flags are **server configuration**. A student's browser must never be able
to switch on a phase that is off because it is not ready (D-068).
"""

from __future__ import annotations

import json

import pytest
from helpers_export import stable_bytes

from supervisorly import jobs, phases, pipeline
from supervisorly.discover import openalex, ror
from supervisorly.fetch.transport import CassetteTransport
from supervisorly.phases import OPTIONAL_PHASES, PHASES_ENV, PhaseFlags

EMAIL = "me@uni.edu"
ALLOW = "User-agent: *\nAllow: /\n"
PLAN = {"intent_kind": "pre_phd", "country": "CA", "field": "causal ml",
        "resolved_topic_ids": ["T10001"], "university_mode": "all"}
_FAST = {"rate_limit": 0.0, "backoff_sleep": lambda _s: None}

ROR_CA = json.dumps({"number_of_results": 1, "items": [
    {"id": "https://ror.org/00abc11",
     "names": [{"value": "Maple University", "types": ["ror_display", "label"], "lang": "en"}],
     "locations": [{"geonames_details": {"country_code": "CA"}}],
     "links": [{"type": "website", "value": "https://maple.example/"}], "types": ["education"]},
]})
ADA_PAGE = ("<html><body><main><h1>Dr. Ada Maple</h1>"
            "<p>I am recruiting two PhD students for Fall 2027.</p></main></body></html>")


# ── parsing ───────────────────────────────────────────────────────────────────
def test_unset_means_every_gated_phase_is_off():
    """Default off. A deploy that forgets the variable must not ship a half-built phase."""
    flags = PhaseFlags.from_env({})
    assert flags.enabled == frozenset()
    assert flags.off() == OPTIONAL_PHASES
    for p in OPTIONAL_PHASES:
        assert not flags.is_on(p)


@pytest.mark.parametrize("raw", ["", "   ", ",", " , ,"])
def test_empty_and_junk_separators_are_off_not_an_error(raw):
    """A malformed flag fails CLOSED. Raising here would take down a worker over a config
    typo, and the safe direction is the one that runs today's behaviour."""
    assert PhaseFlags.from_env({PHASES_ENV: raw}).enabled == frozenset()


def test_names_are_case_and_whitespace_insensitive():
    """`PHASES=" P0 "` is what a human types into a console; it must mean what it says."""
    assert PhaseFlags.from_env({PHASES_ENV: " P0 "}).is_on("p0")


def test_a_typo_is_recorded_rather_than_dropped():
    """A flag that silently does nothing is how "I turned it on" and "it is on" diverge."""
    flags = PhaseFlags.from_env({PHASES_ENV: "p0,pZ"})
    assert flags.is_on("p0")
    assert flags.unknown == ("pz",)


def test_a_planned_but_unbuilt_phase_is_distinguished_from_a_typo():
    """"Known, not built yet" and "not a phase" are different answers for whoever is
    mid-plan, so they are not collapsed into one bucket."""
    flags = PhaseFlags.from_env({PHASES_ENV: "p1,nonsense"})
    assert flags.not_yet_built == ("p1",)
    assert flags.unknown == ("nonsense",)
    assert not flags.is_on("p1"), "naming an unbuilt phase must not pretend it runs"


def test_summary_is_ascii_and_names_both_sides():
    """It goes to a Cloud Logging line, which is ASCII by construction (worker convention)."""
    s = PhaseFlags.from_env({PHASES_ENV: "p0"}).summary()
    assert s.isascii() and "on=p0" in s and "off=" in s


# ── the ledger half ───────────────────────────────────────────────────────────
def _transport():
    tp = CassetteTransport()
    tp.record(ror.country_url("CA"), 200, ROR_CA)
    tp.record(openalex.institutions_url("https://ror.org/00abc11", EMAIL), 200,
              json.dumps({"results": [{"id": "https://openalex.org/I100"}]}))
    tp.record(openalex.authors_url("I100", EMAIL, topic_ids=["T10001"]), 200, json.dumps({
        "results": [{"id": "https://openalex.org/A200", "display_name": "Dr. Ada Maple",
                     "works_count": 30, "cited_by_count": 300,
                     "topics": [{"id": "https://openalex.org/T10001"}],
                     "last_known_institutions": [],
                     "homepage_url": "https://maple.example/~ada"}]}))
    tp.record("https://maple.example/robots.txt", 200, ALLOW)
    tp.record("https://maple.example/~ada", 200, ADA_PAGE)
    return tp


def _run(tmp_path=None, **kw):
    import tempfile
    from pathlib import Path
    d = Path(tmp_path) if tmp_path else Path(tempfile.mkdtemp(prefix="svflag-"))
    return pipeline.run_live(PLAN, _transport(), d / "snaps", email=EMAIL, **_FAST, **kw)


def _ledger(result):
    return {r["phase"]: r for r in result["export"]["run"]["ledger"]}


def test_an_off_phase_writes_a_ledger_row_saying_so():
    """FLAG-2. Off must be VISIBLE. This is the assertion that would have caught the render
    rung doing nothing for two deploys."""
    led = _ledger(_run(phase_flags=PhaseFlags.all_off()))
    for p in OPTIONAL_PHASES:
        assert p in led, f"phase {p} is off and said nothing — that is the silent failure"
        assert led[p]["reached"] == 0
        assert led[p]["reason"], "an off phase must explain itself"


def test_the_off_row_says_how_to_turn_it_on():
    """A ledger entry that only says "did not run" is a shrug. Naming the variable turns it
    into an instruction."""
    led = _ledger(_run(phase_flags=PhaseFlags.all_off()))
    reason = led[OPTIONAL_PHASES[0]]["reason"]
    assert PHASES_ENV in reason and OPTIONAL_PHASES[0] in reason


def test_the_off_row_counts_what_the_flag_actually_cost():
    """"p0 skipped 0" would understate an off flag to nothing. The skip count is the
    shortlist — the professors the phase would have covered."""
    result = _run(phase_flags=PhaseFlags.all_off())
    led = _ledger(result)
    n = len(result["export"]["professors"])
    assert n > 0, "the fixture must actually enumerate someone, or this asserts nothing"
    assert led[OPTIONAL_PHASES[0]]["skipped"] == n


def test_a_typo_reaches_the_ledger_not_just_the_log():
    """The person who set a bad flag reads the dashboard, not the container log."""
    led = _ledger(_run(phase_flags=PhaseFlags.from_env({PHASES_ENV: "p0,typo"})))
    assert "typo" in led["phase_flags"]["reason"]
    assert led["phase_flags"]["skipped"] == 0, (
        "a configuration note must not inflate a skip count — that would be a lie about "
        "coverage, not a warning about config")


def test_no_flag_note_when_the_configuration_is_clean():
    """The note is a warning; a warning that always fires is noise nobody reads."""
    assert "phase_flags" not in _ledger(_run(phase_flags=PhaseFlags.all_off()))


# ── FLAG-4: all off is byte-identical to today ────────────────────────────────
def test_with_every_phase_off_the_evidence_output_is_unchanged():
    """FLAG-4, read precisely: the flags may add LEDGER rows (that is FLAG-2's whole point)
    but must not alter a single professor, field, envelope or coverage line.

    Compared against a run given no flags object at all — i.e. the default path a deploy
    that never heard of PHASES takes.
    """
    a = _run(phase_flags=PhaseFlags.all_off())
    b = _run()                                    # default: reads PHASES, which is unset

    def _payload(result):
        e = json.loads(stable_bytes(result["export"]))
        e["run"].pop("ledger")
        return json.dumps(e, sort_keys=True).encode()

    assert _payload(a) == _payload(b)


def test_an_enabled_phase_gets_no_off_row():
    """The complement of FLAG-2, and the one that keeps the ledger truthful in the other
    direction: a phase that IS on must never be reported as skipped-because-off. Its own
    call site writes the real row once the phase exists.

    Flags are independent, so this holds per phase — with more than one gated phase, turning
    one on leaves every other one's off row exactly where it was.
    """
    led = _ledger(_run(phase_flags=PhaseFlags.of(*OPTIONAL_PHASES)))
    for p in OPTIONAL_PHASES:
        assert "is off" not in (led.get(p, {}).get("reason") or ""), (
            f"{p} is ON but its ledger row still reads as off")


def test_off_rows_are_written_only_for_the_phases_that_are_off():
    """One flag on, the rest off: exactly the off ones explain themselves."""
    on = OPTIONAL_PHASES[0]
    led = _ledger(_run(phase_flags=PhaseFlags.of(on)))
    for p in OPTIONAL_PHASES:
        if p == on:
            continue
        assert PHASES_ENV in (led[p]["reason"] or ""), f"{p} is off and said nothing"


# ── FLAG-3: server config only ────────────────────────────────────────────────
def test_a_request_cannot_turn_a_phase_on(tmp_path):
    """D-068. A plan is request-derived; it must not be able to enable a phase.

    Checked at the seam a request actually crosses — ``run_scan_job`` receives the plan
    verbatim from the job document.
    """
    plan = dict(PLAN, phases="p0", PHASES="p0")   # a hostile/confused client

    class _Hooks:
        def __init__(self): self.result = None
        def on_event(self, e): pass
        def should_stop(self): return False
        def on_done(self, r): self.result = r
        def on_failed(self, m): raise AssertionError(m)

    hooks = _Hooks()
    jobs.run_scan_job(plan, hooks, transport=_transport(), email=EMAIL,
                      db_path=tmp_path / "db.sqlite", snap_root=tmp_path / "snaps",
                      out_html=tmp_path / "d.html", out_json=tmp_path / "d.json",
                      **_FAST)
    led = {r["phase"]: r for r in hooks.result["export"]["run"]["ledger"]}
    for p in OPTIONAL_PHASES:
        assert PHASES_ENV in (led[p]["reason"] or ""), (
            f"a plan key switched on {p} — phase flags must be server config only (D-068)")


def test_the_submitted_run_params_carry_no_phase_key():
    """The other half of the same boundary: nothing phase-shaped is even recorded on the job
    document, so there is no field for a later change to start honouring by accident."""
    import sys
    sys.path.insert(0, "firebase")
    try:
        import _core
    except ImportError:                                   # google deps absent
        pytest.skip("firebase deps not installed")
    finally:
        sys.path.pop(0)

    captured = {}

    class _Store:
        def get(self, job_id): return {"job_id": job_id}
        def set_status(self, job_id, status, **kw): captured.update(kw)

    _core.CloudRunWorker(environ={}, client=_FakeJobsClient()).submit(
        _Store(), "job1", plan=dict(PLAN), email=EMAIL)
    assert "phases" not in json.dumps(captured).lower()


class _FakeJobsClient:
    def run_job(self, request=None): return None
