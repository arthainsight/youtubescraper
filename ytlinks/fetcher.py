"""YouTube-hakujen logiikka (yt-dlp). Ei lataa videotiedostoja.

Haku tehdään kanavan välilehti kerrallaan (videos / shorts / streams) yt-dlp:n
"flat"-tilassa ja laiskasti (lazy_playlist), jolloin tulokset saadaan sivu kerrallaan
ja haun voi keskeyttää. Tarkat julkaisupäivät vaativat yhden pyynnön per video, joten
ne haetaan vain erillisestä valinnasta.
"""
from __future__ import annotations

import threading
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import Any

from .errors import (Cancelled, FetchError, MissingTab, classify_exception,
                     clean_message, is_missing_tab_message)
from .models import KIND_LABELS, FetchOptions, FetchResult, Video, VideoKind
from .results import ResultSet, format_date, is_valid_video_id
from .urls import normalize_channel_url, tab_url

BatchCallback = Callable[[list[Video]], None]
StatusCallback = Callable[[str], None]
YdlFactory = Callable[[dict], Any]  # palauttaa kontekstihallinnan, jolla on extract_info()

BATCH_SIZE = 50
DETAIL_WORKERS = 4


class _Logger:
    """Kerää yt-dlp:n varoitukset talteen konsolin sijaan."""

    def __init__(self) -> None:
        self.warnings: list[str] = []

    def debug(self, msg: str) -> None: ...
    def info(self, msg: str) -> None: ...

    def warning(self, msg: str) -> None:
        self.warnings.append(clean_message(msg))

    def error(self, msg: str) -> None:
        self.warnings.append(clean_message(msg))


def default_ydl_factory(opts: dict):
    import yt_dlp
    return yt_dlp.YoutubeDL(opts)


def _base_opts(logger: _Logger) -> dict:
    return {
        "quiet": True,
        "no_warnings": False,
        "noprogress": True,
        "skip_download": True,
        "logger": logger,
        "socket_timeout": 20,
        "retries": 3,
        "extractor_retries": 3,
        "ignoreerrors": False,
    }


def _entry_to_video(entry: dict, kind: VideoKind, fallback_channel: str) -> Video | None:
    video_id = entry.get("id")
    if not is_valid_video_id(video_id):
        return None
    duration = entry.get("duration")
    return Video(
        video_id=video_id,
        title=(entry.get("title") or "").strip(),
        upload_date=format_date(entry.get("upload_date"),
                                entry.get("timestamp") or entry.get("release_timestamp")),
        duration=int(duration) if isinstance(duration, (int, float)) else None,
        channel=(entry.get("channel") or entry.get("uploader") or fallback_channel or "").strip(),
        kind=kind,
    )


def _channel_name(info: dict) -> str:
    for key in ("channel", "uploader"):
        if info.get(key):
            return str(info[key]).strip()
    title = str(info.get("title") or "")
    for suffix in (" - Videos", " - Shorts", " - Live", " - Videot", " - Lyhytvideot"):
        if title.endswith(suffix):
            return title[: -len(suffix)]
    return title


