"""Build readable, word-timed ASS captions for vertical video."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence


def streamer_tag_layout(
    width: int,
    height: int,
    streamer_tag: str,
    streamer_tag_y: int | None = None,
    has_platform_logo: bool = False,
) -> tuple[int, int, int, tuple[int, int, int] | None]:
    """Return the tag anchor and optional PNG overlay position and size."""
    clean_tag = " ".join(streamer_tag.split()).strip()
    tag_x = max(0, width - 72)
    tag_y = streamer_tag_y if streamer_tag_y is not None else height - 48
    logo_size = min(46, max(32, round(height * 0.024)))
    logo_gap = 10
    available_text_width = max(
        1,
        tag_x - 72 - (logo_size + logo_gap if has_platform_logo else 0),
    )
    tag_font_size = min(
        34,
        max(16, int(available_text_width / (max(1, len(clean_tag)) * 0.62))),
    )
    tag_width = min(
        available_text_width,
        round(len(clean_tag) * tag_font_size * 0.62),
    )
    logo_position = None
    if has_platform_logo:
        logo_x = max(0, tag_x - tag_width - logo_gap - logo_size)
        logo_y = max(0, tag_y - logo_size + 2)
        logo_position = (logo_x, logo_y, logo_size)
    return tag_x, tag_y, tag_font_size, logo_position


def write_ass_captions(
    words: Sequence,
    clip_start: float,
    clip_end: float,
    path: str | Path,
    width: int = 1080,
    height: int = 1920,
    streamer_tag: str = "",
    streamer_platform: str = "",
    streamer_tag_y: int | None = None,
    hook_text: str = "",
    caption_style: str = "creator_pop",
) -> Path:
    """Write high-contrast, timed captions that avoid TikTok's edge controls."""
    if caption_style not in {"creator_pop", "classic"}:
        raise ValueError("caption_style must be 'creator_pop' or 'classic'.")
    if not isinstance(streamer_platform, str) or streamer_platform not in {
        "",
        "twitch",
        "kick",
    }:
        raise ValueError("streamer_platform must be '', 'twitch', or 'kick'.")
    target = Path(path)
    if caption_style == "creator_pop":
        caption_style_line = (
            "Style: TikTok,Impact,76,&H0000D7FF,&H00FFFFFF,&H00000000,"
            "&H70000000,-1,0,0,0,100,100,0,0,3,5,1,2,84,84,500,1"
        )
        hook_style_line = (
            "Style: Hook,Impact,70,&H00FFFFFF,&H00FFFFFF,&H00000000,"
            "&H00962DFF,-1,0,0,0,100,100,0,0,3,10,0,8,100,100,150,1"
        )
        tag_style_line = (
            "Style: StreamerTag,Arial,34,&H00FFFFFF,&H00FFFFFF,&H00000000,"
            "&HFF000000,-1,0,0,0,100,100,0,0,1,6,1,3,48,72,48,1"
        )
    else:
        caption_style_line = (
            "Style: TikTok,Arial,64,&H0000D7FF,&H00FFFFFF,&H00000000,"
            "&H70000000,-1,0,0,0,100,100,0,0,3,8,0,2,120,240,360,1"
        )
        hook_style_line = (
            "Style: Hook,Arial,58,&H00000000,&H00000000,&H00000000,"
            "&H18FFFFFF,-1,0,0,0,100,100,0,0,3,10,0,8,100,100,120,1"
        )
        tag_style_line = (
            "Style: StreamerTag,Arial,34,&H00FFFFFF,&H00FFFFFF,&H00000000,"
            "&HFF000000,-1,0,0,0,100,100,0,0,1,6,1,3,48,72,48,1"
        )
    visible_words = [
        word
        for word in sorted(words, key=lambda item: item.start_time)
        if word.start_time is not None
        and word.end_time is not None
        and word.text.strip()
        and word.end_time > clip_start
        and word.start_time < clip_end
    ]

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        (
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding"
        ),
        caption_style_line,
        hook_style_line,
        tag_style_line,
        "",
        "[Events]",
        (
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
            "MarginV, Effect, Text"
        ),
    ]

    clean_hook = " ".join(hook_text.split()).strip()
    if clean_hook:
        if caption_style == "creator_pop":
            clean_hook = clean_hook.upper()
        lines.append(
            "Dialogue: 2,"
            f"{_ass_time(0)},{_ass_time(clip_end - clip_start)},"
            "Hook,,0,0,0,,"
            + _wrap_hook_text(clean_hook)
        )

    clean_tag = " ".join(streamer_tag.split()).strip()
    if clean_tag:
        if caption_style == "creator_pop":
            clean_tag = clean_tag.upper()
        tag_text = _escape_ass_text(clean_tag)
        tag_x, tag_y, tag_font_size, _logo_position = streamer_tag_layout(
            width,
            height,
            clean_tag,
            streamer_tag_y,
            has_platform_logo=bool(streamer_platform),
        )
        lines.append(
            "Dialogue: 1,"
            f"{_ass_time(0)},{_ass_time(clip_end - clip_start)},"
            "StreamerTag,,0,0,0,,"
            + f"{{\\an3\\pos({tag_x},{tag_y})\\fs{tag_font_size}\\bord6\\3c&H000000&}}"
            + tag_text
        )

    chunks = _group_words(visible_words)
    for chunk in chunks:
        start = max(clip_start, chunk[0].start_time) - clip_start
        end = min(clip_end, chunk[-1].end_time) - clip_start
        if end <= start:
            continue

        text_parts = []
        line_length = 0
        for word in chunk:
            word_text = _escape_ass_text(
                word.text.upper() if caption_style == "creator_pop" else word.text
            )
            if not word_text:
                continue
            if line_length and line_length + len(word.text) + 1 > 22:
                text_parts.append(r"\N")
                line_length = 0
            elif text_parts and not text_parts[-1].endswith(r"\N"):
                text_parts.append(" ")

            karaoke_end = min(clip_end, word.end_time)
            karaoke_start = max(clip_start, word.start_time)
            centiseconds = max(
                1,
                round(max(0.01, karaoke_end - karaoke_start) * 100),
            )
            text_parts.append(f"{{\\k{centiseconds}}}{word_text}")
            line_length += len(word.text) + 1

        if text_parts:
            lines.append(
                "Dialogue: 0,"
                f"{_ass_time(start)},{_ass_time(end)},TikTok,,0,0,0,,"
                + "".join(text_parts)
            )

    target.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    return target


