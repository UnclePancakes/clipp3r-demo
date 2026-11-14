"""Rank and de-duplicate short-form clip candidates using transcript signals."""

from __future__ import annotations

import re
from collections.abc import Sequence

from .txtslice.matcher import MediaSegment


_HOOK_TERMS = {
    "actually",
    "because",
    "best",
    "changed",
    "finally",
    "first",
    "here's",
    "how",
    "imagine",
    "important",
    "learned",
    "mistake",
    "never",
    "problem",
    "secret",
    "stop",
    "surprising",
    "tip",
    "truth",
    "watch",
    "what",
    "why",
    "worst",
    "you",
}
_MOMENT_TERMS = {
    "brilliant",
    "checkmate",
    "donated",
    "donation",
    "fork",
    "gifted",
    "mate",
    "mistake",
    "pin",
    "queen",
    "sacrifice",
    "subscriber",
    "subscribers",
    "sub",
    "subs",
    "tactic",
    "thank",
    "thanks",
    "blunder",
    "capture",
    "check",
    "chess",
    "promoted",
    "promotion",
    "resign",
    "resigned",
    "gambit",
    "stalemate",
    "subscription",
    "subscribing",
    "subscribe",
    "rook",
    "bits",
    "superchat",
    "super",
}
_WORD_PATTERN = re.compile(r"[\w']+", re.UNICODE)
_MOMENT_PHRASES = (
    "thank you for the donation",
    "thanks for the donation",
    "thank you for subscribing",
    "thanks for subscribing",
    "first subscriber",
    "first sub",
    "gifted a sub",
    "gifted subs",
    "check mate",
    "oh my god",
    "no way",
    "let's go",
    "what a move",
    "brilliant move",
    "en passant",
)


def rank_clip_candidates(
    segments: Sequence[MediaSegment],
    transcript: str,
    max_duration: float = 60,
    max_candidates: int | None = None,
) -> list[MediaSegment]:
    """Score transcript-backed clips, favor events, and keep a diverse set."""
    ranked = []
    for segment in segments:
        duration = segment.finish_sec - segment.begin_sec
        if duration <= 0 or duration > max_duration:
            continue

        text = transcript[segment.text_start_idx:segment.text_end_idx].strip()
        if not _WORD_PATTERN.search(text):
            continue
        score = _score_clip(text, duration)
        ranked.append(
            MediaSegment(
                segment.begin_sec,
                segment.finish_sec,
                segment.text_start_idx,
                segment.text_end_idx,
                quality_score=score,
            )
        )

    ranked.sort(key=lambda segment: (-segment.quality_score, segment.begin_sec))
    selected = []
    for candidate in ranked:
        if any(_is_redundant(candidate, existing) for existing in selected):
            continue
        selected.append(candidate)
        if max_candidates is not None and len(selected) >= max_candidates:
            break
    return selected


def build_rolling_candidates(
    sentences: Sequence[dict],
    min_duration: float = 15,
    max_duration: float = 60,
    max_candidates: int = 240,
) -> list[MediaSegment]:
    """Create transcript-aligned fallback windows when topic segmentation is sparse."""
    timed_sentences = sorted(
        [
            sentence
            for sentence in sentences
            if isinstance(sentence.get("sentence"), str)
            and sentence["sentence"].strip()
            and isinstance(sentence.get("start_time"), (int, float))
            and isinstance(sentence.get("end_time"), (int, float))
            and sentence["end_time"] > sentence["start_time"]
            and isinstance(sentence.get("start_char"), int)
            and isinstance(sentence.get("end_char"), int)
            and sentence["end_char"] > sentence["start_char"]
        ],
        key=lambda sentence: sentence["start_time"],
    )
    if not timed_sentences or max_candidates <= 0:
        return []

    span = timed_sentences[-1]["end_time"] - timed_sentences[0]["start_time"]
    if span < min_duration:
        return []
    stride = max(25.0, span / max_candidates)
    target_duration = min(40.0, max_duration)
    results = []
    next_start = timed_sentences[0]["start_time"]
    start_index = 0

    while start_index < len(timed_sentences):
        while (
            start_index < len(timed_sentences)
            and timed_sentences[start_index]["start_time"] < next_start
        ):
            start_index += 1
        if start_index >= len(timed_sentences):
            break

        first = timed_sentences[start_index]
        best = None
        end_index = start_index
        while end_index < len(timed_sentences):
            sentence = timed_sentences[end_index]
            duration = sentence["end_time"] - first["start_time"]
            if duration > max_duration:
                break
            if duration >= min_duration:
                distance = abs(duration - target_duration)
                if best is None or distance < best[0]:
                    best = (distance, sentence)
            end_index += 1

        if best is not None:
            last = best[1]
            results.append(
                MediaSegment(
                    first["start_time"],
                    last["end_time"],
                    first["start_char"],
                    last["end_char"],
                )
            )
        next_start = first["start_time"] + stride

    return results


def _score_clip(text: str, duration: float) -> float:
    words = [word.lower() for word in _WORD_PATTERN.findall(text)]
    if not words:
        return 0.0

    words_per_second = len(words) / duration
    pace_score = max(0.0, 1 - abs(words_per_second - 1.8) / 3.6)
    length_score = max(0.0, 1 - abs(duration - 40) / 40)
    hook_score = float(bool(_HOOK_TERMS.intersection(words[:10])))
    moment_score = float(
        bool(_MOMENT_TERMS.intersection(words))
        or any(phrase in text.lower() for phrase in _MOMENT_PHRASES)
    )
    starts_cleanly = text[:1].isupper() or words[0] in _HOOK_TERMS
    ends_cleanly = text.rstrip().endswith((".", "!", "?", "…"))
    coherence_score = (float(starts_cleanly) + float(ends_cleanly)) / 2

    return round(
        100
        * (
            0.25 * pace_score
            + 0.20 * length_score
            + 0.25 * hook_score
            + 0.10 * coherence_score
            + 0.20 * moment_score
        ),
        1,
    )


def _is_redundant(
    candidate: MediaSegment,
    existing: MediaSegment,
    overlap_threshold: float = 0.55,
) -> bool:
    overlap = max(
        0.0,
        min(candidate.finish_sec, existing.finish_sec)
        - max(candidate.begin_sec, existing.begin_sec),
    )
    shorter_duration = min(
        candidate.finish_sec - candidate.begin_sec,
        existing.finish_sec - existing.begin_sec,
    )
    return shorter_duration > 0 and overlap / shorter_duration >= overlap_threshold
