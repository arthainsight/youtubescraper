"""YouTube-kanavaosoitteiden tunnistus ja normalisointi."""
from __future__ import annotations

import re
from urllib.parse import urlparse

from .errors import InvalidChannelUrl
from .models import TAB_FOR_KIND, VideoKind

_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
_KNOWN_TABS = {"videos", "shorts", "streams", "live", "featured", "playlists",
               "community", "channels", "about", "releases", "podcasts", "search"}
_HANDLE = re.compile(r"^@[\w.\-]{3,100}$")
_CHANNEL_ID = re.compile(r"^UC[\w-]{22}$")
_NAME = re.compile(r"^[^/\s?#]{1,100}$")


def normalize_channel_url(text: str) -> str:
    """Palauttaa kanavan perusosoitteen ilman välilehteä, esim. https://www.youtube.com/@nimi.

    Hyväksytyt muodot: /@kanava, /channel/UC..., /c/nimi, /user/nimi, näiden perään
    liitetyt välilehdet (/videos jne.), pelkkä @kanava ja pelkkä UC-kanavatunnus.
    Nostaa InvalidChannelUrl, jos osoite ei ole kanava.
    """
    raw = (text or "").strip()
    if not raw:
        raise InvalidChannelUrl("Syötä YouTube-kanavan osoite.")

    # Pelkkä tunnus ilman osoitetta
    if _HANDLE.match(raw):
        return f"https://www.youtube.com/{raw}"
    if _CHANNEL_ID.match(raw):
        return f"https://www.youtube.com/channel/{raw}"

    if "://" not in raw:
        raw = "https://" + raw
    try:
        parsed = urlparse(raw)
    except ValueError as exc:
        raise InvalidChannelUrl("Osoite ei ole kelvollinen.") from exc

    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or host not in _HOSTS:
        if host == "youtu.be":
            raise InvalidChannelUrl("Tämä on yksittäisen videon osoite, ei kanavan.")
        raise InvalidChannelUrl("Osoite ei ole YouTube-osoite (youtube.com).")

    parts = [p for p in parsed.path.split("/") if p]
    if not parts:
        raise InvalidChannelUrl("Osoitteesta puuttuu kanava (esim. youtube.com/@kanava).")

    first = parts[0]
    if first.startswith("@"):
        if not _HANDLE.match(first):
            raise InvalidChannelUrl("Kanavan @-tunnus ei ole kelvollinen.")
        base = f"/{first}"
    elif first == "channel":
        if len(parts) < 2 or not _CHANNEL_ID.match(parts[1]):
            raise InvalidChannelUrl("Kanavatunnuksen tulee olla muotoa UC… (24 merkkiä).")
        base = f"/channel/{parts[1]}"
    elif first in ("c", "user"):
        if len(parts) < 2 or not _NAME.match(parts[1]):
            raise InvalidChannelUrl(f"Osoitteesta puuttuu kanavan nimi (/{first}/nimi).")
        base = f"/{first}/{parts[1]}"
    elif first in ("watch", "shorts", "live", "embed", "playlist", "results", "feed"):
        raise InvalidChannelUrl(
            "Tämä ei ole kanavan osoite. Käytä muotoa youtube.com/@kanava tai /channel/UC…")
    else:
        raise InvalidChannelUrl("Osoitetta ei tunnistettu kanavaksi.")

    return "https://www.youtube.com" + base


def tab_url(base_url: str, kind: VideoKind) -> str:
    return f"{base_url}/{TAB_FOR_KIND[kind]}"
