"""Edge cases: login-walled directory → roster-enumeration on the human rung (D-052);
department page not found → distinct NOT_FOUND coverage (D-046/D-060). The tool never
defeats a wall — it routes it to the student's browser instead (D-039/044)."""

from supervisorly.discover import roster
from supervisorly.fetch.fetcher import FetchResult
from supervisorly.model import runs, units
from supervisorly.model.db import open_db

DIR_URL = "https://walled.example/people/"


def _blocked():   # robots Disallow → fetcher returns allowed=False, nothing fetched
    return FetchResult(url=DIR_URL, allowed=False, error="disallowed by robots.txt")


def _not_found():
    return FetchResult(url=DIR_URL, allowed=True, status=404, error="http 404")


def _open():
    return FetchResult(url=DIR_URL, allowed=True, status=200, snapshot_hash="deadbeef")


def test_detect_login_wall_is_conservative():
    assert roster.detect_login_wall("Please sign in to continue to the staff directory.")
    assert roster.detect_login_wall("You must be logged in to view this page.")
    # a normal roster page is NOT a wall
    assert not roster.detect_login_wall(
        "<ul><li>Prof A</li><li>Prof B</li></ul>"
    )


def test_noscript_enable_javascript_banner_beside_content_is_not_a_wall():
    # live audit-2: a content-rich page that merely ships a <noscript>Please enable JavaScript</noscript>
    # fallback (WordPress / embedded map / Disqus) is NOT a wall — its real signals must still be
    # extracted, never discarded as false "blocked" emptiness (D-022/037/046).
    page = ("<html><body>"
            "<noscript>Please enable JavaScript to use all features of this site.</noscript>"
            "<main><h1>Prof. Jane Doe</h1>"
            "<p>I am recruiting PhD students for 2027. Current members of my lab include Alice "
            "and Bob. Find me at https://twitter.com/janedoe for updates on our research.</p>"
            "</main></body></html>")
    assert roster.detect_login_wall(page) is False


def test_content_free_js_shell_is_still_a_wall():
    # a genuinely JS-only shell (server rendered no content) IS a wall — routed to the human rung.
    shell = ('<html><body><div id="root"></div>'
             "<noscript>Please enable JavaScript to run this app.</noscript></body></html>")
    assert roster.detect_login_wall(shell) is True


def test_visible_js_banner_that_matches_an_extractor_is_a_wall_not_a_fact():
    # live audit-3 finding 3: a JS banner whose text happens to contain "recruiting" must be a wall,
    # not extracted as a professor's recruiting claim (the banner is chrome, D-039/044/D-010).
    page = ("<html><body><p>Please enable JavaScript to view current lab openings and recruiting "
            "details.</p><div id=root></div></body></html>")
    assert roster.detect_login_wall(page) is True


def test_terse_real_page_with_cra_noscript_banner_is_not_a_wall():
    # live audit-3 finding 4: a terse but REAL page carrying the CRA noscript banner keeps its signal.
    page = ("<head><noscript>You need to enable JavaScript to run this app.</noscript></head>"
            "<body><div id='root'><p>Now hiring PhD students.</p></div></body>")
    assert roster.detect_login_wall(page) is False


def test_bot_challenge_interstitial_is_a_wall_regardless_of_length():
    # live audit-3 finding 5: a Cloudflare/JS bot-wall (chrome longer than any char floor) is a wall.
    cf = ("<html><body><div>Please enable JavaScript and cookies to continue. Checking if the site "
          "connection is secure. example.edu needs to review the security of your connection before "
          "proceeding. Ray ID: 7a1b. Performance and security by Cloudflare.</div></body></html>")
    assert roster.detect_login_wall(cf) is True
    assert roster.detect_login_wall(
        "<html><body><p>Checking your browser before accessing example.edu.</p></body></html>") is True


