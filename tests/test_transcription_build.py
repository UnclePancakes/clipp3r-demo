from datetime import datetime

from ai_clips_maker.transcribe.transcription import Transcription


def test_transcription_builds_word_sentence_and_character_indexes():
    text = "Hello world. This is a test!"
    start = datetime.now()
    chars = [
        {
            "char": char,
            "start_time": index / 10,
            "end_time": (index + 1) / 10,
            "speaker": None,
        }
        for index, char in enumerate(text)
    ]
    transcription = Transcription({
        "source_software": "test",
        "time_created": start,
        "language": "en",
        "num_speakers": None,
        "char_info": chars,
    })

    assert [word.text for word in transcription.words] == [
        "Hello",
        "world.",
        "This",
        "is",
        "a",
        "test!",
    ]
    assert [item["sentence"] for item in transcription.get_sentence_info()] == [
        "Hello world.",
        "This is a test!",
    ]
    assert transcription.characters[0].word_index == 0
    assert transcription.characters[0].sentence_index == 0
    assert transcription.sentences[1].start_char == 13
    assert transcription.end_time == len(text) / 10
