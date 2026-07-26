"""tests for the HTTP subject-map wrapper (webapi.py) — cassettes only, no network."""

from __future__ import annotations

import json

from supervisorly import preflight, webapi
from supervisorly.discover import openalex
from supervisorly.fetch.transport import CassetteTransport

EMAIL = "test@example.com"


def _topic(n, name, works=100, field="Computer Science", subfield="AI"):
    return {"id": f"https://openalex.org/T{n}", "display_name": name,
            "works_count": works,
            "domain": {"id": "d", "display_name": "Physical Sciences"},
            "field": {"id": "f", "display_name": field},
            "subfield": {"id": "s", "display_name": subfield}}


def _page(topics, count=None):
    return json.dumps({"meta": {"count": count if count is not None else len(topics)},
                       "results": topics})


def test_missing_field_is_a_400():
    status, body = webapi.handle_subject_map({"email": EMAIL})
    assert status == 400 and "field" in body["error"]


def test_invalid_email_is_a_400():
    tp = CassetteTransport()
    status, body = webapi.handle_subject_map({"field": "causal ML", "email": "not-an-email"},
                                             transport=tp)
    assert status == 400 and "email" in body["error"]


def test_email_falls_back_to_the_environment():
    tp = CassetteTransport()
    tp.record(openalex.topics_url("causal ml", EMAIL), 200, _page([_topic(1, "Causal inference")]))
    status, body = webapi.handle_subject_map(
        {"field": "causal ml"}, transport=tp,
        environ={preflight.CONTACT_EMAIL_ENV: EMAIL})
    assert status == 200 and body["groups"], body


def test_valid_field_returns_the_map_shape():
    tp = CassetteTransport()
    tp.record(openalex.topics_url("causal ml", EMAIL), 200,
              _page([_topic(1, "Causal inference", 900), _topic(2, "Machine learning", 5000)]))
    status, body = webapi.handle_subject_map({"field": "causal ml", "email": EMAIL},
                                             transport=tp)
    assert status == 200
    assert body["query"] == "causal ml"
    assert body["groups"][0]["topics"][0]["name"] == "Machine learning"  # works_count sort
    assert body["truncated"] is False


def test_relaxation_flows_through_the_endpoint():
    tp = CassetteTransport()
    tp.record(openalex.topics_url("causal ml", EMAIL), 200, _page([], count=0))
    tp.record(openalex.topics_url("causal", EMAIL), 200,
              _page([_topic(1, "Causal inference")], count=27))
    status, body = webapi.handle_subject_map({"field": "causal ml", "email": EMAIL},
                                             transport=tp)
    assert status == 200 and body["relaxed_from"] == "causal ml"


def test_bad_max_results_is_a_400():
    assert webapi.handle_subject_map({"field": "x", "email": EMAIL, "max_results": "abc"})[0] == 400
    assert webapi.handle_subject_map({"field": "x", "email": EMAIL, "max_results": 0})[0] == 400


def test_internal_failure_is_a_500_without_a_stack(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("secret internals")
    monkeypatch.setattr(webapi.subjects, "subject_map", boom)
    status, body = webapi.handle_subject_map({"field": "x", "email": EMAIL},
                                             transport=CassetteTransport())
    assert status == 500 and "RuntimeError" in body["error"] and "secret internals" not in body["error"]
