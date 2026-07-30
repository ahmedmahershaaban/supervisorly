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

from . import pool as pool_mod
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

#: The two commands that fix the two ways a browser can be missing. Kept together so a UI, the
#: CLI and an error message quote the same strings.
FIX_PACKAGE = 'pip install -e ".[browser]"'
FIX_BROWSER = "python -m playwright install chromium"

_STATUS_CACHE: dict | None = None


def browser_status(*, force: bool = False) -> dict:
    """Whether a Chromium is actually usable — ``{available, reason, fix, version}``.

    Distinct from :meth:`ChromiumRenderer.available`, which *launches* a browser and caches
    "no" for the life of the object. This answers the question a person asks before starting a
    scan, and it separates the two failures that look identical from the outside: the
    **package** is missing (``pip install``) or the **browser binary** is missing
    (``playwright install``). Getting those the wrong way round is a documented way to lose an
    afternoon — the first attempt at this ran `python -m playwright install chromium` against
    an interpreter with no playwright in it.

    Never raises, never launches a page. ``reason``/``fix`` are None when available.
    """
    global _STATUS_CACHE
    if _STATUS_CACHE is not None and not force:
        return dict(_STATUS_CACHE)
    status = _probe_browser()
    _STATUS_CACHE = status
    return dict(status)


def _probe_browser() -> dict:
    try:
        from playwright.sync_api import sync_playwright   # noqa: PLC0415 — optional dep
    except ImportError:
        return {"available": False, "version": None,
                "reason": "the playwright package is not installed in this environment",
                "fix": FIX_PACKAGE}
    try:
        # The package exposes no ``__version__``; the distribution metadata is where the
        # number actually lives, and a status line reading "playwright ?" is a status line
        # nobody trusts.
        from importlib.metadata import version as _dist_version   # noqa: PLC0415
        version = _dist_version("playwright")
    except Exception:                                     # pragma: no cover - defensive
        version = None
    try:
        with sync_playwright() as p:
            exe = p.chromium.executable_path
    except Exception as exc:
        # The driver itself would not start — a broken install, not a missing download.
        return {"available": False, "version": version,
                "reason": f"the playwright driver would not start ({type(exc).__name__})",
                "fix": FIX_PACKAGE}
    if not exe or not Path(exe).exists():
        return {"available": False, "version": version,
                "reason": "playwright is installed but the Chromium binary has not been "
                          "downloaded",
                "fix": FIX_BROWSER}
    if not _PAGE_EXTRACT_JS.is_file():
        # Reported separately and honestly: chromium is fine, our own asset is missing. The
        # combined message used to blame the browser for this and send readers to the wrong
        # component.
        return {"available": False, "version": version,
                "reason": f"the in-page extractor is missing from this install "
                          f"({_PAGE_EXTRACT_JS.name})",
                "fix": "reinstall the package: " + FIX_PACKAGE}
    return {"available": True, "version": version, "reason": None, "fix": None}


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
        # Loaded BEFORE the browser and reported separately. These were one try block, so a
        # missing page_extract.js in the installed wheel was logged as "chromium failed to
        # launch (No such file or directory: .../page_extract.js)" — a message that names the
        # real file while blaming the wrong component, and sends the reader to look at the
        # browser. Chromium was fine. An error line that misattributes costs more time than
        # no error line, because it is believed.
        try:
            self._js = _load_extractor_js()
        except OSError as exc:
            log.warning("page extractor missing (%s) — rendering disabled. It is package "
                        "data: check `extract/*.js` is in pyproject's package-data.", exc)
            self._unavailable = True
            return None
        try:
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(
                args=["--no-sandbox", "--disable-dev-shm-usage"])
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

    # ── the refusal gate, shared by the sync and async paths ─────────────────

    def _refusal(self, url: str) -> str | None:
        """Why this URL must not be rendered, or None if it may be. Bumps the counters.

        Extracted so the batch renderer below asks the SAME question rather than keeping its
        own opinion — the identical reasoning that made ``Fetcher.robots_allows`` public.
        Two robots gates on one host is two chances to disagree, and the permissive one wins.
        """
        if not url:
            return "no url"
        if walls.is_walled(url):
            # Checked BEFORE anything else, because the status-code guard cannot see this
            # class of wall at all: ResearchGate answers 403 to a plain client and 200 to
            # Chromium (measured). A browser is not shown the wall, so refusing on the
            # response is refusing on evidence we will never receive. Refusal has to be a
            # property of the host, decided before the request (D-039/D-043/D-044).
            self.refused_walled += 1
            return "walled host"
        try:
            if not self._robots_check(url):
                self.refused_by_robots += 1
                return "disallowed by robots.txt"
        except Exception:                             # noqa: BLE001 — unknown robots = no
            self.refused_by_robots += 1
            return "robots unavailable"
        return None

    # ── the one operation ────────────────────────────────────────────────────

    def render(self, url: str) -> RenderedPage | None:
        """Render one page and return its extracted main text, or None.

        None covers every reason uniformly — robots said no, the browser is unavailable, the
        host answered non-2xx, navigation failed, the page yielded no text. The caller records
        an honest ``blocked`` either way, and no failure here can propagate into the scan.
        """
        if self._refusal(url) is not None:
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


