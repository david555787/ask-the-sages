"""Run five read-only retrieval experiments and save the complete report.

Run from the repo root with .venv/bin/python step6_experiments.py.
The report is created exclusively: existing output files are never overwritten.
"""

from collections import Counter
import contextlib
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import unicodedata

import chromadb
import numpy as np

from explore_queries import STOPWORDS, keyword_overlap


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "data" / "processed" / "chunks.jsonl"
REPORT = ROOT / "data" / "processed" / "experiments2.txt"
INCLUDE = ["documents", "metadatas", "distances"]
BASELINES = (
    "someone who is afraid of dying",
    "how do I stay calm when people treat me unfairly",
    "doing good without wanting credit",
)
CANDIDATES = (
    "I'm tired of people who talk a lot but do little",
    "why can a gentle person defeat a forceful one",
    "pretending to be an expert when I am not",
    "I get anxious about things I cannot control",
    "being humble gets you further than showing off",
    "I was blamed for something I did not do",
    "my elderly parents need me, how should I treat them",
)
OFF_TOPIC = (
    "what is the capital of France", "how to bake sourdough bread",
    "latest iPhone battery life", "who won the world cup",
    "how do I fix a flat bicycle tire", "python list comprehension",
    "weather forecast for tomorrow", "how to train for a marathon",
    "the plot of Star Wars", "how to write a cover letter",
)
ADJACENT = (
    "how do I choose a college major", "should I quit my job to start a company",
    "is social media making people lonely", "how do I make friends in a new city",
    "what is a good way to deal with a difficult boss",
)
SHORT_QUERIES = (
    "is it better to lead by force or by example",
    "a leader who does not need to boast",
    "is it right to disobey an unjust order",
)


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z]+", text.lower())


class BM25:
    """Okapi BM25 with positive Robertson IDF, k1=1.5 and b=0.75.

    Retain stopwords for BM25; only ALL-keyword matching and keyword overlap
    remove the requested stopword list. Repeated query tokens contribute once
    per occurrence. Equal scores are ordered lexically by deterministic ID.
    """

    def __init__(self, chunks: list[dict]):
        self.chunks = chunks
        self.frequencies = [Counter(tokenize(chunk["text"])) for chunk in chunks]
        self.lengths = [sum(frequency.values()) for frequency in self.frequencies]
        self.average_length = sum(self.lengths) / len(chunks)
        self.document_frequency = Counter(term for frequency in self.frequencies for term in frequency)

    def rank(self, query: str) -> list[tuple[float, int]]:
        scores = [0.0] * len(self.chunks)
        for term, query_frequency in Counter(tokenize(query)).items():
            df = self.document_frequency[term]
            idf = math.log1p((len(self.chunks) - df + 0.5) / (df + 0.5))
            for i, frequency in enumerate(self.frequencies):
                tf = frequency[term]
                if tf:
                    denominator = tf + 1.5 * (1 - 0.75 + 0.75 * self.lengths[i] / self.average_length)
                    scores[i] += query_frequency * idf * tf * (1.5 + 1) / denominator
        return sorted(((score, i) for i, score in enumerate(scores)), key=lambda row: (-row[0], self.chunks[row[1]]["id"]))

    def ranks(self, query: str) -> dict[str, int]:
        return {self.chunks[i]["id"]: rank for rank, (_, i) in enumerate(self.rank(query), 1)}


def result_rows(result: dict):
    return zip(result["ids"][0], result["distances"][0], result["metadatas"][0], result["documents"][0], strict=True)


