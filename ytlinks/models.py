"""Tietomallit."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class VideoKind(str, Enum):
    VIDEO = "video"
    SHORT = "short"
    LIVE = "live"


# Kanavan välilehti yt-dlp:n URL:ssa -> sisältötyyppi
TAB_FOR_KIND = {
    VideoKind.VIDEO: "videos",
    VideoKind.SHORT: "shorts",
    VideoKind.LIVE: "streams",
}

KIND_LABELS = {
    VideoKind.VIDEO: "Video",
    VideoKind.SHORT: "Short",
    VideoKind.LIVE: "Livelähetys",
}


@dataclass
class Video:
    video_id: str
    title: str = ""
    url: str = ""
    upload_date: str = ""  # ISO-muoto YYYY-MM-DD tai tyhjä, jos ei tiedossa
    duration: int | None = None  # sekunteina
    channel: str = ""
    kind: VideoKind = VideoKind.VIDEO

    def __post_init__(self) -> None:
        if not self.url:
            self.url = video_url(self.video_id, self.kind)


def video_url(video_id: str, kind: VideoKind = VideoKind.VIDEO) -> str:
    if kind == VideoKind.SHORT:
        return f"https://www.youtube.com/shorts/{video_id}"
    return f"https://www.youtube.com/watch?v={video_id}"


@dataclass
class FetchOptions:
    kinds: tuple[VideoKind, ...] = (VideoKind.VIDEO,)
    fetch_exact_dates: bool = False  # hidas: yksi pyyntö per video
    limit: int = 0  # 0 = ei rajaa (per välilehti)


@dataclass
class FetchResult:
    channel_name: str = ""
    videos: list[Video] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)  # osittaiset virheet / rajoitukset
    notes: list[str] = field(default_factory=list)  # neutraalit tiedot (esim. puuttuva välilehti)
    cancelled: bool = False

    @property
    def complete(self) -> bool:
        """Tosi vain, jos haku kävi läpi ilman virheitä, keskeytystä tai rajausta."""
        return not self.warnings and not self.cancelled
