"""Output language and audience-level vocabulary shared by both tools."""

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

# Languages where output quality leans hard on the model's own proficiency.
LANG_EXPERIMENTAL = {
    "ja", "ko", "it", "nl", "pl", "tr",
    "hi", "vi", "uk", "fi", "sv", "th",
}

AUDIENCE_INSTRUCTION = {
    "beginner": "Assume the reader has no prior knowledge of the topic. Explain foundational concepts before building on them.",
    "intermediate": "Assume the reader has basic familiarity with the topic. Focus on practical application over fundamentals.",
    "advanced": "Assume the reader is experienced. Skip basics, focus on nuance and edge cases.",
}


def language_options() -> list[dict]:
    """Language catalogue in the shape the frontend renders it.

    `auto`'s instruction text is a sentence aimed at the model, not a menu
    entry, so it gets a short display name of its own.
    """
    return [
        {
            "code": code,
            "name": "preserve source language" if code == "auto" else name,
            "experimental": code in LANG_EXPERIMENTAL,
        }
        for code, name in LANG_INSTRUCTION.items()
    ]


def audience_options() -> list[dict]:
    return [{"level": level, "description": text} for level, text in AUDIENCE_INSTRUCTION.items()]
