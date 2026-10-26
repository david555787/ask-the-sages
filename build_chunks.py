"""Build deterministic JSONL chunks from four local primary texts."""

import json
from itertools import groupby
from pathlib import Path
import random
import re
from statistics import mean

from chunking import load_text, word_count
from parsers import (
    contains_cjk, meditations_books, parse_analects, parse_apology,
    parse_meditations, parse_tao_te_ching,
)


OUTPUT = Path(__file__).resolve().parent / "data" / "processed" / "chunks.jsonl"


def mark_split_parts(chunks: list[dict]) -> tuple[int, int]:
    """Label repeated source sections without changing existing parser functions.

    New parsers already label their parts; using the base section handles both.
    Return the number of split source units and the number of resulting pieces.
    """
    split_units = pieces = 0
    for section, group in groupby(
        chunks, key=lambda chunk: re.sub(r", part \d+/\d+$", "", chunk["section"])
    ):
        parts = list(group)
        if len(parts) > 1:
            split_units += 1
            pieces += len(parts)
            for i, chunk in enumerate(parts, 1):
                chunk["section"] = f"{section}, part {i}/{len(parts)}"
            sizes = [word_count(chunk["text"]) for chunk in parts]
            if min(sizes) < 25:
                print(f"Cannot satisfy 25–150 words at allowed boundaries: {parts[0]['work']}, {section}: {sizes}")
    return split_units, pieces


def main() -> None:
    assert len(meditations_books()) == 12
    works = [
        ("apology", parse_apology()), ("meditations", parse_meditations()),
        ("analects", parse_analects()), ("tao-te-ching", parse_tao_te_ching()),
    ]
    print("Analects ending (last 12 nonblank English lines, through end of stripped file):")
    ending = [line for line in load_text("pg4094.txt").splitlines() if line.strip() and not contains_cjk(line)]
    print("\n".join(ending[-12:]))
    splits = {}
    all_chunks = []
    for slug, chunks in works:
        splits[slug] = mark_split_parts(chunks)
        for number, chunk in enumerate(chunks, 1):
            chunk["id"] = f"{slug}-{number:04d}"
            assert 0 < word_count(chunk["text"]) <= 150, chunk["id"]
            assert "_" not in chunk["text"], chunk["id"]
            assert "[Greek" not in chunk["text"], chunk["id"]
            assert "[A]" not in chunk["text"], chunk["id"]
            assert not re.search(r"\bINDEX\b", chunk["text"], re.I), chunk["id"]
            if slug == "analects":
                assert not contains_cjk(chunk["text"]), chunk["id"]
        all_chunks.extend(chunks)
    assert len({chunk["id"] for chunk in all_chunks}) == len(all_chunks), "Duplicate chunk IDs"

    # Validate all four works before writing any output.
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="\n") as target:
        for chunk in all_chunks:
            target.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    rng = random.Random(0)
    for slug, chunks in works:
        counts = [word_count(chunk["text"]) for chunk in chunks]
        print(f"\n{chunks[0]['work']}: {len(chunks)} chunks")
        print(f"Words min/average/max: {min(counts)}/{mean(counts):.2f}/{max(counts)}")
        print(f"Chunks shorter than 25 words: {sum(count < 25 for count in counts)}")
        units, pieces = splits[slug]
        print(f"Split source units: {units}; resulting part-labelled chunks: {pieces}")
        print("First 3 chunks:")
        for chunk in chunks[:3]:
            print(json.dumps(chunk, ensure_ascii=False, indent=2))
        print("3 random chunks (seed 0):")
        for chunk in rng.sample(chunks, min(3, len(chunks))):
            print(json.dumps(chunk, ensure_ascii=False, indent=2))
    tiny = [chunk for chunk in all_chunks if word_count(chunk["text"]) < 25]
    if len(tiny) <= 15:
        print("\nAll chunks shorter than 25 words:")
        for chunk in tiny:
            print(f"{chunk['work']} — {chunk['section']}: {chunk['text']}")
    else:
        print(f"\n{len(tiny)} chunks are shorter than 25 words; full listing omitted (more than 15).")
    print("Confirmed: no text contains underscores; all IDs are unique.")
    print(f"\nWrote {len(all_chunks)} chunks to {OUTPUT}")


if __name__ == "__main__":
    main()
