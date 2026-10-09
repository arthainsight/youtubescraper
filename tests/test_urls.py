import pytest

from ytlinks.errors import InvalidChannelUrl
from ytlinks.models import VideoKind
from ytlinks.urls import normalize_channel_url, tab_url

UC = "UC" + "a" * 22


@pytest.mark.parametrize("raw,expected", [
    ("https://www.youtube.com/@kanava", "https://www.youtube.com/@kanava"),
    ("youtube.com/@kanava", "https://www.youtube.com/@kanava"),
    ("  @kanava  ", "https://www.youtube.com/@kanava"),
    ("https://m.youtube.com/@kanava/videos", "https://www.youtube.com/@kanava"),
    ("https://www.youtube.com/@kanava/shorts?view=0", "https://www.youtube.com/@kanava"),
    (f"https://www.youtube.com/channel/{UC}", f"https://www.youtube.com/channel/{UC}"),
    (f"https://www.youtube.com/channel/{UC}/streams", f"https://www.youtube.com/channel/{UC}"),
    (UC, f"https://www.youtube.com/channel/{UC}"),
    ("https://www.youtube.com/c/Kanava", "https://www.youtube.com/c/Kanava"),
    ("http://youtube.com/c/Kanava/featured", "https://www.youtube.com/c/Kanava"),
    ("https://www.youtube.com/user/vanhaKanava", "https://www.youtube.com/user/vanhaKanava"),
    ("https://www.youtube.com/@mäki-kanava", "https://www.youtube.com/@mäki-kanava"),
])
def test_valid(raw, expected):
    assert normalize_channel_url(raw) == expected


@pytest.mark.parametrize("raw", [
    "", "   ", "https://example.com/@kanava", "https://www.youtube.com/",
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "https://youtu.be/dQw4w9WgXcQ",
    "https://www.youtube.com/channel/ei-kelvollinen", "https://www.youtube.com/c/",
    "https://www.youtube.com/playlist?list=PL123", "https://www.youtube.com/@a",
    "https://www.youtube.com/jotain", "ftp://youtube.com/@kanava", "tämä ei ole osoite",
])
def test_invalid(raw):
    with pytest.raises(InvalidChannelUrl):
        normalize_channel_url(raw)


def test_tab_url():
    base = "https://www.youtube.com/@k"
    assert tab_url(base, VideoKind.VIDEO) == base + "/videos"
    assert tab_url(base, VideoKind.SHORT) == base + "/shorts"
    assert tab_url(base, VideoKind.LIVE) == base + "/streams"
