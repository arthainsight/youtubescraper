"""Valehaku yt-dlp:lle testeihin (ei verkkoa)."""
from __future__ import annotations


def vid(i: int, **extra) -> dict:
    d = {"id": f"{i:011d}", "title": f"Video {i} äö", "duration": 60 + i}
    d.update(extra)
    return d


class FakeYDL:
    """tabs: {"videos": [entry, ...]}; arvo voi olla Exception -> nostetaan sellaisenaan.
    Merkintä Exception listassa nostetaan iteroinnin aikana."""

    def __init__(self, tabs: dict, opts: dict, detail: dict | None = None) -> None:
        self.tabs, self.opts, self.detail = tabs, opts, detail or {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=False):
        assert download is False
        if "watch?v=" in url:
            vid_id = url.split("v=")[1]
            if vid_id not in self.detail:
                raise RuntimeError("HTTP Error 429: Too Many Requests")
            return self.detail[vid_id]
        tab = url.rsplit("/", 1)[1]
        data = self.tabs.get(tab)
        if isinstance(data, Exception):
            raise data
        if data is None:
            raise RuntimeError(f"This channel does not have a {tab} tab")

        def gen():
            for e in data:
                if isinstance(e, Exception):
                    raise e
                yield e
        return {"channel": "Testikanava", "entries": gen()}


def factory(tabs: dict, detail: dict | None = None):
    return lambda opts: FakeYDL(tabs, opts, detail)
