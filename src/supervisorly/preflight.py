"""Pre-run checks: fail loud on a missing contact email; warn (don't block) on sparse coverage.

Two independent concerns, kept separate on purpose:

* **Being a good API citizen (D-019/023, cost §2).** Reality check on the open services this tool
  uses: **ROR needs no key** (its REST API is open and unauthenticated), and **OpenAlex is free**
  and works without a key too. What OpenAlex *does* want is your **email** — the "polite pool"
  marker (``?mailto=you@example.com``) that earns faster, more reliable service; the same email
  identifies us in the HTTP ``User-Agent`` on every fetch. So the one thing a live scan genuinely
  requires is a **contact email**, and ``require_credentials`` **raises** without it rather than
  hammering public APIs anonymously at scale. An OpenAlex **premium** key is supported but optional.

* **Coverage (D-060).** Some countries/fields are thin in OpenAlex/ROR. That is not a failure; it
  is a fact to state honestly *up front*. ``coverage_preflight`` returns human-readable warnings
  and never raises — the run continues and the coverage is reported honestly.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

# The one required env var for a live scan: your contact email (OpenAlex polite pool + User-Agent).
CONTACT_EMAIL_ENV = "SUPERVISORLY_CONTACT_EMAIL"
# Optional: a paid OpenAlex premium key (higher limits / snapshot). Not required for a scan.
OPENALEX_KEY_ENV = "SUPERVISORLY_OPENALEX_KEY"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Below these, OpenAlex/ROR coverage is thin enough to warn about (order-of-magnitude cut).
SPARSE_WORKS = 500
SPARSE_INSTITUTIONS = 5


class MissingCredentials(RuntimeError):
    """A live scan was attempted without a usable contact email (D-019/023)."""


def require_credentials(env: Mapping[str, str]) -> None:
    """Raise ``MissingCredentials`` unless a valid contact email is set.

    ROR needs no key and OpenAlex is free, so the only hard requirement is identifying ourselves
    politely. ``env`` is passed in (usually ``os.environ``) so this is testable without touching
    the process environment.
    """
    email = (env.get(CONTACT_EMAIL_ENV) or "").strip()
    if not email:
        # The old message said WHAT to set and not HOW, which stranded a real first-time user
        # on Windows: `setx` reported SUCCESS and this error still fired, because setx writes
        # the stored environment for FUTURE shells and never touches the running one. Naming
        # that explicitly costs three lines and is the single most likely reason someone sees
        # this text at all. ASCII only — this goes to a console of unknown encoding.
        raise MissingCredentials(
            f"A live scan needs a contact email so we use the open APIs politely.\n"
            f"  - {CONTACT_EMAIL_ENV}: set this to YOUR email (any address you own). It joins the\n"
            f"    free OpenAlex 'polite pool' (https://openalex.org) and identifies us to servers.\n"
            f"\nSet it for THIS terminal:\n"
            f"  PowerShell   $env:{CONTACT_EMAIL_ENV} = \"you@example.com\"\n"
            f"  macOS/Linux  export {CONTACT_EMAIL_ENV}=\"you@example.com\"\n"
            f"\nAlready ran `setx`? That only applies to NEW terminals - it does not change the\n"
            f"one you are in. Either open a new terminal, or run the PowerShell line above.\n"
            f"\nOr pass it just for this run:  supervisorly scan --email you@example.com ...\n"
            f"\nNo keys are required: ROR's API is open (https://ror.org), and OpenAlex is free.\n"
            f"(Optional: {OPENALEX_KEY_ENV} for a paid OpenAlex premium key - higher limits.)\n"
            f"\nOr use `supervisorly scan --demo` for the offline synthetic demo (nothing needed)."
        )
    if not _EMAIL_RE.match(email):
        raise MissingCredentials(
            f"{CONTACT_EMAIL_ENV}={email!r} does not look like an email address. Set it to a real\n"
            f"address you own (used for the OpenAlex polite pool and our User-Agent)."
        )


def contact_email(env: Mapping[str, str]) -> str | None:
    """The configured contact email (for OpenAlex mailto + User-Agent), or None."""
    return (env.get(CONTACT_EMAIL_ENV) or "").strip() or None


def openalex_key(env: Mapping[str, str]) -> str | None:
    """The optional OpenAlex premium key, or None (the free tier needs no key)."""
    return (env.get(OPENALEX_KEY_ENV) or "").strip() or None


def coverage_preflight(stats: Mapping[str, object]) -> list[str]:
    """Return up-front coverage warnings (empty = looks well-covered). Never raises.

    ``stats`` is what a cheap preflight query returns, e.g.
    ``{"country": "XX", "openalex_works": 120, "ror_institutions": 2}``.
    """
    warnings: list[str] = []
    country = stats.get("country", "this country/field")
    works = int(stats.get("openalex_works", 0) or 0)
    insts = int(stats.get("ror_institutions", 0) or 0)
    # ASCII-only messages: the CLI prints these to the console, and the default Windows codec
    # (cp1252) must never crash on them (same convention as cli._write_result).
    if works < SPARSE_WORKS:
        warnings.append(
            f"OpenAlex coverage for {country} looks thin ({works} works < {SPARSE_WORKS}); "
            "results may be sparse - this is reported honestly, the run continues (D-060)."
        )
    if insts < SPARSE_INSTITUTIONS:
        warnings.append(
            f"ROR lists only {insts} institution(s) for {country} (< {SPARSE_INSTITUTIONS}); "
            "the directory ladder may find fewer targets - run continues."
        )
    return warnings
