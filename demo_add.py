"""Measure duplicate distances and exercise temporary user passage management.

Runs load_db.py once in a fresh .venv interpreter, then removes only this demo's
new user records. It verifies the complete starting record set is restored.
"""

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

from sages import (
    DUPLICATE_MAX, add_passage, ask, delete_user_passages, format_answer,
    list_user_passages, open_collection,
)


TEXT = (
    "On the orbital greenhouse station, the gardener uses a purple umbrella to shield "
    "tomato seedlings from artificial meteor showers. When the alarm sounds, she closes "
    "the silver roof and waits until the simulated hail stops before watering the plants."
)
TITLE = "Temporary orbital greenhouse demonstration"
QUERY = "How does the gardener on an orbital greenhouse protect tomato seedlings during an artificial meteor shower?"


def snapshot(collection) -> dict:
    found = collection.get(include=["embeddings", "documents", "metadatas"])
    return {
        record_id: (document, metadata, np.asarray(embedding, dtype=np.float64).tobytes())
        for record_id, document, metadata, embedding in zip(
            found["ids"], found["documents"], found["metadatas"], found["embeddings"], strict=True
        )
    }


def measure_distances(collection) -> None:
    examples = collection.get(ids=["meditations-0001", "tao-te-ching-0097"], include=["documents", "embeddings"])
    examples = {record_id: (document, np.asarray(vector, dtype=np.float64)) for record_id, document, vector in zip(examples["ids"], examples["documents"], examples["embeddings"], strict=True)}
    original, vector = examples["meditations-0001"]
    assert "grandfather" in original and "morals" in original
    changed = original.replace("grandfather", "grandmother", 1).replace("morals", "manners", 1)
    changed_vector = np.asarray(collection.configuration["embedding_function"](input=[changed])[0], dtype=np.float64)
    unrelated, unrelated_vector = examples["tao-te-ching-0097"]
    print("DUPLICATE THRESHOLD CALIBRATION (before any insertion)", flush=True)
    print(f"DUPLICATE_MAX={DUPLICATE_MAX}; these two examples do not validate a universal threshold.")
    print("Original meditations-0001:", original)
    print("Two words changed:", changed)
    print(f"Squared-L2, original versus two-word edit: {np.sum((vector-changed_vector)**2):.6f}")
    print("Unrelated built-in tao-te-ching-0097:", unrelated)
    print(f"Squared-L2, original versus unrelated built-in: {np.sum((vector-unrelated_vector)**2):.6f}", flush=True)


def main() -> None:
    root = Path(__file__).resolve().parent
    source = root / "data" / "processed" / "chunks.jsonl"
    original_jsonl = source.read_bytes()
    collection = open_collection()
    before = snapshot(collection)
    configuration = copy.deepcopy(collection.configuration_json)
    expected_id = "user-" + hashlib.sha256(("test-tradition" + TITLE + TEXT).encode("utf-8")).hexdigest()[:12]
    if expected_id in before:
        raise ValueError("Demo passage already exists; refusing to remove a pre-existing user record")
    measure_distances(collection)
    # Register the known ID before adding, so partial failures can be cleaned up.
    temporary_ids = [expected_id]
    try:
        added = add_passage(TEXT, " Test-Tradition ", TITLE, collection, source_note="Made-up demo passage")
        assert added["ids"] == temporary_ids and added["new"] == 1 and added["already_present"] == 0
        print("\nFirst addition:", json.dumps(added, ensure_ascii=False, indent=2), flush=True)
        repeated = add_passage(TEXT, "test-tradition", TITLE, collection, source_note="Made-up demo passage")
        assert repeated["ids"] == added["ids"] and repeated["new"] == 0 and repeated["already_present"] == 1
        assert collection.count() == len(before) + 1
        print("\nRepeated addition:", json.dumps(repeated, ensure_ascii=False, indent=2))
        print("\nUser passages:", json.dumps(list_user_passages(collection), ensure_ascii=False, indent=2))
        answer = ask(QUERY, collection)
        assert not answer["refused"]
        assert answer["traditions"][-1] == "test-tradition" or "test-tradition" in answer["traditions"]
        hit = next(row for row in answer["passages"] if row["tradition"] == "test-tradition")
        assert hit["id"] == expected_id and hit["text"] == TEXT
        print("\nImmediate paraphrase search:")
        print(format_answer(answer), flush=True)
        print("\nReloading built-ins once; user record must survive:", flush=True)
        subprocess.run([sys.executable, str(root / "load_db.py")], cwd=root, check=True)
        collection = open_collection()
        surviving = collection.get(ids=temporary_ids, include=["documents", "metadatas"])
        assert surviving["ids"] == temporary_ids and surviving["documents"] == [TEXT]
        assert surviving["metadatas"][0]["source"] == "user"
        assert collection.count() == len(before) + 1
        print("PASS: temporary user passage survives load_db.py; count increased only by one.", flush=True)
        # Explicitly passing a built-in ID cannot delete it.
        assert delete_user_passages(collection, ["meditations-0001"]) == 0
        assert snapshot(collection)["meditations-0001"] == before["meditations-0001"]
    finally:
        removed = delete_user_passages(collection, temporary_ids)
        print(f"\nRemoved {removed} temporary user passage(s).", flush=True)
    assert snapshot(collection) == before, "Existing records or embeddings changed"
    assert collection.count() == len(before)
    assert collection.configuration_json == configuration
    assert collection.configuration["hnsw"]["ef_search"] == 200
    assert source.read_bytes() == original_jsonl
    print("PASS: complete original record set restored, including all built-in embeddings, documents and metadata.")
    print(f"Final count: {collection.count()}; ef_search=200; chunks.jsonl bytes unchanged.")


if __name__ == "__main__":
    main()
