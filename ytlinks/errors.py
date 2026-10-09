"""Virheiden luokittelu ymmärrettäviksi käyttäjäviesteiksi."""
from __future__ import annotations

import re


class InvalidChannelUrl(ValueError):
    """Annettua osoitetta ei tunnistettu YouTube-kanavaksi."""


class FetchError(Exception):
    def __init__(self, message: str, *, kind: str = "unknown", detail: str = "") -> None:
        super().__init__(message)
        self.kind = kind
        self.detail = detail

    @property
    def user_message(self) -> str:
        return str(self)


class Cancelled(Exception):
    """Käyttäjä keskeytti haun."""


class MissingTab(Exception):
    """Kanavalla ei ole pyydettyä välilehteä (esim. ei Shorts-videoita)."""


_ANSI = re.compile(r"\x1b\[[0-9;]*m")

_RULES: list[tuple[str, tuple[str, ...], str]] = [
    ("rate_limit", ("http error 429", "too many requests", "rate-limit", "rate limit"),
     "YouTube rajoitti pyyntöjä (liian monta pyyntöä). Odota hetki ja yritä uudelleen."),
    ("bot_check", ("confirm you’re not a bot", "confirm you're not a bot", "sign in to confirm"),
     "YouTube vaatii kirjautumista tai varmistusta (botintunnistus). Yritä myöhemmin "
     "uudelleen tai toisesta verkosta."),
    ("not_found", ("http error 404", "does not exist", "channel is not available",
                   "this channel does not", "not found", "unavailable", "has been terminated"),
     "Kanavaa ei löytynyt tai se ei ole saatavilla. Tarkista osoite."),
    ("forbidden", ("http error 403", "forbidden"),
     "YouTube tai verkko esti pääsyn (403). Yritä myöhemmin uudelleen."),
    ("network", ("urlopen error", "unable to download", "timed out", "timeout",
                 "connection", "getaddrinfo", "temporary failure", "name resolution",
                 "network is unreachable", "ssl", "proxy"),
     "Verkkovirhe: YouTubeen ei saatu yhteyttä. Tarkista verkkoyhteys ja yritä uudelleen."),
]


def clean_message(exc: BaseException | str) -> str:
    return _ANSI.sub("", str(exc)).strip()


def classify_exception(exc: BaseException) -> FetchError:
    """Muuttaa yt-dlp:n tai verkkokirjaston poikkeuksen FetchErroriksi."""
    if isinstance(exc, FetchError):
        return exc
    raw = clean_message(exc)
    low = raw.lower()
    for kind, needles, message in _RULES:
        if any(n in low for n in needles):
            return FetchError(message, kind=kind, detail=raw)
    return FetchError(f"Haku epäonnistui: {raw or type(exc).__name__}", kind="unknown", detail=raw)


def is_missing_tab_message(message: str) -> bool:
    return bool(re.search(r"does not have an? [\w ]+ tab", clean_message(message), re.I))
