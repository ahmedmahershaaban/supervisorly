"""Supervisorly command line.

Every pipeline stage is independently runnable from here (architecture §7), so the
tool is debuggable and portable. Shipped commands: ``init-db``, ``version``,
``scan`` (demo + live, plan-driven and named-target inputs, D-066), ``map-field``
(the subject-map stage, D-066), ``studio`` (the Scan Studio plan wizard, D-067),
``ingest-page`` (the browser seam, D-064), ``reexport`` (dashboard rebuild from the
persisted store, D-029) and ``pace`` (the social pacing gate, D-065).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import PRODUCT_NAME, __version__
from .model.db import open_db


def cmd_version(_args: argparse.Namespace) -> int:
    print(f"{PRODUCT_NAME} {__version__}")
    return 0


def cmd_init_db(args: argparse.Namespace) -> int:
    path = Path(args.db)
    # sqlite3 can't create the parent directory itself — do it here so a path
    # like output/run.sqlite works on a first run.
    if path.parent != Path("") and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    open_db(path).close()
    print(f"initialised {path}")
    return 0


def cmd_ingest_page(args: argparse.Namespace) -> int:
    """Browser ingest seam (D-064): store agent-extracted page TEXT as a snapshot.

    The agent saves the in-page JS extractor's output to a staging file and calls
    this command; it handles only paths, byte counts, and the one-line result —
    raw HTML/DOM never enters the agent's context.

    Store-only by default; with ``--entity <kind:ref>`` + ``--run <run_id>`` it also runs
    the consumer half (``fetch.browser_fill``): the pipeline's own extractors fill the
    entity's signal fields from the snapshot, its awaiting_human gap tasks close, and the
    run status is recomputed (D-049)."""
    from urllib.parse import urlparse

    from .fetch.browser_rung import ingest_page

    url = (args.url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        print(f"invalid --url {args.url!r}: pass the FINAL http(s) page url.")
        return 2
    file = Path(args.file)
    if not file.is_file():
        print(f"staging file not found: {file}")
        return 2
    raw = file.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        # UTF-16 with BOM — the PowerShell 5.1 `>` / Out-File default on Windows
        text = raw.decode("utf-16")
    else:
        try:
            text = raw.decode("utf-8-sig")     # utf-8-sig also strips a leading BOM
        except UnicodeDecodeError:
            print(f"staging file {file} is not UTF-8 text - re-save it as UTF-8 "
                  f"(e.g. Out-File -Encoding utf8) and retry.")
            return 2
    text = text.lstrip("\ufeff")   # a leading BOM is not content
    if not text.strip():
        print(f"staging file {file} is empty - nothing to ingest.")
        return 2

    # ── optional fill mode: --entity <kind:ref> + --run <run_id>, always together ──
    entity_kind = entity_ref = None
    if (args.entity is None) != (args.run is None):
        print("--entity and --run must be given together (fill mode), or neither "
              "(store-only).")
        return 2
    if args.entity is not None:
        kind, sep, ref = args.entity.partition(":")
        kind = {"professor": "person"}.get(kind.strip(), kind.strip())
        ref = ref.strip()
        if not sep or not kind or not ref:
            print(f"invalid --entity {args.entity!r}: expected <kind>:<ref> "
                  f"(e.g. professor:a1234567890).")
            return 2
        if kind != "person":
            print(f"invalid --entity {args.entity!r}: kind must be 'professor' (or "
                  f"'person') - deep-dive targets are people.")
            return 2
        entity_kind, entity_ref = kind, ref

    db = Path(args.db)
    if db.parent != Path("") and not db.parent.exists():
        db.parent.mkdir(parents=True, exist_ok=True)   # same first-run rule as init-db
    snap_root = Path(args.snap_root) if args.snap_root else db.parent / ".cache" / "snaps"
    conn = open_db(db)
    try:
        if entity_kind is None:
            res = ingest_page(conn, snap_root, final_url=url, text=text)
            # ASCII-only console output (cp1252 consoles can't encode arrows - _write_result)
            print(f"ingested {res['bytes']} bytes -> snap {res['snapshot_hash'][:12]} "
                  f"source {res['source_id']}")
            return 0

        from . import pipeline
        from .fetch.browser_fill import fill_from_browser_page
        from .model import claims, runs

        if runs.get_run(conn, args.run) is None:
            print(f"unknown --run {args.run!r}: no such run in {db}.")
            return 2
        known = claims.claims_for(conn, entity_kind, entity_ref) or any(
            t["target_ref"] == entity_ref for t in runs.tasks_for_run(conn, args.run))
        if not known:
            print(f"unknown --entity {args.entity!r}: {entity_ref} has no claims and is "
                  f"not a target of run {args.run}.")
            return 2
        res = fill_from_browser_page(
            conn, snap_root, run_id=args.run, entity_kind=entity_kind,
            entity_id=entity_ref, final_url=url, text=text)
    finally:
        conn.close()
    filled = " ".join(f"{f}={res['fields'][f]}" for f in pipeline.BROWSER_FILL_FIELDS)
    line = (f"ingested {res['bytes']} bytes -> snap {res['snapshot_hash'][:12]} "
            f"source {res['source_id']}; filled {filled}; "
            f"{res['tasks_closed']} gap(s) closed; run {res['run_status']}")
    if res["rejected"]:
        why = "; ".join(f"{f}: {r}" for f, r in res["rejected"].items())
        line += f"; REJECTED {why} - gap left open"
    print(line)
    return 0


def cmd_reexport(args: argparse.Namespace) -> int:
    """Rebuild the dashboard from the persisted store — no fetching (D-029).

    This is the post-fill step of the browser recipe: after ``ingest-page --entity ...``
    closes a gap, regenerate the dashboard so it shows the filled values. Targets are
    reconstructed from the persisted claims (the store keeps ids, not display names, so a
    re-exported dashboard names professors by id — the full named view comes from a
    ``scan --resume`` re-export)."""
    from . import pipeline

    db = Path(args.db)
    if not db.is_file():
        print(f"database not found: {db} - run a scan first.")
        return 2
    conn = open_db(db)
    try:
        pids = [r["entity_id"] for r in conn.execute(
            "SELECT DISTINCT entity_id FROM claim WHERE entity_kind='person' "
            "ORDER BY entity_id")]
    finally:
        conn.close()
    if not pids:
        print(f"no professor claims in {db} - nothing to re-export.")
        return 2
    result = pipeline.reexport(db, [{"id": pid} for pid in pids],
                               optout_path=args.optout)
    return _write_result(result, Path(args.out), "reexport")


def cmd_pace(args: argparse.Namespace) -> int:
    """Social pacing gate (D-065): check/abort/reset before every browser page."""
    from .ethics import pacing

    if args.reset:
        pacing.reset(None if args.reset == "all" else args.reset, state_path=args.state)
        print(f"RESET host={args.reset}")
        return 0
    if not args.host:
        print("pace needs --host <host> (unless --reset is given).")
        return 2
    if args.abort is not None:
        pacing.abort(args.host, args.abort, state_path=args.state)
        print(f"ABORTED host={args.host} reason={args.abort or 'challenge'}")
        return 0
    res = pacing.check(args.host, state_path=args.state)
    verdict = "ALLOW" if res["allowed"] else "DENY"
    print(f"{verdict} host={args.host} wait={res['wait_seconds']}s reason={res['reason']}")
    return 0 if res["allowed"] else 3


def _warn_if_committable(out: Path) -> None:
    """D-005 guard: scan output holds personal data and must never be committed.

    When the resolved --out path sits inside a git work tree and neither it nor its
    sibling .json is covered by git-ignore rules, warn loudly BEFORE writing. Warn only —
    legitimate out-of-repo paths must keep working, and a missing git binary (or any git
    failure) is a clean no-op."""
    import subprocess

    target = out.resolve()
    cwd = target.parent
    while not cwd.is_dir() and cwd != cwd.parent:
        cwd = cwd.parent

    def _ignored(p: Path) -> bool | None:
        """True/False from git; None when git can't answer (absent, or not a work tree)."""
        try:
            r = subprocess.run(["git", "-C", str(cwd), "check-ignore", "-q", str(p)],
                               capture_output=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return None
        return {0: True, 1: False}.get(r.returncode)   # 128 = not a work tree → no opinion

    ignored = [_ignored(target), _ignored(target.with_suffix(".json"))]
    if not all(i is False for i in ignored):
        return   # ignored, or git/repo unavailable → silent
    # ASCII-only: the default Windows console codec (cp1252) can't encode an em-dash and
    # would crash the command before the files are written (see _write_result).
    print(f"WARNING (D-005): {target} is inside a git work tree and is NOT git-ignored. "
          "Scan output contains personal data and must never be committed. "
          "Write under an ignored directory (e.g. output/) or add the path to .gitignore.",
          file=sys.stderr)


def _write_result(result: dict, out: Path, label: str) -> int:
    """Write the dashboard + sibling JSON and print an ASCII-safe status line."""
    import json
    _warn_if_committable(out)
    if out.parent != Path("") and not out.parent.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result["html"], encoding="utf-8")
    out.with_suffix(".json").write_text(
        json.dumps(result["export"], ensure_ascii=False, indent=2), encoding="utf-8")
    n = len(result["export"]["professors"])
    # Surface the opt-out suppression count so a smaller professor list is never misread as
    # a coverage gap (D-023/D-046).
    opted = (result.get("stats") or {}).get("opted_out") or 0
    opt_note = f", {opted} opted out" if opted else ""
    # ASCII-only console output — the default Windows console codec (cp1252) can't encode a
    # Unicode arrow, which would crash the command after the files were already written.
    print(f"scanned {n} professors ({label}{opt_note}) -> {out} "
          f"(+ {out.with_suffix('.json').name})")
    return 0


