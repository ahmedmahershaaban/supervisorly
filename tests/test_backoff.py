"""Edge case: 429 / 5xx → exponential backoff with jitter, polite, never retries harder
(D-039). Delays grow, are capped, and the client gives up after a bounded number of tries
rather than escalating."""

from supervisorly.fetch.backoff import RetryPolicy
from supervisorly.fetch.fetcher import Fetcher
from supervisorly.fetch.snapshot import SnapshotStore
from supervisorly.fetch.transport import Response

ROBOTS = "User-agent: *\nAllow: /\n"
PAGE = "https://host.example/people/x"


class SeqTransport:
    """Serves robots.txt statically and the page from a scripted status sequence."""

    def __init__(self, sequence):
        self._seq = list(sequence)      # [(status, text), ...]
        self.calls = []

    def get(self, url):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            return Response(url, 200, ROBOTS)
        status, text = self._seq.pop(0)
        return Response(url, status, text)


def _fetcher(tmp_path, sequence, *, policy=None, jitter=0.0):
    slept: list[float] = []
    tp = SeqTransport(sequence)
    f = Fetcher(tp, SnapshotStore(tmp_path / "snaps"),
                retry=policy or RetryPolicy(max_retries=3, base=1.0, cap=30.0),
                sleep=slept.append, jitter=lambda: jitter)
    return f, tp, slept


def test_retries_then_succeeds(tmp_path):
    f, tp, slept = _fetcher(tmp_path, [(429, ""), (429, ""), (200, "<html>ok</html>")])
    res = f.fetch(PAGE)
    assert res.ok and res.status == 200
    assert res.attempts == 3                      # two retries then success
    assert slept == [1.0, 2.0]                    # exponential, deterministic with jitter=0


def test_gives_up_after_max_retries_without_escalating(tmp_path):
    f, tp, slept = _fetcher(tmp_path, [(503, "")] * 4)
    res = f.fetch(PAGE)
    assert not res.ok and res.status == 503 and "503" in res.error
    assert res.attempts == 4                       # 1 initial + 3 retries, then stop
    assert len(slept) == 3                         # exactly max_retries — never more
    assert slept == sorted(slept)                  # non-decreasing: never retries "harder"
    assert all(d <= 30.0 for d in slept)           # every wait within the cap


def test_delays_are_capped(tmp_path):
    f, tp, slept = _fetcher(
        tmp_path, [(503, "")] * 4, policy=RetryPolicy(max_retries=3, base=10.0, cap=15.0)
    )
    f.fetch(PAGE)
    assert slept == [10.0, 15.0, 15.0]             # 10, min(15,20), min(15,40)


def test_jitter_spreads_but_stays_bounded(tmp_path):
    # jitter=0.5 lengthens each wait but keeps it a bounded multiple, never unbounded
    f, tp, slept = _fetcher(tmp_path, [(429, ""), (200, "<html>ok</html>")], jitter=0.5)
    f.fetch(PAGE)
    assert slept == [1.5]                           # base(1) * (1 + 0.5)


def test_404_is_not_retried(tmp_path):
    f, tp, slept = _fetcher(tmp_path, [(404, "nope")])
    res = f.fetch(PAGE)
    assert res.status == 404 and res.attempts == 1
    assert slept == []                              # a 404 is final, not transient
