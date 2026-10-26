"""Embed local chunks into the persistent sages collection using stable IDs."""

from collections import Counter
import json
from pathlib import Path
from time import perf_counter

import chromadb

from chunking import word_count


INPUT = Path(__file__).resolve().parent / "data" / "processed" / "chunks.jsonl"
BATCH_SIZE = 100
FIRST_BATCH_SIZE = 50
METADATA_FIELDS = ("tradition", "work", "section", "translator")


def read_chunks() -> list[dict]:
    """Validate the entire input before creating or modifying a collection."""
    chunks = []
    for line_number, line in enumerate(INPUT.read_text(encoding="utf-8").splitlines(), 1):
        chunk = json.loads(line)
        if not isinstance(chunk["id"], str) or not chunk["id"]:
            raise ValueError(f"Invalid ID on line {line_number}")
        if not isinstance(chunk["text"], str) or not chunk["text"].strip():
            raise ValueError(f"Invalid text on line {line_number}")
        if not all(isinstance(chunk[field], str) and chunk[field] for field in METADATA_FIELDS):
            raise ValueError(f"Invalid metadata on line {line_number}")
        chunks.append(chunk)
    if not chunks:
        raise ValueError("chunks.jsonl is empty")
    if len({chunk["id"] for chunk in chunks}) != len(chunks):
        raise ValueError("Duplicate IDs in chunks.jsonl")
    return chunks


def metadata(chunk: dict) -> dict:
    return {**{field: chunk[field] for field in METADATA_FIELDS}, "words": word_count(chunk["text"])}


def main() -> None:
    chunks = read_chunks()
    client = chromadb.PersistentClient(path="./chroma_store")
    collection = client.get_or_create_collection(name="sages")
    total = len(chunks)
    print(f"Input: {total} chunks; existing sages count: {collection.count()}", flush=True)

    def upsert_batch(start: int, stop: int) -> None:
        batch = chunks[start:stop]
        collection.upsert(
            ids=[chunk["id"] for chunk in batch],
            documents=[chunk["text"] for chunk in batch],
            metadatas=[metadata(chunk) for chunk in batch],
        )
        print(f"Upserted {stop}/{total} chunks (batch size {len(batch)})", flush=True)

    first = min(FIRST_BATCH_SIZE, total)
    started = perf_counter()
    upsert_batch(0, first)
    elapsed = perf_counter() - started
    print(f"First {first} chunks: {elapsed:.3f} seconds", flush=True)
    print(
        f"Estimated time for all {total} chunks: {elapsed * total / first:.3f} seconds; "
        f"remaining: {elapsed * (total - first) / first:.3f} seconds "
        "(linear estimate including first-batch startup)",
        flush=True,
    )
    for start in range(first, total, BATCH_SIZE):
        upsert_batch(start, min(start + BATCH_SIZE, total))

    count = collection.count()
    print(f"collection.count(): {count}", flush=True)
    assert count == total, f"Stored count {count} differs from {total} input lines"

    # Verify actual persisted values, rather than merely report input statistics.
    stored = collection.get(include=["documents", "metadatas"])
    assert set(stored["ids"]) == {chunk["id"] for chunk in chunks}, "Stored IDs differ from input"
    expected = {chunk["id"]: chunk for chunk in chunks}
    traditions = Counter()
    for chunk_id, document, attributes in zip(stored["ids"], stored["documents"], stored["metadatas"], strict=True):
        assert document == expected[chunk_id]["text"], f"Document mismatch: {chunk_id}"
        assert attributes == metadata(expected[chunk_id]), f"Metadata mismatch: {chunk_id}"
        traditions[attributes["tradition"]] += 1
    print("Stored chunks per tradition:", flush=True)
    for tradition, number in sorted(traditions.items()):
        print(f"  {tradition}: {number}", flush=True)
    print("Verified: count, IDs, documents, and metadata match chunks.jsonl.", flush=True)


if __name__ == "__main__":
    main()
