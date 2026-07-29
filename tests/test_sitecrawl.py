"""The bounded lab crawl: every bound is a hard stop, and the caps announce themselves.

The failure mode this guards against is not "we missed a page" — it is "we mirrored a
university". Depth 10 from a homepage reaches ~200,000 pages, which at a polite request per
second is ~55 hours for one institution. So each bound is asserted independently, and a cap
that bites must be *reported*, because a silent truncation reads as "we looked everywhere".
"""
from supervisorly.discover import sitecrawl as S

ENTRY = "https://cs.uni.edu/people/ada"

PAGE = """<html><body>
  <a href="/group/join">Join the group</a>
  <a href="/group/vacancies">Current vacancies</a>
  <a href="/publications">Publications</a>
  <a href="/news/2019/coffee">Department coffee morning</a>
  <a href="https://twitter.com/ada">Twitter</a>
  <a href="https://other.edu/people">Collaborator at another university</a>
  <a href="/cv.pdf">CV (PDF)</a>
  <a href="mailto:ada@uni.edu">Email me</a>
</body></html>"""


def _fetcher(pages):
    seen = []

    def fetch(url):
        seen.append(url)
        return (True, pages[url]) if url in pages else (False, "")
    return fetch, seen


# ── which links are worth a request ──────────────────────────────────────────
def test_only_links_that_could_carry_a_recruiting_sentence_are_followed():
    got = S.links_worth_following(PAGE, ENTRY)
    assert "https://cs.uni.edu/group/join" in got
    assert "https://cs.uni.edu/group/vacancies" in got
    assert "https://cs.uni.edu/news/2019/coffee" not in got


def test_an_offsite_link_is_someone_elses_server_and_robots():
    assert "https://other.edu/people" not in S.links_worth_following(PAGE, ENTRY)


def test_binaries_mailto_and_social_are_never_queued():
    got = S.links_worth_following(PAGE, ENTRY)
    assert not [u for u in got if u.endswith(".pdf")]
    assert not [u for u in got if "mailto" in u or "twitter" in u]


def test_www_and_bare_host_are_the_same_site():
    html = '<a href="https://www.cs.uni.edu/group/join">Join</a>'
    assert S.links_worth_following(html, ENTRY) == ["https://www.cs.uni.edu/group/join"]


def test_fragments_collapse_so_one_page_is_not_fetched_five_times():
    html = ('<a href="/group/join#a">Join</a><a href="/group/join#b">Join us</a>'
            '<a href="/group/join">Join the group</a>')
    assert S.links_worth_following(html, ENTRY) == ["https://cs.uni.edu/group/join"]


def test_malformed_markup_yields_no_links_rather_than_an_exception():
    assert S.links_worth_following("<a href=", ENTRY) == []
    assert S.links_worth_following("", ENTRY) == []
    assert S.links_worth_following(None, ENTRY) == []


def test_the_vocabulary_describes_page_roles_not_research_fields():
    """D-038: 'join the lab' is a page role; 'deep learning' would be a field term list."""
    src = (S.__file__).replace("\\", "/")
    text = open(src, encoding="utf-8").read()
    pattern = text.split("_WORTH_FOLLOWING = re.compile(")[1].split(")")[0]
    for term in ("machine learning", "chemistry", "physics", "biology", "nlp"):
        assert term not in pattern.lower()


# ── the bounds ───────────────────────────────────────────────────────────────
def test_depth_is_capped_at_two_hops_from_the_entry_page():
    pages = {
        ENTRY: '<a href="/l1">group members</a>',
        "https://cs.uni.edu/l1": '<a href="/l2">join us</a>',
        "https://cs.uni.edu/l2": '<a href="/l3">vacancies</a>',
        "https://cs.uni.edu/l3": "<p>too deep</p>",
    }
    fetch, seen = _fetcher(pages)
    got, truncated = S.crawl(ENTRY, fetch)
    assert [u for u, _ in got] == [ENTRY, "https://cs.uni.edu/l1", "https://cs.uni.edu/l2"]
    assert "https://cs.uni.edu/l3" not in seen        # never even requested
    assert truncated is False


def test_the_page_cap_is_hard_and_says_so():
    """20 pages, and the caller learns the walk was cut — never a silent 'we saw it all'."""
    fanout = "".join(f'<a href="/p{i}">join {i}</a>' for i in range(50))
    pages = {ENTRY: fanout}
    pages.update({f"https://cs.uni.edu/p{i}": "<p>x</p>" for i in range(50)})
    fetch, _ = _fetcher(pages)
    got, truncated = S.crawl(ENTRY, fetch)
    assert len(got) == S.MAX_PAGES
    assert truncated is True


def test_a_walk_that_finishes_early_is_not_reported_as_truncated():
    fetch, _ = _fetcher({ENTRY: "<p>a staff card with no links</p>"})
    got, truncated = S.crawl(ENTRY, fetch)
    assert len(got) == 1 and truncated is False


def test_a_cycle_cannot_loop_forever():
    pages = {ENTRY: '<a href="/a">join</a>',
             "https://cs.uni.edu/a": f'<a href="{ENTRY}">people</a><a href="/a">join</a>'}
    fetch, seen = _fetcher(pages)
    got, _ = S.crawl(ENTRY, fetch)
    assert len(seen) == 2 and len(got) == 2


def test_a_dead_page_ends_its_branch_and_not_the_crawl():
    pages = {ENTRY: '<a href="/dead">join</a><a href="/live">vacancies</a>',
             "https://cs.uni.edu/live": "<p>we are recruiting</p>"}
    fetch, _ = _fetcher(pages)                       # /dead is absent -> (False, "")
    got, _ = S.crawl(ENTRY, fetch)
    assert [u for u, _ in got] == [ENTRY, "https://cs.uni.edu/live"]


def test_a_fetcher_that_raises_does_not_kill_the_walk():
    def fetch(url):
        if url.endswith("/boom"):
            raise RuntimeError("connection reset")
        return True, ('<a href="/boom">join</a><a href="/ok">vacancies</a>'
                      if url == ENTRY else "<p>x</p>")
    got, _ = S.crawl(ENTRY, fetch)
    assert "https://cs.uni.edu/ok" in [u for u, _ in got]


def test_this_module_never_fetches_anything_itself():
    """Robots, rate limiting and snapshots stay in the one place that defines them."""
    text = open(S.__file__, encoding="utf-8").read()
    for forbidden in ("httpx", "requests", "urlopen", "urllib.request"):
        assert forbidden not in text


def test_an_empty_entry_is_a_no_op():
    assert S.crawl("", lambda u: (True, "x")) == ([], False)
