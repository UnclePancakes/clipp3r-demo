"""Local CLIPP3R web application for generating short-form video clips."""

from __future__ import annotations

import ipaddress
import logging
import mimetypes
import os
import re
import shutil
import socket
import threading
import uuid
import zipfile
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

from .batch_export import apply_clip_headline, export_clips
from .metadata_suggestions import (
    generate_title_suggestions,
    validate_suggestion_output,
)
from .transcribe.languages import (
    FASTER_WHISPER_LANGUAGE_CODES,
    LANGUAGE_OPTIONS,
    LANGUAGE_NAMES,
)

LOGGER = logging.getLogger(__name__)
MAX_VIDEO_BYTES = 20 * 1024**3
MAX_CLIP_SELECTION = 500
MAX_CLIP_DURATION = 60
MIN_CLIP_DURATION = 15
DEFAULT_CLIPS_DIR = Path.home() / "Desktop" / "YouTube" / "CLIPS"
CREATOR_CONTEXT_FIELDS = ("audience", "topic", "goal", "tone")
VIDEO_EXTENSIONS = {
    ".avi",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".webm",
}
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.RLock()


def create_app(
    data_dir: str | Path | None = None,
    clips_dir: str | Path | None = None,
) -> Flask:
    mimetypes.add_type("font/ttf", ".ttf")
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config["MAX_CONTENT_LENGTH"] = MAX_VIDEO_BYTES
    app.config["CLIPP3R_DATA_DIR"] = Path(
        data_dir
        or os.environ.get(
            "CLIPP3R_DATA_DIR",
            Path.home() / "Videos" / "CLIPP3R",
        )
    ).expanduser().resolve()
    app.config["CLIPP3R_CLIPS_DIR"] = Path(
        clips_dir
        or os.environ.get("CLIPP3R_CLIPS_DIR", DEFAULT_CLIPS_DIR)
    ).expanduser().resolve()

    @app.errorhandler(413)
    def request_too_large(_error):
        return jsonify({
            "error": "This upload exceeds CLIPP3R's 20 GB upload limit."
        }), 413

    @app.get("/")
    def index():
        wallpaper_filename = next(
            (
                filename
                for filename in ("wallpaper.webm", "wallpaper.mp4")
                if (Path(app.static_folder) / filename).is_file()
            ),
            None,
        )
        wallpaper_poster = (
            "wallpaper-poster.jpg"
            if (Path(app.static_folder) / "wallpaper-poster.jpg").is_file()
            else None
        )
        return render_template(
            "index.html",
            language_options=LANGUAGE_OPTIONS,
            wallpaper_filename=wallpaper_filename,
            wallpaper_poster=wallpaper_poster,
        )

    @app.post("/api/jobs")
    def create_job():
        max_clips = _parse_max_clips(
            request.form.get("max_clips")
            if request.files
            else (request.get_json(silent=True) or {}).get("max_clips")
        )
        if max_clips is None:
            return jsonify({"error": "Choose a clip limit from All to 500."}), 400

        payload = request.form if request.files else (request.get_json(silent=True) or {})
        output_mode = _parse_output_mode(payload.get("output_mode", "tiktok"))
        if output_mode is None:
            return jsonify({
                "error": "Choose TikTok-style vertical or Original dimensions."
            }), 400
        caption_style = _parse_caption_style(
            payload.get("caption_style", "creator_pop")
        )
        if caption_style is None:
            return jsonify({"error": "Choose Creator pop or Classic captions."}), 400
        language, language_error = _parse_language(payload.get("language", "auto"))
        if language_error:
            return jsonify({"error": language_error}), 400
        try:
            creator_context = _parse_creator_context(
                payload.get("creator_context", payload)
            )
            streamer_tag = _parse_streamer_tag(payload.get("streamer_tag", ""))
            streamer_platform = _parse_streamer_platform(
                payload.get("streamer_platform", "")
            )
        except ValueError as error:
            return jsonify({"error": str(error)}), 400

        face_tracking = _parse_face_tracking(request)
        job_id = uuid.uuid4().hex
        job_dir = app.config["CLIPP3R_DATA_DIR"] / job_id
        job_dir.mkdir(parents=True, exist_ok=False)

        if request.files:
            uploaded = request.files.get("file")
            if uploaded is None or not uploaded.filename:
                shutil.rmtree(job_dir)
                return jsonify({"error": "Choose a video file to upload."}), 400

            safe_name = secure_filename(uploaded.filename)
            extension = Path(safe_name).suffix.lower()
            if extension not in VIDEO_EXTENSIONS:
                shutil.rmtree(job_dir)
                return jsonify({
                    "error": "Choose a supported video file (MP4, MOV, MKV, WebM, AVI, or MPEG)."
                }), 400
            source_path = job_dir / f"source{extension}"
            uploaded.save(source_path)
            source_name = safe_name
            source_type = "file"
            source_url = None
        else:
            payload = request.get_json(silent=True) or {}
            source_url = str(payload.get("url", "")).strip()
            try:
                _validate_source_url(source_url)
            except ValueError as error:
                shutil.rmtree(job_dir)
                return jsonify({"error": str(error)}), 400
            source_path = None
            source_name = "Video from URL"
            source_type = "url"

        job = {
            "id": job_id,
            "status": "queued",
            "stage": "queued",
            "progress": 0,
            "message": "Your clip job is queued.",
            "source_type": source_type,
            "source_name": source_name,
            "source_url": source_url,
            "source_path": str(source_path) if source_path else None,
            "job_dir": str(job_dir),
            "max_clips": max_clips,
            "face_tracking": face_tracking,
            "output_mode": output_mode,
            "caption_style": caption_style,
            "language": language,
            "creator_context": creator_context,
            "streamer_tag": streamer_tag,
            "streamer_platform": streamer_platform,
            "clips_output_dir": str(app.config["CLIPP3R_CLIPS_DIR"]),
            "clips": [],
            "error": None,
        }
        with JOBS_LOCK:
            JOBS[job_id] = job

        threading.Thread(
            target=_run_job,
            args=(job_id,),
            name=f"clipp3r-{job_id[:8]}",
            daemon=True,
        ).start()
        return jsonify({"job_id": job_id}), 202

    @app.get("/api/jobs/<job_id>")
    def job_status(job_id: str):
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            if job is None:
                return jsonify({"error": "Clip job not found."}), 404
            return jsonify(_public_job(job))

    @app.get("/api/jobs/<job_id>/source")
    def job_source(job_id: str):
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            source_path = (
                Path(job["source_path"]).resolve()
                if job and job.get("source_path")
                else None
            )
            job_dir = (
                Path(job["job_dir"]).resolve()
                if job and job.get("job_dir")
                else None
            )
            if (
                source_path is None
                or job_dir is None
                or source_path.parent != job_dir
                or not source_path.is_file()
            ):
                return jsonify({"error": "The source video is no longer available."}), 404
        return send_file(source_path, conditional=True)

    @app.post("/api/jobs/<job_id>/render")
    def render_selected_clips(job_id: str):
        payload = request.get_json(silent=True)
        clip_names = payload.get("clip_names") if isinstance(payload, dict) else None
        if (
            not isinstance(clip_names, list)
            or not clip_names
            or len(clip_names) > MAX_CLIP_SELECTION
            or any(not isinstance(name, str) for name in clip_names)
            or len(set(clip_names)) != len(clip_names)
        ):
            return jsonify({
                "error": "Select between 1 and 500 clips to render."
            }), 400

        with JOBS_LOCK:
            job = JOBS.get(job_id)
            if job is None or job["status"] != "awaiting_selection":
                return jsonify({
                    "error": "This job is no longer waiting for clip selection."
                }), 409
            candidate_indexes = {
                clip["name"]: index
                for index, clip in enumerate(job["clips"])
            }
            if any(name not in candidate_indexes for name in clip_names):
                return jsonify({
                    "error": "One or more selected clips are unavailable."
                }), 400

            selected_indexes = sorted(
                (candidate_indexes[name] for name in clip_names),
                key=lambda index: job["clips"][index]["start"],
            )
            selected_clips = [job["clips"][index] for index in selected_indexes]
            selected_segments = [
                job["_segments"][index] for index in selected_indexes
            ]
            job.update(
                status="processing",
                stage="rendering",
                progress=25,
                message=f"Rendering {len(selected_clips)} selected clips…",
                clips=selected_clips,
                clip_total=len(selected_clips),
                clip_done=0,
                _segments=selected_segments,
            )

        threading.Thread(
            target=_render_job,
            args=(job_id,),
            name=f"clipp3r-render-{job_id[:8]}",
            daemon=True,
        ).start()
        return jsonify({"status": "rendering", "clip_total": len(selected_clips)}), 202

    @app.post("/api/jobs/<job_id>/clips/<clip_name>/headline")
    def update_clip_headline(job_id: str, clip_name: str):
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return jsonify({"error": "Provide a headline as text."}), 400
        headline = payload.get("headline")
        if not isinstance(headline, str) or len(headline) > 100:
            return jsonify({
                "error": "A headline must be text of 100 characters or fewer."
            }), 400
        headline = " ".join(headline.split()).strip()

        with JOBS_LOCK:
            job = JOBS.get(job_id)
            clip = next(
                (item for item in job["clips"] if item["name"] == clip_name),
                None,
            ) if job and job["status"] == "ready" else None
            if clip is None:
                return jsonify({"error": "Rendered clip was not found."}), 404
            clip_path = Path(clip["path"]).resolve()
            output_dir = Path(job["clips_output_dir"]).resolve()
            if not clip_path.is_file() or clip_path.parent != output_dir:
                return jsonify({"error": "The rendered clip is no longer available."}), 404

            saved_source = clip.get("headline_source_path")
            source_path = Path(saved_source).resolve() if saved_source else clip_path
            if saved_source and (
                not source_path.is_file()
                or source_path.parent != (Path(job["job_dir"]) / "headline_sources").resolve()
            ):
                return jsonify({"error": "The original rendered clip is unavailable."}), 500

            working_path = clip_path.with_name(
                f".{clip_path.stem}.{uuid.uuid4().hex}.mp4"
            )
            created_source = False
            if headline and not saved_source:
                source_path = (
                    Path(job["job_dir"])
                    / "headline_sources"
                    / f"{uuid.uuid4().hex}.mp4"
                )
                source_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(clip_path, source_path)
                except OSError:
                    LOGGER.exception("Could not preserve source clip for headline update")
                    return jsonify({"error": "Could not prepare the clip for editing."}), 500
                created_source = True

            try:
                shutil.copy2(source_path, working_path)
                if headline:
                    apply_clip_headline(
                        working_path,
                        headline,
                        caption_style=job["caption_style"],
                    )
                working_path.replace(clip_path)
            except (OSError, RuntimeError, ValueError):
                working_path.unlink(missing_ok=True)
                if created_source:
                    source_path.unlink(missing_ok=True)
                LOGGER.exception("Could not update headline for clip %s", clip_name)
                return jsonify({"error": "Could not update this clip's headline."}), 500
            finally:
                working_path.unlink(missing_ok=True)

            clip["hook"] = headline
            if headline:
                clip["headline_source_path"] = str(source_path)
            else:
                clip.pop("headline_source_path", None)
                if saved_source:
                    source_path.unlink(missing_ok=True)
            try:
                archive = _write_job_archive(job)
            except OSError:
                LOGGER.exception("Could not refresh clip archive for job %s", job_id)
                return jsonify({
                    "error": "The headline was updated, but the ZIP archive could not be refreshed."
                }), 500
            job["archive"] = str(archive)
            return jsonify({
                "name": clip["name"],
                "headline": headline,
                "archive_url": f"/api/jobs/{job_id}/download",
            })

    @app.post("/api/jobs/<job_id>/suggestions")
    def suggest_metadata(job_id: str):
        payload = request.get_json(silent=True) or {}
        clip_names = payload.get("clip_names")
        contexts = payload.get("contexts", {})
        if (
            not isinstance(clip_names, list)
            or not clip_names
            or len(clip_names) > MAX_CLIP_SELECTION
            or any(not isinstance(name, str) for name in clip_names)
            or len(set(clip_names)) != len(clip_names)
            or not isinstance(contexts, dict)
        ):
            return jsonify({"error": "Select one or more clips to suggest metadata."}), 400

        with JOBS_LOCK:
            job = JOBS.get(job_id)
            if job is None or job["status"] != "ready":
                return jsonify({"error": "The completed clip job was not found."}), 404
            clips_by_name = {clip["name"]: clip for clip in job["clips"]}
            selected_clips = [clips_by_name.get(name) for name in clip_names]
            if any(clip is None for clip in selected_clips):
                return jsonify({"error": "One or more selected clips were not found."}), 404

        suggestions = {}
        clip_contexts = {}
        try:
            for clip in selected_clips:
                raw_context = contexts.get(clip["name"], job.get("creator_context", {}))
                context = _parse_creator_context(raw_context)
                result = generate_title_suggestions(clip["text"], context)
                validate_suggestion_output(result)
                suggestions[clip["name"]] = result
                clip_contexts[clip["name"]] = context
        except (TypeError, ValueError) as error:
            return jsonify({"error": str(error)}), 400

        with JOBS_LOCK:
            for clip_name, result in suggestions.items():
                clips_by_name[clip_name]["suggestions"] = result
                clips_by_name[clip_name]["creator_context"] = clip_contexts[clip_name]
                clips_by_name[clip_name]["metadata_state"] = "suggested"
        return jsonify({"suggestions": suggestions})

    @app.post("/api/jobs/<job_id>/clips/<clip_name>/title")
    def select_clip_title(job_id: str, clip_name: str):
        payload = request.get_json(silent=True) or {}
        title = payload.get("title")
        if not isinstance(title, str) or not title.strip() or len(title.strip()) > 100:
            return jsonify({"error": "Enter a title between 1 and 100 characters."}), 400
        try:
            clip_context = _parse_optional_context(payload.get("context", {}))
        except ValueError as error:
            return jsonify({"error": str(error)}), 400

        with JOBS_LOCK:
            job = JOBS.get(job_id)
            clip = next(
                (item for item in job["clips"] if item["name"] == clip_name),
                None,
            ) if job and job["status"] == "ready" else None
            if clip is None:
                return jsonify({"error": "Clip was not found or is not ready."}), 404
            clip_path = Path(clip["path"]).resolve()
            output_dir = Path(job["clips_output_dir"]).resolve()
            if not clip_path.is_file() or clip_path.parent != output_dir:
                return jsonify({"error": "The clip file is no longer available."}), 404
            try:
                destination = _unique_title_path(
                    output_dir,
                    title,
                    exclude=clip_path,
                )
            except ValueError as error:
                return jsonify({"error": str(error)}), 400

            if clip_path != destination:
                clip_path.replace(destination)
            clip["path"] = str(destination)
            clip["name"] = destination.name
            clip["title"] = title.strip()
            clip["creator_context"] = clip_context
            clip["metadata_state"] = "selected"

            try:
                archive = _write_job_archive(job)
            except OSError:
                LOGGER.exception("Could not refresh clip archive for job %s", job_id)
                return jsonify({
                    "error": "The clip title was saved, but the ZIP archive could not be updated."
                }), 500
            job["archive"] = str(archive)
            response = {
                "name": clip["name"],
                "title": clip["title"],
                "path": str(output_dir),
                "download_url": (
                    f"/api/jobs/{job_id}/clips/{clip['name']}?download=1"
                ),
            }
        return jsonify(response)

    @app.post("/api/jobs/<job_id>/clips/<clip_name>/skip-suggestions")
    def skip_clip_suggestions(job_id: str, clip_name: str):
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            clip = next(
                (item for item in job["clips"] if item["name"] == clip_name),
                None,
            ) if job and job["status"] == "ready" else None
            if clip is None:
                return jsonify({"error": "Clip was not found or is not ready."}), 404
            clip["metadata_state"] = "skipped"
            clip.pop("suggestions", None)
        return jsonify({"status": "skipped"})

    @app.get("/api/jobs/<job_id>/clips/<clip_name>")
    def get_clip(job_id: str, clip_name: str):
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            clip = next(
                (
                    item
                    for item in job["clips"]
                    if item["name"] == clip_name
                ),
                None,
            ) if job else None
        if clip is None or job["status"] != "ready":
            return jsonify({"error": "Clip is not ready."}), 404
        return send_file(
            clip["path"],
            mimetype="video/mp4",
            as_attachment=request.args.get("download") == "1",
            download_name=clip["name"],
            conditional=True,
        )

    @app.get("/api/jobs/<job_id>/download")
    def download_clips(job_id: str):
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            archive = job.get("archive") if job else None
            status = job.get("status") if job else None
        if status != "ready" or not archive or not Path(archive).is_file():
            return jsonify({"error": "Clip archive is not ready."}), 404
        return send_file(
            archive,
            mimetype="application/zip",
            as_attachment=True,
            download_name="CLIPP3R-clips.zip",
        )

    return app


