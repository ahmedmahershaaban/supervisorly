"""The professor profile block: registry facts the scan already had and used to throw away.

The point of these tests is the BOUNDARY, not the plumbing. This block travels beside
quote-gated evidence, so what must never break is that it stays distinguishable from it,
stays redacted, and can never fail a scan by being unavailable.
"""

from __future__ import annotations

import pytest

from supervisorly import pipeline
from supervisorly.export import json_export as jx

TARGET = {
    "id": "A1", "name": "Dr Example",
    "institution_names": ["Cairo University", "Zewail City"],
    "works_count": 143, "cited_by_count": 2210,
    "topic_ids": ["T1", "T2", "T3"],
    "orcid": "https://orcid.org/0000-0002-1825-0097",
    "openalex_id": "https://openalex.org/A1",
    "url": "https://orcid.org/0000-0002-1825-0097", "url_kind": "orcid",
}


def test_the_facts_discovery_already_fetched_reach_the_export():
    p = pipeline._profile_for(TARGET, ["T2", "T3", "T9"])
    assert p["institutions"] == ["Cairo University", "Zewail City"]
    assert (p["works_count"], p["cited_by_count"]) == (143, 2210)
    assert p["topics_total"] == 3
    assert p["topic_overlap"] == 2                    # T2 and T3, not T9
    assert p["orcid"].endswith("0000-0002-1825-0097")


def test_url_kind_travels_so_a_blocked_row_can_explain_itself():
    """"awaiting your browser" reads as "your turn" even when no page was ever found. The
    modal can only tell those apart if it knows what kind of lead the scan had."""
    assert pipeline._profile_for(TARGET, [])["page_url_kind"] == "orcid"
    assert pipeline._profile_for({"id": "A2"}, [])["page_url_kind"] is None


def test_a_professor_with_no_registry_data_still_exports_a_profile():
    """Honest zeroes, not a missing key — the modal must not have to guard every field."""
    p = pipeline._profile_for({"id": "A9"}, [])
    assert p["works_count"] == 0 and p["institutions"] == [] and p["topic_overlap"] == 0
    assert "recent_works" not in p                    # absent, never an empty list pretending


# ------------------------------------------------------------------ recent works

class _OA:
    def __init__(self, works=None, boom=False):
        self.works, self.boom, self.calls = works or [], boom, []

    def works_by_author(self, author_id):
        self.calls.append(author_id)
        if self.boom:
            raise RuntimeError("openalex down")
        return self.works


def test_recent_works_are_newest_first_and_capped():
    oa = _OA([{"title": f"P{y}", "year": y} for y in (2019, 2026, 2021, 2024)]
             + [{"title": f"X{i}", "year": 2000 + i} for i in range(10)])
    t = dict(TARGET)
    pipeline._attach_recent_works([t], oa)
    years = [w["year"] for w in t["recent_works"]]
    assert years == sorted(years, reverse=True)
    assert years[0] == 2026
    assert len(t["recent_works"]) == pipeline.RECENT_WORKS_LIMIT


def test_a_work_with_no_title_is_dropped_rather_than_shown_blank():
    oa = _OA([{"title": None, "year": 2025}, {"title": "Real paper", "year": 2024}])
    t = dict(TARGET)
    pipeline._attach_recent_works([t], oa)
    assert [w["title"] for w in t["recent_works"]] == ["Real paper"]


def test_a_works_lookup_failure_can_never_fail_the_scan():
    """A supplementary signal must not be able to cost the student the whole result (D-037)."""
    t = dict(TARGET)
    pipeline._attach_recent_works([t], _OA(boom=True))          # must not raise
    assert "recent_works" not in t


def test_a_target_with_no_openalex_id_is_skipped_without_a_call():
    oa = _OA([{"title": "P", "year": 2025}])
    pipeline._attach_recent_works([{"id": "A3"}], oa)
    assert oa.calls == []


@pytest.mark.parametrize("oa,label", [(_OA([]), "empty result"), (_OA(boom=True), "failure")])
def test_looking_and_finding_nothing_is_recorded_as_HAVING_LOOKED(oa, label):
    """The modal shows a works COUNT from the author record. An empty publication list beside
    "4 works" reads as a bug unless the page can say which case it is — so the attempt is
    marked before the call and stays marked whatever comes back. Found in a live run: a
    professor showed "4 works" and no publications, with nothing to explain the gap."""
    t = dict(TARGET)
    pipeline._attach_recent_works([t], oa)
    assert t.get("works_checked") is True, label
    assert not t.get("recent_works"), label


def test_a_professor_outside_the_shortlist_is_not_marked_as_checked():
    """The distinction only means something if the un-looked-up case stays unmarked."""
    assert "works_checked" not in pipeline._profile_for(TARGET, [])


def test_the_modal_explains_an_empty_publication_list_either_way():
    from supervisorly.export import dashboard as dash
    html = dash.build_dashboard(
        {"schema_version": 1, "generated_at": "2026-07-29T00:00:00+00:00",
         "run": {"run_id": "r", "status": "finalized"},
         "fields": [{"id": "deadline", "label": "Deadline"}], "professors": []})
    assert "no indexed works for this person" in html      # we asked, OpenAlex had none
    assert "Not looked up" in html                          # outside the deep-dive shortlist
    assert "pr.works_checked" in html                       # the branch that tells them apart


# ------------------------------------------------------------------ the export boundary

def _export(profile):
    return jx._redact_profile(profile)


def test_an_email_hiding_in_a_publication_title_is_still_redacted():
    """A top-level-only redaction pass is a redaction pass with a hole in it — the works list
    is the nested structure that proves the walk goes deeper than one level."""
    out = _export({"recent_works": [{"title": "prof@uni.edu", "year": 2025}],
                   "institutions": ["someone@dept.edu"]})
    assert out["recent_works"][0]["title"] == "[email redacted — see source]"
    assert out["recent_works"][0]["year"] == 2025                 # non-strings untouched
    assert out["institutions"][0] == "[email redacted — see source]"


def test_a_mailto_page_url_cannot_ride_out_through_the_profile():
    out = _export({"page_url": "mailto:prof@uni.edu"})
    assert "@uni.edu" not in out["page_url"]


def test_numbers_and_nulls_survive_redaction_unharmed():
    out = _export({"works_count": 143, "orcid": None, "topics_total": 0})
    assert out == {"works_count": 143, "orcid": None, "topics_total": 0}


def test_the_profile_is_a_separate_key_from_the_quote_gated_fields():
    """The D-010 line in one assertion: nothing from the registry may appear inside `fields`,
    because everything in `fields` has passed the quote gate and this has not."""
    professors = [{"id": "A1", "name": "Dr Example", "profile": pipeline._profile_for(TARGET, [])}]
    out = jx.build_export(
        run_summary={"run_id": "r1", "status": "finalized"},
        field_descriptors=[{"id": "recruiting_signal", "label": "Recruiting"}],
        professors=professors, claims_by_entity={"A1": []},
        generated_at="2026-07-28T00:00:00+00:00")
    prof = out["professors"][0]
    assert "profile" in prof and prof["profile"]["works_count"] == 143
    assert all(k not in prof["fields"] for k in
               ("works_count", "cited_by_count", "institutions", "recent_works"))
