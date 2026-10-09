"""GUI-savutestit offscreen-tilassa; verkkohaku korvataan valehaulla."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog  # noqa: E402

from ytlinks import fetcher  # noqa: E402
from ytlinks.gui import worker as worker_mod  # noqa: E402
from ytlinks.gui.main_window import MainWindow  # noqa: E402
from ytlinks.models import VideoKind  # noqa: E402

from .fakes import factory, vid  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def wait_done(app, win, timeout=5000):
    import time
    end = time.time() + timeout / 1000
    while (win.running or time.time() < end - timeout / 1000 + 0.05) and time.time() < end:
        app.processEvents()
        if not win.running:
            break
    app.processEvents()
    assert not win.running


@pytest.fixture
def win(app, monkeypatch):
    tabs = {"videos": [vid(1, title="Kissa äö"), vid(2, title="Koira"), vid(1, title="duplikaatti")],
            "shorts": [vid(3, title="Kissa short")]}
    real = fetcher.fetch_channel
    monkeypatch.setattr(worker_mod, "fetch_channel",
                        lambda url, opts, **kw: real(url, opts, ydl_factory=factory(tabs), **kw))
    w = MainWindow()
    w.show()
    yield w
    w.close()


def test_collect_filter_copy_export_open(app, win, tmp_path, monkeypatch):
    win.cb_shorts.setChecked(True)
    win.url_edit.setText("youtube.com/@kanava")
    win.start_collect()
    assert win.running and not win.collect_btn.isEnabled() and win.cancel_btn.isEnabled()
    wait_done(app, win)
    assert win.model.rowCount() == 3  # duplikaatti poistettu
    assert "Löydetty: 3" in win.count_label.text() and "Valmis" in win.status_label.text()
    assert win.copy_btn.isEnabled() and not win.banner.isVisible()

    win.filter_edit.setText("kissa")
    assert win.proxy.rowCount() == 2
    win.kind_filter.setCurrentIndex(win.kind_filter.findData(VideoKind.SHORT))
    assert win.proxy.rowCount() == 1
    win.kind_filter.setCurrentIndex(0)
    win.filter_edit.setText("")

    win.copy_links()
    assert QApplication.clipboard().text().count("\n") == 2

    out = tmp_path / "ulos"
    out.mkdir()
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(out / "tulos"), "")))
    win.export_csv_file()
    win.export_txt_file()
    assert "Kissa äö" in (out / "tulos.csv").read_text(encoding="utf-8-sig")
    assert len((out / "tulos.txt").read_text(encoding="utf-8").splitlines()) == 3

    opened = []
    from ytlinks.gui import main_window as mw
    monkeypatch.setattr(mw.QDesktopServices, "openUrl", staticmethod(lambda u: opened.append(u.toString()) or True))
    assert not win.open_btn.isEnabled()
    win.table.selectRow(0)
    assert win.open_btn.isEnabled()
    win.open_selected()
    assert opened and opened[0].startswith("https://www.youtube.com/")


def test_invalid_url_shows_error_and_retry(app, win):
    win.url_edit.setText("https://example.com/x")
    win.start_collect()
    wait_done(app, win)
    assert win.banner.isVisible() and "YouTube-osoite" in win.banner_label.text()
    assert win.retry_btn.isEnabled()
    win.url_edit.setText("@kanava")
    win.retry()  # yrittää uudelleen samalla (virheellisellä) pyynnöllä
    wait_done(app, win)
    assert win.banner.isVisible()


def test_links_only_hides_columns_and_no_kind_blocks_start(app, win):
    win.rb_links.setChecked(True)
    assert win.table.isColumnHidden(0) and not win.table.isColumnHidden(1)
    win.cb_videos.setChecked(False)
    assert not win.collect_btn.isEnabled()


def test_narrow_window_layout(app, win):
    win.resize(360, 700)
    app.processEvents()
    assert win.actions._cols == 1 and win.url_row_widget._narrow