def cmd_studio(args: argparse.Namespace) -> int:
    """Scan Studio (D-067): render a ``map-field`` subject map as the self-contained,
    offline plan wizard. Fails loud (exit 2) on a missing/invalid map file (D-002)."""
    import json

    from .export.studio import build_studio

    p = Path(args.map)
    if not p.is_file():
        print(f"subject map not found: {p} - run `supervisorly map-field` first.")
        return 2
    try:
        smap = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as exc:
        print(f"invalid subject-map JSON in {p}: {exc}")
        return 2
    if not isinstance(smap, dict) or not isinstance(smap.get("groups"), list):
        print(f"{p} is not a subject map (expected a JSON object with a 'groups' list) - "
              "produce one with `supervisorly map-field`.")
        return 2

    out = Path(args.out)
    _warn_if_committable(out)                       # D-005 guard, same as scan --out
    if out.parent != Path("") and not out.parent.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_studio(smap), encoding="utf-8")
    n_topics = sum(len(g.get("topics") or []) for g in smap["groups"] if isinstance(g, dict))
    # ASCII-only console output (cp1252 convention — see _write_result)
    print(f"studio wrote {n_topics} topics in {len(smap['groups'])} groups -> {out}")
    return 0


def cmd_map_field(args: argparse.Namespace) -> int:
    """Subject-map stage (D-066): field free text -> grouped OpenAlex topic map JSON.

    API-derived only (D-038); the user multi-selects from the written map and the selected
    topic IDs become a plan's ``resolved_topic_ids``. Requires a contact email (polite pool),
    exactly like a live scan."""
    import json
    import os

    from . import preflight

    email = args.email or os.environ.get(preflight.CONTACT_EMAIL_ENV)
    try:
        preflight.require_credentials({preflight.CONTACT_EMAIL_ENV: email or ""})
    except preflight.MissingCredentials as exc:
        print(str(exc))
        return 2

    from .discover.subjects import subject_map
    from .fetch.transport import httpx_transport

    transport = httpx_transport(user_agent=f"SupervisorlyBot/0.1 (mailto:{email})")
    smap = subject_map(args.field, transport, email=email,
                       key=(args.openalex_key or os.environ.get(preflight.OPENALEX_KEY_ENV)))
    out = Path(args.out)
    if out.parent != Path("") and not out.parent.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(smap, ensure_ascii=False, indent=2), encoding="utf-8")
    n_topics = sum(len(g["topics"]) for g in smap["groups"])
    # ASCII-only console output (cp1252 convention — see _write_result)
    suffix = " (PARTIAL)" if smap["truncated"] else ""
    print(f"mapped {n_topics} topics in {len(smap['groups'])} groups{suffix} -> {out}")
    if smap.get("relaxed_from"):
        print(f"note: no exact topics for '{smap['relaxed_from']}'; broadened to per-word "
              "search over the OpenAlex topic index")
    return 0


