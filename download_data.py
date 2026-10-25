"""Download raw Gutenberg texts and preview their marker-delimited contents."""

from pathlib import Path
from urllib.request import urlopen


BOOK_IDS = (4094, 216, 1656, 15877)
RAW_DIR = Path(__file__).resolve().parent / "data" / "raw"
URL_PATTERN = "https://www.gutenberg.org/cache/epub/{id}/pg{id}.txt"


def strip_boilerplate(text: str) -> str:
    """Keep only lines between the START and END markers, excluding both.

    Preserve whitespace and line endings inside the markers. Raise ValueError
    if either marker is missing rather than silently returning unstripped text.
    """
    lines = text.splitlines(keepends=True)
    for start, line in enumerate(lines):
        if line.startswith("*** START OF"):
            break
    else:
        raise ValueError("Missing Gutenberg START marker")

    for end in range(start + 1, len(lines)):
        if lines[end].startswith("*** END OF"):
            return "".join(lines[start + 1 : end])
    raise ValueError("Missing Gutenberg END marker after START marker")


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    for book_id in BOOK_IDS:
        path = RAW_DIR / f"pg{book_id}.txt"
        if path.exists():
            print(f"\nGutenberg {book_id}: using existing {path}", flush=True)
        else:
            url = URL_PATTERN.format(id=book_id)
            print(f"\nGutenberg {book_id}: downloading {url}", flush=True)
            with urlopen(url, timeout=60) as response:
                text = response.read().decode("utf-8-sig")
            # Store the original text, including its header, in UTF-8.
            with path.open("w", encoding="utf-8", newline="") as output:
                output.write(text)

        with path.open(encoding="utf-8-sig", newline="") as source:
            original = source.read()
        stripped = strip_boilerplate(original)
        header = original.split("*** START OF", 1)[0]
        for field in ("Title", "Translator"):
            matching = [
                line for line in header.splitlines()
                if line.startswith(f"{field}:")
            ]
            print("\n".join(matching) if matching else f"{field}: (not present in header)")
        print(f"Characters after stripping: {len(stripped)}")
        print("First 40 lines after the start marker:")
        for line in stripped.splitlines()[:40]:
            print(line)


if __name__ == "__main__":
    main()
