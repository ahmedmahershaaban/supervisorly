"""Social pacing — the anti-ban policy as deterministic code (D-065).

X/LinkedIn/Scholar are visited through the user's own logged-in session, per-target
and read-only, so no account is ever flagged. The rules here are enforced before every
browser page:

* jittered minimum intervals per host class — the interval is drawn ONCE when a fetch
  is recorded and pinned as ``next_allowed_epoch``, so re-polling shows a monotonically
  decreasing wait and sleeping the printed wait guarantees an ALLOW (never a metronome),
* per-session page caps (never bulk),
* abort-on-challenge latch (captcha / soft-block / unexpected login redirect → the
  host is latched aborted and the field routes to the human rung; never retry harder),
* Scholar is minimal-use: the tightest interval and the smallest cap.

Non-social hosts are a no-op — the existing per-host rate limiter
(``fetch.ratelimit``) already covers them.

State is a small JSON file (per-host ``{count, last_fetch_epoch, next_allowed_epoch,
aborted, abort_reason}``), by default ``~/.supervisorly/pacing_state.json`` so caps and
latches don't evaporate with the working directory (``--state`` overrides; the in-repo
``pacing_state.json`` gitignore pattern covers that). It holds session metadata only
(D-005). Corruption fails CLOSED — an unreadable file, an invalid structure, or a
semantically broken per-host entry all deny with reason ``state-corrupt``; when in
doubt, don't touch the site.

Concurrency: this is a single-user CLI, so there is no locking. Saves are atomic
(temp file + os.replace), ``abort`` merges its two fields onto a fresh load, and
``check`` merges only its own host entry onto a fresh load at save time — a concurrent
abort latch or another host's check is never clobbered. Residual limitation: two
concurrent checks on the SAME host may merge to a single count increment (accepted;
politeness accounting, not a ledger).
"""

from __future__ import annotations

import json
import math
import os
import random
import time
from pathlib import Path


def _default_state_path() -> Path:
    """Resolved per call so tests (and embedders) can monkeypatch Path.home."""
    return Path.home() / ".supervisorly" / "pacing_state.json"


# Policy table by host class. interval = (min, max) seconds; the jittered interval is
# drawn once per recorded fetch and pinned as next_allowed_epoch. cap = pages/session.
# A host entry ending in "." is prefix-style: it matches itself plus country-TLD
# variants (scholar.google.co.uk, linkedin.com.cn) — the remainder after the prefix
# must be 1-2 short alphabetic labels, so hostile suffixes (….evil.com) never match.
POLICY = {
    "social": {
        "hosts": ("x.com", "twitter.com", "linkedin.com", "linkedin.com."),
        "interval": (45, 120),
        "cap": 15,
    },
    "scholar": {
        # scholar.google.com + every ccTLD (scholar.google.co.uk, …) — prefix match
        "hosts": ("scholar.google.",),
        "interval": (60, 180),
        "cap": 5,
    },
}


def _normalize_host(host: str) -> str:
    """Canonical host form: lowercase, scheme/userinfo/path stripped to the netloc,
    ``:port`` and trailing dot removed. Only framing syntax is stripped — mid-string
    content never is, so hostile lookalikes (x.com.evil.com) stay distinct."""
    h = (host or "").strip().lower()
    if "://" in h:
        h = h.split("://", 1)[1]
    h = h.split("/", 1)[0]            # netloc only (drop any path/query)
    h = h.rsplit("@", 1)[-1]          # drop any userinfo
    if ":" in h:
        h = h.split(":", 1)[0]        # drop :port
    return h.rstrip(".")              # trailing-dot FQDN form


def classify(host: str) -> str | None:
    """Host class by suffix match — subdomains included (mobile.twitter.com → social).
    The input is normalised first, so x.com:443 / x.com. / https://x.com/u all reach
    the same verdict as x.com."""
    h = _normalize_host(host)
    if not h:
        return None
    for cls, rule in POLICY.items():
        for suffix in rule["hosts"]:
            if suffix.endswith("."):
                # prefix-style entry (scholar.google.*, linkedin.com.*): the remainder
                # must look like a country TLD path (co.uk, cn, ca) — anything longer
                # (com.evil.com) is a hostile lookalike and classifies None
                if h == suffix[:-1]:
                    return cls
                if h.startswith(suffix):
                    rest = h[len(suffix):].split(".")
                    if len(rest) <= 2 and all(p.isalpha() and len(p) <= 3 for p in rest):
                        return cls
            elif h == suffix or h.endswith("." + suffix):
                return cls
    return None


def _resolve(state_path: str | Path | None) -> Path:
    return Path(state_path) if state_path else _default_state_path()