# Keys a Scan Studio / conversational plan JSON must carry (D-066). A plan missing any of
# these is rejected loudly with the full expected list, never silently defaulted (D-002).
PLAN_REQUIRED_KEYS = ("intent_kind", "country", "resolved_topic_ids", "field",
                      "university_mode", "universities")

# Valid enum values a plan may carry — mirrors the argparse choices of the overriding flags.
PLAN_UNIVERSITY_MODES = ("all", "prioritise", "only")
PLAN_INTENT_KINDS = ("training", "pre_master", "pre_phd", "mentor", "master", "phd",
                     "postdoc")


def _target_spec_errors(specs, key: str = "targets") -> list[str]:
    """Validation errors for a ``--targets`` / plan-carried targets list (D-002).

    Every entry must be an OpenAlex author URL string or a ``{"name": non-empty str,
    "affiliation": str?}`` object — a numeric name would be searched verbatim (confidently
    resolving whoever OpenAlex's top hit for "42" is), and a non-string affiliation crashes
    the author lookup with an AttributeError traceback instead of a clear message."""
    if not isinstance(specs, list):
        return [f"'{key}' must be a list, got {type(specs).__name__}"]
    errors: list[str] = []
    for i, e in enumerate(specs):
        if isinstance(e, str):
            continue
        if isinstance(e, dict):
            name = e.get("name")
            if not isinstance(name, str) or not name.strip():
                errors.append(f"{key}[{i}]: 'name' must be a non-empty string, got {name!r}")
            affiliation = e.get("affiliation")
            if affiliation is not None and not isinstance(affiliation, str):
                errors.append(f"{key}[{i}]: 'affiliation' must be a string, got "
                              f"{type(affiliation).__name__}")
            continue
        errors.append(f"{key}[{i}] must be an OpenAlex author URL string or a "
                      f'{{"name": ..., "affiliation": ...}} object, got {e!r}')
    return errors


