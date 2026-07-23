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
