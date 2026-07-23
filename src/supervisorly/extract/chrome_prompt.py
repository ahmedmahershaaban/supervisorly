"""chrome-prompt-generator — the emitting half of the human rung (D-043).

Given the exact gaps still open for a professor after the automated phases, generate a
ready-to-paste prompt the student runs in **Claude for Chrome** (their own logged-in
session reaches walled pages the tool cannot). The prompt embeds the required output
shape by calling ``md_grammar.emit`` on a worked example — the **same module** the
``md-ingester`` parses (D-051) — so the two sides can never drift.

Consolidated per professor (D-032): the student runs a few prompts, never one per field.
"""

from __future__ import annotations

from . import md_grammar as mg

_PREAMBLE = """\
You are helping gather PUBLIC information about one professor, from pages the automated
tool could not reach (e.g. X/Twitter, Google Scholar, a login-only page). Rules:
- Only public professional information. Cite a URL and a date for EVERYTHING.
- Quote verbatim — copy the exact sentence, do not paraphrase the evidence.
- If you look and find nothing for a field, say so with `state: searched_absent` — do
  NOT invent or infer. "Found nothing" is a valid, useful answer.
- Do not defeat any login you don't already have; only read what your own session shows.
"""


def generate_prompt(
    *,
    target_kind: str,
    target_ref: str,
    target_name: str | None,
    missing_fields: list[str],
    anchor_links: list[str],
) -> str:
    """Build the human-retrieval prompt for one professor's open gaps."""
    if not missing_fields:
        raise ValueError("generate_prompt called with no missing fields")

    lines = [_PREAMBLE, ""]
    who = f"{target_name} " if target_name else ""
    lines.append(f"## Target\n{who}({target_kind}={target_ref})")
    if anchor_links:
        lines.append("\n## Start here, then follow links outward")
        lines.extend(f"- {u}" for u in anchor_links)

    lines.append("\n## Find each of these fields")
    lines.extend(f"- {f}" for f in missing_fields)

    # Show the required output shape by emitting a worked example in the real grammar.
    example = mg.MDDocument(
        target_kind=target_kind,
        target_ref=target_ref,
        target_name=target_name,
        retrieved_at="<the date you looked>",
        entries=[
            mg.MDEntry(
                field=missing_fields[0],
                value="<the value, or omit this line and use a state below>",
                quote="<the exact sentence you read>",
                source_url="<the page URL>",
                observed_at="<the date on/near the statement, if any>",
            ),
            mg.MDEntry(
                field=(missing_fields[1] if len(missing_fields) > 1 else missing_fields[0]),
                state="searched_absent",
                note="<what you checked and why nothing was found>",
                source_url="<the page you checked>",
                observed_at="<the date you looked>",
            ),
        ],
    )
    lines.append("\n## Return EXACTLY this Markdown shape (one `## field:` block per field)\n")
    lines.append("```")
    lines.append(mg.emit(example).rstrip())
    lines.append("```")
    return "\n".join(lines) + "\n"
