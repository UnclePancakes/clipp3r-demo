from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_clips_maker.transcribe import transcriber as transcriber_module
from ai_clips_maker.webapp import (
    JOBS,
    _parse_language,
    _parse_max_clips,
    _parse_output_mode,
    _parse_caption_style,
    _parse_streamer_platform,
    _run_job,
    _update_job,
    _validate_source_url,
    create_app,
)
from ai_clips_maker.txtslice.matcher import MediaSegment


@pytest.fixture
def client(tmp_path, monkeypatch):
    JOBS.clear()
    app = create_app(
        tmp_path / "clipp3r",
        clips_dir=tmp_path / "final-clips",
    )
    app.config.update(TESTING=True)
    monkeypatch.setattr(
        "ai_clips_maker.webapp.threading.Thread",
        lambda **_kwargs: SimpleNamespace(start=lambda: None),
    )
    return app.test_client()


def test_homepage_serves_clipp3r_workspace(client, monkeypatch):
    monkeypatch.setattr(Path, "is_file", lambda _path: False)
    response = client.get("/")

    assert response.status_code == 200
    assert b"CLIPP3R" in response.data
    assert b"LOCAL FILE" in response.data
    assert b"VIDEO URL" in response.data
    assert b"Creator pop" in response.data
    assert b"STREAMER PLATFORM LOGO" in response.data
    assert b"No platform logo" in response.data
    assert b"Choose moments on the timeline" in response.data
    assert b'id="candidate-search"' in response.data
    assert b'id="candidate-sort"' in response.data
    assert b'id="select-top-10"' in response.data
    assert b'id="select-top-25"' in response.data
    assert b'<details class="creator-brief">' in response.data
    assert b'class="ambient-wallpaper"' not in response.data
    assert b'class="ambient-wallpaper-poster"' not in response.data
    assert b"Classic" in response.data
    assert b"Add or edit headlines" in response.data
    assert response.data.index(b'id="clip-grid"') < response.data.index(
        b'id="suggest-selected"'
    )


def test_homepage_serves_the_locally_bundled_readable_font(client):
    response = client.get("/static/Rubik-Variable.ttf")

    assert response.status_code == 200
    assert response.mimetype == "font/ttf"


@pytest.mark.parametrize("extension", ["webm", "mp4"])
def test_homepage_uses_optional_browser_ready_wallpaper(client, monkeypatch, extension):
    monkeypatch.setattr(Path, "is_file", lambda path: path.name == f"wallpaper.{extension}")

    response = client.get("/")

    assert response.status_code == 200
    assert b'class="ambient-wallpaper"' in response.data
    assert f"/static/wallpaper.{extension}".encode() in response.data


def test_homepage_uses_a_static_wallpaper_for_reduced_motion(client, monkeypatch):
    monkeypatch.setattr(
        Path,
        "is_file",
        lambda path: path.name in {"wallpaper.mp4", "wallpaper-poster.jpg"},
    )

    response = client.get("/")

    assert response.status_code == 200
    assert b'class="ambient-wallpaper"' in response.data
    assert b'class="ambient-wallpaper-poster"' in response.data
    assert b"/static/wallpaper-poster.jpg" in response.data


@pytest.mark.parametrize(
    "value, expected",
    [(None, 0), ("0", 0), ("20", 20), ("500", 500), ("-1", None), ("501", None), ("all", None)],
)
def test_clip_limit_validation(value, expected):
    assert _parse_max_clips(value) == expected


def test_transcription_and_output_choices_validate_supported_values():
    assert _parse_language("auto") == (None, None)
    assert _parse_language("af") == ("af", None)
    language, error = _parse_language("zu")
    assert language is None
    assert "isiZulu" in error
    assert _parse_output_mode("tiktok") == "tiktok"
    assert _parse_output_mode("original") == "original"
    assert _parse_output_mode("stretch") is None
    assert _parse_caption_style("creator_pop") == "creator_pop"
    assert _parse_caption_style("classic") == "classic"
    assert _parse_caption_style("unknown") is None
    assert _parse_streamer_platform("") == ""
    assert _parse_streamer_platform("twitch") == "twitch"
    assert _parse_streamer_platform("kick") == "kick"
    with pytest.raises(ValueError, match="platform"):
        _parse_streamer_platform("youtube")


