"""Explore sages retrieval without inserting, updating, or deleting records.

Run from the repository root:
    .venv/bin/python explore_queries.py "first query" "second query"
Distances rank nearest neighbours; an unrelated query still returns neighbours.
Keyword overlap is a literal whole-word diagnostic, not a relevance score.
"""

import argparse
from itertools import zip_longest
from pathlib import Path
import re
import textwrap

import chromadb


# Original benchmark retained for check_recall.py, which imports this constant.
# Exploration itself uses only the queries supplied on the command line.
QUERIES = (
    ("RELEVANT", "how do I stay calm when people treat me unfairly"),
    ("RELEVANT", "is it better to lead by force or by example"),
    ("RELEVANT", "someone who is afraid of dying"),
    ("RELEVANT", "what makes a person truly wise"),
    ("RELEVANT", "how should a ruler treat his people"),
    ("UNRELATED", "how to install Python on a Mac"),
    ("UNRELATED", "best pizza topping"),
    ("UNRELATED", "quantum chromodynamics"),
)
STOPWORDS = set(
    "the a an of to is do how i in on or and what who when by for be it that "
    "this with as are can should his her their them they you your my me".split()
)
TRADITIONS = ("confucian", "daoist", "stoic", "greek")
INCLUDE = ["documents", "metadatas", "distances"]


def keyword_overlap(query: str, document: str) -> list[str]:
    query_words = set(re.findall(r"[a-z]+", query.lower())) - STOPWORDS
    document_words = set(re.findall(r"[a-z]+", document.lower()))
    return sorted(query_words & document_words)


def stored_records(collection) -> dict:
    """Read IDs, documents and metadata so the run can check they stay intact."""
    records = collection.get(include=["documents", "metadatas"])
    return {
        record_id: (document, metadata)
        for record_id, document, metadata in zip(
            records["ids"], records["documents"], records["metadatas"], strict=True
        )
    }


def print_tradition_comparison(collection, query: str) -> None:
    """Print the complete best passage for each tradition in four columns."""
    columns = []
    width = 48
    for tradition in TRADITIONS:
        result = collection.query(
            query_texts=[query],
            where={"tradition": tradition},
            n_results=1,
            include=INCLUDE,
        )
        if not result["ids"][0]:
            raise ValueError(f"No records found for tradition {tradition}")
        metadata = result["metadatas"][0][0]
        lines = [f"{tradition} | distance {result['distances'][0][0]:.3f}"]
        lines.extend(textwrap.wrap(f"{metadata['work']} | {metadata['section']} | {metadata['words']} words", width))
        lines.append("")
        lines.extend(textwrap.wrap(result["documents"][0][0], width, break_long_words=False, break_on_hyphens=False))
        columns.append(lines)
    print("\nQuery 1 — best full passage per tradition:")
    print(" | ".join("-" * width for _ in columns))
    for row in zip_longest(*columns, fillvalue=""):
        print(" | ".join(cell.ljust(width) for cell in row).rstrip())


def main() -> None:
    parser = argparse.ArgumentParser(description="Explore sages with one query per quoted command-line argument.")
    parser.add_argument("queries", nargs="+", help="Query text (quote each query containing spaces)")
    args = parser.parse_args()
    if any(not query.strip() for query in args.queries):
        parser.error("Queries must not be empty or whitespace-only")
    queries = [("CUSTOM", query) for query in args.queries]
    if not Path("./chroma_store").is_dir():
        raise FileNotFoundError("./chroma_store does not exist; run from the repository root")
    client = chromadb.PersistentClient(path="./chroma_store")
    # get_collection deliberately fails if sages does not already exist.
    collection = client.get_collection(name="sages")
    before_count = collection.count()
    before_records = stored_records(collection)
    if before_count < 5:
        raise ValueError("The sages collection must contain at least five records")
    print(f"Existing sages collection: {before_count} records", flush=True)
    summary = []

    for number, (category, query) in enumerate(queries, 1):
        print(f"\nQuery {number} [{category}]: {query}", flush=True)
        results = collection.query(query_texts=[query], n_results=5, include=INCLUDE)
        if number == 1:
            print("Full raw results object:")
            print(results)
        print("rank | distance | tradition | work | section | words | first 150 characters")
        for rank, (distance, metadata, document) in enumerate(
            zip(results["distances"][0], results["metadatas"][0], results["documents"][0], strict=True), 1
        ):
            print(
                f"{rank} | {distance:.3f} | {metadata['tradition']} | {metadata['work']} | "
                f"{metadata['section']} | {metadata['words']} | {document[:150]}"
            )
            if rank <= 3:
                print(f"  Keyword overlap (rank {rank}): {keyword_overlap(query, document)}")
        assert len(results["ids"][0]) == 5, "Expected five neighbours per query"
        summary.append((number, query, results["distances"][0][0], results["distances"][0][4], results["metadatas"][0][0]["words"]))

    print("\nSummary:")
    print("query | text | best distance | 5th distance | top-1 words")
    for number, query, best, fifth, words in summary:
        print(f"{number} | {query} | {best:.3f} | {fifth:.3f} | {words}")

    print_tradition_comparison(collection, queries[0][1])
    assert collection.count() == before_count, "Collection count changed during exploration"
    assert stored_records(collection) == before_records, "Stored records changed during exploration"
    print(f"\nVerified unchanged: {before_count} IDs, documents, and metadata records.")


if __name__ == "__main__":
    main()
