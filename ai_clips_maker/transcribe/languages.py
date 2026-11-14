"""Language choices exposed by the installed Faster-Whisper backend."""

FASTER_WHISPER_LANGUAGE_CODES = frozenset({
    "af",
    "de",
    "en",
    "es",
    "fr",
    "it",
    "ja",
    "nl",
    "pt",
    "uk",
    "zh",
})

SOUTH_AFRICAN_LANGUAGE_OPTIONS = (
    {"code": "af", "name": "Afrikaans", "supported": True},
    {"code": "zu", "name": "isiZulu", "supported": False},
    {"code": "xh", "name": "isiXhosa", "supported": False},
    {"code": "nso", "name": "Sepedi", "supported": False},
    {"code": "tn", "name": "Setswana", "supported": False},
    {"code": "st", "name": "Sesotho", "supported": False},
    {"code": "ts", "name": "itsonga", "supported": False},
    {"code": "ss", "name": "siSwati", "supported": False},
    {"code": "ve", "name": "Tshivenda", "supported": False},
    {"code": "nr", "name": "isiNdebele", "supported": False},
)

LANGUAGE_NAMES = {
    "de": "German",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "it": "Italian",
    "ja": "Japanese",
    "nl": "Dutch",
    "pt": "Portuguese",
    "uk": "Ukrainian",
    "zh": "Chinese",
}
LANGUAGE_NAMES.update({
    option["code"]: option["name"]
    for option in SOUTH_AFRICAN_LANGUAGE_OPTIONS
})

LANGUAGE_OPTIONS = tuple(
    {"code": code, "name": name, "supported": code in FASTER_WHISPER_LANGUAGE_CODES}
    for code, name in LANGUAGE_NAMES.items()
)
