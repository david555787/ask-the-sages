"""Retrieval, formatting, and explicitly user-owned passage management.

ask() returns a dictionary with query, refused, best_distance and passages.
For an accepted query, passages follows built-in then alphabetical tradition order.
A passage outside the weak threshold has text=None and no source details.
"""

import hashlib
from pathlib import Path
import textwrap

import chromadb

from chunking import split_long_text, word_count


# Empirical value from experiments on about 35 queries, not a guarantee.
STRONG_MAX = 1.10
# Empirical value from experiments on about 35 queries, not a guarantee.
MODERATE_MAX = 1.30
# Empirical value from experiments on about 35 queries, not a guarantee.
WEAK_MAX = 1.40
# Heuristic near-duplicate cutoff; demo_add.py measures examples, not guarantees.
DUPLICATE_MAX = 0.35
# Empirical scope from experiments on about 35 queries, not a guarantee of coverage.
N_TRADITIONS = ["confucian", "daoist", "stoic", "greek"]
# Display names for that empirical experimental scope, not guarantees of coverage.
DISPLAY_NAMES = {"confucian": "Confucian", "daoist": "Daoist", "stoic": "Stoic", "greek": "Greek"}
REMINDER = (
    "These are the closest passages in the translations I loaded, not answers. "
    "A small distance does not guarantee relevance."
)


def open_collection():
    """Open existing ./chroma_store/sages; never create or modify a collection."""
    if not Path("./chroma_store").is_dir():
        raise FileNotFoundError("./chroma_store does not exist; run from the repository root")
    client = chromadb.PersistentClient(path="./chroma_store")
    collection = client.get_collection(name="sages")
    if collection.count() and collection.configuration["hnsw"]["ef_search"] != 200:
        raise ValueError("Expected sages ef_search=200; no configuration was changed")
    return collection


def band(distance: float) -> str:
    """Use strict upper bounds; equality belongs to the next weaker band."""
    if distance < STRONG_MAX:
        return "strong"
    if distance < MODERATE_MAX:
        return "moderate"
    if distance < WEAK_MAX:
        return "weak"
    return "none"