def _group_words(words: Sequence) -> list[list]:
    chunks = []
    current = []
    current_length = 0
    for word in words:
        word_length = len(word.text.strip())
        if current and (
            len(current) >= 5
            or current_length + word_length + 1 > 38
            or _ends_sentence(current[-1].text)
        ):
            chunks.append(current)
            current = []
            current_length = 0
        current.append(word)
        current_length += word_length + (1 if len(current) > 1 else 0)
    if current:
        chunks.append(current)
    return chunks


def _ends_sentence(text: str) -> bool:
    return text.rstrip().endswith((".", "!", "?", "…"))


def _escape_ass_text(text: str) -> str:
    return (
        text.replace("\\", r"\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def _wrap_hook_text(text: str, max_line_length: int = 28) -> str:
    wrapped = []
    current = []
    current_length = 0
    for word in text.split():
        escaped_word = _escape_ass_text(word)
        if current and current_length + len(word) + 1 > max_line_length:
            wrapped.append(" ".join(current))
            current = []
            current_length = 0
        current.append(escaped_word)
        current_length += len(word) + (1 if len(current) > 1 else 0)
    if current:
        wrapped.append(" ".join(current))
    return r"\N".join(wrapped)


def _ass_time(seconds: float) -> str:
    total_centiseconds = max(0, round(seconds * 100))
    centiseconds = total_centiseconds % 100
    total_seconds = total_centiseconds // 100
    second = total_seconds % 60
    total_minutes = total_seconds // 60
    minute = total_minutes % 60
    hour = total_minutes // 60
    return f"{hour}:{minute:02d}:{second:02d}.{centiseconds:02d}"
