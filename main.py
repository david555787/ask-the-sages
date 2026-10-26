"""My Sages: a small terminal app over the existing local passage collection."""

from collections import Counter
import sys

from chromadb.errors import NotFoundError

from sages import (
    DISPLAY_NAMES, N_TRADITIONS, add_passage, ask, delete_user_passages,
    format_answer, list_user_passages, open_collection,
)


MENU = """- My Sages -
1. Ask a question
2. Add a passage
3. Show what is stored
4. Delete my added passages
5. Quit"""


def read_line(prompt: str) -> str:
    """Read a line, echoing piped input so scripted runs make readable transcripts."""
    value = input(prompt)
    if not sys.stdin.isatty():
        print(value)
    return value


def required_input(prompt: str) -> str:
    """Re-prompt until a field contains something besides whitespace."""
    while True:
        value = read_line(prompt).strip()
        if value:
            return value
        print("Please enter a non-empty value.")


def print_build_commands() -> None:
    """Show exact download and build commands without running them."""
    print("No stored passages are available. Run these commands from the project folder:")
    print("mkdir -p data/raw")
    for book_id in (4094, 216, 1656, 15877):
        print(f"curl -fL https://www.gutenberg.org/cache/epub/{book_id}/pg{book_id}.txt -o data/raw/pg{book_id}.txt")
    print(".venv/bin/python build_chunks.py")
    print(".venv/bin/python load_db.py")


def ordered_traditions(values) -> list[str]:
    """Place built-in traditions first, followed by new labels alphabetically."""
    values = set(values)
    return [value for value in N_TRADITIONS if value in values] + sorted(values - set(N_TRADITIONS))


def display_name(tradition: str) -> str:
    """Use the built-in display names or title case for a user-created label."""
    return DISPLAY_NAMES.get(tradition, tradition.title())


def ask_question(collection) -> None:
    """Read a nonempty question, limit it to 500 characters, and display retrieval."""
    question = required_input("Question: ")
    if len(question) > 500:
        print("Question was longer than 500 characters; truncated to 500 characters.")
        question = question[:500]
    print(format_answer(ask(question, collection)))


def add_new_passage(collection) -> None:
    """Collect a passage and require approval of duplicate warnings before writing."""
    metadata = collection.get(include=["metadatas"])["metadatas"]
    traditions = ordered_traditions(row["tradition"] for row in metadata if row and row.get("tradition"))
    print("Existing traditions: " + ", ".join(traditions))
    print("You may enter an existing tradition or a new label.")
    tradition = required_input("Tradition: ")
    title = required_input("Title: ")
    source_note = read_line("Source note (optional): ").strip()
    print("Paste passage text. Finish with a line containing only END.")
    lines = []
    while True:
        line = read_line("> ")
        if line == "END":
            break
        lines.append(line)
    text = "\n".join(lines)
    preview = add_passage(text, tradition, title, collection, source_note, dry_run=True)
    if preview["near_duplicates"]:
        print("Near-duplicate warnings:")
        for warning in preview["near_duplicates"]:
            print(f"  {warning['chunk_id']} -> {warning['id']} | {warning['work']} | {warning['section']} | distance {warning['distance']:.3f}")
        while True:
            answer = read_line("add anyway? y/n: ").strip().lower()
            if answer in ("y", "n"):
                break
            print("Please enter y or n.")
        if answer == "n":
            print("Cancelled. No passage was added.")
            return
    result = add_passage(text, tradition, title, collection, source_note)
    print(f"Added {result['new']} new chunk(s); {result['already_present']} already present.")
    print("IDs: " + ", ".join(result["ids"]))
    print("The passage is searchable now.")


def print_user_passages(rows: list[dict]) -> None:
    """Display each user-owned passage with its ID and a short preview."""
    if not rows:
        print("No user-added passages.")
    for row in rows:
        print(f"{row['id']} | {row['tradition']} | {row['work']} | {row['section']} | {row['words']} words")
        print("  " + row["preview"])


def show_stored(collection) -> None:
    """Print total counts, per-tradition and per-work counts, and user records."""
    metadata = collection.get(include=["metadatas"])["metadatas"]
    traditions = Counter((row or {}).get("tradition", "unknown") for row in metadata)
    works = Counter((row or {}).get("work", "unknown") for row in metadata)
    users = list_user_passages(collection)
    print(f"Stored passages: {collection.count()}; user-added: {len(users)}")
    print("By tradition:")
    for tradition in ordered_traditions(traditions):
        print(f"  {display_name(tradition)}: {traditions[tradition]}")
    print("By work:")
    for work, count in sorted(works.items()):
        print(f"  {work}: {count}")
    print("User-added passages:")
    print_user_passages(users)


def delete_added_passages(collection) -> None:
    """Delete only the listed user records after an exact YES confirmation."""
    users = list_user_passages(collection)
    print_user_passages(users)
    if not users:
        return
    answer = read_line("Type YES to delete these user-added passages: ").strip()
    if answer != "YES":
        print("Cancelled. Nothing was deleted.")
        return
    deleted = delete_user_passages(collection, [row["id"] for row in users])
    print(f"Deleted {deleted} user-added passage(s). Built-in passages were not touched.")


def main() -> None:
    """Open the collection and handle menu choices, input errors, and clean exits."""
    try:
        try:
            collection = open_collection()
        except (FileNotFoundError, NotFoundError):
            print_build_commands()
            return
        if collection.count() == 0:
            print_build_commands()
            return
        print(f"Stored passages: {collection.count()}; user-added: {len(list_user_passages(collection))}")
        actions = {"1": ask_question, "2": add_new_passage, "3": show_stored, "4": delete_added_passages}
        while True:
            print("\n" + MENU)
            choice = read_line("Choice: ").strip()
            if choice == "5":
                print("Goodbye.")
                return
            if choice not in actions:
                print("Please choose a number from 1 to 5.")
                continue
            try:
                actions[choice](collection)
            except (EOFError, KeyboardInterrupt):
                raise
            except Exception as error:
                print(f"Could not complete that action: {error}")
    except (EOFError, KeyboardInterrupt):
        print("\nGoodbye.")
    except Exception as error:
        print(f"Could not open My Sages: {error}")


if __name__ == "__main__":
    main()
