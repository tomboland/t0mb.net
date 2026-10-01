"""Pure data helpers for the cinema command-line tools (no rendering)."""
from pathlib import Path
import re
import unicodedata

ROOT = Path(__file__).resolve().parents[1]


def slug(value):
    text = unicodedata.normalize('NFKD', str(value)).encode('ascii', 'ignore').decode().lower()
    return re.sub('[^a-z0-9]+', '-', text).strip('-')


def normalise_tags(values):
    if not isinstance(values, list):
        raise ValueError('Film tags must be a list of non-empty strings')
    unique = {}
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError('Film tags must be a list of non-empty strings')
        label = unicodedata.normalize('NFC', ' '.join(value.split()))
        unique.setdefault(label.casefold(), label)
    return sorted(unique.values(), key=str.casefold)


def validate_rating(value):
    if value in (None, ''):
        return
    number = float(value)
    if not 0.5 <= number <= 5 or number * 2 != int(number * 2):
        raise ValueError(f'Invalid rating: {value}')
