# Contract — the JSON export (D-046)

The scan's real deliverable. The dashboard is a *view* over this JSON, and the student's Claude
session reads it to answer questions and edit the UI (D-041). Implemented in
`src/supervisorly/export/json_export.py` (`build_export`, `validate_export`).

## Shape

```jsonc
{
  "schema_version": "1",
  "generated_at": "<ISO>",
  "run": { "run_id": "...", "status": "...", "counts": { ... } },
  "fields": [                       // descriptor: the generic dashboard's columns (D-038)
    { "id": "recruiting_status", "label": "Recruiting", "kind": "filter", "datatype": "string" }
  ],
  "professors": [
    { "id": "p1", "name": "…",
      "fields": {
        "recruiting_status": {      // the four-state value envelope
          "state": "value",         // value | searched_absent | never_attempted | blocked
          "value": "recruiting Fall 2027",
          "quote": "…", "source_url": "https://…", "snapshot_hash": "…",
          "observed_at": "…", "confidence": "quoted_official", "extractor": "recruiting-analyst"
        }
      }
    }
  ]
}
```

## Rules (enforced by `validate_export`, tested)

- **Four states, always distinct.** A blank field is `never_attempted`; "we looked, found
  nothing" is `searched_absent`; a failed/awaiting source is `blocked`; only `value` carries a
  value. A professor with no claims is still exported (never dropped, D-037) — every field
  `never_attempted`.
- **Every `value` cites a `source_url`** (D-010).
- **Judgements and bare-email lists never serialise.** A descriptor with `exportable: false`
  (LLM judgements about a person, D-024) is dropped from `fields` *and* from every professor —
  even when a local claim exists. The validator fails if such a field leaks in.
- **`kind`** ∈ filter | sort | facet | score-input | search | display — this is what makes the
  dashboard generic.

See `tests/test_json_export.py`.
