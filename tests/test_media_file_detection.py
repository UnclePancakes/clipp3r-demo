import json
from types import SimpleNamespace
from unittest.mock import patch

from ai_clips_maker.media.media_file import MediaFile


def test_media_file_accepts_ffprobe_recognized_file_when_magic_is_wrong(tmp_path):
    source = tmp_path / "source.mp4"
    source.touch()

    with patch.object(MediaFile, "get_mime_primary_type", return_value="inode"), patch(
        "ai_clips_maker.media.media_file.subprocess.run",
        return_value=SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"streams": [{"codec_type": "video"}]}),
            stderr="",
        ),
    ):
        assert MediaFile(str(source)).check_exists() is None


def test_media_file_rejects_unknown_file_when_ffprobe_finds_no_stream(tmp_path):
    source = tmp_path / "unknown.bin"
    source.touch()

    with patch.object(MediaFile, "get_mime_primary_type", return_value="inode"), patch(
        "ai_clips_maker.media.media_file.subprocess.run",
        return_value=SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"streams": []}),
            stderr="",
        ),
    ):
        assert "Detected type: 'inode'" in MediaFile(str(source)).check_exists()


def test_video_stream_without_attached_picture_is_detected():
    media = MediaFile("source.mp4")

    with patch.object(
        MediaFile,
        "get_video_streams",
        return_value=[{"disposition": {"attached_pic": 0}}],
    ):
        assert media.has_video_stream()


def test_attached_cover_image_is_not_a_video_stream():
    media = MediaFile("source.mp4")

    with patch.object(
        MediaFile,
        "get_video_streams",
        return_value=[{"disposition": {"attached_pic": 1}}],
    ):
        assert not media.has_video_stream()