def _parse_max_clips(value) -> int | None:
    if value is None:
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if not 0 <= parsed <= MAX_CLIP_SELECTION:
        return None
    return parsed


def _parse_output_mode(value: str) -> str | None:
    if isinstance(value, str) and value in {"tiktok", "original"}:
        return value
    return None


def _parse_caption_style(value: str) -> str | None:
    if isinstance(value, str) and value in {"creator_pop", "classic"}:
        return value
    return None


def _parse_language(value: str | None) -> tuple[str | None, str | None]:
    if value is not None and not isinstance(value, str):
        return None, "Choose a language from the available options."
    language = (value or "auto").strip().lower()
    if language == "auto":
        return None, None
    if language in FASTER_WHISPER_LANGUAGE_CODES:
        return language, None
    name = LANGUAGE_NAMES.get(language)
    if name:
        return None, (
            f"{name} is not supported by the installed Faster-Whisper model. "
            "Choose Auto-detect or Afrikaans where supported; CLIPP3R does not "
            "claim reliable transcription for this language."
        )
    return None, (
        "That language is not supported by the installed Faster-Whisper model. "
        "Choose Auto-detect or one of the enabled language options."
    )


def _parse_creator_context(value) -> dict[str, str]:
    if not hasattr(value, "get"):
        raise ValueError("Creator context must be an object of text fields.")
    context = {}
    for field in CREATOR_CONTEXT_FIELDS:
        item = value.get(field, "")
        if item == "" and hasattr(value, "get"):
            item = value.get(f"context_{field}", "")
        if not isinstance(item, str):
            raise ValueError(f"The {field} context must be text.")
        if len(item) > 300:
            raise ValueError(f"The {field} context must be 300 characters or fewer.")
        context[field] = " ".join(item.split()).strip()
    return context


