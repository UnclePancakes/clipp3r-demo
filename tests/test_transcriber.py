from types import SimpleNamespace
from unittest.mock import patch

from ai_clips_maker.transcribe.transcriber import (
    WhisperTranscriber,
    _build_char_info,
)


def test_transcriber_uses_faster_whisper_batched_pipeline():
    with patch("ai_clips_maker.transcribe.transcriber.WhisperModel") as model_class, patch(
        "ai_clips_maker.transcribe.transcriber.BatchedInferencePipeline"
    ) as batched_pipeline:
        WhisperTranscriber(model_size="tiny", device="cpu", precision="int8")

    model_class.assert_called_once_with(
        "tiny",
        device="cpu",
        compute_type="int8",
    )
    batched_pipeline.assert_called_once_with(model=model_class.return_value)


def test_character_timestamps_are_derived_from_word_timestamps():
    segments = [
        SimpleNamespace(
            start=2.0,
            end=4.0,
            text="hello",
            words=[SimpleNamespace(word="hello", start=2.0, end=3.0)],
        )
    ]

    chars = _build_char_info(segments)

    assert "".join(char["char"] for char in chars) == "hello"
    assert chars[0]["start_time"] == 2.0
    assert chars[-1]["end_time"] == 3.0


def test_transcriber_reports_progress_and_warns_on_uncertain_detection(
    monkeypatch,
    caplog,
):
    segments = [
        SimpleNamespace(
            start=0.0,
            end=20.0,
            text="hello",
            words=[SimpleNamespace(word="hello", start=0.0, end=1.0)],
        ),
        SimpleNamespace(
            start=20.0,
            end=50.0,
            text="world",
            words=[SimpleNamespace(word="world", start=20.0, end=21.0)],
        ),
    ]
    media = SimpleNamespace(
        path="source.mp4",
        assert_exists=lambda: None,
        assert_has_audio_stream=lambda: None,
        get_duration=lambda: 100.0,
    )
    monkeypatch.setattr(
        "ai_clips_maker.transcribe.transcriber.MediaEditor",
        lambda: SimpleNamespace(instantiate_as_temporal_media_file=lambda _path: media),
    )
    model = SimpleNamespace(
        transcribe=lambda *_args, **kwargs: (
            iter(segments),
            SimpleNamespace(language="en", language_probability=0.2),
        )
    )
    transcriber = object.__new__(WhisperTranscriber)
    transcriber._model = model
    progress = []
    monkeypatch.setattr(
        "ai_clips_maker.transcribe.transcriber.Transcription",
        lambda data: data,
    )

    transcriber.transcribe("source.mp4", on_progress=progress.append)

    assert progress == [0.2, 0.5]
    assert "language detection is uncertain" in caplog.text
