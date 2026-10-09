"""Tulosten säilytys, duplikaattien poisto, suodatus ja hakeminen."""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from .models import KIND_LABELS, Video, VideoKind

_VIDEO_ID = re.compile(r"^[\w-]{11}$")


def is_valid_video_id(value: object) -> bool:
    return isinstance(value, str) and bool(_VIDEO_ID.match(value))


class ResultSet:
    """Järjestetty kokoelma videoita, joka poistaa duplikaatit video-ID:n perusteella."""

    def __init__(self) -> None:
        self._items: dict[str, Video] = {}
        self.duplicates_skipped = 0

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self):
        return iter(self._items.values())

    def __contains__(self, video_id: str) -> bool:
        return video_id in self._items

    def get(self, video_id: str) -> Video | None:
        return self._items.get(video_id)

    def add_many(self, videos: Iterable[Video]) -> list[Video]:
        """Lisää uudet videot ja palauttaa vain ne, jotka todella lisättiin."""
        added: list[Video] = []
        for video in videos:
            if video.video_id in self._items:
                self.duplicates_skipped += 1
                continue
            self._items[video.video_id] = video
            added.append(video)
        return added

    def update(self, video: Video) -> bool:
        """Korvaa olemassa olevan videon tiedot (esim. tarkka julkaisupäivä)."""
        if video.video_id not in self._items:
            return False
        self._items[video.video_id] = video
        return True

    def as_list(self) -> list[Video]:
        return list(self._items.values())


def normalize_text(text: str) -> str:
    return unicodedata.normalize("NFC", text or "").casefold()


def matches_query(video: Video, query: str, kinds: Iterable[VideoKind] | None = None) -> bool:
    """Kaikkien hakusanojen on löydyttävä otsikosta (kirjainkoolla ei väliä)."""
    if kinds is not None and video.kind not in set(kinds):
        return False
    terms = normalize_text(query).split()
    if not terms:
        return True
    title = normalize_text(video.title)
    return all(t in title for t in terms)


def filter_videos(videos: Iterable[Video], query: str = "",
                  kinds: Iterable[VideoKind] | None = None) -> list[Video]:
    kinds = None if kinds is None else tuple(kinds)
    return [v for v in videos if matches_query(v, query, kinds)]


def format_duration(seconds: int | None) -> str:
    if seconds is None:
        return ""
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def kind_label(kind: VideoKind) -> str:
    return KIND_LABELS[kind]


def format_date(upload_date: object = None, timestamp: object = None) -> str:
    """Muuntaa yt-dlp:n YYYYMMDD- tai epoch-arvon muotoon YYYY-MM-DD. Tyhjä, jos ei tiedossa."""
    if isinstance(upload_date, str) and re.fullmatch(r"\d{8}", upload_date):
        return f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"
    if isinstance(timestamp, (int, float)) and timestamp > 0:
        from datetime import datetime, timezone
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")
    return ""
