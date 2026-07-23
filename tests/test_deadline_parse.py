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


# ── a date belonging to a DIFFERENT clause/event is not an application deadline ─
# (clause-level extraction, audit round 5: the deadline cue+subject and the date must share one
# clause; here the only date is a semester/academic-year start, so there is no deadline date.)
def test_date_that_belongs_to_a_semester_start_is_not_a_deadline():
    assert _deadline(
        "The application deadline has passed, but the fall semester begins 1 September 2026."
    ) is None


def test_no_fixed_deadline_with_only_an_academic_year_date_is_a_miss():
    assert _deadline(
        "There is no fixed application deadline; the academic year begins 1 October 2026."
    ) is None


# ── the firm baseline still holds ─────────────────────────────────────────────
def test_a_clean_published_date_is_still_firm():
    iso, _, conf = _deadline("Applications close on 1 December 2026.")
    assert iso == "2026-12-01" and conf == "quoted_official"


# ── audit round 2: an OPENING date must not be emitted as a deadline ───────────
def test_opening_only_sentence_yields_no_deadline():
    # "applications open" is not a deadline cue — an opening date is the opposite of one
    assert _deadline("Applications open on 1 October 2026.") is None


def test_open_and_close_binds_the_close_date_in_application_context():
    # with an application subject present, the verb "close" owns its clause → the close date
    # (not the earlier opening date) is the firm deadline.
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


# ── audit round 3: everyday "close" near a date must NOT fabricate a deadline ──
def test_incidental_close_does_not_fabricate_a_deadline():
    for sentence in (
        "The building is close to campus; renovations finished 15 June 2021.",
        "A close collaborator since 5 May 2018.",
        "The museum is close by and reopened 12 December 2022.",
        "Office hours close at 5pm; the term started 1 September 2024.",
    ):
        assert _deadline(sentence) is None, sentence


def test_application_specific_deadline_phrasings_still_work():
    # the application/submission-specific cues we DO trust
    for sentence in (
        "Applications close on 1 December 2026.",
        "The closing date for applications is 1 December 2026.",
        "The application deadline is 1 December 2026.",
        "Submissions close 1 December 2026.",
    ):
        iso, _, conf = _deadline(sentence)
        assert iso == "2026-12-01" and conf == "quoted_official", sentence


def test_deadline_verbs_without_application_context_are_not_deadlines():
    # audit round 5: a deadline-shaped VERB (close/due by/closing date/submitted by) in a
    # sentence with no application context must never become a firm application deadline —
    # these all fabricated firm deadlines before the _APP_CONTEXT gate (D-010/D-061).
    for sentence in (
        "Office hours close on Fridays; the term started 1 September 2024.",
        "The library closes on 1 December 2026 for winter break.",
        "The gym registration closes on 1 December 2026.",
        "Rent is due by 1 December 2026.",
        "Payment is due by 1 December 2026.",
        "The store's closing date is 1 December 2026.",
        "Tax returns must be submitted by 1 December 2026.",
    ):
        assert _deadline(sentence) is None, sentence


def test_deadline_verbs_with_application_context_extract_firmly():
    # the legitimate counterparts of the above — an application/submission subject is present
    for sentence in (
        "Applications must be submitted by 1 December 2026.",
        "The submission deadline is 1 December 2026.",
        "Apply by 1 December 2026.",
        "The closing date for applications is 1 December 2026.",
    ):
        iso, _, conf = _deadline(sentence)
        assert iso == "2026-12-01" and conf == "quoted_official", sentence


# ── audit round 5: a compound sentence binds the date to the APPLICATION clause ─
def test_compound_sentence_binds_the_application_deadline_not_an_unrelated_date():
    # an unrelated closing date sits beside the real application deadline; the clause with the
    # application subject wins, not the leftmost cue (semicolon and comma variants).
    iso, _, conf = _deadline(
        "Office hours close on 1 December 2026; applications for the fellowship must be "
        "submitted by 15 January 2027."
    )
    assert iso == "2027-01-15" and conf == "quoted_official"
    iso2, _, conf2 = _deadline(
        "The library closes on 1 December 2026, and the application deadline is 15 January 2027."
    )
    assert iso2 == "2027-01-15" and conf2 == "quoted_official"


# ── audit round 5: domain context (phd/postdoc/position) is recognised ─────────
def test_domain_context_deadline_phrasings_are_recognised():
    for sentence in (
        "The PhD deadline is 1 December 2026.",
        "PhD studentship closes 1 December 2026.",
        "The position closes on 1 December 2026.",
        "The fellowship application deadline is 1 December 2026.",
    ):
        iso, _, conf = _deadline(sentence)
        assert iso == "2026-12-01", sentence