def test_recaptcha_bearing_faculty_page_is_not_a_wall():
    # live audit-4 finding 3 (HIGH): a real faculty page carrying a reCAPTCHA-protected contact form
    # (Google's mandated "protected by reCAPTCHA" notice, or the g-recaptcha/api.js markup) is OPEN,
    # not a wall — the bare `captcha` substring must not match inside reCAPTCHA (D-022/037/046).
    visible = ("<html><body><main><h1>Dr. Jane Doe</h1>"
               "<p>I am recruiting PhD students in quantum optics for Fall 2027. "
               "Applications close on 15 January 2027.</p>"
               "<p>Contact me using the form below. This site is protected by reCAPTCHA.</p>"
               "</main></body></html>")
    assert roster.detect_login_wall(visible) is False
    markup = ('<html><head><script src="https://www.google.com/recaptcha/api.js"></script></head>'
              '<body><main><div class="g-recaptcha"></div>'
              "<p>Now hiring PhD students in AI.</p></main></body></html>")
    assert roster.detect_login_wall(markup) is False
    # a genuine CAPTCHA CHALLENGE (not a mere embed) is still a wall
    assert roster.detect_login_wall(
        "<html><body><p>Please complete the captcha to continue.</p></body></html>") is True


def test_punctuation_free_directory_with_a_js_banner_is_not_a_wall():
    # live audit-4 finding 6 (MED): a card-grid People page with a visible JS notice but NO sentence
    # punctuation must keep its roster as residue — the banner strip must not greedily swallow all the
    # preceding real content and collapse it to a false LOGIN_WALL.
    page = ("<html><body><main>Faculty Directory Jane Smith Professor of Robotics recruiting PhD "
            "students John Doe Professor of AI Please enable JavaScript for the live search box"
            "</main></body></html>")
    assert roster.detect_login_wall(page) is False


def test_classify_directory_three_ways():
    assert roster.classify_directory(_blocked()) == roster.LOGIN_WALL
    assert roster.classify_directory(_not_found()) == roster.NOT_FOUND
    assert roster.classify_directory(_open(), "<ul><li>Prof A</li></ul>") == roster.OPEN
    # a 200 page that is really a login wall
    assert roster.classify_directory(
        _open(), "Sign in to view the staff list."
    ) == roster.LOGIN_WALL


def test_login_wall_routes_to_human_rung_and_scrapes_nothing():
    conn = open_db()
    run_id = runs.create_run(conn)
    out = roster.route_directory(conn, run_id, directory_url=DIR_URL, fetch_result=_blocked())

    assert out["decision"] == roster.LOGIN_WALL
    # the unit is honestly marked, not silently dropped
    assert units.get_unit(conn, out["unit_id"])["coverage_note"] == "LOGIN_WALL"
    # a roster_enumerate task waits on the human rung — nothing was scraped
    tasks = runs.tasks_for_run(conn, run_id)
    assert len(tasks) == 1
    t = tasks[0]
    assert t["stage"] == "roster_enumerate" and t["phase"] == "human"
    assert t["status"] == "awaiting_human"
    assert t["target_kind"] == "unit"
    # no person/deep-dive tasks were created behind the wall
    assert not any(x["target_kind"] == "person" for x in tasks)


def test_not_found_is_distinct_coverage_no_human_task():
    conn = open_db()
    run_id = runs.create_run(conn)
    out = roster.route_directory(conn, run_id, directory_url=DIR_URL, fetch_result=_not_found())

    assert out["decision"] == roster.NOT_FOUND
    assert units.get_unit(conn, out["unit_id"])["coverage_note"] == "NOT_FOUND"
    assert "task_id" not in out
    assert runs.tasks_for_run(conn, run_id) == []


def test_open_directory_proceeds_cleanly():
    conn = open_db()
    run_id = runs.create_run(conn)
    out = roster.route_directory(
        conn, run_id, directory_url=DIR_URL, fetch_result=_open(),
        html="<ul><li>Prof A</li><li>Prof B</li></ul>",
    )
    assert out["decision"] == roster.OPEN
    assert units.get_unit(conn, out["unit_id"])["coverage_note"] is None
    assert runs.tasks_for_run(conn, run_id) == []