def run_experiments(collection, chunks: list[dict]) -> dict:
    baseline = BM25(chunks)
    stats = {}
    print(f"Chroma version: {chromadb.__version__}")
    print(f"Collection: sages; records: {collection.count()}; HNSW: {collection.configuration['hnsw']}")
    print("Tokenization: lowercase [a-z]+; BM25 k1=1.5, b=0.75; IDF=ln(1+(N-df+0.5)/(df+0.5)).")
    print("BM25 retains stopwords; ALL-keyword matching and overlaps remove explore_queries.STOPWORDS.")
    print("BM25 ties: lexical ID order; ranking includes zero-score documents if necessary.")

    print("\nPART 1 - keyword baseline")
    for query in BASELINES:
        words = set(tokenize(query)) - STOPWORDS
        all_count = sum(words <= set(frequency) for frequency in baseline.frequencies)
        print(f"\nQuery: {query}\nNon-stopword query words: {sorted(words)}\nChunks containing ALL words: {all_count}")
        stats[query] = all_count
        ranking = baseline.rank(query)
        print("BM25 top 5: rank | score | id | work | section | first 120 characters")
        for rank, (score, i) in enumerate(ranking[:5], 1):
            chunk = chunks[i]
            print(f"{rank} | {score:.6f} | {chunk['id']} | {chunk['work']} | {chunk['section']} | {chunk['text'][:120]}")
        ranks = {chunks[i]["id"]: rank for rank, (_, i) in enumerate(ranking[:50], 1)}
        result = collection.query(query_texts=[query], n_results=3, include=INCLUDE)
        print("Vector top 3: rank | id | distance | work | section | BM25 rank")
        for rank, (record_id, distance, metadata, _) in enumerate(result_rows(result), 1):
            print(f"{rank} | {record_id} | {distance:.3f} | {metadata['work']} | {metadata['section']} | {ranks.get(record_id, 'not in top 50')}")
    for term in ("dying", "afraid"):
        matching = [chunk["id"] for chunk, frequency in zip(chunks, baseline.frequencies, strict=True) if term in frequency]
        print(f"\nExact word {term!r}: {len(matching)} chunks; IDs: {matching}")
        stats[term] = len(matching)

    print("\nPART 2 - new candidate queries")
    for label, query in zip("ABCDEFG", CANDIDATES, strict=True):
        print(f"\n{label}. {query}")
        ranks = baseline.ranks(query)
        result = collection.query(query_texts=[query], n_results=3, include=INCLUDE)
        for rank, (record_id, distance, metadata, document) in enumerate(result_rows(result), 1):
            print(f"Rank {rank} | id {record_id} | distance {distance:.3f} | {metadata['tradition']} | {metadata['work']} | {metadata['section']} | words {metadata['words']}")
            print(document)
            print(f"Keyword overlap: {keyword_overlap(query, document)}")
            print(f"BM25 rank: {ranks[record_id]}")

    print("\nPART 3 - threshold stress test")
    ranges = {}
    for category, queries in (("Off-topic", OFF_TOPIC), ("Adjacent modern life", ADJACENT)):
        print(f"\n{category}: query | best distance | 5th distance | top-1 first 100 characters")
        distances = []
        for query in queries:
            result = collection.query(query_texts=[query], n_results=5, include=INCLUDE)
            first, fifth = result["distances"][0][0], result["distances"][0][4]
            print(f"{query} | {first:.3f} | {fifth:.3f} | {result['documents'][0][0][:100]}")
            distances.append(first)
        ranges[category] = (min(distances), max(distances))
    stats["distance_ranges"] = ranges

    print("\nPART 4 - short chunks")
    for query in SHORT_QUERIES:
        print(f"\nQuery: {query}")
        for label, where in (("Unfiltered", None), ('where={"words": {"$gte": 25}}', {"words": {"$gte": 25}})):
            print(label)
            result = collection.query(query_texts=[query], n_results=3, include=INCLUDE, where=where)
            for rank, (record_id, distance, metadata, document) in enumerate(result_rows(result), 1):
                print(f"{rank} | {distance:.3f} | {record_id} | {metadata['work']} | {metadata['section']} | words {metadata['words']} | {document[:200]}")

    print("\nPART 5 - stray symbols")
    allowed = set(".,;:!?'\"()[]-—")
    counts = Counter()
    examples = {}
    for chunk in chunks:
        text = chunk["text"]
        seen = set()
        for i, char in enumerate(text):
            if char.isalpha() or char.isdigit() or char.isspace() or char in allowed:
                continue
            counts[char] += 1
            if char not in seen and len(examples.setdefault(char, [])) < 3:
                start = max(0, i - 30)
                stop = min(len(text), start + 60)
                start = max(0, stop - 60)
                examples[char].append((chunk["id"], text[start:stop]))
            seen.add(char)
    for char in sorted(counts, key=ord):
        print(f"\n{char!r} U+{ord(char):04X} {unicodedata.name(char, 'UNNAMED')}: {counts[char]} occurrences")
        for record_id, context in examples[char]:
            print(f"  {record_id}: {context}")
    if not counts:
        print("No stray characters found.")
    stats["stray"] = dict(counts)
    parentheticals = []
    for chunk in chunks:
        matches = [match.group() for match in re.finditer(r"\([ivxlcdm0-9.; ]+\)", chunk["text"], re.I) if re.search(r"[ivxlcdm0-9]", match.group(), re.I)]
        if matches:
            parentheticals.append((chunk["id"], matches))
    print(f"\nChunks with Roman-numeral/digit citation-style parentheticals: {len(parentheticals)}")
    print("Definition: parentheses containing only Roman-numeral letters, digits, periods, semicolons and spaces, with at least one numeral/digit.")
    for record_id, matches in parentheticals[:5]:
        print(f"  {record_id}: {matches}")
    stats["parenthetical_chunks"] = len(parentheticals)
    return stats


