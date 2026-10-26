# Ask the Sages

Ask the Sages is a Python command-line app for asking questions, adding passages, inspecting what is stored, and deleting user-added passages. It retrieves one nearby passage from each available tradition and displays separate blocks with the source, translator, distance, and a strong/moderate/weak label; if the nearest passage is too far away, it refuses to show passages. It returns existing text from the collection rather than generating an answer or calling an external language-model API.

## What is stored

The built-in collection contains **1,124 English-language chunks**, each at most **150 whitespace-separated words**. A chunk is a searchable passage, not necessarily a whole chapter: the four works have different structures, so the parsers use different source units.

| Tradition | Work / Gutenberg edition title | Translator | Built-in chunks | Source | Translation year |git add README.md
git commit -m "Add project README"
git push origin main
|---|---|---|---:|---|---|
| Confucian | Analects / *The Chinese Classics — Volume 1: Confucian Analects* | James Legge | 299 | [Gutenberg #4094](https://www.gutenberg.org/ebooks/4094) | Not specified in the checked ebook metadata |
| Daoist | Tao Te Ching / *The Tao Teh King, or the Tao and its Characteristics* | James Legge | 105 | [Gutenberg #216](https://www.gutenberg.org/ebooks/216) | Not specified in the checked ebook metadata |
| Stoic | Meditations / *Thoughts of Marcus Aurelius Antoninus* | George Long | 615 | [Gutenberg #15877](https://www.gutenberg.org/ebooks/15877) | Not specified in the checked ebook metadata |
| Greek | Plato's *Apology* | Benjamin Jowett | 105 | [Gutenberg #1656](https://www.gutenberg.org/ebooks/1656) | Not specified in the checked ebook metadata |

These are the particular Gutenberg transcriptions used, not claims about a verified print-edition year. Their Gutenberg release dates are dates of electronic publication, not translation dates. The translation years still need bibliographic verification if required by the assignment.

The source units and exclusions are:

- **Apology:** paragraphs from Socrates' speech after the `APOLOGY` heading. Jowett's scholarly introduction is excluded. Short neighbouring paragraphs can be merged when they fit within 150 words; labels use the first original paragraph's number.
- **Meditations:** numbered items within the 12 books, starting at `THE THOUGHTS` after `THE PHILOSOPHY` and stopping before `INDEXES.`. Each book's unnumbered opening is item 1. The biography, philosophy essay, indexes, footnote bodies and markers, Greek transliterations, and two location colophons are excluded. Numeral-only cross-references and stray `+` markers are removed, while translator insertions and parentheticals containing real words remain. Items are never merged.
- **Analects:** English chapters from the first `BOOK I.` heading through Book XX. Whole lines containing CJK characters or fullwidth punctuation are removed, even when they interrupt an English continuation. Consecutive chapters in the same book are merged up to 120 words; a longer individual chapter is handled separately. Digitizer notes and the editorial locator `[17.1]` are excluded. Five printed Roman-numeral chapter headings have errors, so section numbers follow chapter positions within each book.
- **Tao Te Ching:** all 81 chapters, kept separate. Ambiguous starts are inferred between neighbouring explicit chapter starts and validated in order. Front matter and `PART` headings are excluded. **The indented verse is retained**, joined into the chapter text; it is part of the translation.

All files have CRLF line endings normalized and Gutenberg headers/footers removed. Italic underscores are removed. Long units are divided at sentences, then semicolons, colons, commas, and only as a last resort at word boundaries. Split pieces carry `part i/n` labels and are balanced to avoid tiny tails where the allowed boundaries permit it; complete short sayings are still kept.

Each Chroma record has an ID, a document containing the passage text, an embedding, and metadata:

| Field | Purpose |
|---|---|
| `tradition` | Group passages and retrieve one result per tradition. |
| `work` | Identify the work, or the title supplied for a user passage. |
| `section` | Locate the paragraph, book/item, chapter range, or split part. |
| `translator` | Credit the translation; for user passages, hold the supplied source note or `user-added`. |
| `words` | Store an integer word count, used for display and length-filter experiments. |
| `source` | User-added records have `source="user"`, allowing deletion to be restricted to them. Built-ins do not have this field. |

Built-in IDs are deterministic for an unchanged build. User IDs begin with `user-` and use the first 12 hexadecimal characters of SHA-256 over the normalized tradition, title, and chunk text concatenated together. Repeated loading or adding the same passage does not create another ID. Runtime additions go directly into Chroma, **not** into `data/processed/chunks.jsonl`, so the live total can exceed 1,124.

## How to add and search

Choose **1** and enter a question. Empty questions are re-prompted; questions longer than 500 characters are truncated with a notice. The app checks the nearest passage overall, then, if it is close enough, searches separately within every tradition currently stored. The four built-in traditions appear first, followed by new traditions alphabetically. A tradition whose own result is too far away gets a “no close passage” block instead of a passage.

Choose **2** to add text. Enter an existing or new tradition, a title, an optional source note, and the passage; finish with a line containing only `END`. Text must contain at least five words. The app previews the chunks and warns if a nearest existing passage is below the empirical duplicate threshold of **0.35**, asking `add anyway? y/n` before inserting. The new passage is searchable immediately, including under a new tradition label.

Choose **3** to see counts per tradition and work plus user-added records. Choose **4** to delete the listed user-added records after typing exactly `YES`; this action cannot delete built-ins. Choose **5**, or press Ctrl-D/Ctrl-C, to quit.

## The two queries where keyword search fails

The baseline in [step6_experiments.py](step6_experiments.py) is BM25 with `k1=1.5`, `b=0.75`, lowercase alphabetic tokens, **exact word matching, and no stemming**. BM25 retains stopwords; the separate all-keywords check and reported keyword overlaps remove the stopword list in [explore_queries.py](explore_queries.py). The following are the recorded experimental results in [experiments2.txt](data/processed/experiments2.txt), before the later Meditations markup cleanup.

**Video example: “why can a gentle person defeat a forceful one”**

| Vector rank | Passage | Squared-L2 distance | BM25 rank |
|---:|---|---:|---:|
| 1 | Tao Te Ching, Chapter 67, part 2/2 | 0.942 | 59 |
| 2 | Meditations, Book 11, item 9 | 0.958 | 588 |
| 3 | Tao Te Ching, Chapter 69 | 1.011 | 692 |

These passages discuss gentleness, restraint, and responding to opposition, yet none shares an exact non-stopword query token. Exact-word BM25 ranks them poorly because related ideas use different wording, including `gentleness` rather than `gentle`; stemming could help with that particular difference. The Meditations passage concerns remaining gentle toward people who obstruct you, rather than defeating them, so it is a related passage rather than a direct answer.

**Second example: “someone who is afraid of dying”**

| Vector rank | Passage | Squared-L2 distance | BM25 rank |
|---:|---|---:|---|
| 1 | Tao Te Ching, Chapter 74 | 0.875 | 31 |
| 2 | Meditations, Book 9, item 3, part 1/3 | 1.028 | Not in top 50 |
| 3 | Meditations, Book 8, item 58 | 1.090 | Not in top 50 |

Again, none of the three shares an exact non-stopword query token. There are **17 chunks containing `afraid`** and **9 containing `dying`**, but no chunk contains all three content words, `someone`, `afraid`, and `dying`. BM25 does find passages with those words—its first result is Tao Te Ching 75, about taxes and famine—but fails to put the two Meditations passages about fear of death near the top because they use words such as `fear`, `fears`, and `death`.

The vector search has its own failure here: Tao Te Ching 74 discusses people who **do not fear death**. It matches the topic but reverses the question's premise. The two Meditations hits more directly address fear of death. This is why retrieving a related passage is not the same as answering a question.

## Data download and loading

After setting up `.venv` as described below, run these commands from the project root:

```bash
mkdir -p data/raw
curl -fL https://www.gutenberg.org/cache/epub/4094/pg4094.txt -o data/raw/pg4094.txt
curl -fL https://www.gutenberg.org/cache/epub/216/pg216.txt -o data/raw/pg216.txt
curl -fL https://www.gutenberg.org/cache/epub/1656/pg1656.txt -o data/raw/pg1656.txt
curl -fL https://www.gutenberg.org/cache/epub/15877/pg15877.txt -o data/raw/pg15877.txt
.venv/bin/python build_chunks.py
.venv/bin/python load_db.py
```

The files were downloaded manually with `curl` after `download_data.py` encountered a network error and then a certificate-verification error. The commands above reproduce those downloads; the original manual command flags were not recorded. SSL verification was not disabled. `download_data.py` can read existing files without downloading them again.

The original loader processed 50 chunks first, then batches of 100, ending with 74. The [Step 4 notes](prompt_log.md#step-4-load-the-chunks-into-a-persistent-chroma-collection) record:

| Original load run | First 50 chunks, measured | Full-load linear estimate | Full-load measured time |
|---|---:|---:|---|
| 1 | 1.063 s | 23.888 s | Not recorded |
| 2 | 1.025 s | 23.044 s | Not recorded |

Both runs ended at 1,124 records. The estimates are not measurements of the full load. The current loader skips unchanged records, so a reload may perform no embedding at all. It upserts new/changed built-ins, removes stale non-user records, and preserves records with a `user-` ID or `source="user"`; its source-file checks compare only built-ins with the JSONL.

## Database and embedding model

The tested database version is **Chroma 1.5.9**, opened with `chromadb.PersistentClient(path="./chroma_store")`. The app reads the existing collection named `sages`; the separate `smoke` collection is only a persistence smoke test.

Chroma's default embedding function uses the local ONNX **`all-MiniLM-L6-v2`** model and produces 384-dimensional embeddings. On first use it downloads the model archive into `~/.cache/chroma/onnx_models/all-MiniLM-L6-v2/`. Searches run locally once that model is cached; no hosted model API or API key is used. The installed implementation truncates input at **256 tokens**, so the 150-word chunk limit reduces the risk of losing text but does not guarantee every chunk fits within 256 tokens.

Distances use the default **squared L2** metric: smaller is closer. They are not confidence percentages and can exceed 1.

The collection uses **`ef_search=200`**. [check_recall.py](check_recall.py) compared approximate results against NumPy brute-force distances over all stored embeddings. [tune_ef.py](tune_ef.py) then tested 14 queries:

| `ef_search` | Queries recovering all exact top 5 | Correct tradition-filtered top-1 pairs |
|---:|---:|---:|
| 100 | 12/14 | 56/56 |
| 200 | 14/14 | 56/56 |
| 500 | 14/14 | 56/56 |
| 1200 | 14/14 | 56/56 |

The smallest passing value was retained. The benchmark reopens the index in a fresh Python process after each change because the already-open index retained its earlier runtime setting during the initial experiment. Perfect recall on those 14 queries is not a guarantee for every future question or changed corpus. New collections created by `load_db.py` receive the setting automatically; creation arguments do not update an already-existing collection.

## How to run

Python **3.13.2** was used for development. Create the environment with the Python interpreter you intend to use, then invoke its executables explicitly so package installation does not go into an active conda environment:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt "chromadb==1.5.9"
```

The version constraint reproduces the tested Chroma API; `requirements.txt` itself currently contains an unpinned `chromadb` dependency. NumPy is installed as a Chroma dependency.

Next run the [download and loading commands](#data-download-and-loading), then start the menu from the project root:

```bash
.venv/bin/python main.py
```

```text
- My Sages -
1. Ask a question
2. Add a passage
3. Show what is stored
4. Delete my added passages
5. Quit
```

If the collection is missing or empty, the app prints build commands and exits. An existing nonempty collection must have `ef_search=200` to pass the library's opening check.

Useful demonstrations:

```bash
.venv/bin/python demo_ask.py
.venv/bin/python explore_queries.py --full-top3 "why can a gentle person defeat a forceful one"
.venv/bin/python demo_add.py
```

`demo_add.py` temporarily inserts a made-up passage, checks immediate search and reload survival, then removes its own test record. It verifies that the starting records and embeddings are restored. The scripted menu tests are recorded in [cli_transcript1.txt](data/processed/cli_transcript1.txt) and [cli_transcript2.txt](data/processed/cli_transcript2.txt).

`data/`, `chroma_store/`, `.venv/`, `__pycache__/`, and `.env` are git-ignored. A fresh checkout therefore needs its own data download, build, and load. The linked reports are local evidence files and will not be included in a normal Git commit unless separately packaged. The original evaluation scripts assume a built-in-only collection of 1,124 records; runtime user additions can invalidate that assumption. `step6_experiments.py` also refuses to overwrite an existing report by default.

## Limitations and failure cases

The distance bands are empirical choices from experiments on about **35 queries**, not guarantees:

| Band | Unrounded squared-L2 distance |
|---|---|
| Strong | Below 1.10 |
| Moderate | At least 1.10 and below 1.30 |
| Weak | At least 1.30 and below 1.40 |
| None | At least 1.40 |

The overall closest result determines refusal. Otherwise each tradition is judged by its own closest result, and weak passages carry `weak match: read with caution`.

- **Off-topic questions can pass the cutoff.** “the plot of Star Wars” returned 1.343 and was shown as weak rather than refused. Recorded off-topic and adjacent-question distance ranges overlap, including roughly 1.31–1.39. A single distance threshold cannot reliably identify unrelated questions.
- **Low distance does not establish the right meaning.** “my elderly parents need me, how should I treat them” returned Socrates discussing relatives at 1.158 instead of putting the Analects passage on filial duty first. “I was blamed for something I did not do” returned Meditations 12.12 at 0.917, which says not to blame others, rather than addressing being wrongly blamed. These are historical experimental distances; later text cleanup can change embeddings and distances.
- **Weak matches can be off-topic or unkind.** The supplied testing notes report that “why am i stupid” retrieved an Analects passage about the dull who do not learn. The app provides no guarantee that retrieved text is appropriate advice.
- **Short passages remain.** The 25-word filtering experiment changed the unjust-order results but did not demonstrate an improvement across the three test queries, so complete short sayings were retained.
- **The translations use older English.** Modern wording can be farther from the text in embedding space. Even a relevant passage may be phrased in a way the user finds unfamiliar.
- **The corpus and metadata are limited.** These are four particular translations, not comprehensive accounts of their traditions. User additions can introduce unverified text or attribution. The near-duplicate cutoff is also heuristic: one two-word edit measured 0.226543 while an unrelated pair measured 1.701635, which is only a small calibration example.

## AI use and where it was wrong

**AI-generated:** this entire README draft was written by Codex, including the first four sections. It is not a record of independently student-written prose. The student should rewrite those required sections in their own words and review every claim before submission.

The [prompt log](prompt_log.md) records that **Claude** was used in a separate chat for project discussion, planning, and prompt drafting, while **Codex** wrote and ran the Python code. The user supplied constraints, inspected raw files and search output, selected the video query, and directed fixes. The Python implementation was AI-generated through that iterative process.

Examples of corrections and limits in that process:

- An early AI suggestion identified Gutenberg **#2680** for Meditations, but it was a different, older translation. Checking the text header led to **#15877**, whose [Gutenberg page credits George Long](https://www.gutenberg.org/ebooks/15877). The earlier suggestion and correction were supplied in the README skeleton; they are not recorded as a code change in this chat.
- Approximate search initially missed the true nearest passage even though its returned distances were correct. For the unfair-treatment query, the Greek passage at 1.210 was absent from the unfiltered top 10. Brute-force checking exposed this; tuning recovered all exact top-five results for the 14 test queries at `ef_search=200`.
- The original instruction combined a 150-word maximum with never splitting a sentence. A roughly 420-word sentence made those requirements incompatible. The user chose clause boundaries and ultimately a word-boundary fallback rather than silently dropping text.
- The first download attempt failed on network/certificate checks. The user downloaded the files with `curl`; SSL verification was not disabled.
- Deprecated patterns such as `chromadb.Client(Settings(...))` and `collection.persist()` were explicitly prohibited. Neither appears in the project's Python implementation; it uses `PersistentClient`, current collection methods, and automatic persistence.

The saved experiments support specific observations, not a claim that AI-generated code or semantic retrieval is always correct. Translation years and the original full-load elapsed time remain unverified/unrecorded, respectively.
