"""Web-rajapinnan testit Flaskin test clientillä; haku korvataan valehaulla."""
import csv
import io
import time

import pytest

pytest.importorskip("flask")

from ytlinks import fetcher  # noqa: E402
from ytlinks.web.server import create_app  # noqa: E402

from .fakes import factory, vid  # noqa: E402

TABS = {"videos": [vid(1, title="Kissa äö"), vid(2, title="Koira"), vid(1, title="duplikaatti")],
        "shorts": [vid(3, title="Kissa short")]}


def fake_fetch(url, opts, **kw):
    return fetcher.fetch_channel(url, opts, ydl_factory=factory(TABS, kw.pop("detail", None)), **kw)


@pytest.fixture
def client():
    return create_app(fake_fetch).test_client()


def wait(client, job_id, after=0):
    for _ in range(100):
        d = client.get(f"/api/jobs/{job_id}?after={after}").get_json()
        if d["state"] != "running":
            return d
        time.sleep(0.02)
    raise AssertionError("haku ei valmistunut")


def start(client, **body):
    body.setdefault("url", "https://www.youtube.com/@kanava")
    body.setdefault("kinds", ["video", "short"])
    return client.post("/api/jobs", json=body)


def test_index_and_headers(client):
    r = client.get("/")
    assert r.status_code == 200 and "Kerää videot" in r.get_data(as_text=True)
    assert "script-src 'self'" in r.headers["Content-Security-Policy"]
    assert client.get("/static/app.js").status_code == 200


def test_job_flow_dedupes(client):
    r = start(client)
    assert r.status_code == 202
    d = wait(client, r.get_json()["id"])
    assert d["state"] == "done" and d["total"] == 3
    assert [v["id"] for v in d["videos"]] == [f"{i:011d}" for i in (1, 2, 3)]
    assert d["result"]["complete"] and d["result"]["channel"] == "Testikanava"
    assert d["videos"][2]["url"].endswith("/shorts/00000000003")
    # inkrementaalinen nouto
    assert client.get(f"/api/jobs/{d['id']}?after=2").get_json()["videos"][0]["id"] == f"{3:011d}"


@pytest.mark.parametrize("body,msg", [
    ({"url": "https://example.com/x"}, "YouTube-osoite"),
    ({"url": ""}, "Syötä"),
    ({"kinds": []}, "vähintään yksi"),
    ({"kinds": ["foo"]}, "vähintään yksi"),
])
def test_bad_requests(client, body, msg):
    r = start(client, **body)
    assert r.status_code == 400 and msg in r.get_json()["error"]["message"]


def test_failed_job_reports_error():
    def boom(url, opts, **kw):
        raise RuntimeError("HTTP Error 429: Too Many Requests")
    c = create_app(boom).test_client()
    d = wait(c, start(c).get_json()["id"])
    assert d["state"] == "failed" and "rajoitti" in d["error"]["message"]


def test_partial_result_has_warnings():
    tabs = {"videos": [vid(1), RuntimeError("urlopen error timed out")]}
    c = create_app(lambda u, o, **kw: fetcher.fetch_channel(u, o, ydl_factory=factory(tabs), **kw)).test_client()
    d = wait(c, start(c, kinds=["video"]).get_json()["id"])
    assert d["state"] == "done" and not d["result"]["complete"] and d["result"]["warnings"]


def test_cancel():
    import threading
    started = threading.Event()

    def slow(url, opts, cancel=None, **kw):
        started.set()
        cancel.wait(5)
        return fetcher.fetch_channel(url, opts, cancel=cancel, ydl_factory=factory({"videos": [vid(1)]}), **kw)
    c = create_app(slow).test_client()
    jid = start(c, kinds=["video"]).get_json()["id"]
    assert started.wait(2)
    assert c.post(f"/api/jobs/{jid}/cancel").status_code == 200
    d = wait(c, jid)
    assert d["state"] == "done" and d["result"]["cancelled"] and not d["result"]["complete"]


def test_unknown_job_404(client):
    assert client.get("/api/jobs/nope").status_code == 404
    assert client.post("/api/jobs/nope/cancel").status_code == 404


def test_too_many_jobs():
    import threading
    gate = threading.Event()
    c = create_app(lambda u, o, **kw: gate.wait(5)).test_client()
    codes = [start(c).status_code for _ in range(4)]
    gate.set()
    assert codes == [202, 202, 202, 429]


def _vids():
    return [{"id": f"{1:011d}", "title": "Äiti, \"lainaus\"", "date": "2024-01-02", "duration": 65,
             "channel": "Käpy", "kind": "video", "url": "https://evil.example/x"},
            {"id": "bad", "title": "ei"},  # virheellinen ID pudotetaan
            {"id": f"{2:011d}", "title": "=HYPERLINK(1)", "kind": "short"}]


def test_export_txt_ignores_client_url(client):
    r = client.post("/api/export/txt", json={"videos": _vids(), "links_only": True})
    assert r.status_code == 200 and "utf-8" in r.content_type
    assert r.get_data(as_text=True).splitlines() == [
        "https://www.youtube.com/watch?v=00000000001", "https://www.youtube.com/shorts/00000000002"]
    r = client.post("/api/export/txt", json={"videos": _vids(), "links_only": False, "name": "Käpy kanava"})
    assert r.get_data(as_text=True).splitlines()[0] == "Äiti, \"lainaus\"\thttps://www.youtube.com/watch?v=00000000001\t2024-01-02"
    assert "filename*=UTF-8''K%C3%A4py_kanava.txt" in r.headers["Content-Disposition"]


def test_export_csv_bom_umlauts_and_formula_guard(client):
    r = client.post("/api/export/csv", json={"videos": _vids()})
    raw = r.get_data()
    assert raw.startswith(b"\xef\xbb\xbf")
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline="")))
    assert rows[0]["title"] == "Äiti, \"lainaus\"" and rows[0]["channel"] == "Käpy"
    assert rows[1]["title"] == "'=HYPERLINK(1)"


def test_export_validation(client):
    assert client.post("/api/export/pdf", json={"videos": []}).status_code == 404
    assert client.post("/api/export/txt", json={"videos": "x"}).status_code == 400
