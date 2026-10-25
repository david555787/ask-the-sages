"""Offline loading and sentence-preserving chunk helpers."""

from pathlib import Path
import re

from download_data import strip_boilerplate


RAW_DIR = Path(__file__).resolve().parent / "data" / "raw"


def load_text(filename: str) -> str:
    """Read an existing raw file, normalize CRLF, and strip Gutenberg markers.

    Importing download_data does not call its main function or use the network.
    Missing files raise FileNotFoundError; this function never downloads them.
    """
    with (RAW_DIR / filename).open(encoding="utf-8-sig", newline="") as source:
        return strip_boilerplate(source.read().replace("\r\n", "\n"))


def word_count(text: str) -> int:
    """Count whitespace-separated words consistently throughout the pipeline."""
    return len(text.split())


def sentences(text: str) -> list[str]:
    """Find sentence endings, including closing quotes and Victorian -- joins.

    This is a punctuation heuristic, with common abbreviations and Roman-numeral
    citations protected. It does not treat semicolons or commas as sentence ends.
    """
    text = " ".join(text.split())
    result = []
    start = 0
    for match in re.finditer(r'''[.!?]+["'”’\)\]]*(?=\s|--|—|$)''', text):
        prefix = text[: match.start() + 1]
        if text[match.start()] == "." and re.search(
            r"\b(?:Mr|Mrs|Ms|Dr|St|Prof|etc|vs|[ivx]+)\.$", prefix, re.I
        ):
            continue
        result.append(text[start : match.end()].strip())
        start = match.end()
    if text[start:].strip():
        result.append(text[start:].strip())
    return [part for part in result if part]


def _split_oversized_sentence(text: str, max_words: int, level: int = 0) -> list[str]:
    """Use the authorized clause fallback: semicolons, then colons, then commas."""
    if word_count(text) <= max_words:
        return [text]
    punctuation = (";", ":", ",")
    if level == len(punctuation):
        raise ValueError(f"No clause boundary can satisfy max_words={max_words}: {text}")
    parts = re.split(rf"(?<={punctuation[level]})\s+", text)
    return [
        smaller
        for part in parts
        for smaller in _split_oversized_sentence(part, max_words, level + 1)
    ]


def split_long_text(text: str, max_words: int = 150) -> list[str]:
    """Pack sentences up to max_words, using clauses only for oversized ones.

    Never split inside a word. An oversized sentence is split at semicolons,
    then colons and commas only as needed, as authorized for these source texts.
    Raise ValueError if even those boundaries cannot satisfy the word cap.
    """
    if max_words < 1:
        raise ValueError("max_words must be positive")
    normalized = " ".join(text.split())
    if not normalized:
        return []
    if word_count(normalized) <= max_words:
        return [normalized]
    chunks = []
    current = ""
    parts = [
        part for sentence in sentences(normalized)
        for part in _split_oversized_sentence(sentence, max_words)
    ]
    for sentence in parts:
        candidate = f"{current} {sentence}".strip()
        if current and word_count(candidate) > max_words:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks
