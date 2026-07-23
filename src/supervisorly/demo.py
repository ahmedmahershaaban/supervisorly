"""Synthetic offline demo — the `--offline --demo` fixture (goal §4).

Everything here is invented: fake names, ``example`` domains, no real person. This is
the clean-room-safe demo data (D-035: no harvested corpus, no real people). It also
doubles as a genericity fixture — three directory shapes across three countries, plus a
non-English page and a robots-blocked one — to show the pipeline works generically and
stays honest where the deterministic English-first signal tier can't read a language.
"""

from __future__ import annotations

from .fetch.transport import CassetteTransport

# Three distinct directory shapes / countries — all synthetic.
_CA = ("<html><body><main><h1>Dr. Ada Placeholder</h1>"
       "<p>I am recruiting two PhD students to start in Fall 2027.</p>"
       "<p>Applications close on 1 December 2026.</p>"   # firm, published deadline
       "</main></body></html>")
_UK = ("<html><body><section class='profile'><h2>Prof. Ben Example</h2>"
       "<ul><li>Group news</li><li>We are seeking a postdoc in causal inference.</li>"
       "<li>Applications are usually due by 15 September 2026.</li>"  # projected → watch date
       "</ul></section></body></html>")
_AU = ("<html><body><div class='staff'><div class='bio'><strong>A/Prof. Cara Sample</strong>"
       "<div>My lab studies NLP; I am accepting a new PhD student for 2027.</div>"
       "</div></div></body></html>")
_DE = ("<html><body><main><h1>Prof. Dr. Dana Beispiel</h1>"
       "<p>Ich suche motivierte Doktorandinnen und Doktoranden.</p>"  # German — regex won't match
       "</main></body></html>")


def demo_fixture() -> tuple[CassetteTransport, list[dict], dict]:
    """Return (transport, targets, plan) for a fully offline synthetic demo scan."""
    tp = CassetteTransport()
    allow = "User-agent: *\nAllow: /\n"
    tp.record("https://ca-uni.example/robots.txt", 200, allow)
    tp.record("https://uk-uni.example/robots.txt", 200, allow)
    tp.record("https://au-uni.example/robots.txt", 200, allow)
    tp.record("https://de-uni.example/robots.txt", 200, allow)
    tp.record("https://priv-uni.example/robots.txt", 200, "User-agent: *\nDisallow: /people/\n")
    tp.record("https://ca-uni.example/people/ada", 200, _CA)
    tp.record("https://uk-uni.example/staff/ben", 200, _UK)
    tp.record("https://au-uni.example/people/cara", 200, _AU)
    tp.record("https://de-uni.example/team/dana", 200, _DE)

    targets = [
        {"id": "ada",  "name": "Dr. Ada Placeholder", "url": "https://ca-uni.example/people/ada"},
        {"id": "ben",  "name": "Prof. Ben Example",   "url": "https://uk-uni.example/staff/ben"},
        {"id": "cara", "name": "A/Prof. Cara Sample",  "url": "https://au-uni.example/people/cara"},
        {"id": "dana", "name": "Prof. Dr. Dana Beispiel", "url": "https://de-uni.example/team/dana"},
        {"id": "eve",  "name": "Prof. Eve Walled", "url": "https://priv-uni.example/people/eve"},
    ]
    plan = {"intent_kind": "pre_phd", "resolved_topic_ids": ["T_nlp", "T_causal"],
            "countries": ["demo"], "field": "AI"}
    return tp, targets, plan
