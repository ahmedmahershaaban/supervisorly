"""Pre-run checks: fail loud on missing credentials; warn (don't block) on sparse coverage.

Two independent concerns, kept separate on purpose:

* **Credentials (D-014/020, cost §2)** — a *live* scan needs a ROR client id and a free
  OpenAlex key. Running on the anonymous, throttled tiers silently is a defect: the run
  would be slow, rate-limited, and unreproducible. So ``require_credentials`` **raises**
  with the exact env-var names and how to get them. The offline ``--demo`` / cassette path
  never calls this — it needs no network and no keys (that is the whole point of the seam).

* **Coverage (D-060)** — some countries/fields are thin in OpenAlex/ROR. That is not a
  failure; it is a fact to state honestly *up front*. ``coverage_preflight`` returns
  human-readable **warnings** and never raises — the run continues and the coverage is
  reported honestly rather than silently looking empty.
"""

from __future__ import annotations

from collections.abc import Mapping

# Env vars a live scan requires (names are documented in the README).
ROR_CLIENT_ID_ENV = "SUPERVISORLY_ROR_CLIENT_ID"
OPENALEX_KEY_ENV = "SUPERVISORLY_OPENALEX_KEY"

_HOW_TO_GET = {
    ROR_CLIENT_ID_ENV: "register a client id at https://ror.readme.io/ (free)",
    OPENALEX_KEY_ENV: "get a free key / polite-pool email at https://openalex.org/ and "
                      "set it here",
}

# Below these, OpenAlex/ROR coverage is thin enough to warn about (order-of-magnitude cut).
SPARSE_WORKS = 500
SPARSE_INSTITUTIONS = 5


class MissingCredentials(RuntimeError):
    """A live scan was attempted without the required API credentials (D-014/020)."""


def require_credentials(env: Mapping[str, str]) -> None:
    """Raise ``MissingCredentials`` naming every missing var and how to get it.

    Fail loud, never run silently on the throttled anonymous tiers (D-020). ``env`` is
    passed in (usually ``os.environ``) so this is testable without touching the process
    environment.
    """
    missing = [name for name in (ROR_CLIENT_ID_ENV, OPENALEX_KEY_ENV)
               if not (env.get(name) or "").strip()]
    if missing:
        lines = [f"  - {name}: {_HOW_TO_GET[name]}" for name in missing]
        raise MissingCredentials(
            "Missing required credentials for a live scan:\n" + "\n".join(lines) +
            "\n\nSet them and re-run, or use `supervisorly scan --demo` for the offline "
            "synthetic demo (no credentials needed)."
        )


def coverage_preflight(stats: Mapping[str, object]) -> list[str]:
    """Return up-front coverage warnings (empty = looks well-covered). Never raises.

    ``stats`` is what a cheap preflight query returns, e.g.
    ``{"country": "XX", "openalex_works": 120, "ror_institutions": 2}``.
    """
    warnings: list[str] = []
    country = stats.get("country", "this country/field")
    works = int(stats.get("openalex_works", 0) or 0)
    insts = int(stats.get("ror_institutions", 0) or 0)
    if works < SPARSE_WORKS:
        warnings.append(
            f"OpenAlex coverage for {country} looks thin ({works} works < {SPARSE_WORKS}); "
            "results may be sparse — this is reported honestly, the run continues (D-060)."
        )
    if insts < SPARSE_INSTITUTIONS:
        warnings.append(
            f"ROR lists only {insts} institution(s) for {country} (< {SPARSE_INSTITUTIONS}); "
            "the directory ladder may find fewer targets — run continues."
        )
    return warnings
