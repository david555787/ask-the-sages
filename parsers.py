"""Parse only the primary texts of Apology and Meditations, entirely offline."""

import re

from chunking import load_text, split_long_text, word_count


ROMANS = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII")
COLOPHONS = ("Among the Quadi at the Granua.[D]", "This in Carnuntum.[A]")


def record(text: str, work: str, section: str) -> dict:
    greek = work == "Apology"
    return {
        "text": text,
        "tradition": "greek" if greek else "stoic",
        "work": work,
        "section": section,
        "translator": "Benjamin Jowett" if greek else "George Long",
    }


def apology_paragraphs() -> list[str]:
    text = load_text("pg1656.txt")
    introduction = re.search(r"(?m)^INTRODUCTION\.$", text)
    if introduction is None:
        raise ValueError("Apology introduction heading not found")
    heading = re.search(r"(?m)^APOLOGY$", text[introduction.end() :])
    if heading is None:
        raise ValueError("Apology speech heading after introduction not found")
    speech = text[introduction.end() + heading.end() :].strip()
    if not speech.startswith("How you, O Athenians,"):
        raise ValueError("Unexpected Apology speech opening")
    return [" ".join(p.split()) for p in re.split(r"\n\s*\n", speech) if p.strip()]


def parse_apology() -> list[dict]:
    """Merge short adjacent paragraphs without renumbering the source units.

    A merged chunk uses the number of its first original paragraph. Split parts
    repeat their original paragraph number. A short paragraph can join its
    preceding or following whole paragraph, never a fragment of a long one.
    """
    units = []
    for number, paragraph in enumerate(apology_paragraphs(), 1):
        if units and (word_count(paragraph) < 40 or word_count(units[-1][1]) < 40):
            combined = units[-1][1] + " " + paragraph
            if word_count(combined) <= 150:
                units[-1] = (units[-1][0], combined)
                continue
        units.append((number, paragraph))
    chunks = []
    for number, text in units:
        for part in split_long_text(text):
            chunks.append(record(part, "Apology", f"paragraph {number}"))
    return chunks


def meditations_books() -> list[str]:
    text = load_text("pg15877.txt")
    philosophy = re.search(r"(?m)^THE PHILOSOPHY$", text)
    if philosophy is None:
        raise ValueError("Meditations philosophy heading not found")
    thoughts = re.search(r"(?m)^THE THOUGHTS$", text[philosophy.end() :])
    if thoughts is None:
        raise ValueError("Meditations primary-text heading not found")
    start = philosophy.end() + thoughts.end()
    end = re.search(r"(?m)^INDEXES\.$", text[start:])
    if end is None:
        raise ValueError("Meditations indexes boundary not found")
    body = text[start : start + end.start()]
    headings = list(re.finditer(r"(?m)^([IVX]+)\.$", body))
    assert [h.group(1) for h in headings] == list(ROMANS), "Expected exactly 12 ordered books"
    return [
        body[h.end() : headings[i + 1].start() if i + 1 < len(headings) else len(body)]
        for i, h in enumerate(headings)
    ]


def clean_meditations_book(text: str) -> str:
    lines = []
    in_footnote = False
    for line in text.splitlines():
        # Three Book VII footnotes also start at column zero.
        if re.match(r"^\s*\[[A-Z]\](?:\s|$)", line):
            in_footnote = True
            continue
        if in_footnote:
            if not line.strip() or line[:1].isspace():
                continue
            in_footnote = False
        if line.strip() in COLOPHONS:
            continue
        lines.append(line)
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\[Greek:.*?\]", "", cleaned, flags=re.S)
    return re.sub(r"\[[A-Z]\]", "", cleaned)


def meditations_items() -> list[tuple[int, int, str]]:
    units = []
    for book, raw in enumerate(meditations_books(), 1):
        cleaned = clean_meditations_book(raw).strip()
        markers = list(re.finditer(r"(?m)^(\d+)\.\s+", cleaned))
        numbers = [int(m.group(1)) for m in markers]
        assert numbers == list(range(2, len(numbers) + 2)), f"Unexpected numbering in Book {book}"
        first = cleaned[: markers[0].start()] if markers else cleaned
        assert first.strip(), f"Missing unnumbered first item in Book {book}"
        units.append((book, 1, " ".join(first.split())))
        for i, marker in enumerate(markers):
            end = markers[i + 1].start() if i + 1 < len(markers) else len(cleaned)
            units.append((book, int(marker.group(1)), " ".join(cleaned[marker.end() : end].split())))
    return units


def parse_meditations() -> list[dict]:
    chunks = []
    for book, item, text in meditations_items():
        for part in split_long_text(text):
            chunks.append(record(part, "Meditations", f"Book {book}, item {item}"))
    return chunks
