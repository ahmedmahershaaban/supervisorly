# Contract — Phase-3 human-return Markdown grammar (D-051)

The format the student returns from **Claude for Chrome** when the tool asks them to read a
walled page (X, Scholar, a login-only directory). **One grammar, one implementation:**
`src/supervisorly/extract/md_grammar.py` is the single source of truth — the
`chrome-prompt-generator` embeds `emit()`'s output as the required shape, the `md-ingester` calls
`parse()`. They cannot drift.

## Shape

```
# Supervisorly — human retrieval
target: person=<id>  name=<display name>
retrieved_at: <ISO date>

## field: <field_name>
value: <the value>                 # omit when state is not 'value'
quote: <verbatim supporting text>  # kept exactly as written
source_url: <url>
observed_at: <ISO date>
confidence: quoted_official        # optional; one of the D-047 enum
note: <free text>                  # optional; typical with searched_absent
```

- Each `## field:` block becomes **one Claim**.
- A **value must cite a `source_url`** (D-010) — a value without one is rejected, not stored.
- To record an honest "we looked, found nothing," use `state: searched_absent` (with a `note`)
  instead of a value (D-046). Other states: `never_attempted`, `blocked`.
- Every entry is ingested as a normal Claim with `extractor = "human-assisted (Claude for
  Chrome)"` — human data is sourced and dated, **not privileged** (D-043).

## Guarantees (tested)

- **Lossless round-trip:** `parse(emit(doc)) == doc`.
- **Fails loud:** missing `target:`, a value without `source_url`, an invalid `confidence`, or an
  unknown key raises `MDParseError` — the ingester never guesses.

See `tests/test_md_grammar.py`.
