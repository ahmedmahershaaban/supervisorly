"""Social pacing — the anti-ban policy as deterministic code (D-065).

X/LinkedIn/Scholar are visited through the user's own logged-in session, per-target
and read-only, so no account is ever flagged. The rules here are enforced before every
browser page:

* jittered minimum intervals per host class (randomised per call, never a metronome),
* per-session page caps (never bulk),
* abort-on-challenge latch (captcha / soft-block / unexpected login redirect → the
  host is latched aborted and the field routes to the human rung; never retry harder),
* Scholar is minimal-use: the tightest interval and the smallest cap.

Non-social hosts are a no-op — the existing per-host rate limiter
(``fetch.ratelimit``) already covers them.

State is a small JSON file (per-host ``{count, last_fetch_epoch, aborted,
abort_reason}``). It holds session metadata only and is gitignored (D-005). A corrupt
state file fails CLOSED — when in doubt, don't touch the site.
"""

from __future__ import annotations

import json
import random
import time
from pathlib import Path

DEFAULT_STATE_PATH = "pacing_state.json"

# Policy table by host class. interval = (min, max) seconds; the wait target for each
# check is a fresh random point in that range. cap = pages per session.
POLICY = {
    "social": {
        "hosts": ("x.com", "twitter.com", "linkedin.com"),
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


def classify(host: str) -> str | None:
    """Host class by suffix match — subdomains included (mobile.twitter.com → social)."""
    h = (host or "").strip().lower()
    if not h:
        return None
    for cls, rule in POLICY.items():
        for suffix in rule["hosts"]:
            if suffix.endswith("."):
                if h.startswith(suffix) or h == suffix[:-1]:
                    return cls          # prefix-style entry (scholar.google.*)
            elif h == suffix or h.endswith("." + suffix):
                return cls
    return None


def _resolve(state_path: str | Path | None) -> Path:
    return Path(state_path) if state_path else Path(DEFAULT_STATE_PATH)


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
    if path.parent != Path("") and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def _entry(state: dict, host: str) -> dict:
    return state.setdefault("hosts", {}).setdefault(host, {
        "count": 0, "last_fetch_epoch": None, "aborted": False, "abort_reason": None,
    })


def check(
    host: str,
    *,
    now: float | None = None,
    state_path: str | Path | None = None,
    rng: random.Random | None = None,
) -> dict:
    """May the browser fetch one page from ``host`` right now?

    Returns ``{"allowed": bool, "wait_seconds": int, "reason": str}``. An ALLOWED
    check on a paced host records the fetch (count++, last_fetch). ``rng`` is the
    jitter source — injectable so tests get a deterministic interval.
    """
    host = (host or "").strip().lower()
    cls = classify(host)
    if cls is None:
        # no extra constraint beyond the per-host rate limiter — a clean no-op
        return {"allowed": True, "wait_seconds": 0, "reason": "ok"}

    path = _resolve(state_path)
    state = _load(path)
    if state is None:
        return {"allowed": False, "wait_seconds": 0,
                "reason": "state-corrupt (fail closed: fix or delete the state file)"}

    rule = POLICY[cls]
    entry = _entry(state, host)
    if entry["aborted"]:
        return {"allowed": False, "wait_seconds": 0,
                "reason": f"aborted: {entry['abort_reason']}"}
    if entry["count"] >= rule["cap"]:
        return {"allowed": False, "wait_seconds": 0,
                "reason": f"session-cap ({entry['count']}/{rule['cap']} pages this session)"}

    now = time.time() if now is None else now
    jitter = rng if rng is not None else random.SystemRandom()
    target = jitter.uniform(*rule["interval"])     # a fresh random point per call
    last = entry["last_fetch_epoch"]
    if last is not None:
        wait = int(round(target - (now - last)))
        if wait > 0:
            return {"allowed": False, "wait_seconds": wait, "reason": "min-interval"}

    entry["count"] += 1
    entry["last_fetch_epoch"] = now
    _save(path, state)
    return {"allowed": True, "wait_seconds": 0, "reason": "ok"}


def abort(host: str, reason: str, *, state_path: str | Path | None = None) -> dict:
    """Latch a host aborted (abort-on-challenge, D-065). Never retry harder — the
    field becomes ``blocked`` and routes to the human rung."""
    host = (host or "").strip().lower()
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
    state.get("hosts", {}).pop(host.strip().lower(), None)
    _save(path, state)
