"""Exercise sages.py with six questions using the existing collection."""

from sages import ask, format_answer, open_collection


QUERIES = (
    "why can a gentle person defeat a forceful one",
    "someone who is afraid of dying",
    "how do I stay calm when people treat me unfairly",
    "what makes a person truly wise",
    "the plot of Star Wars",
    "how to bake sourdough bread",
)


def main() -> None:
    collection = open_collection()
    for i, query in enumerate(QUERIES):
        if i:
            print("\n" + "=" * 88 + "\n")
        print(format_answer(ask(query, collection)), flush=True)


if __name__ == "__main__":
    main()