def test_url_validation_rejects_private_and_non_http_destinations():
    for url in (
        "",
        "file:///private/video.mp4",
        "http://127.0.0.1/video",
        "http://localhost/video",
        "https://user:password@example.com/video",
    ):
        with pytest.raises(ValueError):
            _validate_source_url(url)


def test_url_submission_rejects_private_hosts(client):
    response = client.post(
        "/api/jobs",
        json={"url": "http://127.0.0.1/video.mp4"},
    )

    assert response.status_code == 400
    assert "public" in response.json["error"].lower()


def test_local_video_upload_creates_a_queued_job(client):
    response = client.post(
        "/api/jobs",
        data={
            "file": (BytesIO(b"test video bytes"), "my source.mp4"),
            "max_clips": "0",
            "face_tracking": "true",
            "output_mode": "original",
            "caption_style": "classic",
            "language": "af",
            "streamer_tag": "  SONICINSIDE  ",
            "streamer_platform": "twitch",
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 202
    job_id = response.json["job_id"]
    status = client.get(f"/api/jobs/{job_id}")
    assert status.json["status"] == "queued"
    assert status.json["max_clips"] == 0
    assert status.json["face_tracking"] is True
    assert status.json["output_mode"] == "original"
    assert JOBS[job_id]["caption_style"] == "classic"
    assert status.json["language"] == "af"
    assert status.json["source_name"] == "my_source.mp4"
    data_dir = client.application.config["CLIPP3R_DATA_DIR"]
    assert (data_dir / job_id / "source.mp4").read_bytes() == b"test video bytes"
    assert JOBS[job_id]["streamer_tag"] == "SONICINSIDE"
    assert JOBS[job_id]["streamer_platform"] == "twitch"


def test_source_video_can_be_previewed_during_candidate_review(client):
    response = client.post(
        "/api/jobs",
        data={
            "file": (BytesIO(b"source video bytes"), "source.mp4"),
            "max_clips": "0",
        },
        content_type="multipart/form-data",
    )
    job_id = response.json["job_id"]

    preview = client.get(f"/api/jobs/{job_id}/source")

    assert preview.status_code == 200
    assert preview.data == b"source video bytes"


def test_render_endpoint_uses_only_selected_candidate_clips(
    client,
    monkeypatch,
    tmp_path,
):
    job_id = "selected-candidates"
    job_dir = tmp_path / "clipp3r" / job_id
    job_dir.mkdir(parents=True)
    segments = [
        MediaSegment(index * 30, index * 30 + 25, 0, 20, quality_score=80)
        for index in range(3)
    ]
    clips = [
        {
            "name": f"candidate_{index + 1:03d}",
            "start": segment.begin_sec,
            "end": segment.finish_sec,
            "duration": segment.finish_sec - segment.begin_sec,
            "score": segment.quality_score,
            "text": "A candidate moment.",
            "hook": "",
        }
        for index, segment in enumerate(segments)
    ]
    JOBS[job_id] = {
        "id": job_id,
        "status": "awaiting_selection",
        "clips": clips,
        "_segments": segments,
        "job_dir": str(job_dir),
    }
    rendered = []

    class ImmediateThread:
        def __init__(self, target, args, **_kwargs):
            self.target = target
            self.args = args

        def start(self):
            self.target(*self.args)

    monkeypatch.setattr(
        "ai_clips_maker.webapp.threading.Thread",
        ImmediateThread,
    )
    monkeypatch.setattr(
        "ai_clips_maker.webapp._render_job",
        lambda _job_id: rendered.append(JOBS[job_id]["clips"]),
    )

    response = client.post(
        f"/api/jobs/{job_id}/render",
        json={"clip_names": ["candidate_003", "candidate_001"]},
    )

    assert response.status_code == 202
    assert response.json["clip_total"] == 2
    assert [clip["name"] for clip in rendered[0]] == [
        "candidate_001",
        "candidate_003",
    ]
    assert [segment.begin_sec for segment in JOBS[job_id]["_segments"]] == [0, 60]
    assert JOBS[job_id]["status"] == "processing"


def test_render_endpoint_rejects_empty_or_unknown_selections(client):
    job_id = "invalid-selection"
    JOBS[job_id] = {
        "id": job_id,
        "status": "awaiting_selection",
        "clips": [],
        "_segments": [],
    }

    empty = client.post(
        f"/api/jobs/{job_id}/render",
        json={"clip_names": []},
    )
    unknown = client.post(
        f"/api/jobs/{job_id}/render",
        json={"clip_names": ["missing"]},
    )

    assert empty.status_code == 400
    assert unknown.status_code == 400


def test_multipart_upload_accepts_source_creator_context(client):
    response = client.post(
        "/api/jobs",
        data={
            "file": (BytesIO(b"test video bytes"), "context source.mp4"),
            "max_clips": "0",
            "context_audience": "Local history fans",
            "context_topic": "Community archives",
            "context_goal": "Inform",
            "context_tone": "Warm",
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 202
    assert JOBS[response.json["job_id"]]["creator_context"] == {
        "audience": "Local history fans",
        "topic": "Community archives",
        "goal": "Inform",
        "tone": "Warm",
    }


@pytest.mark.parametrize(
    "streamer_tag, expected_error",
    [
        (17, "must be text"),
        ("x" * 61, "60 characters or fewer"),
    ],
)
def test_url_submission_rejects_invalid_streamer_tag(
    client,
    monkeypatch,
    streamer_tag,
    expected_error,
):
    monkeypatch.setattr(
        "ai_clips_maker.webapp.socket.getaddrinfo",
        lambda *_args: [
            (None, None, None, None, ("93.184.216.34", 443))
        ],
    )
    response = client.post(
        "/api/jobs",
        json={
            "url": "https://example.com/video",
            "streamer_tag": streamer_tag,
        },
    )

    assert response.status_code == 400
    assert expected_error in response.json["error"]


@pytest.mark.parametrize(
    "creator_context, expected_error",
    [
        ({"audience": "a" * 301}, "300 characters or fewer"),
        ({"topic": 123}, "must be text"),
    ],
)
def test_url_submission_rejects_invalid_creator_context(
    client,
    monkeypatch,
    creator_context,
    expected_error,
):
    monkeypatch.setattr(
        "ai_clips_maker.webapp.socket.getaddrinfo",
        lambda *_args: [
            (None, None, None, None, ("93.184.216.34", 443))
        ],
    )
    response = client.post(
        "/api/jobs",
        json={
            "url": "https://example.com/video",
            "creator_context": creator_context,
        },
    )

    assert response.status_code == 400
    assert expected_error in response.json["error"]


def test_job_status_hides_source_url_and_internal_paths(client, monkeypatch):
    monkeypatch.setattr(
        "ai_clips_maker.webapp.socket.getaddrinfo",
        lambda *_args: [
            (None, None, None, None, ("93.184.216.34", 443))
        ],
    )
    response = client.post(
        "/api/jobs",
        json={"url": "https://example.com/video?token=secret"},
    )

    job_id = response.json["job_id"]
    status = client.get(f"/api/jobs/{job_id}")

    assert status.status_code == 200
    assert "secret" not in str(status.json)
    assert "source_path" not in status.json


def test_url_job_accepts_afrikaans_and_original_output(client, monkeypatch):
    monkeypatch.setattr(
        "ai_clips_maker.webapp.socket.getaddrinfo",
        lambda *_args: [
            (None, None, None, None, ("93.184.216.34", 443))
        ],
    )
    response = client.post(
        "/api/jobs",
        json={
            "url": "https://example.com/video",
            "language": "af",
            "output_mode": "original",
        },
    )

    assert response.status_code == 202
    job = JOBS[response.json["job_id"]]
    assert job["language"] == "af"
    assert job["output_mode"] == "original"


def test_job_rejects_unsupported_south_african_language(client):
    response = client.post(
        "/api/jobs",
        json={
            "url": "https://example.com/video",
            "language": "zu",
            "output_mode": "tiktok",
        },
    )

    assert response.status_code == 400
    assert "isiZulu" in response.json["error"]


def test_all_good_picks_are_offered_for_timeline_review(client, tmp_path, monkeypatch):
    job_id = "all-ranked-candidates"
    job_dir = tmp_path / "clipp3r" / job_id
    job_dir.mkdir(parents=True)
    source_path = job_dir / "source.mp4"
    source_path.write_bytes(b"video")
    transcript = SimpleNamespace(
        text="A transcript with enough text for every clip.",
        words=[],
        end_time=260,
    )
    candidates = [
        MediaSegment(20 * i, 20 * i + 20, 0, len(transcript.text), quality_score=80)
        for i in range(12)
    ]
    observed_progress = []

    class FakeTranscriber:
        def __init__(self, model_size=None):
            assert model_size == "small"

        def transcribe(self, _path, lang, on_progress):
            assert lang == "af"
            on_progress(0.5)
            return transcript

    class FakeClipFinder:
        def __init__(self, **_kwargs):
            pass

        def find_clips(self, _transcription):
            return candidates

    monkeypatch.setattr(
        transcriber_module,
        "WhisperTranscriber",
        FakeTranscriber,
    )
    monkeypatch.setattr(
        "ai_clips_maker.txtslice.segment_picker.ClipFinder",
        FakeClipFinder,
    )
    JOBS[job_id] = {
        "id": job_id,
        "status": "queued",
        "source_path": str(source_path),
        "job_dir": str(job_dir),
        "max_clips": 0,
        "face_tracking": True,
        "output_mode": "original",
        "language": "af",
        "creator_context": {
            "audience": "Gardeners",
            "topic": "Water conservation",
            "goal": "Explain",
            "tone": "Practical",
        },
        "streamer_tag": "SONICINSIDE",
        "streamer_platform": "",
        "caption_style": "creator_pop",
        "clips_output_dir": str(tmp_path / "final-clips"),
        "clips": [],
        "error": None,
    }

    def record_update(job_id, **updates):
        if updates.get("stage") == "transcribing" or updates.get(
            "message", ""
        ).startswith("Transcribing"):
            observed_progress.append(updates["progress"])
        _update_job(job_id, **updates)

    monkeypatch.setattr("ai_clips_maker.webapp._update_job", record_update)
    _run_job(job_id)

    assert JOBS[job_id]["status"] == "awaiting_selection"
    assert len(JOBS[job_id]["clips"]) == 12
    assert JOBS[job_id]["clips"][0]["hook"] == ""
    assert JOBS[job_id]["clips"][0]["name"] == "candidate_001"
    assert JOBS[job_id]["source_duration"] >= candidates[-1].finish_sec
    assert not (tmp_path / "final-clips").exists()
    assert observed_progress == [12, 17]


def test_clip_headline_is_updated_after_render_and_archive_refreshed(
    client,
    tmp_path,
    monkeypatch,
):
    job_id = "post-render-headline"
    job_dir = tmp_path / "clipp3r" / job_id
    output_dir = tmp_path / "final-clips"
    job_dir.mkdir(parents=True)
    output_dir.mkdir()
    clip_path = output_dir / "clip_001.mp4"
    clip_path.write_bytes(b"rendered-captioned-clip")
    JOBS[job_id] = {
        "id": job_id,
        "status": "ready",
        "job_dir": str(job_dir),
        "caption_style": "creator_pop",
        "clips_output_dir": str(output_dir),
        "clips": [{
            "name": clip_path.name,
            "path": str(clip_path),
            "text": "This is the visible clip transcript.",
            "hook": "",
        }],
    }
    applied_headlines = []

    def fake_apply(path, headline, caption_style):
        applied_headlines.append((headline, caption_style))
        path.write_bytes(path.read_bytes() + headline.encode("utf-8"))

    monkeypatch.setattr(
        "ai_clips_maker.webapp.apply_clip_headline",
        fake_apply,
    )

    assert client.post(
        f"/api/jobs/{job_id}/clips/{clip_path.name}/headline",
        json={"headline": "x" * 101},
    ).status_code == 400
    first = client.post(
        f"/api/jobs/{job_id}/clips/{clip_path.name}/headline",
        json={"headline": "  A watched, specific hook  "},
    )

    assert first.status_code == 200
    assert first.json["headline"] == "A watched, specific hook"
    assert clip_path.read_bytes() == b"rendered-captioned-clipA watched, specific hook"
    private_status = client.get(f"/api/jobs/{job_id}").json
    assert "headline_source_path" not in str(private_status)

    second = client.post(
        f"/api/jobs/{job_id}/clips/{clip_path.name}/headline",
        json={"headline": "A corrected hook"},
    )
    assert second.status_code == 200
    assert clip_path.read_bytes() == b"rendered-captioned-clipA corrected hook"

    cleared = client.post(
        f"/api/jobs/{job_id}/clips/{clip_path.name}/headline",
        json={"headline": ""},
    )
    assert cleared.status_code == 200
    assert clip_path.read_bytes() == b"rendered-captioned-clip"
    assert JOBS[job_id]["clips"][0]["hook"] == ""
    assert applied_headlines == [
        ("A watched, specific hook", "creator_pop"),
        ("A corrected hook", "creator_pop"),
    ]

    import zipfile

    with zipfile.ZipFile(JOBS[job_id]["archive"]) as archive:
        assert archive.read(clip_path.name) == b"rendered-captioned-clip"


def test_selected_clip_suggestions_are_validated_and_use_clip_context(
    client,
    tmp_path,
):
    job_id = "metadata-suggestions"
    output_dir = tmp_path / "final-clips"
    output_dir.mkdir()
    clip_path = output_dir / "clip_001.mp4"
    clip_path.write_bytes(b"clip")
    JOBS[job_id] = {
        "id": job_id,
        "status": "ready",
        "clips_output_dir": str(output_dir),
        "creator_context": {
            "audience": "",
            "topic": "",
            "goal": "",
            "tone": "",
        },
        "clips": [{
            "name": clip_path.name,
            "path": str(clip_path),
            "text": (
                "We learned how to build reliable garden irrigation systems. "
                "This method uses water more efficiently."
            ),
            "start": 0,
            "end": 20,
            "duration": 20,
            "score": 80,
        }],
    }

    response = client.post(
        f"/api/jobs/{job_id}/suggestions",
        json={
            "clip_names": [clip_path.name],
            "contexts": {
                clip_path.name: {
                    "audience": "Home gardeners",
                    "topic": "Water-saving irrigation",
                    "goal": "Explain a practical technique",
                    "tone": "Friendly and clear",
                }
            },
        },
    )

    assert response.status_code == 200
    suggestions = response.json["suggestions"][clip_path.name]
    assert len(suggestions["options"]) == 3
    assert len({option["title"] for option in suggestions["options"]}) == 3
    assert all(option["rationale"] for option in suggestions["options"])
    assert 0 < len(suggestions["hashtags"]) <= 4
    assert any("verify" in uncertainty.lower() for uncertainty in suggestions["uncertainties"])
    clip = JOBS[job_id]["clips"][0]
    assert clip["metadata_state"] == "suggested"
    assert clip["creator_context"]["audience"] == "Home gardeners"


def test_selected_title_renames_download_and_refreshes_zip(client, tmp_path):
    job_id = "selected-title"
    output_dir = tmp_path / "final-clips"
    output_dir.mkdir()
    clip_path = output_dir / "clip_001.mp4"
    clip_path.write_bytes(b"clip")
    JOBS[job_id] = {
        "id": job_id,
        "status": "ready",
        "clips_output_dir": str(output_dir),
        "clips": [{
            "name": clip_path.name,
            "path": str(clip_path),
            "text": "A complete transcript.",
        }],
    }

    response = client.post(
        f"/api/jobs/{job_id}/clips/{clip_path.name}/title",
        json={
            "title": "A better garden title",
            "context": {
                "audience": "Gardeners",
                "topic": "Gardening",
                "goal": "",
                "tone": "",
            },
        },
    )

    assert response.status_code == 200
    renamed = output_dir / "A better garden title.mp4"
    assert renamed.read_bytes() == b"clip"
    assert not clip_path.exists()
    assert Path(JOBS[job_id]["archive"]).parent == output_dir
    import zipfile

    with zipfile.ZipFile(JOBS[job_id]["archive"]) as archive:
        assert archive.namelist() == [renamed.name]


def test_clip_suggestions_can_be_skipped_without_changing_clip(client, tmp_path):
    job_id = "skip-suggestions"
    output_dir = tmp_path / "final-clips"
    output_dir.mkdir()
    clip_path = output_dir / "clip_001.mp4"
    clip_path.write_bytes(b"clip")
    JOBS[job_id] = {
        "id": job_id,
        "status": "ready",
        "clips_output_dir": str(output_dir),
        "clips": [{
            "name": clip_path.name,
            "path": str(clip_path),
            "text": "Transcript.",
            "suggestions": {"options": []},
        }],
    }

    response = client.post(
        f"/api/jobs/{job_id}/clips/{clip_path.name}/skip-suggestions"
    )

    assert response.status_code == 200
    assert JOBS[job_id]["clips"][0]["metadata_state"] == "skipped"
    assert "suggestions" not in JOBS[job_id]["clips"][0]
    assert clip_path.read_bytes() == b"clip"
