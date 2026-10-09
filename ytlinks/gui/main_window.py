"""Pääikkuna."""
from __future__ import annotations

import re

from PySide6.QtCore import QThread, QUrl, Qt
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFrame,
                               QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton,
                               QRadioButton, QSpinBox, QTableView, QVBoxLayout, QWidget)

from .. import __version__
from ..exporters import export_csv, export_txt
from ..models import FetchOptions, FetchResult, Video, VideoKind
from .table_model import (COL_CHANNEL, COL_DATE, COL_DURATION, COL_ID, COL_KIND, COL_TITLE,
                          COL_URL, VideoFilterProxy, VideoTableModel)
from .worker import FetchWorker

STYLE = """
QMainWindow, QWidget { font-size: 10.5pt; }
QPushButton { padding: 6px 12px; border-radius: 5px; border: 1px solid #b8bec6; background: #f4f6f8; }
QPushButton:hover:enabled { background: #e6ebf0; }
QPushButton:disabled { color: #9aa1a9; background: #eef0f2; }
QPushButton#primary { background: #d32f2f; color: white; border: 1px solid #b71c1c; font-weight: bold; }
QPushButton#primary:hover:enabled { background: #e53935; }
QPushButton#primary:disabled { background: #e0a3a3; color: #fff; }
QLineEdit, QSpinBox, QComboBox { padding: 5px; border: 1px solid #b8bec6; border-radius: 5px; }
QGroupBox { border: 1px solid #d5d9de; border-radius: 6px; margin-top: 10px; padding: 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; font-weight: bold; }
QFrame#banner { border-radius: 6px; padding: 4px; }
QFrame#banner[level="error"] { background: #fdecea; border: 1px solid #e57373; }
QFrame#banner[level="warn"] { background: #fff4e0; border: 1px solid #f0b05a; }
QTableView { gridline-color: #e1e4e8; alternate-background-color: #f7f9fb; }
QProgressBar { border: 1px solid #b8bec6; border-radius: 5px; text-align: center; height: 16px; }
QProgressBar::chunk { background: #d32f2f; }
"""

NARROW_WIDTH = 560  # tämän alla käytetään pinottua (mobiilin kaltaista) asettelua


