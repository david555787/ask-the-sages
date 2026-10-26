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
    """Try semicolons, colons, commas, then word boundaries as a last resort."""
    if word_count(text) <= max_words:
        return [text]
    punctuation = (";", ":", ",")
    if level == len(punctuation):
        # Expose all last-resort word boundaries to the balancing pass.
        return text.split()
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
    If those boundaries cannot satisfy the cap, split at a word boundary.
    Remove only italic underscores before segmentation. For long units, choose
    contiguous parts globally: first minimize the worst shortfall below 25
    words, then total shortfall, then part count, then squared word counts.
    Thus feasible parts all have 25–max_words words and are evenly balanced;
    impossible units retain the closest balance at the same allowed boundaries.
    """
    if max_words < 1:
        raise ValueError("max_words must be positive")
    normalized = " ".join(text.replace("_", "").split())
    if not normalized:
        return []
    if word_count(normalized) <= max_words:
        return [normalized]
    parts = [
        part for sentence in sentences(normalized)
        for part in _split_oversized_sentence(sentence, max_words)
    ]
    counts = [word_count(part) for part in parts]
    # Dynamic programming over allowed sentence/clause/last-resort word edges.
    # Search from the highest minimum down. This separates the minimax
    # objective from the additive objectives, preserving optimal substructure.
    for minimum in range(min(25, max_words), 0, -1):
        best = [None] * (len(parts) + 1)
        best[0] = (0, 0, 0)
        previous = [None] * (len(parts) + 1)
        for end in range(1, len(parts) + 1):
            count = 0
            for start in range(end - 1, -1, -1):
                count += counts[start]
                if count > max_words:
                    break
                if count < minimum or best[start] is None:
                    continue
                deficit, number, squares = best[start]
                candidate = (deficit + max(0, 25 - count), number + 1, squares + count * count)
                if best[end] is None or candidate < best[end]:
                    best[end] = candidate
                    previous[end] = start
        if best[-1] is not None:
            chunks = []
            end = len(parts)
            while end:
                start = previous[end]
                chunks.append(" ".join(parts[start:end]))
                end = start
            return list(reversed(chunks))
    raise AssertionError("Allowed boundaries could not produce any partition")
