"""Export suggested transcript segments as vertical MP4 clips."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Sequence

from .captions import streamer_tag_layout, write_ass_captions
from .face_tracking import track_face_centers
from .txtslice.matcher import MediaSegment


def export_clips(
    video_path: str | Path,
    segments: Sequence[MediaSegment],
    output_dir: str | Path,
    max_clips: int | None = None,
    output_width: int = 1080,
    output_height: int = 1920,
    words: Sequence | None = None,
    face_tracking: bool = True,
    on_clip_complete: Callable[[int, int, Path], None] | None = None,
    output_mode: str = "tiktok",
    streamer_tag: str = "",
    streamer_platform: str = "",
    hooks: Sequence[str] | None = None,
    caption_style: str = "creator_pop",
) -> list[Path]:
    """Render captioned clips in TikTok portrait or source-native dimensions."""
    source = Path(video_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Input video does not exist: {source}")

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise FileNotFoundError(
            "FFmpeg was not found on PATH. Install FFmpeg and restart the terminal."
        )
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise FileNotFoundError(
            "FFprobe was not found on PATH. Install FFmpeg and restart the terminal."
        )

    if output_mode not in {"tiktok", "original"}:
        raise ValueError("output_mode must be 'tiktok' or 'original'.")
    if not isinstance(streamer_platform, str) or streamer_platform not in {
        "",
        "twitch",
        "kick",
    }:
        raise ValueError("streamer_platform must be '', 'twitch', or 'kick'.")
    if output_width <= 0 or output_height <= 0:
        raise ValueError("Output width and height must be positive.")
    if output_mode == "tiktok" and (output_width % 2 or output_height % 2):
        raise ValueError("Output width and height must be even numbers for H.264.")
    if max_clips is not None and max_clips <= 0:
        raise ValueError("max_clips must be a positive integer.")

    if output_mode == "original":
        output_width, output_height = _probe_video_dimensions(ffprobe, source)
        if output_width % 2 or output_height % 2:
            raise ValueError(
                "The source video has odd pixel dimensions, which cannot be "
                "preserved in a broadly compatible H.264 MP4."
            )

    streamer_tag_y = None
    if streamer_tag and output_mode == "tiktok":
        source_width, source_height = _probe_video_dimensions(ffprobe, source)
        foreground_height = min(
            output_height,
            round(output_width * source_height / source_width),
        )
        streamer_tag_y = min(
            output_height,
            (output_height + foreground_height) // 2,
        ) - 48
    logo_position = None
    logo_path = None
    if streamer_tag and streamer_platform:
        _tag_x, _tag_y, _font_size, logo_position = streamer_tag_layout(
            output_width,
            output_height,
            streamer_tag,
            streamer_tag_y,
            has_platform_logo=True,
        )
        logo_path = (
            Path(__file__).parent
            / "assets"
            / "platform"
            / f"{streamer_platform}.png"
        )
        if not logo_path.is_file():
            raise FileNotFoundError(
                f"The {streamer_platform} logo asset is missing: {logo_path}"
            )

    ordered_segments = sorted(segments, key=lambda segment: segment.begin_sec)
    if max_clips is not None:
        ordered_segments = ordered_segments[:max_clips]
    if not ordered_segments:
        raise ValueError("No valid clip segments were provided.")
    if hooks is not None and (
        isinstance(hooks, str)
        or len(hooks) != len(ordered_segments)
        or any(not isinstance(hook, str) or len(hook) > 100 for hook in hooks)
    ):
        raise ValueError("Provide one hook of at most 100 characters per clip.")

    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)

    exported_paths = []
    for index, segment in enumerate(ordered_segments, start=1):
        start = float(segment.begin_sec)
        end = float(segment.finish_sec)
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
            raise ValueError(
                f"Invalid clip range at index {index}: start={start}, end={end}"
            )

        output_path = destination / f"clip_{index:03d}.mp4"
        if output_path.exists():
            raise FileExistsError(
                f"Refusing to overwrite existing clip: {output_path}"
            )

        with tempfile.NamedTemporaryFile(
            prefix=f"clip_{index:03d}_",
            suffix=".ass",
            dir=destination,
            delete=False,
        ) as subtitle_file:
            subtitle_path = Path(subtitle_file.name)
        try:
            write_ass_captions(
                words or [],
                start,
                end,
                subtitle_path,
                output_width,
                output_height,
                streamer_tag=streamer_tag,
                streamer_platform=streamer_platform,
                streamer_tag_y=streamer_tag_y,
                hook_text=hooks[index - 1] if hooks is not None else "",
                caption_style=caption_style,
            )
            face_samples = (
                track_face_centers(source, start, end)
                if face_tracking and output_mode == "tiktok"
                else []
            )
            video_filter = _build_video_filter(
                output_width,
                output_height,
                subtitle_path,
                face_samples,
                output_mode=output_mode,
                logo_position=logo_position,
            )
            command = [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-n",
                "-ss",
                f"{start:.6f}",
                "-i",
                str(source),
            ]
            if logo_path is not None:
                command.extend([
                    "-loop",
                    "1",
                    "-framerate",
                    "30",
                    "-i",
                    str(logo_path),
                ])
            command.extend([
                "-t",
                f"{end - start:.6f}",
                "-filter_complex",
                video_filter,
                "-map",
                "[outv]",
                "-map",
                "0:a?",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "21",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                str(output_path),
            ])
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                output_path.unlink(missing_ok=True)
                raise RuntimeError(
                    f"FFmpeg failed to render clip {index} from {source}: "
                    f"{result.stderr.strip() or result.stdout.strip()}"
                )
            if not output_path.is_file():
                raise RuntimeError(
                    f"FFmpeg returned success but did not create {output_path}"
                )

            probe_result = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration:stream=codec_type,width,height",
                    "-of",
                    "json",
                    str(output_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if probe_result.returncode != 0:
                output_path.unlink()
                raise RuntimeError(
                    f"FFprobe could not validate clip {index} at {output_path}: "
                    f"{probe_result.stderr.strip() or probe_result.stdout.strip()}"
                )
            try:
                metadata = json.loads(probe_result.stdout)
                duration = float(metadata["format"]["duration"])
                video_stream = next(
                    stream
                    for stream in metadata["streams"]
                    if stream["codec_type"] == "video"
                )
            except (
                KeyError,
                StopIteration,
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ) as error:
                output_path.unlink()
                raise RuntimeError(
                    f"FFmpeg produced an invalid clip {index} at {output_path}"
                ) from error
            if (
                not math.isfinite(duration)
                or duration <= 0
                or video_stream.get("width") != output_width
                or video_stream.get("height") != output_height
            ):
                output_path.unlink()
                raise RuntimeError(
                    f"FFmpeg produced an invalid clip {index} at {output_path}: "
                    f"duration={duration}, dimensions="
                    f"{video_stream.get('width')}x{video_stream.get('height')}"
                )
            exported_paths.append(output_path)
            if on_clip_complete is not None:
                on_clip_complete(index, len(ordered_segments), output_path)
        finally:
            subtitle_path.unlink(missing_ok=True)

    return exported_paths


def apply_clip_headline(
    clip_path: str | Path,
    headline: str,
    caption_style: str = "creator_pop",
) -> None:
    """Apply or clear a headline on an already rendered clip in place."""
    target = Path(clip_path).expanduser().resolve()
    if not target.is_file():
        raise FileNotFoundError(f"Rendered clip does not exist: {target}")
    if not isinstance(headline, str) or len(headline) > 100:
        raise ValueError("A clip headline must be text of at most 100 characters.")
    if caption_style not in {"creator_pop", "classic"}:
        raise ValueError("caption_style must be 'creator_pop' or 'classic'.")

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if ffmpeg is None or ffprobe is None:
        raise FileNotFoundError(
            "FFmpeg and FFprobe are required to update a clip headline."
        )
    metadata = _probe_rendered_clip(ffprobe, target)
    clean_headline = " ".join(headline.split()).strip()
    with tempfile.NamedTemporaryFile(
        prefix=f".{target.stem}_",
        suffix=".mp4",
        dir=target.parent,
        delete=False,
    ) as temporary_video_file:
        temporary_video = Path(temporary_video_file.name)
    with tempfile.NamedTemporaryFile(
        prefix=f".{target.stem}_headline_",
        suffix=".ass",
        dir=target.parent,
        delete=False,
    ) as subtitle_file:
        subtitle_path = Path(subtitle_file.name)
    try:
        write_ass_captions(
            [],
            0,
            metadata["duration"],
            subtitle_path,
            metadata["width"],
            metadata["height"],
            hook_text=clean_headline,
            caption_style=caption_style,
        )
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-i",
            str(target),
            "-vf",
            f"subtitles=filename='{_escape_filter_value(str(subtitle_path.resolve()))}'",
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "21",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            str(temporary_video),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(
                "FFmpeg could not update the clip headline: "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        updated = _probe_rendered_clip(ffprobe, temporary_video)
        if (
            updated["width"] != metadata["width"]
            or updated["height"] != metadata["height"]
            or abs(updated["duration"] - metadata["duration"]) > 0.5
            or updated["has_audio"] != metadata["has_audio"]
        ):
            raise RuntimeError(
                "FFmpeg produced a clip with changed dimensions, duration, or audio."
            )
        temporary_video.replace(target)
    finally:
        subtitle_path.unlink(missing_ok=True)
        temporary_video.unlink(missing_ok=True)


def _build_video_filter(
    output_width: int,
    output_height: int,
    subtitle_path: Path,
    face_samples: Sequence[tuple[float, float]],
    output_mode: str = "tiktok",
    logo_position: tuple[int, int, int] | None = None,
) -> str:
    escaped_subtitles = _escape_filter_value(str(subtitle_path.resolve()))
    if output_mode == "original":
        caption_filter = (
            f"[0:v]subtitles=filename='{escaped_subtitles}'[captioned]"
        )
    else:
        crop_x = _face_crop_expression(face_samples)
        caption_filter = (
            f"[0:v]split=2[background][foreground];"
            f"[background]scale=-2:{output_height}:flags=lanczos,"
            f"crop={output_width}:{output_height}:"
            f"x='{crop_x}':y=0,"
            "gblur=sigma=32:steps=2[blurred];"
            f"[foreground]scale={output_width}:-2:flags=lanczos[fullframe];"
            "[blurred][fullframe]"
            "overlay=(W-w)/2:(H-h)/2:shortest=1,"
            f"subtitles=filename='{escaped_subtitles}'[captioned]"
        )
    if logo_position is None:
        return caption_filter.replace("[captioned]", "[outv]")
    logo_x, logo_y, logo_size = logo_position
    return (
        f"{caption_filter};"
        f"[1:v]scale={logo_size}:{logo_size}:flags=lanczos,"
        f"format=rgba[platformlogo];"
        f"[captioned][platformlogo]overlay={logo_x}:{logo_y}:shortest=1[outv]"
    )


def _probe_rendered_clip(ffprobe: str, path: Path) -> dict:
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,width,height",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"FFprobe could not validate clip {path}: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    try:
        metadata = json.loads(result.stdout)
        video = next(
            stream for stream in metadata["streams"]
            if stream.get("codec_type") == "video"
        )
        duration = float(metadata["format"]["duration"])
        width = int(video["width"])
        height = int(video["height"])
    except (KeyError, StopIteration, TypeError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError(f"FFprobe returned invalid clip metadata for {path}.") from error
    if (
        not math.isfinite(duration)
        or duration <= 0
        or width <= 0
        or height <= 0
    ):
        raise RuntimeError(f"FFprobe returned invalid clip metadata for {path}.")
    return {
        "duration": duration,
        "width": width,
        "height": height,
        "has_audio": any(
            stream.get("codec_type") == "audio"
            for stream in metadata["streams"]
        ),
    }


def _probe_video_dimensions(ffprobe: str, source: Path) -> tuple[int, int]:
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            str(source),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"FFprobe could not read source video dimensions: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    try:
        streams = json.loads(result.stdout)["streams"]
        width = int(streams[0]["width"])
        height = int(streams[0]["height"])
    except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError(
            "FFprobe did not report valid source video dimensions."
        ) from error
    if width <= 0 or height <= 0:
        raise RuntimeError(
            f"FFprobe reported invalid source dimensions: {width}x{height}."
        )
    return width, height


def _face_crop_expression(samples: Sequence[tuple[float, float]]) -> str:
    if not samples:
        return "(iw-ow)/2"
    expression = f"clip(iw*{samples[-1][1]:.6f}-ow/2\\,0\\,iw-ow)"
    for index in range(len(samples) - 2, -1, -1):
        start, center = samples[index]
        next_start, next_center = samples[index + 1]
        duration = max(next_start - start, 0.001)
        interpolated = (
            f"{center:.6f}+({next_center - center:.6f})"
            f"*(t-{start:.6f})/{duration:.6f}"
        )
        expression = (
            f"if(lt(t\\,{next_start:.6f})\\,"
            f"clip(iw*({interpolated})-ow/2\\,0\\,iw-ow)\\,"
            f"{expression})"
        )
    return expression


def _escape_filter_value(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace(",", "\\,")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )
