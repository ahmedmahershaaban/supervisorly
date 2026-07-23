"""Reality-based credential checks (D-014/019/023) and sparse coverage (D-060).

ROR is keyless and OpenAlex is free, so the only hard requirement for a live scan is a valid
**contact email** (the OpenAlex polite pool + our User-Agent). An OpenAlex premium key is optional."""

import pytest

from supervisorly import demo, pipeline, preflight


def test_missing_contact_email_fails_loud_with_the_exact_fix():
    with pytest.raises(preflight.MissingCredentials) as ei:
        preflight.require_credentials({})
    msg = str(ei.value)
    assert preflight.CONTACT_EMAIL_ENV in msg
    assert "openalex.org" in msg and "ror.org" in msg
    assert "no keys are required" in msg.lower()     # honest: not a key hunt
    assert "--demo" in msg                            # points at the credential-free path


def test_a_garbage_email_is_rejected():
    with pytest.raises(preflight.MissingCredentials):
        preflight.require_credentials({preflight.CONTACT_EMAIL_ENV: "not-an-email"})


def test_a_valid_contact_email_passes_no_keys_needed():
    preflight.require_credentials({preflight.CONTACT_EMAIL_ENV: "me@uni.edu"})  # no raise


def test_openalex_premium_key_is_optional():
    # a scan is allowed with just the email; the premium key is a nice-to-have, not required
    env = {preflight.CONTACT_EMAIL_ENV: "me@uni.edu"}
    preflight.require_credentials(env)                 # no raise, no key present
    assert preflight.openalex_key(env) is None
    assert preflight.openalex_key({**env, preflight.OPENALEX_KEY_ENV: "sk-123"}) == "sk-123"


def test_contact_email_helper_reads_the_value():
    assert preflight.contact_email({preflight.CONTACT_EMAIL_ENV: " me@uni.edu "}) == "me@uni.edu"
    assert preflight.contact_email({}) is None


def test_sparse_coverage_warns_but_does_not_block():
    warnings = preflight.coverage_preflight(
        {"country": "Testistan", "openalex_works": 12, "ror_institutions": 1}
    )
    assert warnings
    assert any("Testistan" in w for w in warnings)
    assert all("continues" in w.lower() for w in warnings)


def test_well_covered_country_has_no_warnings():
    assert preflight.coverage_preflight(
        {"country": "BigLand", "openalex_works": 50000, "ror_institutions": 80}
    ) == []


def test_offline_demo_needs_no_credentials(tmp_path):
    """The whole offline path runs green without ever calling require_credentials."""
    tp, targets, plan = demo.demo_fixture()
    result = pipeline.run_offline(plan, targets, tp, tmp_path / "snaps")
    assert result["export"]["professors"]
