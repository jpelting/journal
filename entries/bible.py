import json
import re
import urllib.parse
import urllib.request

from django.conf import settings

# Standard USFM 3-letter book codes.
USFM_BOOK_CODES = {
    "genesis": "GEN", "exodus": "EXO", "leviticus": "LEV", "numbers": "NUM",
    "deuteronomy": "DEU", "joshua": "JOS", "judges": "JDG", "ruth": "RUT",
    "1 samuel": "1SA", "2 samuel": "2SA", "1 kings": "1KI", "2 kings": "2KI",
    "1 chronicles": "1CH", "2 chronicles": "2CH", "ezra": "EZR", "nehemiah": "NEH",
    "esther": "EST", "job": "JOB", "psalm": "PSA", "psalms": "PSA",
    "proverbs": "PRO", "ecclesiastes": "ECC", "song of solomon": "SNG",
    "song of songs": "SNG", "isaiah": "ISA", "jeremiah": "JER",
    "lamentations": "LAM", "ezekiel": "EZK", "daniel": "DAN", "hosea": "HOS",
    "joel": "JOL", "amos": "AMO", "obadiah": "OBA", "jonah": "JON",
    "micah": "MIC", "nahum": "NAM", "habakkuk": "HAB", "zephaniah": "ZEP",
    "haggai": "HAG", "zechariah": "ZEC", "malachi": "MAL",
    "matthew": "MAT", "mark": "MRK", "luke": "LUK", "john": "JHN",
    "acts": "ACT", "romans": "ROM", "1 corinthians": "1CO", "2 corinthians": "2CO",
    "galatians": "GAL", "ephesians": "EPH", "philippians": "PHP",
    "colossians": "COL", "1 thessalonians": "1TH", "2 thessalonians": "2TH",
    "1 timothy": "1TI", "2 timothy": "2TI", "titus": "TIT", "philemon": "PHM",
    "hebrews": "HEB", "james": "JAS", "1 peter": "1PE", "2 peter": "2PE",
    "1 john": "1JN", "2 john": "2JN", "3 john": "3JN", "jude": "JUD",
    "revelation": "REV", "revelations": "REV",
}

REFERENCE_RE = re.compile(r"^(.*?)\s+(\d+)(?::(\d+(?:-\d+)?))?$")


def _to_usfm(reference):
    """Convert a human reference like 'Philippians 4:6-7' to USFM 'PHP.4.6-7', or None."""
    match = REFERENCE_RE.match(reference.strip())
    if not match:
        return None
    book, chapter, verses = match.groups()
    code = USFM_BOOK_CODES.get(book.strip().lower())
    if not code:
        return None
    return f"{code}.{chapter}.{verses}" if verses else f"{code}.{chapter}"


def get_passage_text(reference):
    """Fetch verse text for a human-readable reference (e.g. 'Philippians 4:6-7')
    from the configured translation, or None on any failure.

    Best-effort external call: an unparseable reference, missing App Key, or any
    network/API problem should degrade to no verse text rather than break whatever
    is saving the prompt.
    """
    if not settings.YVP_APP_KEY:
        return None
    usfm = _to_usfm(reference)
    if not usfm:
        return None
    url = (
        f"https://api.youversion.com/v1/bibles/{settings.BIBLE_VERSION_ID}"
        f"/passages/{urllib.parse.quote(usfm)}?format=text"
    )
    req = urllib.request.Request(url, headers={"X-YVP-App-Key": settings.YVP_APP_KEY})
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.load(response)
        return data["content"].strip()
    except Exception:
        return None