def ask(query: str, collection) -> dict:
    """Gate on the overall nearest neighbour, then retrieve one per tradition.

    Traditions are discovered on every call. Entries with band='none' retain the tradition and
    its best distance but set id/work/section/translator/text to None.
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a nonempty string")
    metadata = collection.get(include=["metadatas"])["metadatas"]
    present = {row["tradition"] for row in metadata if row and isinstance(row.get("tradition"), str) and row["tradition"]}
    traditions = [t for t in N_TRADITIONS if t in present] + sorted(present - set(N_TRADITIONS))
    best = collection.query(query_texts=[query], n_results=1, include=["distances"])
    if not best["ids"][0]:
        raise ValueError("The sages collection is empty")
    distance = float(best["distances"][0][0])
    result = {"query": query, "refused": band(distance) == "none", "best_distance": distance, "traditions": traditions, "passages": []}
    if result["refused"]:
        return result

    for tradition in traditions:
        found = collection.query(
            query_texts=[query], where={"tradition": tradition}, n_results=1,
            include=["documents", "metadatas", "distances"],
        )
        distance = float(found["distances"][0][0]) if found["ids"][0] else float("inf")
        label = band(distance)
        entry = {
            "tradition": tradition, "id": None, "work": None, "section": None,
            "translator": None, "distance": distance, "band": label, "text": None,
        }
        if label != "none":
            metadata = found["metadatas"][0][0]
            entry.update(
                id=found["ids"][0][0], work=metadata["work"], section=metadata["section"],
                translator=metadata["translator"], text=found["documents"][0][0],
            )
        result["passages"].append(entry)
    return result


def format_answer(result: dict, width: int = 88) -> str:
    """Return printable text without printing, changing result, or querying Chroma."""
    if width < 1:
        raise ValueError("width must be positive")

    def wrap(text: str) -> str:
        return textwrap.fill(text, width=width, break_long_words=False, break_on_hyphens=False)

    blocks = [wrap(f"Question: {result['query']}")]
    total = len(result.get("traditions", N_TRADITIONS))
    if result["refused"]:
        blocks.append(f"0 of {total} traditions had a passage.")
        blocks.append(wrap(
            "None of the loaded traditions contains a passage close to this question. "
            f"Best distance: {result['best_distance']:.3f}."
        ))
    else:
        count = sum(entry["band"] != "none" for entry in result["passages"])
        blocks.append(f"{count} of {total} traditions had a passage.")
        for entry in result["passages"]:
            name = DISPLAY_NAMES.get(entry["tradition"], entry["tradition"].title())
            if entry["band"] == "none":
                blocks.append(wrap(
                    f"{name} | none | distance {entry['distance']:.3f}\n"
                    "This tradition has no close passage."
                ))
                continue
            lines = [
                wrap(f"{name} | {entry['work']} | {entry['section']}"),
                wrap(f"Translator: {entry['translator']}"),
                f"{entry['band']} | distance {entry['distance']:.3f}",
            ]
            if entry["band"] == "weak":
                lines.append("weak match: read with caution")
            lines.append(wrap(entry["text"]))
            blocks.append("\n".join(lines))
    blocks.append(wrap(REMINDER))
    return "\n\n".join(blocks)


def add_passage(text: str, tradition: str, title: str, collection, source_note: str = "", *, dry_run: bool = False) -> dict:
    """Upsert deterministic user chunks, reporting nearest pre-insertion records.

    ids contains unique chunk IDs; new/already_present count unique IDs before
    this call. nearest lists all comparisons, while near_duplicates includes
    only distances strictly below DUPLICATE_MAX. Repeated identical chunks in
    one input share an ID and retain their first part label.
    With dry_run=True, validate and report predicted IDs/duplicates without writing.
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Passage text must not be empty")
    text = text.strip()
    if word_count(text) < 5:
        raise ValueError("Passage text must contain at least 5 words")
    if not isinstance(tradition, str) or not tradition.strip():
        raise ValueError("Tradition must be a non-empty string")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Title must be a non-empty string")
    if not isinstance(source_note, str):
        raise ValueError("Source note must be a string")
    tradition, title = tradition.strip().lower(), title.strip()
    parts = split_long_text(text)
    if not parts or word_count(" ".join(parts)) < 5:
        raise ValueError("Passage text must contain at least 5 words after normalization")
    records = {}
    for i, part in enumerate(parts, 1):
        record_id = "user-" + hashlib.sha256((tradition + title + part).encode("utf-8")).hexdigest()[:12]
        records.setdefault(record_id, {
            "text": part,
            "metadata": {
                "tradition": tradition, "work": title,
                "section": "user-added" + (f", part {i}/{len(parts)}" if len(parts) > 1 else ""),
                "translator": source_note or "user-added", "words": word_count(part), "source": "user",
            },
        })
    ids = list(records)
    existing = collection.get(ids=ids, include=["documents", "metadatas"])
    for record_id, document, attributes in zip(existing["ids"], existing["documents"], existing["metadatas"], strict=True):
        if not attributes or attributes.get("source") != "user":
            raise ValueError(f"Refusing to overwrite a non-user record: {record_id}")
        wanted = records[record_id]
        if document != wanted["text"] or attributes.get("tradition") != tradition or attributes.get("work") != title:
            raise ValueError(f"Deterministic ID collision; existing record was not changed: {record_id}")
    nearest = []
    if collection.count():
        for record_id, record in records.items():
            result = collection.query(query_texts=[record["text"]], n_results=1, include=["metadatas", "distances"])
            attributes = result["metadatas"][0][0]
            nearest.append({
                "chunk_id": record_id, "id": result["ids"][0][0], "work": attributes["work"],
                "section": attributes["section"], "distance": float(result["distances"][0][0]),
            })
    # All duplicate checks happen before the first write.
    if not dry_run:
        for start in range(0, len(ids), 100):
            batch = ids[start : start + 100]
            collection.upsert(
                ids=batch, documents=[records[i]["text"] for i in batch],
                metadatas=[records[i]["metadata"] for i in batch],
            )
    return {
        "ids": ids, "new": len(ids) - len(existing["ids"]), "already_present": len(existing["ids"]),
        "nearest": nearest, "near_duplicates": [row for row in nearest if row["distance"] < DUPLICATE_MAX],
    }


def list_user_passages(collection) -> list[dict]:
    """List only records explicitly marked source=user, sorted by ID."""
    found = collection.get(where={"source": "user"}, include=["documents", "metadatas"])
    rows = []
    for record_id, document, attributes in zip(found["ids"], found["documents"], found["metadatas"], strict=True):
        rows.append({
            "id": record_id, "tradition": attributes["tradition"], "work": attributes["work"],
            "section": attributes["section"], "words": attributes["words"], "preview": document[:80],
        })
    return sorted(rows, key=lambda row: row["id"])


def delete_user_passages(collection, ids=None) -> int:
    """Delete only source=user records; explicit built-in IDs are ignored."""
    if ids is not None:
        if isinstance(ids, str):
            raise ValueError("ids must be a sequence of IDs, not one string")
        ids = list(ids)
        if not all(isinstance(record_id, str) and record_id for record_id in ids):
            raise ValueError("Every ID must be a non-empty string")
        ids = list(dict.fromkeys(ids))
        if not ids:
            return 0
    found = collection.get(ids=ids, where={"source": "user"}, include=["metadatas"])
    eligible = [record_id for record_id, attributes in zip(found["ids"], found["metadatas"], strict=True) if attributes.get("source") == "user"]
    for start in range(0, len(eligible), 100):
        collection.delete(ids=eligible[start : start + 100], where={"source": "user"})
    return len(eligible)
