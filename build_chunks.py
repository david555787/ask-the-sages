"""Build deterministic JSONL chunks from the two local primary texts."""

import json
from pathlib import Path
import random
import re
from statistics import mean

from chunking import word_count
from parsers import meditations_books, parse_apology, parse_meditations


OUTPUT = Path(__file__).resolve().parent / "data" / "processed" / "chunks.jsonl"


def main() -> None:
    assert len(meditations_books()) == 12
    works = [("apology", parse_apology()), ("meditations", parse_meditations())]
    all_chunks = []
    for slug, chunks in works:
        for number, chunk in enumerate(chunks, 1):
            chunk["id"] = f"{slug}-{number:04d}"
            assert 0 < word_count(chunk["text"]) <= 150, chunk["id"]
            assert "[Greek" not in chunk["text"], chunk["id"]
            assert "[A]" not in chunk["text"], chunk["id"]
            assert not re.search(r"\bINDEX\b", chunk["text"], re.I), chunk["id"]
        all_chunks.extend(chunks)

    # Validate both works before writing any output.
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="\n") as target:
        for chunk in all_chunks:
            target.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    rng = random.Random(0)
    for _, chunks in works:
        counts = [word_count(chunk["text"]) for chunk in chunks]
        print(f"\n{chunks[0]['work']}: {len(chunks)} chunks")
        print(f"Words min/average/max: {min(counts)}/{mean(counts):.2f}/{max(counts)}")
        print("First 3 chunks:")
        for chunk in chunks[:3]:
            print(json.dumps(chunk, ensure_ascii=False, indent=2))
        print("3 random chunks (seed 0):")
        for chunk in rng.sample(chunks, min(3, len(chunks))):
            print(json.dumps(chunk, ensure_ascii=False, indent=2))
    print(f"\nWrote {len(all_chunks)} chunks to {OUTPUT}")


if __name__ == "__main__":
    main()
