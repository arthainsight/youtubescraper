import threading

import pytest

from ytlinks import fetcher
from ytlinks.errors import FetchError, InvalidChannelUrl, classify_exception
from ytlinks.models import FetchOptions, VideoKind

from .fakes import factory, vid

URL = "https://www.youtube.com/@kanava"
ALL = (VideoKind.VIDEO, VideoKind.SHORT, VideoKind.LIVE)


def run(tabs, kinds=(VideoKind.VIDEO,), **kw):
    opts = kw.pop("options", FetchOptions(kinds=kinds))
    return fetcher.fetch_channel(URL, opts, ydl_factory=factory(tabs, kw.pop("detail", None)), **kw)


def test_basic_fetch_and_fields():
    r = run({"videos": [vid(1, upload_date="20240105"), vid(2)]})
    assert r.complete and r.channel_name == "Testikanava"
    assert [v.video_id for v in r.videos] == [f"{1:011d}", f"{2:011d}"]
    assert r.videos[0].upload_date == "2024-01-05" and r.videos[0].duration == 61
    assert r.videos[1].upload_date == "" and r.videos[0].channel == "Testikanava"


def test_dedupe_across_tabs_and_kind_of_first():
    r = run({"videos": [vid(1), vid(2)], "shorts": [vid(2), vid(3)], "streams": [vid(3), vid(4)]}, ALL)
    assert [v.video_id for v in r.videos] == [f"{i:011d}" for i in (1, 2, 3, 4)]
    assert r.videos[1].kind == VideoKind.VIDEO and r.videos[2].kind == VideoKind.SHORT


def test_skips_invalid_entries():
    r = run({"videos": [None, {"id": "UCxxxxxxxxxxxxxxxxxxxxxx", "title": "kanava"}, vid(1)]})
    assert len(r.videos) == 1


def test_missing_tab_is_note_not_warning():
    r = run({"videos": [vid(1)]}, (VideoKind.VIDEO, VideoKind.SHORT))
    assert r.complete and any("Short" in n for n in r.notes)


def test_partial_failure_is_reported_not_complete():
    boom = RuntimeError("HTTP Error 429: Too Many Requests")
    batches = []
    r = run({"videos": [vid(1), vid(2), boom]}, on_batch=batches.append)
    assert len(r.videos) == 2 and not r.complete
    assert "osittaiset" in r.warnings[0] and "rajoitti" in r.warnings[0]
    assert sum(len(b) for b in batches) == 2


def test_one_tab_fails_other_ok():
    r = run({"videos": [vid(1)], "shorts": RuntimeError("urlopen error timed out")},
            (VideoKind.VIDEO, VideoKind.SHORT))
    assert len(r.videos) == 1 and not r.complete and "Verkkovirhe" in r.warnings[0]


def test_total_failure_raises():
    with pytest.raises(FetchError) as ei:
        run({"videos": RuntimeError("<urlopen error [Errno -2] Name or service not known>")})
    assert ei.value.kind == "network"


def test_invalid_url_raises():
    with pytest.raises(InvalidChannelUrl):
        fetcher.fetch_channel("https://example.com", FetchOptions(), ydl_factory=factory({}))


def test_empty_channel_note():
    r = run({"videos": []})
    assert r.videos == [] and r.complete and any("ei löytynyt" in n for n in r.notes)


def test_batches_emitted_in_chunks():
    batches = []
    run({"videos": [vid(i) for i in range(1, 121)]}, on_batch=batches.append)
    assert [len(b) for b in batches] == [50, 50, 20]


def test_cancel_marks_partial():
    cancel = threading.Event()
    seen = []

    def on_batch(b):
        seen.extend(b)
        cancel.set()

    r = run({"videos": [vid(i) for i in range(1, 200)]}, on_batch=on_batch, cancel=cancel)
    assert r.cancelled and not r.complete and 0 < len(r.videos) < 199


def test_limit_marks_incomplete():
    seen_opts = []

    def fac(opts):
        seen_opts.append(opts)
        return factory({"videos": [vid(i) for i in range(1, 50)]})(opts)

    r = fetcher.fetch_channel(URL, FetchOptions(limit=3), ydl_factory=fac)
    assert len(r.videos) == 3 and not r.complete and seen_opts[0]["playlistend"] == 3


def test_ydl_options_no_download_and_flat():
    seen = []

    def fac(opts):
        seen.append(opts)
        return factory({"videos": [vid(1)]})(opts)

    fetcher.fetch_channel(URL, FetchOptions(), ydl_factory=fac)
    o = seen[0]
    assert o["skip_download"] is True and o["extract_flat"] == "in_playlist" and o["lazy_playlist"]


def test_exact_dates_fill_and_report_failures():
    detail = {f"{1:011d}": {"upload_date": "20231224", "title": "x"}}  # 2 puuttuu -> 429
    updates = []
    r = run({"videos": [vid(1), vid(2), vid(3, upload_date="20200101")]},
            options=FetchOptions(fetch_exact_dates=True), detail=detail, on_update=updates.extend)
    by_id = {v.video_id: v for v in r.videos}
    assert by_id[f"{1:011d}"].upload_date == "2023-12-24"
    assert by_id[f"{3:011d}"].upload_date == "2020-01-01"
    assert by_id[f"{2:011d}"].upload_date == ""
    assert len(updates) == 1 and not r.complete and "1/2" in r.warnings[-1]


@pytest.mark.parametrize("msg,kind", [
    ("ERROR: HTTP Error 429: Too Many Requests", "rate_limit"),
    ("Sign in to confirm you’re not a bot", "bot_check"),
    ("HTTP Error 404: Not Found", "not_found"),
    ("Unable to download API page: <urlopen error timed out>", "network"),
    ("jotain outoa", "unknown"),
])
def test_classify(msg, kind):
    e = classify_exception(RuntimeError(msg))
    assert e.kind == kind and e.user_message
