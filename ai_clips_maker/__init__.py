from importlib import import_module

_EXPORTS = {
    "AudioFile": (".media.audio_file", "AudioFile"),
    "AudioVideoFile": (".media.audiovideo_file", "AudioVideoFile"),
    "Character": (".transcribe.transcription_element", "Character"),
    "ClipFinder": (".txtslice.segment_picker", "ClipFinder"),
    "Crops": (".resize.crops", "Crops"),
    "MediaEditor": (".media.editor", "MediaEditor"),
    "MediaSegment": (".txtslice.matcher", "MediaSegment"),
    "Segment": (".resize.segment", "Segment"),
    "Sentence": (".transcribe.transcription_element", "Sentence"),
    "Transcriber": (".transcribe.transcriber", "WhisperTranscriber"),
    "Transcription": (".transcribe.transcription", "Transcription"),
    "VideoFile": (".media.video_file", "VideoFile"),
    "WhisperTranscriber": (".transcribe.transcriber", "WhisperTranscriber"),
    "Word": (".transcribe.transcription_element", "Word"),
    "resize": (".resize.resize", "resize"),
}

__all__ = [
    "AudioFile",
    "AudioVideoFile",
    "Character",
    "ClipFinder",
    "Crops",
    "MediaSegment",
    "MediaEditor",
    "Segment",
    "Sentence",
    "Transcriber",
    "WhisperTranscriber",
    "Transcription",
    "VideoFile",
    "Word",
    "resize",
]


def __getattr__(name: str):
    try:
        module_name, object_name = _EXPORTS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    value = getattr(import_module(module_name, __name__), object_name)
    globals()[name] = value
    return value
