"""Server-side page rendering — read a public page that only exists after JavaScript runs.

**Why.** A measured run found 52 of 52 deep-dived professors `blocked`, because OpenAlex
carries no homepage for them and the fallback — their ORCID profile — is a JavaScript
application: 65 KB of HTML whose entire visible text is CSS font declarations. The record is
real, public and robots-allowed; our reader simply could not execute the page. That is a
limitation of the fetcher, not a wall being respected (`BLOCKERS.md` B-003, D-073).

**This is not the human rung.** D-043/D-044 route *walled* sources — login, bot-wall — to the
student's own browser, and that is unchanged. This module renders pages we are already
allowed to read. The distinction is load-bearing, so it is enforced rather than documented:

- **robots.txt is checked before every navigation, and this class cannot be constructed
  without a checker.** When we drive the browser we ARE the robot; a headless Chromium that
  ignores robots is precisely the abuse the rule exists to prevent.
- **A non-2xx response is a refusal, not an obstacle.** ResearchGate answers 403 to machines;
  rendering it anyway would be defeating a bot-wall (D-039). Rendering is for pages that say
  yes and then need JavaScript, never for pages that say no.

**Why the text is extracted in-page.** ``extract/page_extract.js`` is evaluated inside the
document, and it mirrors ``normalize.main_text`` exactly — same skipped tags, same whitespace
collapsing. So a rendered snapshot is byte-compatible with a fetched one and the D-010 quote
gate runs unchanged. Re-implementing the extraction here in Python would create a second
definition of "the text of a page", and quotes verified against one would fail against the
other.

**Optional dependency.** Playwright is imported lazily and only inside the worker image. Any
absence — package missing, browser missing, launch failure — makes ``available()`` False and
every ``render()`` return None, so the CLI, the test suite and the offline demo need none of
it (D-011/D-063) and a scan never dies because a browser would not start (D-068 fail-closed).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from . import walls
from .robots import USER_AGENT

log = logging.getLogger(__name__)

#: Per-page budget. A professor page that needs longer than this is not worth stalling a scan
#: of two dozen others for; it stays an honest open gap.
DEFAULT_TIMEOUT_MS = 20_000
#: Give up on network idle after this and take what has rendered — many academic pages hold a
#: socket open forever (analytics, chat widgets) and would otherwise always hit the timeout.
SETTLE_MS = 1_500

_PAGE_EXTRACT_JS = Path(__file__).resolve().parent.parent / "extract" / "page_extract.js"


@dataclass(frozen=True)
class RenderedPage:
    final_url: str
    title: str | None
    text: str
    status: int


def _load_extractor_js() -> str:
    """The in-page extractor source, as a callable expression Playwright can evaluate."""
    return _PAGE_EXTRACT_JS.read_text(encoding="utf-8")


class ChromiumRenderer:
    """Renders public pages with headless Chromium, one browser reused across pages.

    ``robots_check(url) -> bool`` is REQUIRED and is called before every navigation. There is
    deliberately no default: a renderer that is robots-gated only when someone remembers to
    pass a checker is not robots-gated.
    """

    def __init__(self, robots_check, *, timeout_ms: int = DEFAULT_TIMEOUT_MS,
                 user_agent: str = USER_AGENT) -> None:
        if not callable(robots_check):
            raise ValueError("robots_check is required — a renderer that skips robots is a "
                             "crawler pretending to be a browser (D-005/D-039)")
        self._robots_check = robots_check
        self._timeout_ms = timeout_ms
        self._user_agent = user_agent
        self._pw = None
        self._browser = None
        self._js = None
        #: Latched after a failed launch. Without it, every page retries the launch: the
        #: second attempt calls ``sync_playwright().start()`` while the first context is still
        #: alive and fails with "Sync API inside the asyncio loop", which is a misleading
        #: message for "we already tried". One failure per run is a diagnosis; twenty-five is
        #: a slow scan that reports the wrong cause.
        self._unavailable = False
        self.rendered = 0
        self.refused_by_robots = 0
        self.refused_walled = 0
        self.failed = 0

    # ── lifecycle ────────────────────────────────────────────────────────────

    def available(self) -> bool:
        """True only if a browser actually launched. Never raises."""
        return self._ensure_browser() is not None

    def _ensure_browser(self):
        if self._browser is not None:
            return self._browser
        if self._unavailable:
            return None
        try:
            from playwright.sync_api import sync_playwright  # noqa: PLC0415 — optional dep
        except ImportError:
            log.info("playwright not installed — server-side rendering disabled")
            self._unavailable = True
            return None
        try:
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(
                args=["--no-sandbox", "--disable-dev-shm-usage"])
            self._js = _load_extractor_js()
        except Exception as exc:                      # noqa: BLE001 — fail-closed
            log.warning("chromium failed to launch (%s) — rendering disabled", exc)
            # Tear the half-started context down. Leaving `_pw` alive was a real bug: the next
            # call started a SECOND playwright and failed with "Sync API inside the asyncio
            # loop", reporting a threading problem when the truth was a missing browser binary.
            try:
                if self._pw is not None:
                    self._pw.stop()
            except Exception:                         # noqa: BLE001 — teardown must not raise
                pass
            self._pw = self._browser = None
            self._unavailable = True
            return None
        return self._browser

    def close(self) -> None:
        for obj, stop in ((self._browser, "close"), (self._pw, "stop")):
            try:
                if obj is not None:
                    getattr(obj, stop)()
            except Exception:                         # noqa: BLE001 — teardown must not raise
                pass
        self._browser = self._pw = None

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
        return False

    # ── the one operation ────────────────────────────────────────────────────

    def render(self, url: str) -> RenderedPage | None:
        """Render one page and return its extracted main text, or None.

        None covers every reason uniformly — robots said no, the browser is unavailable, the
        host answered non-2xx, navigation failed, the page yielded no text. The caller records
        an honest ``blocked`` either way, and no failure here can propagate into the scan.
        """
        if not url:
            return None
        if walls.is_walled(url):
            # Checked BEFORE anything else, because the status-code guard below cannot see
            # this class of wall at all: ResearchGate answers 403 to a plain client and 200
            # to Chromium (measured). A browser is not shown the wall, so refusing on the
            # response is refusing on evidence we will never receive. Refusal has to be a
            # property of the host, decided before the request (D-039/D-043/D-044).
            self.refused_walled += 1
            return None
        try:
            if not self._robots_check(url):
                self.refused_by_robots += 1
                return None
        except Exception:                             # noqa: BLE001 — unknown robots = no
            self.refused_by_robots += 1
            return None

        browser = self._ensure_browser()
        if browser is None:
            return None

        page = None
        try:
            page = browser.new_page(user_agent=self._user_agent)
            page.set_default_timeout(self._timeout_ms)
            resp = page.goto(url, wait_until="domcontentloaded", timeout=self._timeout_ms)
            status = resp.status if resp is not None else 0
            if not (200 <= status < 300):
                # A refusal, not an obstacle: 403/401 is a wall, and walls go to the human
                # rung untouched (D-039/D-043). Rendering past one is exactly what this
                # module must not do.
                self.failed += 1
                return None
            try:
                page.wait_for_load_state("networkidle", timeout=SETTLE_MS)
            except Exception:                         # noqa: BLE001 — see SETTLE_MS
                pass
            result = page.evaluate(self._js, {})
            text = (result or {}).get("text") or ""
            if not text.strip():
                self.failed += 1
                return None
            self.rendered += 1
            return RenderedPage(
                final_url=(result or {}).get("finalUrl") or page.url or url,
                title=(result or {}).get("title"),
                text=text,
                status=status,
            )
        except Exception as exc:                      # noqa: BLE001 — fail-closed
            log.info("render failed for %s: %s", url, exc)
            self.failed += 1
            return None
        finally:
            try:
                if page is not None:
                    page.close()
            except Exception:                         # noqa: BLE001
                pass
