"""TXT- ja CSV-vienti (UTF-8)."""
from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path

from .models import Video

CSV_HEADER_FULL = ["title", "url", "video_id", "upload_date", "duration_seconds", "channel", "type"]
CSV_HEADER_LINKS = ["url"]


def _clean(text: str) -> str:
    return " ".join((text or "").split())  # ei rivinvaihtoja/tabulaattoreita TXT-riveille


def render_txt(videos: Iterable[Video], links_only: bool = True) -> str:
    """Linkkitila: yksi URL per rivi. Muuten: otsikko<TAB>URL<TAB>päivä per rivi."""
    lines = []
    for v in videos:
        if links_only:
            lines.append(v.url)
        else:
            lines.append(f"{_clean(v.title)}\t{v.url}\t{v.upload_date}")
    return "\n".join(lines) + ("\n" if lines else "")


def export_txt(path: str | Path, videos: Iterable[Video], links_only: bool = True) -> int:
    videos = list(videos)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(render_txt(videos, links_only))
    return len(videos)


def export_csv(path: str | Path, videos: Iterable[Video], links_only: bool = False) -> int:
    """Kirjoittaa CSV:n UTF-8-BOM-koodauksella, jotta Excel näyttää ääkköset oikein."""
    videos = list(videos)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        if links_only:
            w.writerow(CSV_HEADER_LINKS)
            for v in videos:
                w.writerow([v.url])
        else:
            w.writerow(CSV_HEADER_FULL)
            for v in videos:
                w.writerow([v.title, v.url, v.video_id, v.upload_date,
                            "" if v.duration is None else v.duration, v.channel, v.kind.value])
    return len(videos)