# ── audit round 6: a domain word in a MODIFIER (not the cue's subject) is not an
#    application deadline — tuition/registration/event deadlines that merely mention
#    "PhD"/"program" must not be fabricated as firm application deadlines. ───────
def test_payment_due_dates_are_not_application_deadlines():
    # audit (live): a fee/tuition/fine/deposit date that merely mentions "application(s)"/"applicants"
    # must NOT be emitted as a firm application deadline (D-061/D-010).
    for sentence in (
        "The application fee is due by 1 December 2026.",
        "Application fees are due by 1 December 2026.",
        "Tuition fees for applicants are due by 1 December 2026.",
        "Library fines for applicants are due by 1 December 2026.",
        "The application deposit is due by 1 December 2026.",
        # plural payment nouns must be excluded too (live probe L9i: bare "deposit" missed "Deposits")
        "Deposits for PhD applicants are due 1 December 2026.",
        "Payments for applicants are due by 1 December 2026.",
    ):
        assert _deadline(sentence) is None, sentence


def test_real_application_deadlines_still_qualify_next_to_no_payment_word():
    for sentence in (
        "Applications are due by 1 December 2026.",
        "The application deadline is 1 December 2026.",
        "Apply by 1 December 2026.",
    ):
        iso, _, conf = _deadline(sentence)
        assert iso == "2026-12-01" and conf == "quoted_official", sentence


def test_domain_word_in_a_modifier_is_not_an_application_deadline():
    for sentence in (
        "Tuition and fees for the PhD program are due by 1 December 2026.",
        "Course registration for PhD students is due by 1 December 2026.",
        "Health insurance enrollment for PhD students is due by 1 December 2026.",
        "The security deposit for PhD student housing is due by 1 December 2026.",
        "Registration for the PhD orientation closes on 1 December 2026.",
        "Registration for the postdoc symposium closes on 1 December 2026.",
        "Advisor selection for first-year PhD students is due by 1 December 2026.",
    ):
        assert _deadline(sentence) is None, sentence


def test_payment_subject_with_adjacent_domain_word_is_not_a_deadline():
    # live audit-2 finding: a fee/tuition/deposit due-date whose money noun is governed via
    # "for <domain>" ("the deposit FOR PhD studentships is due") must NOT be a firm deadline — the
    # domain word sits in a payment modifier, so the DATE attaches to the money (D-010/D-061). This
    # is the adjacent-domain-token bypass the bare _PAYMENT guard missed.
    for sentence in (
        "The deposit for PhD studentships is due by 1 December 2026.",
        "Tuition for the postdoc positions is due by 1 December 2026.",
        "Tuition fees for PhD studentships are due by 1 December 2026.",
        "Payment for the fellowship is due by 1 December 2026.",
        "The deposit for the scholarship is due by 1 December 2026.",
    ):
        assert _deadline(sentence) is None, sentence


def test_real_application_deadline_beside_a_fee_word_in_one_clause_still_qualifies():
    # live audit-2 finding: the _PAYMENT exclusion must not over-drop a REAL "Applications close"
    # deadline merely because a fee word co-occurs in the same undelimited clause — the application
    # is the clean subject of its own cue, so the close date is firm.
    iso, _, conf = _deadline("Applications close on 1 December 2026 and the fee is due then.")
    assert iso == "2026-12-01" and conf == "quoted_official"


# ── audit round 5: no quadratic blow-up on long unpunctuated text ──────────────
def test_long_unpunctuated_text_does_not_blow_up():
    # a large boilerplate/nav dump with no sentence punctuation must stay fast (no O(n^2))
    big = "Prof Someone " * 8000 + "applications close 1 December 2026"
    iso, _, conf = pipeline.extract_deadline(f"<html><body><main>{big}</main></body></html>")
    assert iso == "2026-12-01"      # still found, and returns promptly (guarded by test timeout)


# ── audit round 3: a non-firm phrase in a dateless OTHER clause must not demote ─
def test_nonfirm_in_a_dateless_clause_does_not_demote_a_firm_deadline():
    iso, _, conf = _deadline(
        "The application deadline is 1 December 2026; the spring semester begins later."
    )
    assert iso == "2026-12-01" and conf == "quoted_official"


def test_projected_keyword_in_the_clause_makes_it_a_watch_date():
    # a projection word sharing the deadline clause → the date is a watch date, not firm (D-061)
    iso, _, conf = _deadline("Applications typically close 1 December 2026.")
    assert iso == "2026-12-01" and conf == "inferred"