def _plan_value_errors(data: dict) -> list[str]:
    """Type + enum checks on a plan's VALUES (key presence is checked separately, D-002).

    A mangled value must fail loud, never silently mangle: ``list("Uni")`` would otherwise
    become three one-letter "universities" (scanning nothing, misread as a coverage gap) and
    ``list("T10001")`` a list of characters. Enum typos are worse — a plan's
    ``university_mode: "onyl"`` would silently INVERT the asked-for scope ("only these" ->
    the whole country). Case is significant: ``"ONLY"`` is rejected, never quietly
    normalised — a scope decision is never silently rewritten."""
    errors: list[str] = []

    def check_str_list(key: str) -> None:
        v = data.get(key)
        if v is None:
            return
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            errors.append(f"'{key}' must be a list of strings, got "
                          f"{type(v).__name__}")

    check_str_list("resolved_topic_ids")
    check_str_list("universities")
    for key in ("country", "university_mode", "intent_kind", "field", "email"):
        v = data.get(key)
        if v is not None and not isinstance(v, str):
            errors.append(f"'{key}' must be a string, got {type(v).__name__}")
    mode = data.get("university_mode")
    if isinstance(mode, str) and mode not in PLAN_UNIVERSITY_MODES:
        errors.append(f"'university_mode' must be one of {', '.join(PLAN_UNIVERSITY_MODES)}, "
                      f"got {mode!r}")
    intent = data.get("intent_kind")
    if isinstance(intent, str) and intent not in PLAN_INTENT_KINDS:
        errors.append(f"'intent_kind' must be one of {', '.join(PLAN_INTENT_KINDS)}, "
                      f"got {intent!r}")
    if "targets" in data:
        target_errors = _target_spec_errors(data["targets"])
        if target_errors:
            errors.append("invalid 'targets': " + "; ".join(target_errors))
    return errors


