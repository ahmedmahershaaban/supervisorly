"""D-038, enforced: the engine authors no institution URL, ever.

"Generate, don't look up" is the constraint the whole product rests on — no embedded
university list, no path dictionary, no seed addresses. A scan's URLs must all come from what
it discovered this run, so the tool works in a country nobody anticipated and cannot quietly
become a curated list of places someone already knew about.

That rule is easy to state and easy to erode. A single "helpful" constant — one known
admissions path, one university domain used to make a demo work — is how a generative
discovery ladder turns into a lookup table, and it never announces itself. Ahmed caught two
URLs in a PLAN DOCUMENT and asked whether anything was seeded; this test is so the answer
stops depending on anyone remembering.

Scope: the shipped engine. Tests and the offline demo are exempt for opposite reasons — tests
must be able to name hosts to assert against them, and the demo's `.example` addresses are
reserved-by-RFC fixtures that exist precisely so the demo touches no real institution.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[1] / "src" / "supervisorly"

#: The only hosts the engine may name, each an INFRASTRUCTURE endpoint rather than a source of
#: professors: open scholarly APIs, the configurable LLM endpoint, the public archive, and the
#: search engine the human-rung button hands to the student's own browser. None of them is an
#: institution, and none of them narrows which institutions can be found.
ALLOWED_HOSTS = {
    "api.openalex.org",        # topics/authors/works — the discovery spine
    "openalex.org",            # the canonical entity URI form (…/A123)
    "api.ror.org",             # institution registry, queried BY COUNTRY, never by name
    "pub.orcid.org",           # per-person registry, queried by the iD discovery found
    "orcid.org",               # the iD's canonical URI form
    "www.orcid.org",           # XML namespace URIs in the ORCID payload — not fetched
    "web.archive.org",         # historical snapshots of a URL discovery already found
    "duckduckgo.com",          # the human-rung SEARCH box, opened in the student's browser
    "github.com",              # a documentation reference in a docstring
    "ror.org",                 # the registry's canonical id URI form
    "127.0.0.1",               # the local dev server bind address
    # Interchangeable LLM endpoints (D-068 §3). Naming several is the OPPOSITE of a lookup
    # table: the endpoint is server config, and listing verified alternatives is what stops
    # one provider becoming load-bearing.
    "api.kimi.com", "generativelanguage.googleapis.com", "api.deepseek.com", "api.groq.com",
}

#: Files whose JOB is to name hosts we must NOT touch. A refusal list is the exact inverse of
#: a seed list: a seed list narrows where professors may be FOUND, which is what D-038
#: forbids; a refusal list narrows what we may AUTOMATE AGAINST, which D-039/D-043/D-044
#: require. Exempting them is not a loophole — a wall we cannot name is a wall we cannot
#: refuse, and `walls.py` exists precisely because a status-code check could not see one.
REFUSAL_FILES = {"walls.py", "pacing.py"}

#: A host must contain a dot — otherwise `https://mailto:...` in a docstring and bare
#: `localhost` forms register as hosts and the guard reports noise instead of seeds.
_URL = re.compile(r"https?://([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")
#: `.example` is reserved by RFC 2606 and cannot resolve — the offline demo uses it so the
#: demo provably touches no real institution (D-011/D-063).
_RESERVED = re.compile(r"\.example$|\.invalid$|\.test$|\.localhost$")


def _engine_sources(include_refusal: bool = False):
    for path in sorted(ENGINE.rglob("*.py")):
        if "__pycache__" in path.parts or path.name == "demo.py":
            continue
        if not include_refusal and path.name in REFUSAL_FILES:
            continue
        yield path


def test_the_engine_names_no_host_outside_the_infrastructure_allowlist():
    offenders: list[str] = []
    for path in _engine_sources():
        for host in _URL.findall(path.read_text(encoding="utf-8")):
            if host in ALLOWED_HOSTS or _RESERVED.search(host):
                continue
            offenders.append(f"{path.relative_to(ENGINE.parent.parent)}: {host}")
    assert not offenders, (
        "the engine names a host that is not infrastructure — if this is an institution, a "
        "faculty directory or a known admissions path, it is a seed list and D-038 forbids "
        "it:\n  " + "\n  ".join(offenders))


def test_no_academic_HOST_is_hardcoded_anywhere_in_the_engine():
    """The specific shape of the mistake: a university address baked in because it made one
    country work. The next country then works worse, silently.

    Checked on hosts parsed out of real URLs, not on raw substrings — the first version of
    this test flagged five files for docstrings containing `prof@uni.edu`, which is an
    illustrative example in prose, not an address the code will ever visit. A guard that
    cries wolf about documentation gets switched off.

    Refusal files are exempt and must be: `academia.edu` appears in `walls.py` because we
    refuse to automate against it, which is the inverse of seeding."""
    offenders = []
    for path in _engine_sources():
        for host in _URL.findall(path.read_text(encoding="utf-8")):
            if _RESERVED.search(host) or host in ALLOWED_HOSTS:
                continue
            if re.search(r"\.(edu|ac)(\.[a-z]{2})?$", host):
                offenders.append(f"{path.relative_to(ENGINE.parent.parent)}: {host}")
    assert not offenders, (
        "an academic host is hardcoded — institutions must come from the country-scoped "
        "registry query, never from source:\n  " + "\n  ".join(offenders))


def test_no_directory_path_dictionary_creeps_in():
    """No guessed paths — `/staff`, `/faculty`, `/people`, `/admission`. This is the same
    defect as a seed list wearing different clothes, and Ahmed put the reason better than the
    original plan did: **the patterns change from site to site and country to country, so the
    path must be EXTRACTED, never predicted.**

    An Egyptian, Japanese or Brazilian university does not arrange itself like the ones whose
    conventions someone happened to encode, and an Arabic-language site may share no path
    vocabulary at all. Guessing works for the sites the author thought of and fails silently
    everywhere else — which reads as "that country has no professors" rather than as a bug.

    The supported method is: fetch what the ladder discovered, EXTRACT its links, and decide
    what a page is from the page itself (`roster.classify_directory`) — after fetching, not
    before. Following a site's own links needs no dictionary and works in any language."""
    suspicious = re.compile(
        r'["\'](?:/(?:staff|faculty|people|team|members|admission|admissions|apply'
        r'|graduate|postgraduate)/?)["\']')
    offenders = []
    for path in _engine_sources():
        text = path.read_text(encoding="utf-8")
        for m in suspicious.finditer(text):
            line = text[:m.start()].count("\n") + 1
            offenders.append(f"{path.relative_to(ENGINE.parent.parent)}:{line} {m.group(0)}")
    assert not offenders, (
        "a directory-path dictionary is forming — paths differ per site and per country, so "
        "they must be extracted from the pages we fetch, never listed:\n  "
        + "\n  ".join(offenders))


