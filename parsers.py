"""Parse four local primary texts entirely offline."""

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


def contains_cjk(text: str) -> bool:
    """Detect CJK scripts, radicals, compatibility forms, and wide punctuation."""
    ranges = (
        (0x1100, 0x11FF), (0x2E80, 0xA4CF), (0xA960, 0xA97F),
        (0xAC00, 0xD7FF), (0xF900, 0xFAFF), (0xFE10, 0xFE1F),
        (0xFE30, 0xFE4F), (0xFF00, 0xFFEF), (0x1B000, 0x1B2FF),
        (0x20000, 0x323AF),
    )
    return any(low <= ord(char) <= high for char in text for low, high in ranges)


def _roman_number(roman: str) -> int:
    values = {"I": 1, "V": 5, "X": 10, "L": 50}
    total = 0
    for i, char in enumerate(roman):
        value = values[char]
        total += -value if i + 1 < len(roman) and value < values[roman[i + 1]] else value
    return total


def _legge_record(text: str, work: str, section: str) -> dict:
    return {
        "text": text,
        "tradition": "confucian" if work == "Analects" else "daoist",
        "work": work,
        "section": section,
        "translator": "James Legge",
    }


def _legge_parts(text: str, work: str, section: str) -> list[dict]:
    parts = split_long_text(text)
    return [
        _legge_record(part, work, section + (f", part {i}/{len(parts)}" if len(parts) > 1 else ""))
        for i, part in enumerate(parts, 1)
    ]


def analects_chapters() -> list[list[str]]:
    """Filter whole Chinese lines before detecting English chapter boundaries.

    Source Roman chapter labels contain typos; chapter positions define the
    section numbers. Every discrepancy is printed for inspection.
    """
    text = load_text("pg4094.txt")
    english = "\n".join(line for line in text.splitlines() if not contains_cjk(line))
    # This edition has one standalone editorial locator before Book XVII, I.
    english = re.sub(r"(?m)^\[17\.1\][ \t]*$", "", english)
    headings = list(re.finditer(r"(?m)^BOOK ([IVX]+)\.[^\n]*$", english))
    assert [_roman_number(h.group(1)) for h in headings] == list(range(1, 21)), "Expected 20 Analects books"
    books = []
    for book, heading in enumerate(headings, 1):
        end = headings[book].start() if book < len(headings) else len(english)
        body = english[heading.end() : end]
        markers = list(re.finditer(r"(?m)^[ \t]*CHAP(?:TER)?\.?[ \t]+([IVXL]+)\.?[ \t]+", body))
        assert markers, f"No chapters in Analects Book {book}"
        assert not body[: markers[0].start()].strip(), f"Unexpected Analects Book {book} preface"
        chapters = []
        for chapter, marker in enumerate(markers, 1):
            if _roman_number(marker.group(1)) != chapter:
                print(f"Analects heading mismatch: Book {book}, chapter {chapter} is printed {marker.group(1)}")
            stop = markers[chapter].start() if chapter < len(markers) else len(body)
            chapters.append(" ".join(body[marker.end() : stop].split()))
        books.append(chapters)
    return books


def parse_analects() -> list[dict]:
    """Merge whole chapters within a book up to 120 words; split long chapters."""
    chunks = []
    for book, chapters in enumerate(analects_chapters(), 1):
        pending = ""
        first = last = 0

        def flush() -> None:
            if pending:
                label = f"chapter {first}" if first == last else f"chapters {first}-{last}"
                chunks.extend(_legge_parts(pending, "Analects", f"Book {book}, {label}"))

        for chapter, text in enumerate(chapters, 1):
            candidate = f"{pending} {text}".strip()
            if pending and word_count(candidate) <= 120:
                pending = candidate
                last = chapter
                continue
            flush()
            pending = text
            first = last = chapter
        flush()
    assert all(not contains_cjk(chunk["text"]) for chunk in chunks)
    return chunks


def tao_chapters() -> list[str]:
    """Find explicit N. 1. starts, then infer missing chapters within anchors."""
    lines = load_text("pg216.txt").splitlines()
    explicit = []
    for i, line in enumerate(lines):
        match = re.match(r"^(?:Ch\.[ \t]+)?(\d+)\.[ \t]+1\.(?:[ \t]|$)", line)
        if match:
            explicit.append((int(match.group(1)), i))
    numbers = [n for n, _ in explicit]
    assert numbers == sorted(set(numbers)), "Repeated or unordered Tao chapter anchors"
    assert numbers[0] == 1 and numbers[-1] == 81
    known = dict(explicit)
    starts = dict(known)
    for chapter in range(1, 82):
        if chapter in known:
            continue
        left = max(n for n in known if n < chapter)
        right = min(n for n in known if n > chapter)
        candidates = [
            i for i in range(known[left] + 1, known[right])
            if re.match(rf"^{chapter}\.(?:[ \t]|$)", lines[i])
        ]
        assert len(candidates) == 1, f"Ambiguous Tao chapter {chapter}: {candidates}"
        starts[chapter] = candidates[0]
        print(f"Inferred Tao chapter {chapter}: stripped-text line {candidates[0] + 1}: {lines[candidates[0]]}")
    ordered = sorted(starts, key=starts.get)
    assert ordered == list(range(1, 82)), "Expected Tao chapters 1–81 once, in order"
    print("Tao excluded before chapter 1:")
    print("\n".join(lines[: starts[1]]).strip())
    # In this edition the final chapter ends with this verified final sentence.
    # Bound it explicitly so trailing material cannot join chapter 81 silently.
    final_line = "all the doing in the way of the sage he does not strive."
    endings = [i for i in range(starts[81], len(lines)) if lines[i].strip() == final_line]
    assert len(endings) == 1, "Tao final sentence changed; inspect the end boundary"
    end = endings[0] + 1
    tail = "\n".join(lines[end:])
    print("Tao excluded after chapter 81:", tail.strip() or "(blank lines only; Gutenberg footer already stripped)")
    chapters = []
    for chapter in range(1, 82):
        stop = starts[chapter + 1] if chapter < 81 else end
        chapter_lines = lines[starts[chapter] : stop]
        chapter_lines[0] = re.sub(r"^(?:Ch\.[ \t]+)?\d+\.[ \t]*", "", chapter_lines[0])
        kept = []
        for line in chapter_lines:
            if re.fullmatch(r"PART (?:[IVX]+|\d+)\.", line.strip()):
                print(f"Tao excluded structural heading: {line.strip()}")
                continue
            # Drop sub-paragraph numbering, including standalone verse labels.
            line = re.sub(r"^\d+\.[ \t]*", "", line)
            kept.append(line)
        chapters.append(" ".join(" ".join(kept).split()))
    return chapters


def parse_tao_te_ching() -> list[dict]:
    """Keep every prose and verse line, with each chapter an independent unit."""
    return [
        chunk for chapter, text in enumerate(tao_chapters(), 1)
        for chunk in _legge_parts(text, "Tao Te Ching", f"Chapter {chapter}")
    ]
