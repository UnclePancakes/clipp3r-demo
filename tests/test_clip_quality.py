from ai_clips_maker.clip_quality import (
    build_rolling_candidates,
    rank_clip_candidates,
)
from ai_clips_maker.txtslice.segment_picker import ClipFinder
from ai_clips_maker.txtslice.matcher import MediaSegment


def test_rolling_candidates_cover_sparse_four_hour_transcripts():
    sentences = []
    for index in range(1440):
        start = index * 10
        sentences.append({
            "sentence": f"Chess position {index}.",
            "start_time": float(start),
            "end_time": float(start + 5),
            "start_char": index * 24,
            "end_char": index * 24 + 22,
        })

    candidates = build_rolling_candidates(sentences)

    assert 100 <= len(candidates) <= 240
    assert candidates[0].begin_sec == 0
    assert candidates[-1].finish_sec > 4 * 60 * 60 - 120
    assert all(15 <= clip.finish_sec - clip.begin_sec <= 60 for clip in candidates)


def test_clip_finder_adds_rolling_windows_when_topic_tiling_finds_none(monkeypatch):
    sentences = []
    transcript_parts = []
    offset = 0
    for index in range(240):
        text = f"Chess move {index}. "
        sentences.append({
            "sentence": text.strip(),
            "start_time": float(index * 20),
            "end_time": float(index * 20 + 5),
            "start_char": offset,
            "end_char": offset + len(text.strip()),
        })
        transcript_parts.append(text)
        offset += len(text)

    class FakeEmbedder:
        def embed_sentences(self, items):
            return [None] * len(items)

    monkeypatch.setattr(
        "ai_clips_maker.txtslice.segment_picker.TextEmbedder",
        FakeEmbedder,
    )
    monkeypatch.setattr(
        ClipFinder,
        "_text_tile_multiple_rounds",
        lambda *_args, **_kwargs: [],
    )
    finder = object.__new__(ClipFinder)
    finder._min_clip_duration = 15
    finder._max_clip_duration = 60

    class SparseTranscription:
        text = "".join(transcript_parts)
        end_time = 240 * 20

        def get_sentence_info(self):
            return sentences

        def get_char_info(self):
            raise AssertionError("Long videos should not use the whole-source segment.")

    candidates = finder.find_clips(SparseTranscription())

    assert 100 <= len(candidates) <= 240
    assert candidates[0].begin_sec == 0
    assert candidates[-1].finish_sec > 240 * 20 - 120


def test_event_language_increases_candidate_score():
    quiet = "A move in the position, and then we consider the board. " * 7
    event = "Thank you for the donation! " + quiet
    transcript = quiet + event
    candidates = [
        MediaSegment(0, 40, 0, len(quiet)),
        MediaSegment(60, 100, len(quiet), len(transcript)),
    ]

    ranked = rank_clip_candidates(candidates, transcript)

    assert ranked[0].begin_sec == 60
    assert ranked[0].quality_score > next(
        clip.quality_score for clip in ranked if clip.begin_sec == 0
    )


def test_rank_clip_candidates_prioritizes_hook_and_suppresses_overlap():
    strong = "Why this changed everything? " + "We learned an important secret. " * 7
    weak = "This is a recording. " + "The discussion continued for some time. " * 7
    transcript = strong + " " + weak
    strong_end = len(strong)
    weak_start = strong_end + 1

    candidates = [
        MediaSegment(0, 45, 0, strong_end),
        MediaSegment(8, 53, 0, strong_end),
        MediaSegment(60, 105, weak_start, len(transcript)),
    ]

    ranked = rank_clip_candidates(candidates, transcript)

    assert ranked[0].begin_sec == 0
    assert ranked[0].quality_score > ranked[-1].quality_score
    assert len(ranked) == 2
    assert all(segment.finish_sec - segment.begin_sec <= 60 for segment in ranked)


def test_rank_clip_candidates_rejects_empty_and_overlong_segments():
    transcript = "An interesting story. "
    candidates = [
        MediaSegment(0, 20, 0, 0),
        MediaSegment(0, 61, 0, len(transcript)),
    ]

    assert rank_clip_candidates(candidates, transcript) == []
