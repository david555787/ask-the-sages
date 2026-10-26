"""Audit Chroma recall against exact squared-L2 search without writing records.

Run from the repository root: .venv/bin/python check_recall.py
"""

import copy
from pathlib import Path

import chromadb
import numpy as np

from explore_queries import QUERIES


INCLUDE = ["documents", "metadatas", "distances"]
STORED_INCLUDE = ["embeddings", "documents", "metadatas"]


def main() -> None:
    if not Path("./chroma_store").is_dir():
        raise FileNotFoundError("Run from the repository root containing chroma_store")
    client = chromadb.PersistentClient(path="./chroma_store")
    collection = client.get_collection(name="sages")
    configuration = copy.deepcopy(collection.configuration_json)
    stored = collection.get(include=STORED_INCLUDE)
    ids = stored["ids"]
    assert collection.count() == len(ids) == 1124, "Expected all 1,124 stored records"
    assert len(set(ids)) == len(ids)
    embeddings = np.asarray(stored["embeddings"], dtype=np.float64)
    assert embeddings.ndim == 2 and embeddings.shape[0] == len(ids)
    assert np.isfinite(embeddings).all()
    index = {record_id: i for i, record_id in enumerate(ids)}
    config = collection.configuration
    assert config["hnsw"]["space"] == "l2", "This audit requires squared-L2 search"
    # Installed 1.5.9 CollectionCommon._embed(is_query=True) resolves the
    # configured embedding function and calls embed_query(input=...). Use the
    # same public configuration and query embedding method, not a new model.
    embedding_function = config["embedding_function"]
    if embedding_function is None:
        raise ValueError("No embedding function found in the collection configuration")
    print(f"Chroma {chromadb.__version__}; stored embeddings: {embeddings.shape}", flush=True)
    print(f"Current HNSW configuration: {config['hnsw']}", flush=True)
    historical_greek = [
        i for i, metadata in enumerate(stored["metadatas"])
        if metadata["tradition"] == "greek" and metadata["section"] == "paragraph 63, part 1/4"
    ]
    assert len(historical_greek) == 1, "Earlier Greek passage cannot be identified uniquely"
    summaries = []
    all_distances_match = True

    def row(rank: int, i: int, distance: float) -> str:
        metadata = stored["metadatas"][i]
        return (
            f"{rank:2d} | {distance:.3f} | {ids[i]} | {metadata['tradition']} | "
            f"{metadata['section']} | {stored['documents'][i][:100]}"
        )

    for number, (_, query) in enumerate(QUERIES, 1):
        vector = np.asarray(embedding_function.embed_query(input=[query])[0], dtype=np.float64)
        assert vector.shape == embeddings.shape[1:]
        difference = embeddings - vector
        exact_distances = np.sum(difference * difference, axis=1)
        # Stable ID tie-breaker for equal exact distances.
        order = np.lexsort((np.asarray(ids), exact_distances))
        exact_ids = [ids[i] for i in order[:5]]
        ann10 = collection.query(query_texts=[query], n_results=10, include=INCLUDE)
        # Also reproduce the original exploration's actual n_results=5 search.
        # HNSW's candidates may depend on k; do not silently substitute a top-10 prefix.
        ann5 = collection.query(query_texts=[query], n_results=5, include=INCLUDE)
        matches = []
        max_error = 0.0
        for result in (ann10, ann5):
            for record_id, distance in zip(result["ids"][0], result["distances"][0], strict=True):
                exact = float(exact_distances[index[record_id]])
                matches.append(f"{distance:.3f}" == f"{exact:.3f}")
                max_error = max(max_error, abs(distance - exact))
        same_decimals = all(matches)
        all_distances_match &= same_decimals
        overlap5 = len(set(exact_ids) & set(ann5["ids"][0]))
        overlap10_prefix = len(set(exact_ids) & set(ann10["ids"][0][:5]))
        summaries.append((number, query, overlap5, overlap10_prefix, same_decimals, max_error))

        if number == 1:
            print(f"\nQuery 1: {query}")
            exact_rows = [row(rank, i, float(exact_distances[i])) for rank, i in enumerate(order[:10], 1)]
            ann_rows = [
                row(rank, index[record_id], distance)
                for rank, (record_id, distance) in enumerate(zip(ann10["ids"][0], ann10["distances"][0], strict=True), 1)
            ]
            width = max(len("EXACT SQUARED-L2 TOP 10"), *(len(line) for line in exact_rows))
            print(f"{'EXACT SQUARED-L2 TOP 10':<{width}} || CHROMA n_results=10 TOP 10")
            print("Each side: rank | distance | id | tradition | section | first 100 characters")
            for left, right in zip(exact_rows, ann_rows, strict=True):
                print(f"{left:<{width}} || {right}")
            print("Exact top-5 IDs:", exact_ids)
            print("Chroma top-5 IDs (n_results=5):", ann5["ids"][0])
            print("Chroma first-5 IDs (n_results=10):", ann10["ids"][0][:5])
            print("Top-5 ordered lists identical (n_results=5):", exact_ids == ann5["ids"][0])
            print("Top-5 ordered lists identical (top-10 prefix):", exact_ids == ann10["ids"][0][:5])
            greek_i = historical_greek[0]
            greek_rank = int(np.flatnonzero(order == greek_i)[0]) + 1
            print(
                f"Earlier Greek passage: {ids[greek_i]}; exact rank {greek_rank}; "
                f"exact squared-L2 {exact_distances[greek_i]:.3f}"
            )
            filtered = collection.query(query_texts=[query], where={"tradition": "greek"}, n_results=1, include=INCLUDE)
            filtered_id = filtered["ids"][0][0]
            filtered_distance = filtered["distances"][0][0]
            filtered_exact = exact_distances[index[filtered_id]]
            filtered_match = f"{filtered_distance:.3f}" == f"{filtered_exact:.3f}"
            all_distances_match &= filtered_match
            print(f"Greek-filtered rerun: {filtered_id}; Chroma {filtered_distance:.3f}; exact {filtered_exact:.3f}; match: {filtered_match}")
            print("Query 1 unfiltered distances match exact to 3 decimals:", same_decimals)

    print("\nRecall comparison (intersection counts out of the exact top 5):")
    print("query | text | Chroma k=5 overlap | Chroma k=10 first-5 overlap | distances match (3dp) | max absolute error")
    for number, query, overlap5, overlap10, match, error in summaries:
        print(f"{number} | {query} | {overlap5}/5 | {overlap10}/5 | {match} | {error:.3e}")
    print("All checked Chroma distances match brute force to 3 decimals:", all_distances_match)

    after = collection.get(include=STORED_INCLUDE)
    assert collection.count() == len(ids)
    assert set(after["ids"]) == set(ids)
    for i, record_id in enumerate(after["ids"]):
        old = index[record_id]
        assert after["documents"][i] == stored["documents"][old]
        assert after["metadatas"][i] == stored["metadatas"][old]
        assert np.array_equal(np.asarray(after["embeddings"][i], dtype=np.float64), embeddings[old])
    assert collection.configuration_json == configuration
    print("Verified unchanged: all 1,124 IDs, embeddings, documents, metadata, and collection configuration.")


if __name__ == "__main__":
    main()
