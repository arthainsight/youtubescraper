"""Paikallinen web-palvelin: selainkäyttöliittymä + JSON-rajapinta."""
from __future__ import annotations

import argparse
import threading
import webbrowser
from collections.abc import Callable
from urllib.parse import quote

from flask import Flask, Response, jsonify, request

from ..errors import InvalidChannelUrl
from ..exporters import csv_bytes, render_txt
from ..fetcher import fetch_channel
from ..models import FetchOptions, Video, VideoKind
from ..results import is_valid_video_id
from ..urls import normalize_channel_url
from .jobs import JobManager, TooManyJobs

MAX_EXPORT_ROWS = 200_000


def _parse_kinds(raw) -> tuple[VideoKind, ...]:
    kinds = []
    for item in raw if isinstance(raw, list) else []:
        try:
            k = VideoKind(item)
        except ValueError:
            continue
        if k not in kinds:
            kinds.append(k)
    return tuple(kinds)


def _video_from_payload(d: object) -> Video | None:
    """Rakentaa videon asiakkaan datasta; URL johdetaan aina ID:stä (ei luoteta annettuun)."""
    if not isinstance(d, dict) or not is_valid_video_id(d.get("id")):
        return None
    try:
        kind = VideoKind(d.get("kind", "video"))
    except ValueError:
        kind = VideoKind.VIDEO
    dur = d.get("duration")
    return Video(video_id=d["id"], title=str(d.get("title") or "")[:500],
                 upload_date=str(d.get("date") or "")[:10],
                 duration=dur if isinstance(dur, int) and not isinstance(dur, bool) else None,
                 channel=str(d.get("channel") or "")[:200], kind=kind)


def create_app(fetch: Callable = fetch_channel) -> Flask:
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024
    app.json.ensure_ascii = False
    jobs = JobManager(fetch)

    @app.after_request
    def headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; "
            "frame-ancestors 'none'")
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    @app.post("/api/jobs")
    def start_job():
        body = request.get_json(silent=True) or {}
        url = str(body.get("url") or "")
        try:
            normalize_channel_url(url)
        except InvalidChannelUrl as exc:
            return jsonify(error={"message": str(exc), "detail": ""}), 400
        kinds = _parse_kinds(body.get("kinds"))
        if not kinds:
            return jsonify(error={"message": "Valitse vähintään yksi sisältötyyppi.", "detail": ""}), 400
        limit = body.get("limit", 0)
        limit = limit if isinstance(limit, int) and not isinstance(limit, bool) and 0 <= limit <= 100000 else 0
        opts = FetchOptions(kinds=kinds, fetch_exact_dates=bool(body.get("exact_dates")), limit=limit)
        try:
            job = jobs.start(url, opts)
        except TooManyJobs:
            return jsonify(error={"message": "Liian monta hakua käynnissä. Odota hetki.", "detail": ""}), 429
        return jsonify(id=job.id), 202

    def _job_or_404(job_id: str):
        job = jobs.get(job_id)
        return job

    @app.get("/api/jobs/<job_id>")
    def poll(job_id: str):
        job = _job_or_404(job_id)
        if job is None:
            return jsonify(error={"message": "Hakua ei löytynyt (palvelin on voinut käynnistyä uudelleen).",
                                  "detail": ""}), 404
        after = request.args.get("after", 0, type=int) or 0
        uafter = request.args.get("uafter", 0, type=int) or 0
        return jsonify(job.snapshot(max(after, 0), max(uafter, 0)))

    @app.post("/api/jobs/<job_id>/cancel")
    def cancel(job_id: str):
        job = _job_or_404(job_id)
        if job is None:
            return jsonify(error={"message": "Hakua ei löytynyt.", "detail": ""}), 404
        job.cancel.set()
        return jsonify(ok=True)

    @app.post("/api/export/<fmt>")
    def export(fmt: str):
        if fmt not in ("txt", "csv"):
            return jsonify(error={"message": "Tuntematon muoto.", "detail": ""}), 404
        body = request.get_json(silent=True) or {}
        raw = body.get("videos")
        if not isinstance(raw, list) or len(raw) > MAX_EXPORT_ROWS:
            return jsonify(error={"message": "Virheellinen vientipyyntö.", "detail": ""}), 400
        videos = [v for v in (_video_from_payload(d) for d in raw) if v]
        links_only = bool(body.get("links_only"))
        if fmt == "txt":
            data = render_txt(videos, links_only).encode("utf-8")
            mime = "text/plain; charset=utf-8"
        else:
            data = csv_bytes(videos, links_only)
            mime = "text/csv; charset=utf-8"
        name = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(body.get("name") or "")
                       ).strip("_") or "youtube_videot"
        resp = Response(data, mimetype=mime)
        resp.headers["Content-Disposition"] = (
            f"attachment; filename=\"youtube_videot.{fmt}\"; filename*=UTF-8''{quote(name)}.{fmt}")
        return resp

    return app


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="YouTube-linkkien kerääjä (selainversio)")
    ap.add_argument("--host", default="127.0.0.1",
                    help="oletus 127.0.0.1 (vain tämä kone). 0.0.0.0 avaa palvelun koko "
                         "lähiverkkoon – käytä vain luotetussa verkossa, sovelluksessa ei ole kirjautumista")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true", help="älä avaa selainta automaattisesti")
    args = ap.parse_args(argv)

    app = create_app()
    url = f"http://{'127.0.0.1' if args.host in ('0.0.0.0', '::') else args.host}:{args.port}/"
    if args.host in ("0.0.0.0", "::"):
        print("VAROITUS: palvelu on avoinna lähiverkossa ilman kirjautumista.")
    print(f"Avaa selaimessa: {url}   (lopeta: Ctrl+C)")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host=args.host, port=args.port, threaded=True)
    return 0
