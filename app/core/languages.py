LANG_INSTRUCTION = {
    "auto": "the same language as the source content",
    "ar": "العربية (Arabic)",
    "de": "Deutsch (German)",
    "en": "English",
    "es": "Español (Spanish)",
    "fi": "Suomi (Finnish)",
    "fr": "Français (French)",
    "hi": "हिन्दी (Hindi)",
    "id": "Bahasa Indonesia",
    "it": "Italiano (Italian)",
    "ja": "日本語 (Japanese)",
    "ko": "한국어 (Korean)",
    "nl": "Nederlands (Dutch)",
    "pl": "Polski (Polish)",
    "pt": "Português (Portuguese)",
    "ru": "Русский (Russian)",
    "sv": "Svenska (Swedish)",
    "th": "ภาษาไทย (Thai)",
    "tr": "Türkçe (Turkish)",
    "uk": "Українська (Ukrainian)",
    "vi": "Tiếng Việt (Vietnamese)",
    "zh": "简体中文 (Chinese)",
}

# Output quality in these depends on how proficient the chosen model is.
LANG_EXPERIMENTAL = {
    "ja", "ko", "it", "nl", "pl", "tr",
    "hi", "vi", "uk", "fi", "sv", "th",
}

AUDIENCE_INSTRUCTION = {
    "beginner": "Assume the reader has no prior knowledge of the topic. Explain foundational concepts before building on them.",
    "intermediate": "Assume the reader has basic familiarity with the topic. Focus on practical application over fundamentals.",
    "advanced": "Assume the reader is experienced. Skip basics, focus on nuance and edge cases.",
}

AUDIENCE_LEVEL = {"beginner": 1, "intermediate": 2, "advanced": 3}


def language_options() -> list[dict]:
    return [
        {"value": code, "label": name, "experimental": code in LANG_EXPERIMENTAL}
        for code, name in LANG_INSTRUCTION.items()
    ]


def audience_options() -> list[dict]:
    return [
        {"value": level, "label": level.title(), "description": text}
        for level, text in AUDIENCE_INSTRUCTION.items()
    ]
