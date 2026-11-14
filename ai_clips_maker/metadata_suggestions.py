"""Transcript-grounded draft title and hashtag suggestions for selected clips."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

_WORD_PATTERN = re.compile(r"[#\w'-]+", re.UNICODE)
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
_HASHTAG_PATTERN = re.compile(r"^#[\w]{2,40}$", re.UNICODE)
_STOP_WORDS = frozenset({
    "about", "after", "again", "also", "because", "been", "before", "being",
    "between", "could", "does", "doing", "during", "from", "going", "have",
    "here", "into", "just", "know", "like", "more", "most", "much", "only",
    "other", "over", "really", "said", "some", "such", "than", "that", "their",
    "them", "then", "there", "these", "they", "thing", "think", "this", "those",
    "through", "time", "very", "want", "well", "were", "what", "when", "where",
    "which", "while", "with", "would", "your",
})
_CONTEXT_FIELDS = ("audience", "topic", "goal", "tone")


def generate_title_suggestions(
    transcript: str,
    context: dict[str, str],
) -> dict[str, Any]:
    """Create three distinct, transcript-grounded draft titles and tags."""
    cleaned = " ".join(transcript.split()).strip()
    words = _WORD_PATTERN.findall(cleaned)
    if not words:
        raise ValueError("This clip has no usable transcript for title suggestions.")

    sentences = [
        sentence.strip(" \t\r\n-–—")
        for sentence in _SENTENCE_BOUNDARY.split(cleaned)
        if sentence.strip(" \t\r\n-–—")
    ]
    lead = sentences[0].strip(" .!?")
    lead = _limit_title(lead, 68)
    subject = _context_value(context, "topic") or _extract_subject(words)
    if not subject:
        subject = _limit_title(lead, 48)
    if not subject:
        raise ValueError("The transcript is too unclear to suggest a title.")

    direct_title = _limit_title(lead, 90)
    second_title = _limit_title(f"A closer look at {subject}", 90)
    third_title = _limit_title(f"The key point about {subject}", 90)
    used = {direct_title.casefold()}
    if second_title.casefold() in used:
        second_title = _limit_title(f"What the clip says about {subject}", 90)
    used.add(second_title.casefold())
    if third_title.casefold() in used:
        third_title = _limit_title(f"Why {subject} matters", 90)
    if third_title.casefold() in used:
        third_title = _limit_title(f"{subject}: the clip's main idea", 90)

    options = [
        {
            "title": direct_title or _limit_title(f"What the clip says about {subject}", 90),
            "rationale": "Uses the clip's opening wording as a direct, transcript-backed hook.",
        },
        {
            "title": second_title,
            "rationale": "Names the stated topic and invites interest without promising an unseen result.",
        },
        {
            "title": third_title,
            "rationale": "Frames the clip as a concise takeaway; check that the full clip supports that emphasis.",
        },
    ]
    result = {
        "summary": _limit_title(lead, 180),
        "options": options,
        "hashtags": _make_hashtags(context, words),
        "uncertainties": _uncertainties(cleaned, words, context),
    }
    validate_suggestion_output(result)
    return result


def validate_suggestion_output(value: Any) -> None:
    """Validate the small, stable response schema used by the UI."""
    if not isinstance(value, dict):
        raise ValueError("Title suggestions must be an object.")
    if not isinstance(value.get("summary"), str) or not value["summary"].strip():
        raise ValueError("Title suggestions need a non-empty transcript summary.")
    options = value.get("options")
    if not isinstance(options, list) or len(options) != 3:
        raise ValueError("Title suggestions must include exactly three options.")
    titles = []
    for option in options:
        if not isinstance(option, dict):
            raise ValueError("Each title option must be an object.")
        title = option.get("title")
        rationale = option.get("rationale")
        if (
            not isinstance(title, str)
            or not title.strip()
            or len(title) > 100
            or not isinstance(rationale, str)
            or not rationale.strip()
        ):
            raise ValueError("Each title needs a short title and rationale.")
        titles.append(title.casefold().strip())
    if len(set(titles)) != 3:
        raise ValueError("The three title suggestions must be distinct.")

    hashtags = value.get("hashtags")
    if (
        not isinstance(hashtags, list)
        or len(hashtags) > 4
        or any(not isinstance(tag, str) or not _HASHTAG_PATTERN.fullmatch(tag) for tag in hashtags)
        or len({tag.casefold() for tag in hashtags}) != len(hashtags)
    ):
        raise ValueError("Hashtags must be a short list of distinct, valid tags.")
    uncertainties = value.get("uncertainties")
    if (
        not isinstance(uncertainties, list)
        or any(not isinstance(item, str) or not item.strip() for item in uncertainties)
    ):
        raise ValueError("Uncertainties must be a list of non-empty notes.")


def _extract_subject(words: list[str]) -> str:
    candidates = [
        word.strip("'’-").lower()
        for word in words
        if len(word.strip("'’-")) >= 4
        and word.strip("'’-").lower() not in _STOP_WORDS
        and not word.strip("'’-").isdigit()
    ]
    if not candidates:
        return ""
    counts = Counter(candidates)
    first_seen = {word: candidates.index(word) for word in counts}
    ranked = sorted(counts, key=lambda word: (-counts[word], first_seen[word]))
    return " and ".join(_title_case(word) for word in ranked[:2])


def _make_hashtags(context: dict[str, str], words: list[str]) -> list[str]:
    candidates = []
    topic = _context_value(context, "topic")
    if topic:
        candidates.append(topic)
    candidates.extend(
        word.strip("'’-")
        for word in words
        if len(word.strip("'’-")) >= 4
        and word.strip("'’-").lower() not in _STOP_WORDS
    )

    tags = []
    seen = set()
    for phrase in candidates:
        tag = "#" + "".join(
            part[:1].upper() + part[1:]
            for part in re.findall(r"[^\W_]+", phrase, flags=re.UNICODE)
        )
        if (
            len(tag) < 3
            or len(tag) > 41
            or not _HASHTAG_PATTERN.fullmatch(tag)
            or tag.casefold() in seen
        ):
            continue
        tags.append(tag)
        seen.add(tag.casefold())
        if len(tags) == 3:
            break
    return tags


def _uncertainties(
    transcript: str,
    words: list[str],
    context: dict[str, str],
) -> list[str]:
    notes = []
    if len(words) < 8:
        notes.append("The transcript is very short; review it before using these drafts.")
    if transcript[-1:] not in ".!?…":
        notes.append("The transcript may end mid-thought or be incomplete.")
    if not _context_value(context, "audience"):
        notes.append("The target audience was not provided.")
    if not _context_value(context, "topic"):
        notes.append("The topic was inferred from transcript words; verify it.")
    notes.append("Verify names, claims, and transcript accuracy against the video.")
    return notes


def _context_value(context: dict[str, str], field: str) -> str:
    value = context.get(field, "")
    return " ".join(value.split()).strip() if isinstance(value, str) else ""


def _title_case(value: str) -> str:
    return value[:1].upper() + value[1:]


def _limit_title(value: str, limit: int) -> str:
    value = " ".join(value.split()).strip(" :;,-")
    if len(value) <= limit:
        return value
    shortened = value[: limit + 1].rsplit(" ", 1)[0].rstrip(" :;,-")
    return shortened or value[:limit].rstrip()