class FlowGrid(QWidget):
    """Ruudukko, joka asettelee lapsensa uudelleen leveyden mukaan (1..n saraketta)."""

    def __init__(self, widgets: list[QWidget], min_cell: int = 170, parent=None) -> None:
        super().__init__(parent)
        self._widgets = widgets
        self._min_cell = min_cell
        self._cols = 0
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._relayout(max(1, len(widgets)))

    def _relayout(self, cols: int) -> None:
        if cols == self._cols:
            return
        self._cols = cols
        for w in self._widgets:
            self._grid.removeWidget(w)
        for i, w in enumerate(self._widgets):
            self._grid.addWidget(w, i // cols, i % cols)
        for c in range(cols):
            self._grid.setColumnStretch(c, 1)

    def resizeEvent(self, event) -> None:
        cols = max(1, min(len(self._widgets), self.width() // self._min_cell))
        self._relayout(cols)
        super().resizeEvent(event)


class UrlRow(QWidget):
    """URL-kenttä ja painikkeet: kapeassa ikkunassa painikkeet siirtyvät kentän alle."""

    def __init__(self, edit: QWidget, *buttons: QWidget) -> None:
        super().__init__()
        self._edit, self._buttons = edit, buttons
        self._narrow: bool | None = None
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._layout(False)

    def _layout(self, narrow: bool) -> None:
        if narrow == self._narrow:
            return
        self._narrow = narrow
        for w in (self._edit, *self._buttons):
            self._grid.removeWidget(w)
        n = len(self._buttons)
        if narrow:
            self._grid.addWidget(self._edit, 0, 0, 1, n)
            for i, b in enumerate(self._buttons):
                self._grid.addWidget(b, 1, i)
        else:
            self._grid.addWidget(self._edit, 0, 0)
            for i, b in enumerate(self._buttons):
                self._grid.addWidget(b, 0, i + 1)
        self._grid.setColumnStretch(0, 1)

    def resizeEvent(self, event) -> None:
        self._layout(self.width() < NARROW_WIDTH - 60)
        super().resizeEvent(event)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("YouTube-linkkien kerääjä")
        self.resize(980, 760)
        self.setMinimumWidth(340)
        self.setStyleSheet(STYLE)

        self._thread: QThread | None = None
        self._worker: FetchWorker | None = None
        self._last_request: tuple[str, FetchOptions] | None = None
        self._channel_name = ""

        self.model = VideoTableModel(self)
        self.proxy = VideoFilterProxy(self)
        self.proxy.setSourceModel(self.model)

        self._build_ui()
        self._wire()
        self._apply_view_mode()
        self._update_buttons()

    # ---------- rakenne ----------
    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)

        # URL-rivi
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("YouTube-kanavan osoite, esim. https://www.youtube.com/@kanava")
        self.url_edit.setClearButtonEnabled(True)
        self.collect_btn = QPushButton("Kerää videot")
        self.collect_btn.setObjectName("primary")
        self.cancel_btn = QPushButton("Peruuta")
        self.url_row_widget = UrlRow(self.url_edit, self.collect_btn, self.cancel_btn)
        lay.addWidget(self.url_row_widget)

        # Asetukset
        self.cb_videos = QCheckBox("Kaikki videot")
        self.cb_videos.setChecked(True)
        self.cb_shorts = QCheckBox("Shorts-videot")
        self.cb_live = QCheckBox("Livelähetykset")
        kinds_box = QGroupBox("Haettava sisältö")
        kl = QVBoxLayout(kinds_box)
        for cb in (self.cb_videos, self.cb_shorts, self.cb_live):
            kl.addWidget(cb)

        self.rb_links = QRadioButton("Vain linkit")
        self.rb_details = QRadioButton("Linkit, otsikot ja julkaisupäivät")
        self.rb_details.setChecked(True)
        self.cb_exact = QCheckBox("Hae tarkat julkaisupäivät (hidas)")
        self.cb_exact.setToolTip("YouTube ei anna päivää kanavalistauksessa. Tämä tekee yhden "
                                 "pyynnön per video ja voi kestää pitkään.")
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(0, 100000)
        self.limit_spin.setSpecialValueText("Ei rajaa")
        self.limit_spin.setToolTip("Enimmäismäärä per välilehti (videot / Shorts / livet)")
        view_box = QGroupBox("Näkymä ja haku")
        vl = QVBoxLayout(view_box)
        vl.addWidget(self.rb_links)
        vl.addWidget(self.rb_details)
        vl.addWidget(self.cb_exact)
        lim = QHBoxLayout()
        lim.addWidget(QLabel("Enintään / välilehti:"))
        lim.addWidget(self.limit_spin, 1)
        vl.addLayout(lim)

        opts = FlowGrid([kinds_box, view_box], min_cell=260)
        lay.addWidget(opts)

        # Edistyminen
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.status_label = QLabel("Syötä kanavan osoite ja paina ”Kerää videot”.")
        self.status_label.setWordWrap(True)
        self.count_label = QLabel("Löydetty: 0")
        self.count_label.setStyleSheet("font-weight: bold;")
        status_row = QHBoxLayout()
        status_row.addWidget(self.status_label, 1)
        status_row.addWidget(self.count_label)
        lay.addWidget(self.progress)
        lay.addLayout(status_row)

        # Virhe-/varoituspalkki
        self.banner = QFrame()
        self.banner.setObjectName("banner")
        bl = QHBoxLayout(self.banner)
        self.banner_label = QLabel()
        self.banner_label.setWordWrap(True)
        self.banner_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.retry_btn = QPushButton("Yritä uudelleen")
        bl.addWidget(self.banner_label, 1)
        bl.addWidget(self.retry_btn)
        self.banner.hide()
        lay.addWidget(self.banner)

        # Suodatus
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Hae otsikosta…")
        self.filter_edit.setClearButtonEnabled(True)
        self.kind_filter = QComboBox()
        self.kind_filter.addItem("Kaikki tyypit", None)
        self.kind_filter.addItem("Videot", VideoKind.VIDEO)
        self.kind_filter.addItem("Shorts", VideoKind.SHORT)
        self.kind_filter.addItem("Livelähetykset", VideoKind.LIVE)
        frow = QHBoxLayout()
        frow.addWidget(self.filter_edit, 1)
        frow.addWidget(self.kind_filter)
        lay.addLayout(frow)

        # Taulukko
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)  # alussa löytöjärjestys
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(COL_TITLE, QHeaderView.Stretch)
        self.table.setColumnWidth(COL_URL, 300)
        self.table.setColumnWidth(COL_DATE, 110)
        self.table.setColumnWidth(COL_DURATION, 70)
        self.table.setColumnWidth(COL_KIND, 90)
        self.table.setColumnWidth(COL_ID, 110)
        self.table.setColumnWidth(COL_CHANNEL, 140)
        lay.addWidget(self.table, 1)

        # Toimintopainikkeet
        self.copy_btn = QPushButton("Kopioi kaikki linkit")
        self.txt_btn = QPushButton("Vie TXT")
        self.csv_btn = QPushButton("Vie CSV")
        self.open_btn = QPushButton("Avaa linkki valitulle videolle")
        self.actions = FlowGrid([self.copy_btn, self.txt_btn, self.csv_btn, self.open_btn],
                                min_cell=210)
        lay.addWidget(self.actions)

        self.footer = QLabel(f"v{__version__} · Kopiointi ja vienti koskevat näkyvillä olevia rivejä "
                             "(suodatin huomioidaan).")
        self.footer.setWordWrap(True)
        self.footer.setStyleSheet("color: #6b727a; font-size: 9pt;")
        lay.addWidget(self.footer)

    def _wire(self) -> None:
        self.collect_btn.clicked.connect(self.start_collect)
        self.url_edit.returnPressed.connect(self.start_collect)
        self.cancel_btn.clicked.connect(self.cancel_collect)
        self.retry_btn.clicked.connect(self.retry)
        self.rb_links.toggled.connect(self._apply_view_mode)
        self.rb_details.toggled.connect(self._apply_view_mode)
        self.filter_edit.textChanged.connect(self._on_filter_changed)
        self.kind_filter.currentIndexChanged.connect(self._on_filter_changed)
        self.copy_btn.clicked.connect(self.copy_links)
        self.txt_btn.clicked.connect(self.export_txt_file)
        self.csv_btn.clicked.connect(self.export_csv_file)
        self.open_btn.clicked.connect(self.open_selected)
        self.table.doubleClicked.connect(lambda _i: self.open_selected())
        self.table.selectionModel().selectionChanged.connect(lambda *_: self._update_buttons())
        self.proxy.rowsInserted.connect(lambda *_: self._update_buttons())
        self.proxy.rowsRemoved.connect(lambda *_: self._update_buttons())
        self.proxy.modelReset.connect(self._update_buttons)
        self.proxy.layoutChanged.connect(self._update_buttons)
        self.rb_details.toggled.connect(self.cb_exact.setEnabled)
        for cb in (self.cb_videos, self.cb_shorts, self.cb_live):
            cb.toggled.connect(self._update_buttons)

    # ---------- tila ----------
    @property
    def running(self) -> bool:
        return self._thread is not None

    @property
    def links_only(self) -> bool:
        return self.rb_links.isChecked()

    def _apply_view_mode(self, *_args) -> None:
        only_links = self.links_only
        for col in (COL_TITLE, COL_DATE, COL_DURATION, COL_KIND, COL_ID, COL_CHANNEL):
            hide = only_links
            if col == COL_ID:
                hide = True
            self.table.setColumnHidden(col, hide)
        self.table.setColumnHidden(COL_URL, False)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(COL_URL, QHeaderView.Stretch if only_links else QHeaderView.Interactive)
        hdr.setSectionResizeMode(COL_TITLE, QHeaderView.Stretch)
        if not self.rb_details.isChecked():
            self.cb_exact.setChecked(False)
        self.cb_exact.setEnabled(self.rb_details.isChecked() and not self.running)

    def _selected_kinds(self) -> tuple[VideoKind, ...]:
        kinds = []
        if self.cb_videos.isChecked():
            kinds.append(VideoKind.VIDEO)
        if self.cb_shorts.isChecked():
            kinds.append(VideoKind.SHORT)
        if self.cb_live.isChecked():
            kinds.append(VideoKind.LIVE)
        return tuple(kinds)

    def _update_buttons(self, *_args) -> None:
        running = self.running
        has_rows = self.proxy.rowCount() > 0
        self.collect_btn.setEnabled(not running and bool(self._selected_kinds()))
        self.cancel_btn.setEnabled(running)
        self.url_edit.setEnabled(not running)
        for w in (self.cb_videos, self.cb_shorts, self.cb_live, self.rb_links, self.rb_details,
                  self.limit_spin):
            w.setEnabled(not running)
        self.cb_exact.setEnabled(self.rb_details.isChecked() and not running)
        for b in (self.copy_btn, self.txt_btn, self.csv_btn):
            b.setEnabled(has_rows)
        self.open_btn.setEnabled(self.table.currentIndex().isValid()
                                 and bool(self.table.selectionModel().selectedRows()))
        self.retry_btn.setEnabled(not running and self._last_request is not None)
        self.collect_btn.setToolTip("" if self._selected_kinds() else "Valitse vähintään yksi sisältötyyppi.")
        self._update_count()

    def _update_count(self) -> None:
        total, shown = self.model.rowCount(), self.proxy.rowCount()
        text = f"Löydetty: {total}"
        if shown != total:
            text += f" (näkyvissä {shown})"
        self.count_label.setText(text)

    def _show_banner(self, text: str, level: str) -> None:
        self.banner_label.setText(text)
        self.banner.setProperty("level", level)
        self.banner.style().unpolish(self.banner)
        self.banner.style().polish(self.banner)
        self.banner.show()

    # ---------- haku ----------
    def current_options(self) -> FetchOptions:
        return FetchOptions(kinds=self._selected_kinds(),
                            fetch_exact_dates=self.cb_exact.isChecked() and self.rb_details.isChecked(),
                            limit=self.limit_spin.value())

    def start_collect(self) -> None:
        if self.running or not self.collect_btn.isEnabled():
            return
        url = self.url_edit.text().strip()
        if not url:
            self._show_banner("Syötä YouTube-kanavan osoite.", "error")
            return
        self._start(url, self.current_options())

    def retry(self) -> None:
        if self.running or self._last_request is None:
            return
        self._start(*self._last_request)

    def _start(self, url: str, options: FetchOptions) -> None:
        self._last_request = (url, options)
        self.banner.hide()
        self.model.clear()
        self._channel_name = ""
        self.progress.setRange(0, 0)  # epämääräinen eteneminen
        self.status_label.setText("Aloitetaan haku…")

        self._thread = QThread(self)
        self._worker = FetchWorker(url, options)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.status.connect(self.status_label.setText)
        self._worker.batch.connect(self._on_batch)
        self._worker.updated.connect(self.model.update)
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.done.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)
        self._thread.start()
        self._update_buttons()

    def cancel_collect(self) -> None:
        if self._worker:
            self._worker.cancel()
            self.status_label.setText("Keskeytetään…")
            self.cancel_btn.setEnabled(False)

    def _cleanup_thread(self) -> None:
        if self._worker:
            self._worker.deleteLater()
        if self._thread:
            self._thread.deleteLater()
        self._worker = None
        self._thread = None
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self._apply_view_mode()
        self._update_buttons()

    def _on_batch(self, videos: list[Video]) -> None:
        self.model.append(videos)
        self._update_count()

    def _on_finished(self, result: FetchResult) -> None:
        self._channel_name = result.channel_name
        n = len(result.videos)
        name = f" kanavalta {result.channel_name}" if result.channel_name else ""
        if result.complete:
            self.status_label.setText(f"Valmis: {n} videota{name}.")
        else:
            self.status_label.setText(f"Haku päättyi, mutta tulokset eivät ole täydelliset: {n} videota{name}.")
        lines = list(result.warnings)
        if lines:
            self._show_banner("⚠ Tulokset ovat osittaiset.\n• " + "\n• ".join(lines), "warn")
        if result.notes:
            self.status_label.setText(self.status_label.text() + "  " + " ".join(result.notes))
        if not self.links_only and result.videos and not any(v.upload_date for v in result.videos):
            self.status_label.setText(self.status_label.text()
                                      + "  Julkaisupäivät eivät sisältyneet listaukseen – "
                                        "valitse ”Hae tarkat julkaisupäivät”.")

    def _on_failed(self, message: str, detail: str) -> None:
        self.status_label.setText("Haku epäonnistui.")
        text = "✖ " + message
        if detail and detail not in message:
            text += f"\n\nTekninen tieto: {detail[:400]}"
        self._show_banner(text, "error")

    # ---------- suodatus ----------
    def _on_filter_changed(self, *_args) -> None:
        self.proxy.set_query(self.filter_edit.text())
        kind = self.kind_filter.currentData()
        self.proxy.set_kinds({kind} if kind else None)
        self._update_buttons()

    # ---------- toiminnot ----------
    def visible_videos(self) -> list[Video]:
        return self.proxy.visible_videos()

    def copy_links(self) -> None:
        videos = self.visible_videos()
        if not videos:
            return
        QGuiApplication.clipboard().setText("\n".join(v.url for v in videos))
        self.status_label.setText(f"Kopioitu leikepöydälle: {len(videos)} linkkiä.")

    def _default_name(self, ext: str) -> str:
        base = re.sub(r"[^\w\-]+", "_", self._channel_name, flags=re.UNICODE).strip("_") or "youtube_videot"
        return f"{base}.{ext}"

    def _export(self, ext: str, label: str, writer) -> None:
        videos = self.visible_videos()
        if not videos:
            return
        path, _ = QFileDialog.getSaveFileName(self, f"Vie {label}", self._default_name(ext),
                                              f"{label} (*.{ext})")
        if not path:
            return
        if not path.lower().endswith(f".{ext}"):
            path += f".{ext}"
        try:
            count = writer(path, videos)
        except OSError as exc:
            QMessageBox.critical(self, "Vienti epäonnistui",
                                 f"Tiedostoa ei voitu tallentaa:\n{path}\n\n{exc}")
            return
        self.status_label.setText(f"Viety {count} riviä: {path}")

    def export_txt_file(self) -> None:
        self._export("txt", "TXT", lambda p, v: export_txt(p, v, links_only=self.links_only))

    def export_csv_file(self) -> None:
        self._export("csv", "CSV", lambda p, v: export_csv(p, v, links_only=self.links_only))

    def open_selected(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "Ei valintaa", "Valitse ensin video taulukosta.")
            return
        src = self.proxy.mapToSource(rows[0])
        video = self.model.video_at(src.row())
        if not QDesktopServices.openUrl(QUrl(video.url)):
            QMessageBox.warning(self, "Linkin avaus epäonnistui",
                                f"Selainta ei voitu avata. Linkki:\n{video.url}")

    def closeEvent(self, event) -> None:
        if self._worker and self._thread:
            self._worker.cancel()
            self._thread.quit()
            self._thread.wait(5000)
        super().closeEvent(event)
