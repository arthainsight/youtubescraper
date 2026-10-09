import csv

from ytlinks.exporters import export_csv, export_txt, render_txt
from ytlinks.models import Video, VideoKind
from ytlinks.results import (ResultSet, filter_videos, format_date, format_duration,
                             is_valid_video_id)


def v(i, title="x", kind=VideoKind.VIDEO, **kw):
    return Video(video_id=f"{i:011d}", title=title, kind=kind, **kw)


def test_dedupe_by_id_keeps_first():
    rs = ResultSet()
    added = rs.add_many([v(1, "a"), v(2, "b"), v(1, "toinen")])
    assert [x.title for x in added] == ["a", "b"]
    assert len(rs) == 2 and rs.duplicates_skipped == 1
    assert rs.add_many([v(2), v(3)]) == [v(3)]
    assert [x.video_id for x in rs] == [f"{i:011d}" for i in (1, 2, 3)]


def test_update_and_missing():
    rs = ResultSet()
    rs.add_many([v(1)])
    assert rs.update(v(1, upload_date="2024-01-02"))
    assert rs.get(f"{1:011d}").upload_date == "2024-01-02"
    assert not rs.update(v(9))


def test_urls_by_kind():
    assert v(1).url.endswith("watch?v=00000000001")
    assert v(1, kind=VideoKind.SHORT).url.endswith("/shorts/00000000001")


def test_filter_case_accent_and_terms():
    vs = [v(1, "Äidin KEITTIÖ"), v(2, "Auto korjaus"), v(3, "Short", VideoKind.SHORT)]
    assert [x.video_id for x in filter_videos(vs, "äidin keittiö")] == [vs[0].video_id]
    assert [x.video_id for x in filter_videos(vs, "korjaus auto")] == [vs[1].video_id]
    assert len(filter_videos(vs, "")) == 3
    assert filter_videos(vs, "", [VideoKind.SHORT]) == [vs[2]]
    assert filter_videos(vs, "ei löydy") == []


def test_formatters():
    assert format_date("20240131") == "2024-01-31"
    assert format_date(None, 1704067200) == "2024-01-01"
    assert format_date("abc") == "" and format_date() == ""
    assert format_duration(65) == "1:05" and format_duration(3725) == "1:02:05"
    assert format_duration(None) == ""
    assert is_valid_video_id("dQw4w9WgXcQ") and not is_valid_video_id("UCxyz") and not is_valid_video_id(None)


def test_txt_links_and_details(tmp_path):
    vs = [v(1, "Ääkköset: ööö\nrivi", upload_date="2024-01-01"), v(2, "b")]
    assert render_txt(vs).splitlines() == [vs[0].url, vs[1].url]
    p = tmp_path / "a.txt"
    assert export_txt(p, vs, links_only=False) == 2
    lines = p.read_text(encoding="utf-8").splitlines()
    assert lines[0] == f"Ääkköset: ööö rivi\t{vs[0].url}\t2024-01-01"
    assert render_txt([]) == ""


def test_csv_utf8_roundtrip_and_bom(tmp_path):
    vs = [v(1, 'Pää, "lainaus" ääkköset åäö', upload_date="2024-01-01", duration=65, channel="Käpy"),
          v(2, "ilman", kind=VideoKind.SHORT)]
    p = tmp_path / "a.csv"
    assert export_csv(p, vs) == 2
    raw = p.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    rows = list(csv.DictReader(open(p, encoding="utf-8-sig", newline="")))
    assert rows[0]["title"] == vs[0].title and rows[0]["channel"] == "Käpy"
    assert rows[0]["duration_seconds"] == "65" and rows[1]["type"] == "short"
    assert rows[1]["duration_seconds"] == ""


def test_csv_links_only(tmp_path):
    p = tmp_path / "l.csv"
    export_csv(p, [v(1)], links_only=True)
    assert p.read_text(encoding="utf-8-sig").splitlines() == ["url", v(1).url]
