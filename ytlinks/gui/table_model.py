"""Tulostaulukon malli ja suodatus (Qt)."""
from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt

from ..models import Video, VideoKind
from ..results import format_duration, kind_label, matches_query

COLUMNS = ["Otsikko", "URL", "Julkaisupäivä", "Kesto", "Tyyppi", "Video-ID", "Kanava"]
COL_TITLE, COL_URL, COL_DATE, COL_DURATION, COL_KIND, COL_ID, COL_CHANNEL = range(7)


class VideoTableModel(QAbstractTableModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._videos: list[Video] = []
        self._row_by_id: dict[str, int] = {}

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._videos)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return COLUMNS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        v = self._videos[index.row()]
        col = index.column()
        if role in (Qt.DisplayRole, Qt.ToolTipRole):
            return {
                COL_TITLE: v.title, COL_URL: v.url, COL_DATE: v.upload_date or "–",
                COL_DURATION: format_duration(v.duration), COL_KIND: kind_label(v.kind),
                COL_ID: v.video_id, COL_CHANNEL: v.channel,
            }[col]
        if role == Qt.UserRole:  # lajitteluarvo
            if col == COL_DURATION:
                return -1 if v.duration is None else v.duration
            if col == COL_DATE:
                return v.upload_date
            return (v.title if col == COL_TITLE else self.data(index, Qt.DisplayRole)).casefold()
        return None

    def video_at(self, row: int) -> Video:
        return self._videos[row]

    def videos(self) -> list[Video]:
        return list(self._videos)

    def clear(self) -> None:
        self.beginResetModel()
        self._videos = []
        self._row_by_id = {}
        self.endResetModel()

    def append(self, videos: list[Video]) -> None:
        if not videos:
            return
        start = len(self._videos)
        self.beginInsertRows(QModelIndex(), start, start + len(videos) - 1)
        for i, v in enumerate(videos):
            self._row_by_id[v.video_id] = start + i
        self._videos.extend(videos)
        self.endInsertRows()

    def update(self, videos: list[Video]) -> None:
        for v in videos:
            row = self._row_by_id.get(v.video_id)
            if row is None:
                continue
            self._videos[row] = v
            self.dataChanged.emit(self.index(row, 0), self.index(row, len(COLUMNS) - 1))


class VideoFilterProxy(QSortFilterProxyModel):
    """Suodattaa otsikon hakusanoilla ja tyypin mukaan."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._query = ""
        self._kinds: set[VideoKind] | None = None
        self.setSortRole(Qt.UserRole)

    def set_query(self, query: str) -> None:
        self._query = query
        self.invalidate()

    def set_kinds(self, kinds: set[VideoKind] | None) -> None:
        self._kinds = kinds
        self.invalidate()

    def filterAcceptsRow(self, source_row, source_parent) -> bool:
        video = self.sourceModel().video_at(source_row)
        return matches_query(video, self._query, self._kinds)

    def visible_videos(self) -> list[Video]:
        src = self.sourceModel()
        return [src.video_at(self.mapToSource(self.index(r, 0)).row())
                for r in range(self.rowCount())]
