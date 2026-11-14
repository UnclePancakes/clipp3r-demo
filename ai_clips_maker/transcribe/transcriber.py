"""
Faster-Whisper transcription with timed words for clip segmentation.

Key Features:
-------------
- Language auto-detection or manual selection (ISO 639-1)
- Word-level timestamps with character times interpolated within each word
- WhisperX: https://github.com/m-bain/whisperX
"""

from datetime import datetime
from collections.abc import Callable
import logging

# Internal imports
from .exceptions import NoSpeechError, TranscriberConfigError
from .languages import FASTER_WHISPER_LANGUAGE_CODES
from .transcription import Transcription
from ai_clips_maker.media.audio_file import AudioFile
from ai_clips_maker.media.editor import MediaEditor
from ai_clips_maker.utils.config_manager import ConfigManager
from ai_clips_maker.utils.pytorch import assert_valid_torch_device, get_compute_device
from ai_clips_maker.utils.type_checker import TypeChecker
from ai_clips_maker.utils.utils import find_missing_dict_keys

# External libraries
import torch
import whisperx
from faster_whisper import BatchedInferencePipeline, WhisperModel

LOGGER = logging.getLogger(__name__)


def _build_char_info(segments) -> list[dict]:
    char_info = []
    for segment in segments:
        words = segment.words or []
        if words:
            for word in words:
                text = word.word
                start = word.start if word.start is not None else segment.start
                end = word.end if word.end is not None else segment.end
                duration_per_char = (end - start) / max(len(text), 1)
                for index, char in enumerate(text):
                    char_info.append({
                        "char": char,
                        "start_time": start + index * duration_per_char,
                        "end_time": start + (index + 1) * duration_per_char,
                        "speaker": None,
                    })
        else:
            text = segment.text
            duration_per_char = (segment.end - segment.start) / max(len(text), 1)
            for index, char in enumerate(text):
                char_info.append({
                    "char": char,
                    "start_time": segment.start + index * duration_per_char,
                    "end_time": segment.start + (index + 1) * duration_per_char,
                    "speaker": None,
                })
    return char_info


class WhisperTranscriber:
    """
    Audio transcriber using Faster-Whisper models.
    """

    def __init__(self, model_size=None, device=None, precision=None) -> None:
        self._config = WhisperTranscriberConfig()
        self._type_checker = TypeChecker()

        self._device = device or get_compute_device()
        self._precision = precision or ("float16" if torch.cuda.is_available() else "int8")
        self._model_size = model_size or ("large-v2" if torch.cuda.is_available() else "tiny")

        assert_valid_torch_device(self._device)
        self._config.assert_valid_model_size(self._model_size)
        self._config.assert_valid_precision(self._precision)

        model = WhisperModel(
            self._model_size,
            device=self._device,
            compute_type=self._precision,
        )
        self._model = BatchedInferencePipeline(model=model)

    def transcribe(
        self,
        audio_path: str,
        lang: str = None,
        batch_size: int = 16,
        on_progress: Callable[[float], None] | None = None,
    ) -> Transcription:
        """
        Transcribes an audio or video file to text with word timestamps.
        """
        editor = MediaEditor()
        media = editor.instantiate_as_temporal_media_file(audio_path)
        media.assert_exists()
        media.assert_has_audio_stream()
        media_duration = media.get_duration()

        if lang:
            self._config.assert_valid_language(lang)

        # Request word timestamps so long recordings do not need full-audio alignment.
        raw_segments, transcription_info = self._model.transcribe(
            media.path,
            language=lang,
            batch_size=batch_size,
            vad_filter=True,
            word_timestamps=True,
            log_progress=on_progress is None,
        )
        language_probability = getattr(
            transcription_info,
            "language_probability",
            None,
        )
        if (
            lang is None
            and language_probability is not None
            and language_probability < 0.5
        ):
            LOGGER.warning(
                "Automatic language detection is uncertain (model probability %.2f); "
                "review the transcript and select a supported language if known.",
                language_probability,
            )
        transcribed_segments = []
        last_progress = 0.0
        for segment in raw_segments:
            transcribed_segments.append(segment)
            if on_progress and media_duration > 0:
                progress = min(1.0, max(0.0, float(segment.end) / media_duration))
                if progress >= 1.0 or progress - last_progress >= 0.01:
                    on_progress(progress)
                    last_progress = progress
        raw_segments = transcribed_segments
        if not raw_segments:
            raise NoSpeechError(f"No speech detected in: {media.path}")

        char_info = _build_char_info(raw_segments)
        if not char_info:
            raise NoSpeechError(f"No speech detected in: {media.path}")

        return Transcription({
            "source_software": "faster-whisper",
            "time_created": datetime.now(),
            "language": transcription_info.language,
            "num_speakers": None,
            "char_info": char_info,
        })

    def detect_language(self, media_file: AudioFile) -> str:
        """
        Detects the spoken language in the media file.
        """
        self._type_checker.assert_type(media_file, "media_file", AudioFile)
        media_file.assert_exists()
        media_file.assert_has_audio_stream()
        audio = whisperx.load_audio(media_file.path)
        language, _, _ = self._model.model.detect_language(audio)
        return language


class WhisperTranscriberConfig(ConfigManager):
    """
    Configuration validator for WhisperTranscriber.
    """

    def check_valid_config(self, config: dict) -> str | None:
        required = {
            "language": self.check_valid_language,
            "model_size": self.check_valid_model_size,
            "precision": self.check_valid_precision,
        }

        missing = find_missing_dict_keys(config, required.keys())
        if missing:
            return f"Missing config keys: {missing}"

        for key, checker in required.items():
            if config[key] is None:
                continue
            msg = checker(config[key])
            if msg:
                return msg
        return None

    def get_valid_model_sizes(self) -> list[str]:
        return ["tiny", "base", "small", "medium", "large-v1", "large-v2"]

    def get_valid_languages(self) -> list[str]:
        return sorted(FASTER_WHISPER_LANGUAGE_CODES)

    def get_valid_precisions(self) -> list[str]:
        return ["float32", "float16", "int8"]

    def check_valid_model_size(self, size: str) -> str | None:
        if size not in self.get_valid_model_sizes():
            return f"Invalid model size '{size}'. Valid options: {self.get_valid_model_sizes()}"
        return None

    def check_valid_language(self, code: str) -> str | None:
        if code not in self.get_valid_languages():
            return f"Invalid language code '{code}'. Valid options: {self.get_valid_languages()}"
        return None

    def check_valid_precision(self, precision: str) -> str | None:
        if precision not in self.get_valid_precisions():
            return f"Invalid precision '{precision}'. Valid: {self.get_valid_precisions()}"
        return None

    def assert_valid_model_size(self, size: str) -> None:
        msg = self.check_valid_model_size(size)
        if msg:
            raise TranscriberConfigError(msg)

    def assert_valid_language(self, code: str) -> None:
        msg = self.check_valid_language(code)
        if msg:
            raise TranscriberConfigError(msg)

    def assert_valid_precision(self, precision: str) -> None:
        msg = self.check_valid_precision(precision)
        if msg:
            raise TranscriberConfigError(msg)


TranscriberConfigManager = WhisperTranscriberConfig