def main(*, overwrite_report: bool = False) -> None:
    # Explicit replacement is available for regenerating only this task's report.
    if REPORT.exists() and not overwrite_report:
        raise FileExistsError(f"Refusing to overwrite existing file: {REPORT}")
    if not Path("./chroma_store").is_dir():
        raise FileNotFoundError("Run from the repository root containing chroma_store")
    original_source = SOURCE.read_bytes()
    chunks = [json.loads(line) for line in original_source.decode("utf-8").splitlines()]
    client = chromadb.PersistentClient(path="./chroma_store")
    collection = client.get_collection(name="sages")
    original_config = copy.deepcopy(collection.configuration_json)
    before = collection.get(include=["embeddings", "documents", "metadatas"])
    assert collection.count() == len(before["ids"]) == len(chunks) == 1124
    expected = {chunk["id"]: chunk for chunk in chunks}
    assert len(expected) == len(chunks) and set(before["ids"]) == set(expected)
    for record_id, document in zip(before["ids"], before["documents"], strict=True):
        assert document == expected[record_id]["text"]
    with REPORT.open("w" if overwrite_report else "x", encoding="utf-8", newline="\n") as report:
        with contextlib.redirect_stdout(report):
            stats = run_experiments(collection, chunks)
            after = collection.get(include=["embeddings", "documents", "metadatas"])
            index = {record_id: i for i, record_id in enumerate(before["ids"])}
            assert collection.count() == len(after["ids"]) == 1124
            assert set(after["ids"]) == set(index)
            for i, record_id in enumerate(after["ids"]):
                old = index[record_id]
                assert after["documents"][i] == before["documents"][old]
                assert after["metadatas"][i] == before["metadatas"][old]
                assert np.array_equal(after["embeddings"][i], before["embeddings"][old])
            assert collection.configuration_json == original_config
            assert SOURCE.read_bytes() == original_source
            print("\nVerified unchanged: all 1,124 stored IDs, embeddings, documents, metadata, collection configuration, and chunks.jsonl bytes.")
            print(f"chunks.jsonl SHA256: {hashlib.sha256(original_source).hexdigest()}")
    print(f"Full output: {REPORT}")
    print("Completed all five parts: 31 vector searches; collection and source unchanged (1,124 chunks).")
    print("All-keyword chunk counts:", {query: stats[query] for query in BASELINES})
    print(f"Exact words: dying={stats['dying']} chunks; afraid={stats['afraid']} chunks.")
    for category, (low, high) in stats["distance_ranges"].items():
        print(f"{category} best-distance range: {low:.3f}–{high:.3f}")
    print(f"Stray character types: {len(stats['stray'])}; citation-style parenthetical chunks: {stats['parenthetical_chunks']}.")


if __name__ == "__main__":
    main()
