"""Field normalisation utilities shared across connectors.

Provides helpers for normalising DOI strings, dates, and language codes.
All web-scraping-specific parsing (HTML extraction, author/keyword
parsing, paper assembly from ``<meta>`` tags) lives in
:class:`~findpapers.connectors.web_scraping.WebScrapingConnector`.
"""

from __future__ import annotations

from datetime import date, datetime

# ---------------------------------------------------------------------------
# DOI utilities
# ---------------------------------------------------------------------------

# doi.org URL prefixes that some databases add before the bare DOI.
DOI_URL_PREFIXES = (
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "http://dx.doi.org/",
)

# Protocol-only prefix used in some DC metadata fields (e.g. dc.identifier)
# and some publishers' citation_doi tags.  The "doi:" scheme is defined in
# RFC 3986 and used by many publishers without a space after the colon.
_DOI_PROTOCOL_PREFIXES = ("doi:10.",)


def normalize_doi(raw: str) -> str | None:
    """Strip doi.org URL prefixes and return a bare DOI, or ``None`` if invalid.

    Handles the following input forms:

    * Bare DOI: ``"10.1234/example"``
    * URL form: ``"https://doi.org/10.1234/example"``
    * Protocol prefix: ``"doi:10.1234/example"`` (used in Dublin Core
      ``dc.identifier`` fields by many publishers)

    Parameters
    ----------
    raw : str
        Raw DOI string (may include a ``https://doi.org/`` or ``doi:`` prefix).

    Returns
    -------
    str | None
        Bare DOI starting with ``10.``, or ``None`` when the value is not a
        recognisable DOI.
    """
    value = raw.strip()
    # Strip URL-form prefixes first.
    for prefix in DOI_URL_PREFIXES:
        if value.lower().startswith(prefix):
            value = value[len(prefix) :]
            break
    else:
        # Strip protocol-only prefix (doi:10. / doi: 10.).
        low = value.lower()
        for prefix in _DOI_PROTOCOL_PREFIXES:
            if low.startswith(prefix):
                # Keep the "10." part: remove only the "doi:" / "doi: " part.
                value = value[prefix.index("1") :]
                break
    return value if value.startswith("10.") else None


# ---------------------------------------------------------------------------
# Date utilities
# ---------------------------------------------------------------------------


def parse_date(value: str | None) -> date | None:
    """Parse a date string into a :class:`datetime.date`.

    Tries several common metadata date formats in order:

    * Numeric-only formats (matched against the first 10 characters):
      ``YYYY-MM-DD``, ``YYYY/MM/DD``, ``YYYY-MM``, ``YYYY/MM``, ``YYYY``.
    * Full-string formats with written month names (e.g. ``"November 1998"``,
      ``"Oct 4, 2017"``).

    Parameters
    ----------
    value : str | None
        Date string.

    Returns
    -------
    date | None
        Parsed date, or ``None`` when parsing fails.
    """
    if not value:
        return None
    value = value.strip()
    # Numeric formats: slice to 10 chars to tolerate trailing time/timezone.
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m", "%Y/%m", "%Y"):
        try:
            return datetime.strptime(value[:10], fmt).date()
        except ValueError:
            continue
    # US-style numeric format MM/DD/YYYY (used by PubMed's citation_date).
    for fmt in ("%m/%d/%Y",):
        try:
            return datetime.strptime(value[:10], fmt).date()
        except ValueError:
            continue
    # Written month-name formats: must match the full string.
    # Includes both "Month YYYY" and "YYYY Month" variants (e.g. PubMed's
    # citation_date uses "2023 Dec", year first followed by abbreviated month).
    for fmt in (
        "%B %d, %Y",
        "%b %d, %Y",
        "%B %Y",
        "%b %Y",
        "%Y %B",
        "%Y %b",
        "%d %B %Y",
        "%d %b %Y",
    ):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Language normalisation
# ---------------------------------------------------------------------------

