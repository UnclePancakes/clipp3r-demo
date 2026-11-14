"""Command-line interface for creating short-form clips."""

import argparse
from pathlib import Path

from .batch_export import export_clips


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Transcribe a video, suggest topical segments, and export them as "
            "captioned vertical MP4 clips with face-aware framing."
        )
    )
    parser.add_argument("video", type=Path, help="Path to the source video.")
    parser.add_argument(
        "--output",
        type=Path,
        help="Output folder (defaults to <video-name>_clips beside the source).",
    )
    parser.add_argument(
        "--min-duration",
        type=int,
        default=15,
        help="Minimum suggested clip duration in seconds (default: 15).",
    )
    parser.add_argument(
        "--max-duration",
        type=int,
        default=60,
        help="Maximum suggested clip duration in seconds (default: 60).",
    )
    parser.add_argument(
        "--max-clips",
        type=int,
        default=0,
        help="Maximum clips to export; 0 exports every ranked candidate (default: 0).",
    )
    parser.add_argument(
        "--language",
        help="Optional Faster-Whisper language code, including af for Afrikaans.",
    )
    parser.add_argument(
        "--output-mode",
        choices=("tiktok", "original"),
        default="tiktok",
        help="Output format: TikTok-style 9:16 or original source dimensions (default: tiktok).",
    )
    parser.add_argument(
        "--no-face-tracking",
        action="store_true",
        help="Use centered blurred backgrounds instead of detecting and following faces.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    video_path = args.video.expanduser().resolve()

    if not video_path.is_file():
        parser.error(f"video does not exist: {video_path}")
    if args.min_duration <= 0 or args.max_duration < args.min_duration:
        parser.error("duration limits must be positive and max must be >= min")
    if args.max_clips < 0:
        parser.error("--max-clips must be zero (all clips) or a positive integer")

    output_dir = args.output or video_path.with_name(f"{video_path.stem}_clips")

    from .transcribe.transcriber import WhisperTranscriber
    from .txtslice.segment_picker import ClipFinder

    print(f"Transcribing {video_path}...")
    transcription = WhisperTranscriber().transcribe(
        audio_path=str(video_path),
        lang=args.language,
    )
    segments = ClipFinder(
        min_clip_duration=args.min_duration,
        max_clip_duration=args.max_duration,
    ).find_clips(transcription)
    segments = [
        segment
        for segment in segments
        if args.min_duration
        <= segment.finish_sec - segment.begin_sec
        <= args.max_duration
    ]
    if not segments:
        parser.error(
            "No segments were found within the requested duration limits. "
            "Try lowering --min-duration or increasing --max-duration."
        )

    output_paths = export_clips(
        video_path=video_path,
        segments=segments,
        output_dir=output_dir,
        max_clips=args.max_clips or None,
        words=transcription.words,
        face_tracking=not args.no_face_tracking,
        output_mode=args.output_mode,
    )
    for output_path in output_paths:
        print(f"Created: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
