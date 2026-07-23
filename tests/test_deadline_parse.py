"""Regression tests for the deadline parser, from the adversarial audit (§5).

Covers three confirmed findings:
  * ordinal ("1st December") and numeric ("13/12/2026") dates are recognised, not dropped;
  * an impossible calendar date (Feb 31) is never invented into a value;
  * a date living in a *different clause* than the deadline cue is shown as watch, not firm.
"""

from supervisorly import pipeline


def _page(sentence):
    return f"<html><body><main><p>{sentence}</p></main></body></html>"


def _deadline(sentence):
    return pipeline.extract_deadline(_page(sentence))


# ── finding: ordinal + numeric shapes must be recognised (not searched_absent) ─
def test_ordinal_month_day_is_firm():
    iso, _, conf = _deadline("Applications close December 1st, 2026.")
    assert iso == "2026-12-01" and conf == "quoted_official"


def test_ordinal_day_month_is_firm():
    iso, _, conf = _deadline("Applications close 1st December 2026.")
    assert iso == "2026-12-01" and conf == "quoted_official"


def test_disambiguated_numeric_date_is_a_watch_date():
    # 13 > 12 → day=13, month=12; numeric form is inherently lower-confidence → watch
    iso, _, conf = _deadline("The application deadline is 13/12/2026.")
    assert iso == "2026-12-13" and conf == "inferred"


def test_genuinely_ambiguous_numeric_is_not_guessed():
    # 01/12/2026 could be 1 Dec or 12 Jan — unknowable without locale, so we do NOT guess
    assert pipeline._normalize_date("Applications due 01/12/2026.") is None
    assert _deadline("Applications due 01/12/2026.") is None


# ── finding: impossible calendar dates must never become a value ───────────────
def test_impossible_dates_are_rejected():
    assert pipeline._normalize_date("February 31, 2026") is None
    assert pipeline._normalize_date("31 April 2026") is None
    assert pipeline._normalize_date("2026-02-30") is None
    # and end to end: an impossible-date deadline sentence yields no deadline value
    assert _deadline("Applications close February 31, 2026.") is None


# ── finding: a date in a different clause than the cue is not firm ─────────────
def test_date_in_a_different_clause_is_watch_not_firm():
    iso, _, conf = _deadline(
        "The application deadline has passed, but the fall semester begins 1 September 2026."
    )
    assert iso == "2026-09-01" and conf == "inferred"          # never shown as firm


def test_no_fixed_deadline_clause_is_watch():
    iso, _, conf = _deadline(
        "There is no fixed application deadline; the academic year begins 1 October 2026."
    )
    assert iso == "2026-10-01" and conf == "inferred"


# ── the firm baseline still holds ─────────────────────────────────────────────
def test_a_clean_published_date_is_still_firm():
    iso, _, conf = _deadline("Applications close on 1 December 2026.")
    assert iso == "2026-12-01" and conf == "quoted_official"


# ── audit round 2: an OPENING date must not be emitted as a deadline ───────────
def test_opening_only_sentence_yields_no_deadline():
    # "applications open" is not a deadline cue — an opening date is the opposite of one
    assert _deadline("Applications open on 1 October 2026.") is None


def test_open_and_close_sentence_binds_the_close_date():
    # the date nearest the cue ("close") is the deadline — not the earlier opening date
    iso, _, conf = _deadline(
        "Applications open on 1 October 2026 and close on 1 December 2026."
    )
    assert iso == "2026-12-01" and conf == "quoted_official"


def test_deadline_stated_before_the_cue_is_still_found():
    iso, _, conf = _deadline("1 December 2026 is the application deadline.")
    assert iso == "2026-12-01" and conf == "quoted_official"


# ── audit round 2: a firm deadline in the cue's own clause stays firm ──────────
def test_but_in_a_later_clause_does_not_demote_a_firm_deadline():
    iso, _, conf = _deadline(
        "Applications are due by 1 December 2026, but decisions come in March."
    )
    assert iso == "2026-12-01" and conf == "quoted_official"


def test_generic_start_word_does_not_demote_a_firm_deadline():
    iso, _, conf = _deadline("The deadline to start your application is 1 December 2026.")
    assert iso == "2026-12-01" and conf == "quoted_official"


def test_semicolon_apply_early_stays_firm():
    iso, _, conf = _deadline("The application deadline is 1 December 2026; apply early.")
    assert iso == "2026-12-01" and conf == "quoted_official"