class BatchRenderer(ChromiumRenderer):
    """Render MANY urls: concurrent across hosts, strictly serial within each (CC-3.3/CC-3.4).

    **Async pages, not threads.** Playwright's sync API is bound to its creating thread, so
    wrapping ``ChromiumRenderer`` in a thread pool marshals every call back to one thread and
    buys contention instead of speed. This class therefore uses ``playwright.async_api`` and
    the asyncio ``HostPool``; the two APIs cannot share a browser, so a batch launches its own
    and closes it — which is why this is a separate entry point rather than a method that
    quietly changes what ``render()`` does.

    **It inherits the refusal gate rather than restating it.** Walls and robots are decided by
    ``ChromiumRenderer._refusal``, the same code the single-page path uses.

    Everything still fails closed: no Playwright, a browser that will not launch, a host that
    times out — each is ``None`` for that URL and never an exception for the batch.

    **Its production caller is the render-all deep dive.** This class spent a while as a
    tested primitive with nothing calling it, and the reason was sound: while Chromium was a
    fallback that fired on one page in twenty, a batch had nothing to be concurrent about.
    ``--render-all`` inverts that — every deep-dive target now wants a browser — so
    ``pipeline._prerender_batch`` renders them as one batch before the per-target loop, and
    ``_render_page`` consumes the result. P1's admissions crawl and P2's directory walk are
    still the other intended callers.
    """

    def __init__(self, robots_check, *, max_concurrent: int = pool_mod.DEFAULT_MAX_CONCURRENT,
                 **kw) -> None:
        super().__init__(robots_check, **kw)
        self.max_concurrent = max_concurrent

    async def render_many_async(self, urls) -> dict[str, RenderedPage | None]:
        """Render every URL, keyed by URL. Refused and failed pages map to ``None``."""
        urls = list(dict.fromkeys(u for u in urls if u))       # dedupe, order preserved
        out: dict[str, RenderedPage | None] = {u: None for u in urls}
        todo = [u for u in urls if self._refusal(u) is None]
        if not todo:
            return out
        try:
            from playwright.async_api import async_playwright  # noqa: PLC0415 — optional dep
        except ImportError:
            return out                                         # inert, exactly like render()

        if self._js is None:
            try:
                self._js = _load_extractor_js()
            except OSError as exc:
                # The page_extract.js packaging bug, caught loudly rather than as 40 blanks.
                log.warning("render batch disabled — extractor js unreadable: %s", exc)
                return out

        hp = pool_mod.HostPool(self.max_concurrent)
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(args=["--no-sandbox"])
                try:
                    async def one(url: str):
                        page = await browser.new_page(user_agent=self._user_agent)
                        try:
                            page.set_default_timeout(self._timeout_ms)
                            resp = await page.goto(url, wait_until="domcontentloaded",
                                                   timeout=self._timeout_ms)
                            status = resp.status if resp is not None else 0
                            if not (200 <= status < 300):
                                self.failed += 1
                                return None
                            try:
                                await page.wait_for_load_state("networkidle", timeout=SETTLE_MS)
                            except Exception:         # noqa: BLE001 — see SETTLE_MS
                                pass
                            result = await page.evaluate(self._js, {})
                            text = (result or {}).get("text") or ""
                            if not text.strip():
                                self.failed += 1
                                return None
                            self.rendered += 1
                            return RenderedPage(
                                final_url=(result or {}).get("finalUrl") or page.url or url,
                                title=(result or {}).get("title"), text=text, status=status)
                        finally:
                            # Released here, not at the end of the batch: a page held open per
                            # URL would make peak memory scale with the QUEUE rather than with
                            # the concurrency limit, which is the whole point of the cap.
                            try:
                                await page.close()
                            except Exception:         # noqa: BLE001
                                pass

                    for url, res in zip(todo, await hp.map(todo, one)):
                        if isinstance(res, BaseException):
                            log.info("render failed for %s: %s", url, res)
                            self.failed += 1
                            continue
                        out[url] = res
                finally:
                    await browser.close()
        except Exception as exc:                      # noqa: BLE001 — fail-closed, whole batch
            log.info("render batch unavailable: %s", exc)
        self.peak_per_host = hp.peak_per_host
        self.peak_in_flight = hp.peak_in_flight
        return out

    def render_many(self, urls) -> dict[str, RenderedPage | None]:
        """Synchronous entry point, for the synchronous pipeline above it."""
        return pool_mod.run_sync(self.render_many_async(urls))
