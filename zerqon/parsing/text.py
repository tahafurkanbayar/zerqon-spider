"""Metin normalizasyonu, kelime sayımı, içerik hash'leri ve SimHash (bkz. ADR-013)."""

from __future__ import annotations

import hashlib
import re
import unicodedata

_WORD_RE = re.compile(r"[^\W_]+(?:['’-][^\W_]+)*", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")
MAX_SHINGLES = 6000
SIMHASH_BITS = 64


def collapse_ws(text: str | None) -> str:
    return _SPACE_RE.sub(" ", text or "").strip()


def words(text: str) -> list[str]:
    return _WORD_RE.findall(text)


def word_count(text: str) -> int:
    return len(words(text))


def normalize_for_hash(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(words(text))


def text_hash(text: str) -> str | None:
    normalized = normalize_for_hash(text)
    if not normalized:
        return None
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def _hash64(value: str) -> int:
    return int.from_bytes(hashlib.blake2b(value.encode("utf-8"), digest_size=8).digest(), "big")


def simhash(text: str, shingle_size: int = 3) -> int | None:
    """64-bit SimHash; SQLite INTEGER sığsın diye işaretli tamsayı döner."""
    tokens = normalize_for_hash(text).split()
    if len(tokens) < shingle_size:
        return None
    vector = [0] * SIMHASH_BITS
    count = 0
    for i in range(len(tokens) - shingle_size + 1):
        h = _hash64(" ".join(tokens[i : i + shingle_size]))
        for bit in range(SIMHASH_BITS):
            vector[bit] += 1 if (h >> bit) & 1 else -1
        count += 1
        if count >= MAX_SHINGLES:
            break
    value = 0
    for bit in range(SIMHASH_BITS):
        if vector[bit] > 0:
            value |= 1 << bit
    return value - (1 << 64) if value >= (1 << 63) else value


def to_unsigned(value: int) -> int:
    return value + (1 << 64) if value < 0 else value


def hamming(a: int, b: int) -> int:
    return bin(to_unsigned(a) ^ to_unsigned(b)).count("1")


def simhash_bands(value: int, bands: int = 4) -> list[tuple[int, int]]:
    """LSH bantları: (bant indeksi, 16-bit değer)."""
    unsigned = to_unsigned(value)
    width = SIMHASH_BITS // bands
    mask = (1 << width) - 1
    return [(i, (unsigned >> (i * width)) & mask) for i in range(bands)]