# Mapping from ISO 639-2 terminological (T) and bibliographic (B) 3-letter codes
# to their ISO 639-1 2-letter equivalents.
_ISO_639_2_TO_1: dict[str, str] = {
    "eng": "en",
    "fra": "fr",
    "fre": "fr",  # bibliographic variant
    "deu": "de",
    "ger": "de",  # bibliographic variant
    "spa": "es",
    "por": "pt",
    "ita": "it",
    "nld": "nl",
    "dut": "nl",  # bibliographic variant
    "rus": "ru",
    "zho": "zh",
    "chi": "zh",  # bibliographic variant
    "jpn": "ja",
    "kor": "ko",
    "ara": "ar",
    "tur": "tr",
    "pol": "pl",
    "ces": "cs",
    "cze": "cs",  # bibliographic variant
    "slk": "sk",
    "slo": "sk",  # bibliographic variant
    "hun": "hu",
    "ron": "ro",
    "rum": "ro",  # bibliographic variant
    "bul": "bg",
    "hrv": "hr",
    "swe": "sv",
    "nor": "no",
    "nob": "no",
    "nno": "nn",
    "dan": "da",
    "fin": "fi",
    "heb": "he",
    "ind": "id",
    "msa": "ms",
    "may": "ms",  # bibliographic variant
    "vie": "vi",
    "tha": "th",
    "fas": "fa",
    "per": "fa",  # bibliographic variant
    "ukr": "uk",
    "cat": "ca",
    "slv": "sl",
    "srp": "sr",
    "ell": "el",
    "gre": "el",  # bibliographic variant
    "lat": "la",
    "ben": "bn",
    "hin": "hi",
    "tam": "ta",
    "tel": "te",
    "mar": "mr",
    "urd": "ur",
    "swa": "sw",
    "mlt": "mt",
    "lit": "lt",
    "lav": "lv",
    "est": "et",
    "isl": "is",
    "ice": "is",  # bibliographic variant
    "gle": "ga",
    "bos": "bs",
    "mkd": "mk",
    "mac": "mk",  # bibliographic variant
    "alb": "sq",
    "sqi": "sq",
    "bel": "be",
    "glg": "gl",
    "eus": "eu",
    "afr": "af",
    "amh": "am",
    "hau": "ha",
    "yor": "yo",
    "ibo": "ig",
    "zul": "zu",
    "xho": "xh",
    "sna": "sn",
    "som": "so",
    "kin": "rw",
    "nep": "ne",
    "sin": "si",
    "khm": "km",
    "lao": "lo",
    "mya": "my",
    "bur": "my",  # bibliographic variant
    "mon": "mn",
    "kaz": "kk",
    "uzb": "uz",
    "aze": "az",
    "geo": "ka",
    "kat": "ka",
    "hye": "hy",
    "arm": "hy",  # bibliographic variant
    "mri": "mi",
    "mao": "mi",  # bibliographic variant
    "tgl": "tl",
    "jav": "jv",
    "sun": "su",
}

_LANGUAGE_NAME_TO_1: dict[str, str] = {
    "english": "en",
    "french": "fr",
    "german": "de",
    "spanish": "es",
    "portuguese": "pt",
    "italian": "it",
    "dutch": "nl",
    "russian": "ru",
    "chinese": "zh",
    "japanese": "ja",
    "korean": "ko",
    "arabic": "ar",
    "turkish": "tr",
    "polish": "pl",
    "czech": "cs",
    "slovak": "sk",
    "hungarian": "hu",
    "romanian": "ro",
    "bulgarian": "bg",
    "croatian": "hr",
    "swedish": "sv",
    "norwegian": "no",
    "danish": "da",
    "finnish": "fi",
    "hebrew": "he",
    "indonesian": "id",
    "malay": "ms",
    "vietnamese": "vi",
    "thai": "th",
    "persian": "fa",
    "farsi": "fa",
    "ukrainian": "uk",
    "catalan": "ca",
    "slovenian": "sl",
    "serbian": "sr",
    "greek": "el",
    "latin": "la",
    "bengali": "bn",
    "hindi": "hi",
    "tamil": "ta",
    "telugu": "te",
    "marathi": "mr",
    "urdu": "ur",
    "swahili": "sw",
    "maltese": "mt",
    "lithuanian": "lt",
    "latvian": "lv",
    "estonian": "et",
    "icelandic": "is",
    "irish": "ga",
    "bosnian": "bs",
    "macedonian": "mk",
    "albanian": "sq",
    "belarusian": "be",
    "galician": "gl",
    "basque": "eu",
    "afrikaans": "af",
}

# Valid ISO 639-1 2-letter codes used as a passthrough guard.
_VALID_ISO_639_1: frozenset[str] = frozenset(_ISO_639_2_TO_1.values())


def normalize_language(value: str | None) -> str | None:
    """Normalise a language identifier to an ISO 639-1 2-letter code.

    Accepts ISO 639-1 2-letter codes (``"en"``), ISO 639-2 3-letter codes
    (terminological and bibliographic, e.g. ``"eng"``, ``"fre"``), and common
    full English language names (``"English"``, ``"french"``).

    Parameters
    ----------
    value : str | None
        Raw language value coming from an upstream API.

    Returns
    -------
    str | None
        Lower-cased ISO 639-1 2-letter code, or ``None`` when the input is
        empty or cannot be recognised.

    Examples
    --------
    >>> normalize_language("eng")
    'en'
    >>> normalize_language("EN")
    'en'
    >>> normalize_language("English")
    'en'
    >>> normalize_language("unknown_lang")
    None
    """
    if not value:
        return None
    lowered = value.strip().lower()
    if not lowered:
        return None

    if lowered in _VALID_ISO_639_1:
        return lowered

    if len(lowered) == 3 and lowered in _ISO_639_2_TO_1:
        return _ISO_639_2_TO_1[lowered]

    if lowered in _LANGUAGE_NAME_TO_1:
        return _LANGUAGE_NAME_TO_1[lowered]

    return None