def iter_tab(url: str, kind: VideoKind, *, ydl_factory: YdlFactory, logger: _Logger,
             limit: int = 0) -> Iterable[tuple[str, dict]]:
    """Tuottaa (kanavan nimi, merkintä) -pareja. Nostaa MissingTab / FetchError."""
    opts = _base_opts(logger)
    opts.update({"extract_flat": "in_playlist", "lazy_playlist": True})
    if limit > 0:
        opts["playlistend"] = limit
    try:
        with ydl_factory(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return
            name = _channel_name(info)
            count = 0
            for entry in info.get("entries") or []:
                if entry is None:
                    continue
                yield name, entry
                count += 1
                if limit > 0 and count >= limit:
                    return
    except (Cancelled, GeneratorExit):
        raise
    except Exception as exc:  # yt-dlp:n DownloadError/ExtractorError ym.
        if is_missing_tab_message(str(exc)):
            raise MissingTab(str(exc)) from exc
        raise classify_exception(exc) from exc


def fetch_channel(
    channel_url: str,
    options: FetchOptions,
    *,
    on_batch: BatchCallback | None = None,
    on_update: BatchCallback | None = None,
    on_status: StatusCallback | None = None,
    cancel: threading.Event | None = None,
    ydl_factory: YdlFactory = default_ydl_factory,
) -> FetchResult:
    """Hakee kanavan videot. Nostaa InvalidChannelUrl tai FetchError vain, jos mitään
    ei saatu haettua; osittaisissa onnistumisissa virheet palautetaan result.warnings-listassa."""
    cancel = cancel or threading.Event()
    status = on_status or (lambda _m: None)
    emit = on_batch or (lambda _b: None)

    base = normalize_channel_url(channel_url)
    kinds = options.kinds or (VideoKind.VIDEO,)
    logger = _Logger()
    results = ResultSet()
    result = FetchResult()
    first_error: FetchError | None = None

    def check_cancel() -> None:
        if cancel.is_set():
            raise Cancelled()

    try:
        for kind in kinds:
            check_cancel()
            label = KIND_LABELS[kind].lower()
            status(f"Haetaan: {label}…")
            batch: list[Video] = []
            tab_count = 0
            try:
                for name, entry in iter_tab(tab_url(base, kind), kind, ydl_factory=ydl_factory,
                                            logger=logger, limit=options.limit):
                    check_cancel()
                    if name and not result.channel_name:
                        result.channel_name = name
                    video = _entry_to_video(entry, kind, result.channel_name)
                    if video is None:
                        continue
                    tab_count += 1
                    batch.append(video)
                    if len(batch) >= BATCH_SIZE:
                        emit(results.add_many(batch))
                        batch = []
                        status(f"Haetaan: {label}… ({len(results)} löydetty)")
                if batch:
                    emit(results.add_many(batch))
                if options.limit > 0 and tab_count >= options.limit:
                    result.warnings.append(
                        f"{KIND_LABELS[kind]}: haku rajattiin {options.limit} ensimmäiseen "
                        "– kaikkia videoita ei haettu.")
            except MissingTab:
                result.notes.append(f"Kanavalla ei ole tyyppiä: {KIND_LABELS[kind]}.")
            except FetchError as exc:
                if batch:
                    emit(results.add_many(batch))
                first_error = first_error or exc
                result.warnings.append(
                    f"{KIND_LABELS[kind]}: haku keskeytyi virheeseen – tulokset ovat osittaiset. "
                    f"{exc.user_message}")

        if options.fetch_exact_dates and len(results):
            _fetch_details(results, on_update=on_update, status=status, cancel=cancel,
                           ydl_factory=ydl_factory, result=result)
    except Cancelled:
        result.cancelled = True
        result.warnings.append("Haku keskeytettiin – tulokset ovat osittaiset.")

    result.videos = results.as_list()
    result.notes.extend(w for w in dict.fromkeys(logger.warnings) if w)

    if not result.videos and first_error is not None:
        raise first_error
    if not result.videos and not result.cancelled and not result.warnings:
        result.notes.append("Kanavalta ei löytynyt valittuja videoita.")
    return result


def _fetch_details(results: ResultSet, *, on_update: BatchCallback | None,
                   status: StatusCallback, cancel: threading.Event,
                   ydl_factory: YdlFactory, result: FetchResult) -> None:
    """Hakee puuttuvat julkaisupäivät ja kestot videokohtaisesti (hidas)."""
    todo = [v for v in results if not v.upload_date]
    if not todo:
        return
    total = len(todo)
    done = 0
    failed = 0
    lock = threading.Lock()
    logger = _Logger()

    def one(video: Video) -> Video | None:
        if cancel.is_set():
            return None
        opts = _base_opts(logger)
        opts["extract_flat"] = False
        try:
            with ydl_factory(opts) as ydl:
                info = ydl.extract_info(video.url, download=False)
        except Exception:
            return replace(video, upload_date=video.upload_date)  # sama, merkitään epäonnistuneeksi
        if not info:
            return None
        return replace(
            video,
            title=video.title or (info.get("title") or "").strip(),
            upload_date=format_date(info.get("upload_date"),
                                    info.get("timestamp") or info.get("release_timestamp")),
            duration=video.duration if video.duration is not None else (
                int(info["duration"]) if isinstance(info.get("duration"), (int, float)) else None),
        )

    status(f"Haetaan tarkkoja julkaisupäiviä… (0/{total})")
    with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as pool:
        for original, updated in zip(todo, pool.map(one, todo)):
            with lock:
                done += 1
                if updated is None or not updated.upload_date:
                    failed += 1
                else:
                    results.update(updated)
                    if on_update:
                        on_update([updated])
            status(f"Haetaan tarkkoja julkaisupäiviä… ({done}/{total})")
            if cancel.is_set():
                raise Cancelled()
    if failed:
        result.warnings.append(
            f"Julkaisupäivä puuttuu {failed}/{total} videolta (haku epäonnistui tai päivää ei saatu).")