def _load_plan(path: str) -> tuple[dict | None, str | None]:
    """Load + validate a ``--plan`` JSON file; returns ``(plan, None)`` or ``(None, error)``."""
    import json

    p = Path(path)
    if not p.is_file():
        return None, f"plan file not found: {p}"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as exc:
        return None, f"invalid plan JSON in {p}: {exc}"
    if not isinstance(data, dict):
        return None, (f"plan file {p} must hold a JSON object with keys: "
                      f"{', '.join(PLAN_REQUIRED_KEYS)}.")
    missing = [k for k in PLAN_REQUIRED_KEYS if k not in data]
    if missing:
        return None, (f"plan file {p} is missing required key(s): {', '.join(missing)}. "
                      f"Expected a Scan Studio plan with keys: {', '.join(PLAN_REQUIRED_KEYS)}.")
    errors = _plan_value_errors(data)
    if errors:
        return None, f"plan file {p}: " + "; ".join(errors)
    return data, None


def _load_target_specs(path: str) -> tuple[list | None, str | None]:
    """Load a ``--targets`` JSON file: ``[{name, affiliation?}, ...]`` or URL strings."""
    import json

    p = Path(path)
    if not p.is_file():
        return None, f"targets file not found: {p}"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as exc:
        return None, f"invalid targets JSON in {p}: {exc}"
    errors = _target_spec_errors(data)
    if errors:
        return None, (f"targets file {p}: " + "; ".join(errors) +
                      ". Expected a list of {\"name\": ..., \"affiliation\": ...} objects "
                      "or OpenAlex author URL strings.")
    return data, None


def _author_to_target(a: dict) -> dict:
    """An OpenAlex author dict -> a deep-dive target in the ladder's shape (nothing dropped)."""
    from .discover.ladder import _author_url
    url, url_kind = _author_url(a)          # homepage wins, else the ORCID profile (live fix)
    target = {
        "id": a.get("short_id") or (a.get("name") or "unknown").strip().casefold(),
        "name": a.get("name"),
        "url": url,
        "url_kind": url_kind,
        "openalex_id": a.get("openalex_id"),
        "orcid": a.get("orcid"),
        "ror_id": None,
        "institution_names": list(a.get("institution_names") or []),
        "topic_ids": list(a.get("topic_ids") or []),
        "works_count": int(a.get("works_count") or 0),
        "cited_by_count": int(a.get("cited_by_count") or 0),
    }
    if a.get("resolution"):
        target["resolution"] = a["resolution"]
    return target


def _resolve_named_targets(oa, specs: list) -> tuple[list[dict], list[str], list[str]]:
    """Resolve ``--targets`` specs via OpenAlex author search (D-066).

    Returns ``(targets, skipped, notes)``: every spec that resolves to nothing goes into
    ``skipped`` WITH its reason and is reported by the caller — nobody is silently dropped
    (D-022). ``notes`` carries non-fatal honesty lines (e.g. an affiliation that could not be
    confirmed -> ``resolution: unverified`` on the target)."""
    targets: list[dict] = []
    skipped: list[str] = []
    notes: list[str] = []
    for spec in specs:
        markers_before = len(oa.truncated_sources)
        if isinstance(spec, str):
            short_id = spec.rstrip("/").rsplit("/", 1)[-1]
            author = oa.author_by_id(short_id)
            label = spec
        else:
            author = oa.author_search(spec["name"], spec.get("affiliation"))
            label = spec["name"]
        if not author:
            # Distinguish a lookup FAILURE (a truncation-class event — the run is marked
            # PARTIAL, D-037) from a genuine absence (200, empty results — an honest skip).
            if len(oa.truncated_sources) > markers_before:
                skipped.append(f"{label}: OpenAlex lookup FAILED - the run is marked PARTIAL "
                               "in the coverage (likely transient; retry later)")
            else:
                skipped.append(f"{label}: no OpenAlex author match")
            continue
        target = _author_to_target(author)
        targets.append(target)
        if target.get("resolution") == "unverified":
            notes.append(f"{label}: resolved to {author.get('name')} "
                         f"({author.get('openalex_id')}) but the affiliation did not match any "
                         "last-known institution - target marked resolution=unverified.")
    return targets, skipped, notes