def _parse_streamer_tag(value) -> str:
    if not isinstance(value, str):
        raise ValueError("The streamer tag must be text.")
    if len(value) > 60:
        raise ValueError("The streamer tag must be 60 characters or fewer.")
    return " ".join(value.split()).strip()


def _parse_streamer_platform(value) -> str:
    if not isinstance(value, str) or value not in {"", "twitch", "kick"}:
        raise ValueError("Choose no platform logo, Twitch, or Kick.")
    return value


def _parse_optional_context(value) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("Clip-specific context must be an object.")
    return _parse_creator_context(value)


def _safe_title_stem(title: str) -> str:
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", title)
    stem = " ".join(stem.split()).strip(" .")
    if not stem:
        raise ValueError("The selected title has no characters valid in a filename.")
    if stem.upper() in {
        "CON", "PRN", "AUX", "NUL",
        *(f"COM{number}" for number in range(1, 10)),
        *(f"LPT{number}" for number in range(1, 10)),
    }:
        stem = f"_{stem}"
    return stem[:150].rstrip(" .")


def _unique_title_path(
    output_dir: Path,
    title: str,
    exclude: Path | None = None,
) -> Path:
    stem = _safe_title_stem(title)
    candidate = output_dir / f"{stem}.mp4"
    suffix = 2
    while candidate.exists() and candidate.resolve() != (exclude.resolve() if exclude else None):
        candidate = output_dir / f"{stem} ({suffix}).mp4"
        suffix += 1
    return candidate


