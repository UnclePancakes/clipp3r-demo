from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from ai_clips_maker.batch_export import export_clips
from ai_clips_maker.captions import streamer_tag_layout
from ai_clips_maker.txtslice.matcher import MediaSegment


def test_export_clips_sorts_limits_and_uses_centered_vertical_crop(tmp_path):
    source = tmp_path / "source.mp4"
    source.touch()
    segments = [
        MediaSegment(20, 30, 0, 1),
        MediaSegment(2, 8, 0, 1),
    ]

    def run_process(command, **kwargs):
        if command[0] == "ffmpeg":
            Path(command[-1]).touch()
            return SimpleNamespace(returncode=0, stderr="", stdout="")
        return SimpleNamespace(
            returncode=0,
            stderr="",
            stdout=(
                '{"format":{"duration":"6.0"},"streams":'
                '[{"codec_type":"video","width":1080,"height":1920}]}'
            ),
        )

    with patch("ai_clips_maker.batch_export.shutil.which", side_effect=lambda tool: tool), patch(
        "ai_clips_maker.batch_export.subprocess.run", side_effect=run_process
    ) as run, patch(
        "ai_clips_maker.batch_export.write_ass_captions"
    ) as write_captions:
        paths = export_clips(
            source,
            segments,
            tmp_path / "clips",
            max_clips=1,
            face_tracking=False,
            streamer_tag="SONICINSIDE",
            streamer_platform="twitch",
        )

    assert paths == [tmp_path / "clips" / "clip_001.mp4"]
    command = next(
        call.args[0]
        for call in run.call_args_list
        if call.args[0][0] == "ffmpeg"
    )
    assert command[command.index("-ss") + 1] == "2.000000"
    video_filter = command[command.index("-filter_complex") + 1]
    assert "gblur=sigma=32:steps=2" in video_filter
    assert "scale=1080:-2:flags=lanczos" in video_filter
    assert "subtitles=filename=" in video_filter
    assert "(iw-ow)/2" in video_filter
    assert run.call_count == 3
    assert write_captions.call_args.kwargs["streamer_platform"] == "twitch"
    logo = streamer_tag_layout(
        1080,
        1920,
        "SONICINSIDE",
        write_captions.call_args.kwargs["streamer_tag_y"],
        has_platform_logo=True,
    )[3]
    assert logo is not None
    logo_x, logo_y, logo_size = logo
    assert f"overlay={logo_x}:{logo_y}:shortest=1[outv]" in video_filter
    assert f"scale={logo_size}:{logo_size}:flags=lanczos" in video_filter
    assert command[command.index("-loop") + 1] == "1"
    assert command[command.index("-i", command.index("-loop")) + 1].endswith(
        "twitch.png"
    )


def test_export_clips_can_preserve_original_dimensions(tmp_path):
    source = tmp_path / "source.mp4"
    source.touch()

    def run_process(command, **_kwargs):
        if command[0] == "ffmpeg":
            Path(command[-1]).touch()
            return SimpleNamespace(returncode=0, stderr="", stdout="")
        return SimpleNamespace(
            returncode=0,
            stderr="",
            stdout=(
                '{"format":{"duration":"6.0"},"streams":'
                '[{"codec_type":"video","width":1920,"height":1080}]}'
            ),
        )

    with patch("ai_clips_maker.batch_export.shutil.which", side_effect=lambda tool: tool), patch(
        "ai_clips_maker.batch_export.subprocess.run", side_effect=run_process
    ) as run:
        paths = export_clips(
            source,
            [MediaSegment(2, 8, 0, 1)],
            tmp_path / "original",
            face_tracking=True,
            output_mode="original",
        )

    assert paths == [tmp_path / "original" / "clip_001.mp4"]
    ffmpeg_command = next(
        call.args[0] for call in run.call_args_list if call.args[0][0] == "ffmpeg"
    )
    video_filter = ffmpeg_command[ffmpeg_command.index("-filter_complex") + 1]
    assert video_filter.startswith("[0:v]subtitles=filename=")
    assert "split=2" not in video_filter
    assert run.call_count == 3


def test_export_clips_fails_when_ffmpeg_fails(tmp_path):
    source = tmp_path / "source.mp4"
    source.touch()
    segment = MediaSegment(2, 8, 0, 1)

    with patch("ai_clips_maker.batch_export.shutil.which", side_effect=lambda tool: tool), patch(
        "ai_clips_maker.batch_export.subprocess.run",
        return_value=SimpleNamespace(returncode=1, stderr="encode failed", stdout=""),
    ):
        with pytest.raises(RuntimeError, match="encode failed"):
            export_clips(
                source,
                [segment],
                tmp_path / "clips",
                face_tracking=False,
            )


def test_export_clips_removes_invalid_ffmpeg_output(tmp_path):
    source = tmp_path / "source.mp4"
    source.touch()
    segment = MediaSegment(2, 8, 0, 1)
    output = tmp_path / "clips" / "clip_001.mp4"

    def run_process(command, **kwargs):
        if command[0] == "ffmpeg":
            Path(command[-1]).write_bytes(b"invalid")
            return SimpleNamespace(returncode=0, stderr="", stdout="")
        return SimpleNamespace(
            returncode=0,
            stderr="",
            stdout='{"format":{"duration":"0"},"streams":[]}',
        )

    with patch("ai_clips_maker.batch_export.shutil.which", side_effect=lambda tool: tool), patch(
        "ai_clips_maker.batch_export.subprocess.run", side_effect=run_process
    ):
        with pytest.raises(RuntimeError, match="invalid clip"):
            export_clips(
                source,
                [segment],
                tmp_path / "clips",
                face_tracking=False,
            )

    assert not output.exists()


def test_export_clips_rejects_invalid_dimensions(tmp_path):
    source = tmp_path / "source.mp4"
    source.touch()
    segment = MediaSegment(2, 8, 0, 1)

    with patch("ai_clips_maker.batch_export.shutil.which", side_effect=lambda tool: tool):
        with pytest.raises(ValueError, match="even numbers"):
            export_clips(
                source,
                [segment],
                tmp_path / "clips",
                output_width=1079,
                face_tracking=False,
            )


def test_face_crop_expression_interpolates_tracked_face_positions(tmp_path):
    source = tmp_path / "source.mp4"
    source.touch()
    segment = MediaSegment(2, 8, 0, 1)

    from ai_clips_maker.batch_export import _face_crop_expression

    expression = _face_crop_expression([(0, 0.25), (1.5, 0.75)])

    assert "lt(t\\,1.500000)" in expression
    assert "clip(iw*(0.250000+(0.500000)" in expression


def test_export_clips_refuses_to_overwrite_existing_clip(tmp_path):
    source = tmp_path / "source.mp4"
    source.touch()
    output = tmp_path / "clips" / "clip_001.mp4"
    output.parent.mkdir()
    output.write_bytes(b"keep existing")

    with patch("ai_clips_maker.batch_export.shutil.which", side_effect=lambda tool: tool):
        with pytest.raises(FileExistsError, match="Refusing to overwrite"):
            export_clips(
                source,
                [MediaSegment(2, 8, 0, 1)],
                output.parent,
                face_tracking=False,
            )

    assert output.read_bytes() == b"keep existing"
