"""Verkkohaku omassa säikeessään, jotta käyttöliittymä ei jäädy."""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal

from ..errors import FetchError, InvalidChannelUrl, classify_exception
from ..fetcher import fetch_channel
from ..models import FetchOptions, FetchResult, Video


class FetchWorker(QObject):
    status = Signal(str)
    batch = Signal(list)       # list[Video]: uudet videot
    updated = Signal(list)     # list[Video]: täydennetyt tiedot
    finished_ok = Signal(object)    # FetchResult
    failed = Signal(str, str)       # käyttäjäviesti, tekninen lisätieto
    done = Signal()

    def __init__(self, url: str, options: FetchOptions) -> None:
        super().__init__()
        self._url = url
        self._options = options
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        try:
            result: FetchResult = fetch_channel(
                self._url, self._options,
                on_batch=self.batch.emit, on_update=self.updated.emit,
                on_status=self.status.emit, cancel=self.cancel_event)
            self.finished_ok.emit(result)
        except InvalidChannelUrl as exc:
            self.failed.emit(str(exc), "")
        except Exception as exc:
            err = classify_exception(exc)
            self.failed.emit(err.user_message, err.detail)
        finally:
            self.done.emit()