def cmd_scan(args: argparse.Namespace) -> int:
    out = Path(args.out)
    if out.parent != Path("") and not out.parent.exists():
        out.parent.mkdir(parents=True, exist_ok=True)   # for snapshots + the live DB
    snap_root = out.parent / ".cache" / "snaps"

    if args.demo:
        from .demo import demo_fixture
        from .pipeline import run_offline
        tp, targets, plan = demo_fixture()
        result = run_offline(plan, targets, tp, snap_root, optout_path=args.optout)
        return _write_result(result, out, "demo")

    # ── live scan ──
    import os

    from . import preflight
    # --plan: a Scan Studio / conversational plan JSON supplies the base scope; explicit
    # flags OVERRIDE the plan's values (D-066). Fail loud on a missing/invalid plan (D-002).
    # Loaded BEFORE the credentials check so a Studio plan's own "email" can satisfy it.
    plan_file: dict = {}
    if args.plan:
        plan_file, err = _load_plan(args.plan)
        if err:
            print(err)
            return 2

    email = (args.email or os.environ.get(preflight.CONTACT_EMAIL_ENV)
             or plan_file.get("email"))
    try:
        preflight.require_credentials({preflight.CONTACT_EMAIL_ENV: email or ""})
    except preflight.MissingCredentials as exc:
        print(str(exc))
        return 2

    # --targets: named professors to deep-dive directly (resolved below, after the transport).
    # A Studio plan may carry the same list under "targets" — the flag wins when both exist.
    target_specs: list | None = None
    if args.targets:
        target_specs, err = _load_target_specs(args.targets)
        if err:
            print(err)
            return 2
    elif plan_file.get("targets"):
        target_specs = plan_file["targets"]     # shape already validated by _load_plan

    country_in = args.country if args.country is not None else plan_file.get("country")
    field = args.field if args.field is not None else plan_file.get("field")
    topic_ids = list(plan_file.get("resolved_topic_ids") or [])
    if target_specs is None and not country_in:
        print("a live scan needs --country and --field (or a --plan file, or --targets; "
              "or use --demo for the offline demo). See --help.")
        return 2
    if country_in and not field and not topic_ids:
        print("a live scan needs --field (or a --plan with resolved_topic_ids). See --help.")
        return 2

    from .discover.countries import to_country_code
    # --country (or a plan's country) may be a NAME ("Canada") or alpha-2; ROR's filter needs
    # ISO alpha-2. Resolve here, where the plan is built, and fail loud on anything
    # unrecognized (D-002) — never silently query ROR with a filter that matches 0 institutions.
    country_code = None
    if country_in:
        country_code = to_country_code(country_in)
        if not country_code:
            print(f"unrecognized --country {country_in!r}: pass an ISO 3166-1 alpha-2 code "
                  "(e.g. CA) or an English country name (e.g. Canada).")
            return 2

    intent = args.intent or plan_file.get("intent_kind") or "pre_phd"
    university_mode = args.university_mode or plan_file.get("university_mode") or "all"
    if args.universities is not None:
        universities = [u.strip() for u in args.universities.split(",") if u.strip()]
    else:
        universities = list(plan_file.get("universities") or [])

    from .discover.openalex import OpenAlexClient
    from .fetch.transport import httpx_transport
    from .pipeline import run_live
    openalex_key = args.openalex_key or os.environ.get(preflight.OPENALEX_KEY_ENV)
    plan = {"intent_kind": intent, "country": country_code, "field": field,
            "university_mode": university_mode, "universities": universities,
            "resolved_topic_ids": topic_ids}
    transport = httpx_transport(user_agent=f"SupervisorlyBot/0.1 (mailto:{email})")

    targets_override = None
    targets_truncated: list[str] = []
    if target_specs is not None:
        oa = OpenAlexClient(transport, email=email, key=openalex_key)
        targets_override, skipped, notes = _resolve_named_targets(oa, target_specs)
        # The author lookups happened on THIS client, not run_live's own — hand its
        # truncation markers (author-search@/author@) to run_live so a lookup FAILURE
        # surfaces as PARTIAL coverage + persisted run counts, exactly like the ladder's
        # own markers (D-037), instead of reading as "none were dropped".
        targets_truncated = list(oa.truncated_sources)
        for line in notes:
            print(f"WARNING: {line}")
        for line in skipped:
            print(f"SKIPPED target {line}")          # reported, never silently dropped (D-022)
        if not targets_override and not country_code:
            print("no --targets entry resolved and no --country ladder was requested - "
                  "nothing to scan.")
            return 2

    if args.shortlist < 1:
        # fail loud (D-002): a 0/negative shortlist would silently deep-dive NOBODY while
        # the export still lists everyone as enumerated-but-unchecked.
        print(f"--shortlist must be a positive integer, got {args.shortlist}.")
        return 2

    result = run_live(
        plan, transport, snap_root, email=email,
        openalex_key=openalex_key,
        db_path=out.parent / "supervisorly.sqlite", optout_path=args.optout, resume=args.resume,
        targets_override=targets_override, targets_truncated=targets_truncated,
        shortlist_size=args.shortlist,
    )
    # sparse-coverage preflight + discovery warnings (D-060) — ASCII-safe by construction
    # (preflight/ladder messages are ASCII-only, like the rest of this console output).
    for w in result["stats"].get("warnings", []):
        print(f"WARNING: {w}")
    return _write_result(result, out, "live")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="supervisorly", description=__doc__)
    p.add_argument("--version", action="version", version=f"{PRODUCT_NAME} {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("version", help="print the version").set_defaults(func=cmd_version)

    pi = sub.add_parser("init-db", help="create/migrate a scan database")
    pi.add_argument("--db", default="supervisorly.sqlite", help="database path")
    pi.set_defaults(func=cmd_init_db)

    ps = sub.add_parser("scan", help="run a scan and write a dashboard")
    ps.add_argument("--demo", action="store_true", help="run the offline synthetic demo (no keys)")
    ps.add_argument("--out", default="output/dashboard.html", help="dashboard output path")
    ps.add_argument("--optout", default=None,
                    help="path to an optout.txt suppression list (D-023)")
    # live-scan flags
    ps.add_argument("--country", help="country to scan: ISO alpha-2 code or English name "
                                      "(e.g. CA or Canada) (a live scan)")
    ps.add_argument("--field", help="research field / subfield (a live scan)")
    ps.add_argument("--intent", default=None,
                    choices=["training", "pre_master", "pre_phd", "mentor", "master", "phd",
                             "postdoc"],
                    help="what you're looking for (default: pre_phd; overrides --plan)")
    ps.add_argument("--universities", default=None,
                    help="comma-separated universities to prioritise / restrict to")
    ps.add_argument("--university-mode", dest="university_mode", default=None,
                    choices=["all", "prioritise", "only"],
                    help="how to use --universities (default: all; overrides --plan)")
    ps.add_argument("--plan", default=None,
                    help="a Scan Studio plan JSON (D-066): supplies the scan scope; explicit "
                         "flags override its values")
    ps.add_argument("--targets", default=None,
                    help="a JSON file of named professors ([{name, affiliation?}] or OpenAlex "
                         "author URLs) to deep-dive directly (D-066)")
    ps.add_argument("--email", default=None,
                    help="contact email for the OpenAlex polite pool "
                         "(or set SUPERVISORLY_CONTACT_EMAIL)")
    ps.add_argument("--openalex-key", dest="openalex_key", default=None,
                    help="optional OpenAlex premium key (higher limits)")
    ps.add_argument("--resume", action="store_true",
                    help="reuse prior state; skip already-completed targets (cheap re-scan)")
    ps.add_argument("--shortlist", type=int, default=40, metavar="N",
                    help="deep-dive only the top N discovered professors by topic fit "
                         "(D-056; default 40). The rest stay listed, unchecked. Named "
                         "--targets always deep-dive.")
    ps.set_defaults(func=cmd_scan)

    pm = sub.add_parser("map-field", help="map a free-text field to a hierarchical OpenAlex "
                                          "subject map (D-066) for topic multi-select")
    pm.add_argument("--field", required=True, help="research field free text (e.g. 'causal ML')")
    pm.add_argument("--out", default="output/subject_map.json",
                    help="subject-map JSON output path (default: output/subject_map.json)")
    pm.add_argument("--email", default=None,
                    help="contact email for the OpenAlex polite pool "
                         "(or set SUPERVISORLY_CONTACT_EMAIL)")
    pm.add_argument("--openalex-key", dest="openalex_key", default=None,
                    help="optional OpenAlex premium key (higher limits)")
    pm.set_defaults(func=cmd_map_field)

    pt = sub.add_parser("studio", help="render a subject map as the self-contained Scan Studio "
                                       "plan wizard (D-067): intent, country, universities, "
                                       "topic multi-select, named professors -> plan JSON")
    pt.add_argument("--map", required=True, dest="map",
                    help="subject-map JSON from `map-field` (default output/subject_map.json)")
    pt.add_argument("--out", default="output/studio.html",
                    help="studio HTML output path (default: output/studio.html)")
    pt.set_defaults(func=cmd_studio)

    pb = sub.add_parser("ingest-page",
                        help="store browser-extracted page TEXT as a snapshot (D-064); "
                             "with --entity + --run it also fills that target's fields and "
                             "closes its awaiting_human gap tasks")
    pb.add_argument("--url", required=True, help="the FINAL page url (after redirects)")
    pb.add_argument("--file", required=True,
                    help="staging file holding the in-page extractor's text output")
    pb.add_argument("--db", default="output/supervisorly.sqlite",
                    help="database path (default: output/supervisorly.sqlite - the store a "
                         "default `scan --out output/...` writes; if your scan used a custom "
                         "--out, pass --db <out-dir>/supervisorly.sqlite)")
    pb.add_argument("--snap-root", dest="snap_root", default=None,
                    help="snapshot store root (default: <db-dir>/.cache/snaps)")
    pb.add_argument("--entity", default=None, metavar="KIND:REF",
                    help="fill this target from the page (e.g. professor:a1234567890); "
                         "requires --run")
    pb.add_argument("--run", dest="run", default=None, metavar="RUN_ID",
                    help="the run the entity belongs to; required with --entity")
    pb.set_defaults(func=cmd_ingest_page)

    pr = sub.add_parser("reexport", help="rebuild the dashboard from the persisted store "
                                         "(D-029) - e.g. after an ingest-page fill; "
                                         "no fetching")
    pr.add_argument("--db", default="output/supervisorly.sqlite",
                    help="database path (default: output/supervisorly.sqlite - the store a "
                         "default `scan --out output/...` writes)")
    pr.add_argument("--out", default="output/dashboard.html",
                    help="dashboard output path (default: output/dashboard.html)")
    pr.add_argument("--optout", default=None,
                    help="path to an optout.txt suppression list (D-023)")
    pr.set_defaults(func=cmd_reexport)

    pp = sub.add_parser("pace", help="social pacing gate — run before every browser page "
                                     "(D-065); exit 0 = ALLOW, 3 = DENY")
    pp.add_argument("--host", help="page host being considered (e.g. x.com)")
    pp.add_argument("--abort", nargs="?", const="", default=None, metavar="REASON",
                    help="latch the host aborted (captcha/soft-block/login redirect)")
    pp.add_argument("--reset", nargs="?", const="all", default=None, metavar="HOST",
                    help="clear pacing state for HOST, or all hosts when omitted")
    pp.add_argument("--state", default=None,
                    help="pacing state path (default: ~/.supervisorly/pacing_state.json)")
    pp.set_defaults(func=cmd_pace)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
