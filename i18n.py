"""Tiny JSON-backed i18n helper.

Translation dictionaries live in translations/<lang>.json. Any language
code can be requested - if no file exists for it, or a key is missing,
we fall back to English. This keeps the schema "open": adding support for
a new country is just dropping in another JSON file.
"""

import json
import os

TRANSLATIONS_DIR = os.path.join(os.path.dirname(__file__), "translations")
DEFAULT_LANGUAGE = "en"

SUPPORTED_LANGUAGES = {
    "en": "English",
    "bn": "বাংলা (Bangla)",
    "es": "Español",
    "ro": "Română",
}

_cache = {}


def _load(lang):
    if lang in _cache:
        return _cache[lang]
    path = os.path.join(TRANSLATIONS_DIR, f"{lang}.json")
    if not os.path.exists(path):
        _cache[lang] = {}
        return _cache[lang]
    with open(path, encoding="utf-8") as fh:
        _cache[lang] = json.load(fh)
    return _cache[lang]


def translate(key, lang=DEFAULT_LANGUAGE):
    strings = _load(lang)
    if key in strings:
        return strings[key]
    if lang != DEFAULT_LANGUAGE:
        return _load(DEFAULT_LANGUAGE).get(key, key)
    return key
