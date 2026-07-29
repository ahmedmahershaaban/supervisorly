"""Phase feature flags (plan FLAG) — shipping a half-finished phase safely.

Every gated phase lands behind a flag that is **off by default**, so the branch is always
deployable and a bad phase is one config change from gone.

**Why this exists at all.** The render rung shipped and did nothing for two deploys because a
separate change had quietly removed its input. Nothing was broken enough to fail, so nothing
said anything, and finding it took log archaeology. A flag alone would not have helped — an
*off* phase that says nothing is the same silence. So the two halves are inseparable: the flag
decides whether a phase runs, and the CC-1 ledger records that it did not. ``off_reason``
exists to make writing that row the path of least resistance.

**Server config only** (the D-068 rule). ``PHASES`` is read from the process environment and
from nowhere else. It is never a request parameter, never a field on the job document, never
part of the plan: a student's browser must not be able to turn on a phase that is off because
it is not ready. ``from_env`` is the only constructor production uses; the explicit
constructor exists for tests, which need to drive both states without mutating the
environment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

#: The environment variable, comma-separated: ``PHASES="p0,p1"``.
PHASES_ENV = "PHASES"

#: Every phase that is gated by a flag, in plan order. This is an **enum of phases**, not a
#: dictionary of search terms — D-038 forbids the latter and says nothing about the former.
#:
#: A phase belongs here once it has a call site that can be skipped. Listing a phase before
#: it is wired would let ``PHASES=p2`` report as accepted while changing nothing, which is
#: the failure mode this module was written to prevent.
OPTIONAL_PHASES: tuple[str, ...] = ("p0",)

#: Recognised but not yet wired. Naming them separately means ``PHASES=p1`` is answered with
#: "known, not built yet" rather than "unknown" — a real distinction for whoever is mid-plan.
PLANNED_PHASES: tuple[str, ...] = ("p1", "p2", "p4", "p5", "p6")


@dataclass(frozen=True)
class PhaseFlags:
    """Which gated phases may run. Immutable: read once, never re-read mid-run.

    A run that re-read the environment between phases could take two different code paths
    inside one scan and produce a result no single configuration explains.
    """

    enabled: frozenset[str]
    #: Names given in ``PHASES`` that match no phase at all. Kept rather than dropped — a
    #: typo'd flag silently doing nothing is how "I turned it on" and "it is on" diverge.
    unknown: tuple[str, ...] = ()
    #: Names that are recognised but not yet implemented (``PLANNED_PHASES``).
    not_yet_built: tuple[str, ...] = ()

    @classmethod
    def from_env(cls, environ=None) -> "PhaseFlags":
        """Parse ``PHASES`` from the process environment. Absent or empty → everything off.

        Off is the default on purpose: a deploy that forgets the variable ships the branch's
        existing behaviour, never a half-finished phase.
        """
        raw = (environ if environ is not None else os.environ).get(PHASES_ENV) or ""
        names = [n.strip().lower() for n in raw.split(",")]
        names = [n for n in names if n]
        known = set(OPTIONAL_PHASES)
        planned = set(PLANNED_PHASES)
        return cls(
            enabled=frozenset(n for n in names if n in known),
            unknown=tuple(dict.fromkeys(n for n in names if n not in known | planned)),
            not_yet_built=tuple(dict.fromkeys(n for n in names if n in planned)),
        )

    @classmethod
    def all_off(cls) -> "PhaseFlags":
        """Every gated phase off — the default, and what an unset ``PHASES`` produces."""
        return cls(enabled=frozenset())

    @classmethod
    def of(cls, *names: str) -> "PhaseFlags":
        """Turn on exactly ``names``. For tests and the CLI; production uses ``from_env``."""
        return cls(enabled=frozenset(n.strip().lower() for n in names if n.strip()))

    def is_on(self, phase: str) -> bool:
        return phase.strip().lower() in self.enabled

    def off(self) -> tuple[str, ...]:
        """The gated phases that will not run, in plan order."""
        return tuple(p for p in OPTIONAL_PHASES if p not in self.enabled)

    def off_reason(self, phase: str) -> str:
        """The ledger reason for a phase that a flag turned off.

        Names the variable, so the row answers "how do I turn it on?" and not merely "it did
        not run" — the difference between a ledger entry and a shrug.
        """
        return f"phase {phase} is off — set {PHASES_ENV}={phase} to enable it"

    def summary(self) -> str:
        """One ASCII line for the worker's start log (D-005: no personal data here, ever)."""
        on = ",".join(sorted(self.enabled)) or "none"
        parts = [f"on={on}", f"off={','.join(self.off()) or 'none'}"]
        if self.not_yet_built:
            parts.append(f"not-yet-built={','.join(self.not_yet_built)}")
        if self.unknown:
            parts.append(f"unknown={','.join(self.unknown)}")
        return " ".join(parts)
