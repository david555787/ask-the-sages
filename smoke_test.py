"""Check Chroma persistence with stable IDs and a semantic query."""

import chromadb


def main():
    client = chromadb.PersistentClient(path="./chroma_store")
    collection = client.get_or_create_collection(name="smoke")

    sentences = [
        "I am nervous about starting a new job tomorrow.",
        "My friend and I made peace after an argument.",
        "I feel lonely after moving to a new city.",
        "I am learning to be patient with my children.",
        "My family is grieving the loss of our grandmother.",
        "I am saving money to return to school.",
        "A walk in the park helps me handle stress.",
        "I am grateful for a neighbor who brought me dinner.",
        "I need courage to apologize for my mistake.",
        "I am excited to celebrate my sister's wedding.",
    ]
    collection.upsert(
        ids=[f"smoke-{i:02d}" for i in range(1, 11)],
        documents=sentences,
        metadatas=[{"tradition": "test"} for _ in sentences],
    )

    print("collection.count():", collection.count(), flush=True)
    results = collection.query(
        query_texts=["How can I cope with feeling alone in a new place?"],
        n_results=3,
        include=["documents", "metadatas", "distances"],
    )
    print(results, flush=True)


if __name__ == "__main__":
    main()
