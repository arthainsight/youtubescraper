"""Taustahaut selainkäyttöliittymälle: yksi säie per haku, tulokset noudetaan pollaamalla."""
from __future__ import annotations

import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable

from ..errors import InvalidChannelUrl, classify_exception
from ..fetcher import fetch_channel
from ..models import FetchOptions, FetchResult, Video

MAX_RUNNING = 3
MAX_JOBS = 30


def video_to_dict(v: Video) -> dict:
    return {"id": v.video_id, "title": v.title, "url": v.url, "date": v.upload_date,
            "duration": v.duration, "channel": v.channel, "kind": v.kind.value}


class TooManyJobs(Exception):
    pass


class Job:
    def __init__(self, url: str, options: FetchOptions) -> None:
        self.id = uuid.uuid4().hex
        self.url, self.options = url, options
        self.cancel = threading.Event()
        self.lock = threading.Lock()
        self.state = "running"  # running | done | failed
        self.status = "Aloitetaan haku…"
        self.videos: list[dict] = []
        self.updates: list[dict] = []
        self.result: dict | None = None
        self.error: dict | None = None
        self.created = time.time()

    def snapshot(self, after: int, uafter: int) -> dict:
        with self.lock:
            return {"id": self.id, "state": self.state, "status": self.status,
                    "total": len(self.videos), "videos": self.videos[after:],
                    "updates": self.updates[uafter:], "utotal": len(self.updates),
                    "result": self.result, "error": self.error}

    def run(self, fetch: Callable[..., FetchResult]) -> None:
        def on_batch(batch: list[Video]) -> None:
            with self.lock:
                self.videos.extend(video_to_dict(v) for v in batch)

        def on_update(batch: list[Video]) -> None:
            with self.lock:
                self.updates.extend(video_to_dict(v) for v in batch)

        def on_status(text: str) -> None:
            with self.lock:
                self.status = text

        try:
            res = fetch(self.url, self.options, on_batch=on_batch, on_update=on_update,
                        on_status=on_status, cancel=self.cancel)
            with self.lock:
                self.result = {"channel": res.channel_name, "complete": res.complete,
                               "cancelled": res.cancelled, "warnings": res.warnings,
                               "notes": res.notes, "count": len(res.videos)}
                self.state = "done"
                self.status = "Valmis." if res.complete else "Haku päättyi, tulokset eivät ole täydelliset."
        except InvalidChannelUrl as exc:
            self._fail(str(exc), "")
        except Exception as exc:
            err = classify_exception(exc)
            self._fail(err.user_message, err.detail)

    def _fail(self, message: str, detail: str) -> None:
        with self.lock:
            self.error = {"message": message, "detail": detail[:400]}
            self.state = "failed"
            self.status = "Haku epäonnistui."


class JobManager:
    def __init__(self, fetch: Callable[..., FetchResult] = fetch_channel) -> None:
        self._fetch = fetch
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._lock = threading.Lock()

    def start(self, url: str, options: FetchOptions) -> Job:
        with self._lock:
            if sum(j.state == "running" for j in self._jobs.values()) >= MAX_RUNNING:
                raise TooManyJobs()
            job = Job(url, options)
            self._jobs[job.id] = job
            while len(self._jobs) > MAX_JOBS:  # pudota vanhin valmis haku
                old = next((k for k, j in self._jobs.items() if j.state != "running"), None)
                if old is None:
                    break
                del self._jobs[old]
        threading.Thread(target=job.run, args=(self._fetch,), daemon=True).start()
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)
