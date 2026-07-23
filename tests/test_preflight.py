"""Edge cases: sparse OpenAlex/ROR coverage (D-060) and missing credentials (D-014/020)."""

import pytest

from supervisorly import demo, pipeline, preflight


def test_missing_credentials_fails_loud_with_the_exact_fix():
    with pytest.raises(preflight.MissingCredentials) as ei:
        preflight.require_credentials({})
    msg = str(ei.value)
    # names the exact env vars AND how to get each — not a vague "config error"
    assert preflight.ROR_CLIENT_ID_ENV in msg
    assert preflight.OPENALEX_KEY_ENV in msg
    assert "ror.readme.io" in msg and "openalex.org" in msg
    # points at the credential-free escape hatch
    assert "--demo" in msg


def test_partial_credentials_still_fails_naming_only_the_missing_one():
    with pytest.raises(preflight.MissingCredentials) as ei:
        preflight.require_credentials({preflight.ROR_CLIENT_ID_ENV: "abc"})
    msg = str(ei.value)
    assert preflight.OPENALEX_KEY_ENV in msg
    assert preflight.ROR_CLIENT_ID_ENV not in msg  # the one that's present isn't listed


def test_complete_credentials_pass():
    preflight.require_credentials(
        {preflight.ROR_CLIENT_ID_ENV: "abc", preflight.OPENALEX_KEY_ENV: "def"}
    )  # no raise


def test_sparse_coverage_warns_but_does_not_block():
    warnings = preflight.coverage_preflight(
        {"country": "Testistan", "openalex_works": 12, "ror_institutions": 1}
    )
    assert warnings  # something was flagged
    assert any("Testistan" in w for w in warnings)
    assert all("continues" in w.lower() for w in warnings)  # never a hard stop


def test_well_covered_country_has_no_warnings():
    assert preflight.coverage_preflight(
        {"country": "BigLand", "openalex_works": 50000, "ror_institutions": 80}
    ) == []


def test_offline_demo_needs_no_credentials(tmp_path):
    """The whole offline path runs green without ever calling require_credentials."""
    tp, targets, plan = demo.demo_fixture()
    result = pipeline.run_offline(plan, targets, tp, tmp_path / "snaps")
    assert result["export"]["professors"]  # it ran and produced output, no creds needed