def _load(path: Path) -> dict | None:
    """State dict, ``{}`` when the file is absent (fresh start), or None when the
    file exists but is unreadable/invalid — corruption fails closed."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("hosts", {}), dict):
        return None
    return data


def _save(path: Path, state: dict) -> None:
    """Atomic save: temp file + os.replace, so a crash mid-write never leaves a
    half-written (and therefore fail-closed-corrupt) state file behind."""
    if path.parent != Path("") and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def _default_entry() -> dict:
    return {"count": 0, "last_fetch_epoch": None, "next_allowed_epoch": None,
            "aborted": False, "abort_reason": None}


def _entry_ok(entry: object) -> bool:
    """A semantically broken entry (wrong types, missing keys) fails CLOSED like a
    corrupt file does — never crash, never guess."""
    if not isinstance(entry, dict):
        return False

    def _num(v: object) -> bool:
        return v is None or (isinstance(v, (int, float)) and not isinstance(v, bool))

    return (
        isinstance(entry.get("count"), int)
        and not isinstance(entry["count"], bool)
        and "aborted" in entry and isinstance(entry["aborted"], bool)
        and (entry.get("abort_reason") is None or isinstance(entry["abort_reason"], str))
        and _num(entry.get("last_fetch_epoch"))
        and _num(entry.get("next_allowed_epoch"))
    )


def _entry(state: dict, host: str) -> dict:
    hosts = state.setdefault("hosts", {})
    entry = hosts.get(host)
    if not isinstance(entry, dict):
        entry = _default_entry()
        hosts[host] = entry
    return entry


def _corrupt() -> dict:
    return {"allowed": False, "wait_seconds": 0,
            "reason": "state-corrupt (fail closed: fix or delete the state file)"}


def _record_fetch(path: Path, host: str, now: float, next_allowed: float) -> bool:
    """Merge this host's fetch record onto a FRESH load and save (see module docstring
    for the concurrency contract). Returns False when the on-disk state is corrupt —
    fail closed rather than clobber it."""
    fresh = _load(path)
    if fresh is None:
        return False
    existing = fresh.get("hosts", {}).get(host)
    if existing is not None and not _entry_ok(existing):
        return False
    entry = _entry(fresh, host)
    # aborted/abort_reason are left untouched: a concurrent abort latch survives
    entry["count"] += 1
    entry["last_fetch_epoch"] = now
    entry["next_allowed_epoch"] = next_allowed
    _save(path, fresh)
    return True


def check(
    host: str,
    *,
    now: float | None = None,
    state_path: str | Path | None = None,
    rng: random.Random | None = None,
) -> dict:
    """May the browser fetch one page from ``host`` right now?

    Returns ``{"allowed": bool, "wait_seconds": int, "reason": str}``. An ALLOWED
    check on a paced host records the fetch (count++, last_fetch) and pins the next
    allowed instant (one jitter draw, stored) — re-polls see the same, decreasing
    wait. ``rng`` is the jitter source — injectable so tests get a deterministic
    interval.
    """
    host = _normalize_host(host)
    cls = classify(host)
    if cls is None:
        # no extra constraint beyond the per-host rate limiter — a clean no-op
        return {"allowed": True, "wait_seconds": 0, "reason": "ok"}

    path = _resolve(state_path)
    state = _load(path)
    if state is None:
        return _corrupt()

    rule = POLICY[cls]
    entry = state.get("hosts", {}).get(host)
    if entry is not None and not _entry_ok(entry):
        return _corrupt()
    if entry is None:
        entry = _default_entry()
    if entry["aborted"]:
        return {"allowed": False, "wait_seconds": 0,
                "reason": f"aborted: {entry['abort_reason']}"}
    if entry["count"] >= rule["cap"]:
        return {"allowed": False, "wait_seconds": 0,
                "reason": f"session-cap ({entry['count']}/{rule['cap']} pages this session)"}

    now = time.time() if now is None else now
    jitter = rng if rng is not None else random.SystemRandom()
    next_allowed = entry.get("next_allowed_epoch")
    if next_allowed is None and entry["last_fetch_epoch"] is not None:
        # legacy entry written before interval pinning — fall back to a fresh draw
        next_allowed = entry["last_fetch_epoch"] + jitter.uniform(*rule["interval"])
    if next_allowed is not None:
        wait = int(math.ceil(next_allowed - now))
        if wait > 0:
            return {"allowed": False, "wait_seconds": wait, "reason": "min-interval"}

    pinned = now + jitter.uniform(*rule["interval"])
    if not _record_fetch(path, host, now, pinned):
        return _corrupt()
    return {"allowed": True, "wait_seconds": 0, "reason": "ok"}


def abort(host: str, reason: str, *, state_path: str | Path | None = None) -> dict:
    """Latch a host aborted (abort-on-challenge, D-065). Never retry harder — the
    field becomes ``blocked`` and routes to the human rung. Only the aborted fields
    are merged onto a fresh load, so the latch never overwrites fetch history (and a
    stale check-save never overwrites the latch)."""
    host = _normalize_host(host)
    path = _resolve(state_path)
    state = _load(path) or {}
    entry = _entry(state, host)
    entry["aborted"] = True
    entry["abort_reason"] = reason or "challenge"
    _save(path, state)
    return {"host": host, "aborted": True, "abort_reason": entry["abort_reason"]}


def reset(host: str | None = None, *, state_path: str | Path | None = None) -> None:
    """Clear pacing state for one host, or every host when ``host`` is None."""
    path = _resolve(state_path)
    if host is None:
        if path.exists():
            path.unlink()
        return
    state = _load(path) or {}
    state.get("hosts", {}).pop(_normalize_host(host), None)
    _save(path, state)