def _move_clip_to_output(path: Path, output_dir: Path) -> Path:
    with JOBS_LOCK:
        destination = _unique_title_path(output_dir, path.stem)
        path.replace(destination)
        return destination


def _write_job_archive(job: dict) -> Path:
    output_dir = Path(job["clips_output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / f"CLIPP3R-{job['id']}.zip"
    temporary_archive = output_dir / f".CLIPP3R-{job['id']}.tmp.zip"
    with zipfile.ZipFile(
        temporary_archive,
        "w",
        compression=zipfile.ZIP_STORED,
    ) as bundle:
        for clip in job["clips"]:
            path = Path(clip["path"])
            if path.is_file():
                bundle.write(path, arcname=path.name)
    temporary_archive.replace(archive)
    return archive


def _parse_face_tracking(request_obj) -> bool:
    value = (
        request_obj.form.get("face_tracking", "true")
        if request_obj.files
        else (request_obj.get_json(silent=True) or {}).get("face_tracking", True)
    )
    return value not in (False, 0, "0", "false", "off", "no")


def _validate_source_url(url: str) -> None:
    parsed = urlparse(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Enter a complete public HTTP or HTTPS video URL.")

    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith(".localhost") or hostname.endswith(".local"):
        raise ValueError("CLIPP3R can only fetch public video URLs.")

    try:
        addresses = {ipaddress.ip_address(hostname)}
    except ValueError:
        try:
            addresses = {
                ipaddress.ip_address(result[4][0])
                for result in socket.getaddrinfo(hostname, parsed.port or 443)
            }
        except OSError as error:
            raise ValueError("The video URL host could not be resolved.") from error

    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("CLIPP3R can only fetch public video URLs.")


def _run_job(job_id: str) -> None:
    job = _get_job(job_id)
    if job is None:
        return
    job_dir = Path(job["job_dir"])
    try:
        source_path = Path(job["source_path"]) if job["source_path"] else None
        if source_path is None:
            source_path = _download_source(job)
        _update_job(
            job_id,
            status="processing",
            stage="transcribing",
            progress=12,
            message=(
                "Upload complete. Transcribing the full source to find candidate moments; "
                "long recordings can take a while."
            ),
        )

        from .transcribe.transcriber import WhisperTranscriber
        from .txtslice.segment_picker import ClipFinder

        def transcription_progress(fraction: float) -> None:
            video_percent = round(fraction * 100)
            progress = 12 + round(10 * fraction)
            _update_job(
                job_id,
                progress=progress,
                message=f"Transcribing the full video… {video_percent}% scanned.",
            )

        transcriber = WhisperTranscriber(
            model_size="small" if job["language"] == "af" else None
        )
        transcription = transcriber.transcribe(
            str(source_path),
            lang=job["language"],
            on_progress=transcription_progress,
        )
        _update_job(
            job_id,
            stage="selecting_clips",
            progress=23,
            message="Scoring topic boundaries, event language, and transcript-aligned moments…",
        )
        candidates = ClipFinder(
            min_clip_duration=MIN_CLIP_DURATION,
            max_clip_duration=MAX_CLIP_DURATION,
        ).find_clips(transcription)
        candidates = [
            segment
            for segment in candidates
            if MIN_CLIP_DURATION
            <= segment.finish_sec - segment.begin_sec
            <= MAX_CLIP_DURATION
        ]
        if not candidates:
            raise RuntimeError(
                "No transcript-backed moments between 15 and 60 seconds were found. "
                "Try a longer source or review the source audio quality."
            )

        if job["max_clips"]:
            candidates = candidates[:job["max_clips"]]
        candidates.sort(key=lambda segment: segment.begin_sec)
        clips = []
        for index, segment in enumerate(candidates, start=1):
            snippet = transcription.text[
                segment.text_start_idx:segment.text_end_idx
            ].strip()
            clips.append({
                "name": f"candidate_{index:03d}",
                "start": round(segment.begin_sec, 2),
                "end": round(segment.finish_sec, 2),
                "duration": round(segment.finish_sec - segment.begin_sec, 1),
                "score": round(segment.quality_score),
                "text": snippet,
                "hook": "",
            })

        _update_job(
            job_id,
            status="awaiting_selection",
            stage="select_clips",
            progress=25,
            message=(
                f"Found {len(clips)} candidate moments. Review the timeline and "
                "choose which clips to render."
            ),
            clips=clips,
            clip_total=0,
            clip_done=0,
            _segments=candidates,
            _words=transcription.words,
            source_duration=max(
                transcription.end_time,
                max(segment.finish_sec for segment in candidates),
            ),
        )
    except Exception as error:
        LOGGER.exception("CLIPP3R job %s failed", job_id)
        _update_job(
            job_id,
            status="error",
            stage="error",
            message="This clip job could not be completed.",
            error=str(error),
        )


def _render_job(job_id: str) -> None:
    job = _get_job(job_id)
    if job is None:
        return
    try:
        candidates = job["_segments"]
        hooks = [clip["hook"] for clip in job["clips"]]
        source_path = Path(job["source_path"])
        job_dir = Path(job["job_dir"])

        def clip_rendered(done: int, clip_total: int, _path: Path) -> None:
            progress = 25 + round(74 * done / clip_total)
            _update_job(
                job_id,
                progress=progress,
                clip_done=done,
                message=f"Rendering clip {done} of {clip_total}…",
            )

        paths = export_clips(
            video_path=source_path,
            segments=candidates,
            output_dir=job_dir / "clips",
            words=job["_words"],
            face_tracking=job["face_tracking"] and job["output_mode"] == "tiktok",
            on_clip_complete=clip_rendered,
            output_mode=job["output_mode"],
            streamer_tag=job["streamer_tag"],
            streamer_platform=job["streamer_platform"],
            hooks=hooks,
            caption_style=job["caption_style"],
        )
        clips_output_dir = Path(job["clips_output_dir"])
        clips_output_dir.mkdir(parents=True, exist_ok=True)
        published_paths = [
            _move_clip_to_output(path, clips_output_dir)
            for path in paths
        ]
        clips = []
        for candidate, path in zip(job["clips"], published_paths):
            clip = dict(candidate)
            clip.update({
                "name": path.name,
                "path": str(path),
                "metadata_state": "not_requested",
            })
            clips.append(clip)

        job["clips"] = clips
        archive = _write_job_archive(job)
        with JOBS_LOCK:
            job.pop("_segments", None)
            job.pop("_words", None)
        _update_job(
            job_id,
            status="ready",
            stage="ready",
            progress=100,
            message=f"Your {len(clips)} clips are ready.",
            clips=clips,
            archive=str(archive),
            clips_output_dir=str(clips_output_dir),
            output_dir=str(clips_output_dir),
        )
    except Exception as error:
        LOGGER.exception("CLIPP3R render job %s failed", job_id)
        with JOBS_LOCK:
            job.pop("_segments", None)
            job.pop("_words", None)
        _update_job(
            job_id,
            status="error",
            stage="error",
            message="This clip job could not be completed.",
            error=str(error),
        )


def _download_source(job: dict) -> Path:
    try:
        import yt_dlp
    except ImportError as error:
        raise RuntimeError(
            'URL importing requires yt-dlp. Install it with "py -m pip install -e .".'
        ) from error

    job_id = job["id"]
    job_dir = Path(job["job_dir"])
    _update_job(
        job_id,
        status="downloading",
        stage="downloading",
        progress=2,
        message="Fetching the source video…",
    )

    def report_download(event: dict) -> None:
        if event.get("status") == "downloading":
            downloaded = event.get("downloaded_bytes", 0)
            total = event.get("total_bytes") or event.get("total_bytes_estimate")
            progress = min(7, 2 + round(5 * downloaded / total)) if total else 3
            _update_job(
                job_id,
                progress=progress,
                message="Downloading source video…",
            )

    options = {
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "outtmpl": str(job_dir / "source.%(ext)s"),
        "noplaylist": True,
        "no_warnings": True,
        "quiet": True,
        "progress_hooks": [report_download],
        "restrictfilenames": True,
        "retries": 3,
        "socket_timeout": 30,
    }
    with yt_dlp.YoutubeDL(options) as downloader:
        info = downloader.extract_info(job["source_url"], download=True)
        title = info.get("title") or job["source_url"]

    candidates = [
        path
        for path in job_dir.glob("source.*")
        if path.is_file()
        and path.suffix.lower() in VIDEO_EXTENSIONS
        and not path.name.endswith((".part", ".ytdl"))
    ]
    if not candidates:
        raise RuntimeError("The source download completed without a usable video file.")
    source_path = max(candidates, key=lambda path: path.stat().st_size)
    if source_path.stat().st_size == 0:
        raise RuntimeError("The source video download is empty.")
    _update_job(job_id, source_name=title, source_path=str(source_path))
    return source_path


def _get_job(job_id: str) -> dict | None:
    with JOBS_LOCK:
        return JOBS.get(job_id)


def _update_job(job_id: str, **updates) -> None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is not None:
            job.update(updates)


def _public_job(job: dict) -> dict:
    public = {
        key: value
        for key, value in job.items()
        if key not in {"source_path", "job_dir", "source_url", "archive"}
        and not key.startswith("_")
    }
    public["clips"] = [
        {
            key: value
            for key, value in clip.items()
            if key not in {"path", "headline_source_path"}
        }
        for clip in job["clips"]
    ]
    public["download_url"] = (
        f"/api/jobs/{job['id']}/download"
        if job["status"] == "ready"
        else None
    )
    return public


app = create_app()


def main() -> None:
    host = os.environ.get("CLIPP3R_HOST", "127.0.0.1")
    port = int(os.environ.get("CLIPP3R_PORT", "8787"))
    print(f"CLIPP3R is ready at http://{host}:{port}")
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