def test_refusal_files_are_exempt_for_the_opposite_reason():
    """Guard the exemption itself. `walls.py` and `pacing.py` name hosts deliberately, and the
    distinction that makes that legitimate is directional: a seed list narrows where
    professors may be FOUND; a refusal list narrows what we may AUTOMATE AGAINST. If a file
    in this set ever starts naming universities, the exemption is being abused."""
    for name in REFUSAL_FILES:
        matches = [p for p in ENGINE.rglob(name)]
        assert matches, f"{name} no longer exists — update REFUSAL_FILES"
        text = matches[0].read_text(encoding="utf-8")
        for host in _URL.findall(text):
            assert not re.search(r"\.(edu|ac)\b", host), (
                f"{name} names an academic host ({host}) — a refusal list must contain "
                "platforms we refuse to automate against, not institutions")


def test_the_allowlist_itself_contains_no_institution():
    """The guard's own escape hatch. Every entry must be infrastructure that does not narrow
    WHICH institutions can be discovered — adding a university here would defeat the test by
    permission rather than by oversight."""
    for host in ALLOWED_HOSTS:
        assert not re.search(r"\.(edu|ac)\b", host), host
        assert host.count(".") <= 3, host


def test_country_is_the_only_geography_the_engine_is_given():
    """ROR is queried BY COUNTRY, which is what makes "any country" true. A test that the
    query is built from the plan's country rather than from a curated set of institutions."""
    ror = (ENGINE / "discover" / "ror.py").read_text(encoding="utf-8")
    assert "country" in ror
    # no bare list of institution names to prefer
    assert not re.search(r'\[\s*"[A-Z][a-z]+ University"', ror)
