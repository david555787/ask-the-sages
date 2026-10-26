"""Benchmark existing sages HNSW recall; retain the smallest perfect setting.

Only ef_search is changed. No records are inserted, re-embedded, or deleted.
Timings include query-text embedding and search, after model warm-up.
"""

import copy
import argparse
import json
from pathlib import Path
from statistics import mean
import subprocess
import sys
from time import perf_counter

import chromadb
import numpy as np

from explore_queries import QUERIES as ORIGINAL_QUERIES, TRADITIONS


QUERIES = tuple(query for _, query in ORIGINAL_QUERIES) + (
    "I keep comparing myself to people who are more successful than me",
    "should I speak up even if it makes me unpopular",
    "how can I be content with a simple life",
    "a leader who does not need to boast",
    "is it right to disobey an unjust order",
    "doing good without wanting credit",
)
EF_VALUES = (100, 200, 500, 1200)
STORED_INCLUDE = ["embeddings", "documents", "metadatas"]


def assert_records_unchanged(collection, before: dict) -> None:
    after = collection.get(include=STORED_INCLUDE)
    index = {record_id: i for i, record_id in enumerate(before["ids"])}
    assert collection.count() == len(after["ids"]) == len(index) == 1124
    assert set(after["ids"]) == set(index)
    for i, record_id in enumerate(after["ids"]):
        old = index[record_id]
        assert after["documents"][i] == before["documents"][old], record_id
        assert after["metadatas"][i] == before["metadatas"][old], record_id
        assert np.array_equal(after["embeddings"][i], before["embeddings"][old]), record_id


def main(worker_value: int | None = None) -> int | None:
    if not Path("./chroma_store").is_dir():
        raise FileNotFoundError("Run from the repository root containing chroma_store")
    assert chromadb.__version__ == "1.5.9", "Recheck configuration API for this version"
    client = chromadb.PersistentClient(path="./chroma_store")
    collection = client.get_collection(name="sages")
    before = collection.get(include=STORED_INCLUDE)
    assert collection.count() == len(before["ids"]) == 1124
    original_configuration = copy.deepcopy(collection.configuration_json)
    original_ef = collection.configuration["hnsw"]["ef_search"]
    assert collection.configuration["hnsw"]["space"] == "l2"
    embeddings = np.asarray(before["embeddings"], dtype=np.float64)
    ids = np.asarray(before["ids"])
    ef = collection.configuration["embedding_function"]
    exact = []
    # Precompute ground truth once and warm up the collection's own model.
    for query in QUERIES:
        vector = np.asarray(ef.embed_query(input=[query])[0], dtype=np.float64)
        distances = np.sum((embeddings - vector) ** 2, axis=1)
        order = np.lexsort((ids, distances))
        top5 = set(ids[order[:5]])
        filtered = {
            tradition: next(
                str(ids[i]) for i in order if before["metadatas"][i]["tradition"] == tradition
            )
            for tradition in TRADITIONS
        }
        exact.append((top5, filtered))

    outcomes = []
    for value in ((worker_value,) if worker_value is not None else EF_VALUES):
        # Installed Collection.modify passes configuration to rust.update_collection;
        # UpdateHNSWConfiguration explicitly supports ef_search in Chroma 1.5.9.
        collection.modify(configuration={"hnsw": {"ef_search": value}})
        collection = client.get_collection(name="sages")
        assert collection.configuration["hnsw"]["ef_search"] == value
        if worker_value is None:
            # A live index retained its old runtime ef in our first experiment.
            # Reopen in a separate interpreter after each persisted modification.
            completed = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--worker", str(value)],
                capture_output=True, text=True,
            )
            if completed.returncode:
                print(completed.stdout, end="", flush=True)
                print(completed.stderr, end="", file=sys.stderr, flush=True)
                raise RuntimeError(f"Fresh-process benchmark failed for ef_search={value}")
            marker = "BENCHMARK_RESULT: "
            result_lines = [line for line in completed.stdout.splitlines() if line.startswith(marker)]
            assert len(result_lines) == 1
            outcomes.append(tuple(json.loads(result_lines[0][len(marker):])))
            print("\n".join(line for line in completed.stdout.splitlines() if not line.startswith(marker)), flush=True)
            continue
        print(f"\nef_search={value}", flush=True)
        print("query | exact top-5 overlap | confucian | daoist | stoic | greek", flush=True)
        unfiltered_times = []
        filtered_times = []
        perfect_queries = correct_pairs = 0
        for number, (query, (top5, filtered)) in enumerate(zip(QUERIES, exact, strict=True), 1):
            started = perf_counter()
            result = collection.query(query_texts=[query], n_results=5, include=["distances"])
            unfiltered_times.append(perf_counter() - started)
            overlap = len(top5 & set(result["ids"][0]))
            perfect_queries += overlap == 5
            statuses = []
            for tradition in TRADITIONS:
                started = perf_counter()
                result = collection.query(
                    query_texts=[query], where={"tradition": tradition},
                    n_results=1, include=["distances"],
                )
                filtered_times.append(perf_counter() - started)
                correct = result["ids"][0][0] == filtered[tradition]
                correct_pairs += correct
                statuses.append("PASS" if correct else f"FAIL ({result['ids'][0][0]} != {filtered[tradition]})")
            print(f"{number:2d} | {overlap}/5 | " + " | ".join(statuses), flush=True)
        average_ms = mean(unfiltered_times + filtered_times) * 1000
        print(f"Perfect unfiltered queries: {perfect_queries}/14; correct filtered pairs: {correct_pairs}/56")
        print(f"Average query time (embedding + search, 70 calls): {average_ms:.3f} ms")
        print(f"Unfiltered mean: {mean(unfiltered_times)*1000:.3f} ms; filtered mean: {mean(filtered_times)*1000:.3f} ms", flush=True)
        outcomes.append((value, perfect_queries, correct_pairs, average_ms))

    if worker_value is not None:
        assert_records_unchanged(collection, before)
        assert collection.configuration_json == original_configuration
        print("BENCHMARK_RESULT: " + json.dumps(outcomes[0]))
        return None

    passing = [value for value, queries, pairs, _ in outcomes if queries == 14 and pairs == 56]
    selected = min(passing) if passing else None
    final_ef = selected if selected is not None else original_ef
    collection.modify(configuration={"hnsw": {"ef_search": final_ef}})
    collection = client.get_collection(name="sages")
    assert collection.configuration["hnsw"]["ef_search"] == final_ef
    expected_configuration = copy.deepcopy(original_configuration)
    expected_configuration["hnsw"]["ef_search"] = final_ef
    assert collection.configuration_json == expected_configuration, "Unexpected configuration change"
    assert_records_unchanged(collection, before)
    print("\nSummary: ef_search | perfect unfiltered /14 | correct filtered /56 | mean ms")
    for value, queries, pairs, average in outcomes:
        print(f"{value} | {queries}/14 | {pairs}/56 | {average:.3f}")
    if selected is None:
        print(f"No tested value passes all checks; restored original ef_search={original_ef}. No value selected.")
    else:
        print(f"Selected smallest perfect ef_search={selected}")
    print("Verified: all 1,124 IDs, embeddings, documents and metadata unchanged; only ef_search may differ.")
    return selected


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=int, choices=EF_VALUES, help=argparse.SUPPRESS)
    main(parser.parse_args().worker)
