"""Supervisorly — find a research supervisor in any country, with evidence.

A Claude-Code-first skill + agents + tools. This package is the deterministic
layer (D-009): it fetches, parses, caches, deduplicates, scores and exports, and
contains **no LLM calls**. The LLM judgement lives in the agents under
``.claude/agents/`` and is orchestrated by ``.claude/skills/supervisorly/SKILL.md``.

Design source of truth: ``docs/`` (DECISIONS.md is binding).
"""

# The product name lives in exactly one place so a rename is a one-line change
# (D-006, D-012).
PRODUCT_NAME = "Supervisorly"

__version__ = "0.1.0"
