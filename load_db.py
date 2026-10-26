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
EF_SEARCH = 200  # Smallest tested value with perfect recall on the 14-query audit.
METADATA_FIELDS = ("tradition", "work", "section", "translator")


def is_user_record(record_id: str, attributes: dict | None) -> bool:
    """Protect either the reserved ID prefix or the explicit ownership marker."""
    return record_id.startswith("user-") or bool(attributes and attributes.get("source") == "user")


def read_chunks() -> list[dict]:
    """Validate the entire input before creating or modifying a collection."""
    chunks = []
    for line_number, line in enumerate(INPUT.read_text(encoding="utf-8").splitlines(), 1):
        chunk = json.loads(line)
        if not isinstance(chunk["id"], str) or not chunk["id"]:
            raise ValueError(f"Invalid ID on line {line_number}")
        if is_user_record(chunk["id"], chunk):
            raise ValueError(f"User records do not belong in chunks.jsonl (line {line_number})")
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
    # Installed 1.5.9 accepts this creation configuration. For an existing
    # collection it is ignored; tune_ef.py handles updates and fresh-process tests.
    collection = client.get_or_create_collection(
        name="sages", configuration={"hnsw": {"ef_search": EF_SEARCH}}
    )
    total = len(chunks)
    print(f"Input: {total} chunks; existing sages count: {collection.count()}", flush=True)
    before = collection.get(include=["documents", "metadatas"])
    existing = {
        record_id: (document, attributes)
        for record_id, document, attributes in zip(before["ids"], before["documents"], before["metadatas"], strict=True)
    }
    expected = {chunk["id"]: chunk for chunk in chunks}
    collisions = [record_id for record_id in expected if record_id in existing and is_user_record(record_id, existing[record_id][1])]
    if collisions:
        raise ValueError(f"Input IDs conflict with protected user records: {collisions}")

    def upsert_batch(start: int, stop: int) -> None:
        batch = chunks[start:stop]
        changed = [chunk for chunk in batch if existing.get(chunk["id"]) != (chunk["text"], metadata(chunk))]
        if changed:
            collection.upsert(
                ids=[chunk["id"] for chunk in changed],
                documents=[chunk["text"] for chunk in changed],
                metadatas=[metadata(chunk) for chunk in changed],
            )
        print(f"Processed {stop}/{total} built-in chunks: upserted {len(changed)}, unchanged {len(batch)-len(changed)}", flush=True)

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

    stale = sorted(record_id for record_id, (_, attributes) in existing.items() if record_id not in expected and not is_user_record(record_id, attributes))
    for start in range(0, len(stale), BATCH_SIZE):
        collection.delete(ids=stale[start : start + BATCH_SIZE])
    print(f"Removed stale built-in IDs: {len(stale)}", flush=True)
    count = collection.count()
    print(f"collection.count(): {count}", flush=True)

    # Compare only built-ins with the source; user-owned records are independent.
    stored = collection.get(include=["documents", "metadatas"])
    built_in_ids = {record_id for record_id, attributes in zip(stored["ids"], stored["metadatas"], strict=True) if not is_user_record(record_id, attributes)}
    assert built_in_ids == set(expected), "Stored built-in IDs differ from input"
    assert len(built_in_ids) == total
    assert count == len(stored["ids"])
    traditions = Counter()
    for chunk_id, document, attributes in zip(stored["ids"], stored["documents"], stored["metadatas"], strict=True):
        if is_user_record(chunk_id, attributes):
            if chunk_id in existing:
                assert (document, attributes) == existing[chunk_id], f"User record changed: {chunk_id}"
            continue
        assert document == expected[chunk_id]["text"], f"Document mismatch: {chunk_id}"
        assert attributes == metadata(expected[chunk_id]), f"Metadata mismatch: {chunk_id}"
        traditions[attributes["tradition"]] += 1
    print("Stored built-in chunks per tradition:", flush=True)
    for tradition, number in sorted(traditions.items()):
        print(f"  {tradition}: {number}", flush=True)
    protected_before = {record_id for record_id, (_, attributes) in existing.items() if is_user_record(record_id, attributes)}
    assert protected_before <= set(stored["ids"]), "A protected user record was lost"
    print(f"Verified: {total} built-ins match chunks.jsonl; {len(protected_before)} user records preserved.", flush=True)


if __name__ == "__main__":
    main()
