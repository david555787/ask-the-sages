# Prompt Log

## Tools

I used Codex to write and run the code. I used Claude to discuss project topics, plan the steps, and draft the prompts that I gave to Codex.

## Development log

### Step 1: Chroma persistent smoke test


Prompt (verbatim):

```
I'm starting a brand-new standalone Python project in this folder, which is already a git repository (currently on branch "master"). Please do the following yourself, running the commands for me:

1. Rename the git branch to "main".
2. Create requirements.txt containing chromadb, and a .gitignore that ignores chroma_store/, data/, .venv/, __pycache__/ and .env.
3. Create a virtual environment in .venv inside this folder and install requirements.txt into it. IMPORTANT: my shell has a conda "base" environment active, so make sure everything is installed into the project's .venv and NOT into conda. Always call .venv/bin/python and .venv/bin/pip explicitly.
4. Write smoke_test.py that:
   - creates chromadb.PersistentClient(path="./chroma_store")
   - gets or creates a collection called "smoke"
   - upserts 10 short hand-written sentences (about different life situations) with unique string ids and a metadata field "tradition" set to "test"
   - prints collection.count()
   - runs one query with n_results=3 and prints the FULL raw results object, including distances
5. Run smoke_test.py TWICE in separate runs and show me both outputs, so I can confirm that count() is still 10 on the second run (proving the data persists).
6. Show me the output of ".venv/bin/pip show chromadb" so I can record the installed version.
7. Make one git commit with the message "Step 1: Chroma persistent smoke test". Do not push anything.

Use only the current Chroma API. Do NOT use chromadb.Client(Settings(...)) or collection.persist().

If a command fails because of network access or sandbox permissions, stop and tell me exactly what was blocked instead of working around it.

After that, explain what each argument of query() does and the exact shape of the results object (I'm told it is a list of lists), and point out anything in the output that surprised you or that I should double-check.
```

What happened (my notes):

- The sandbox blocked the pip install with a DNS error because it had no network access. I approved the command once, and the install then succeeded.
- I ran the script again myself in the terminal, and collection.count() was still 10.
- The installed Chroma version is 1.5.9.
- The three distances were 0.60, 1.33 and 1.52. They are L2 distances, so they can be greater than 1.
- The third result was a less relevant sentence, but it was still returned. This shows that top-k always returns k results, even when the match is weak.

### Step 2: Download the Gutenberg texts

Tool: Codex (GPT-6.1 Sol, Medium, as shown in the app)

Prompt (verbatim):

```
Add a script download_data.py that downloads these four Project Gutenberg plain-text files using only the Python standard library (urllib), saving each into data/raw/ as UTF-8:

- 4094 (Confucian Analects, Legge)
- 216 (Tao Te Ching, Legge)
- 1656 (Plato's Apology, Jowett)
- 15877 (Marcus Aurelius, Meditations, George Long translation)

URL pattern: https://www.gutenberg.org/cache/epub/{id}/pg{id}.txt

Also write a function strip_boilerplate(text) that keeps only the text between the line starting with "*** START OF" and the line starting with "*** END OF" (exclude those marker lines). Do not parse chapters yet.

For each file, print: the Title and Translator lines from the original header, the total character count after stripping, and the first 40 lines after the start marker. Skip downloading if the file already exists. Use .venv/bin/python explicitly. If a command fails because of network access or sandbox permissions, stop and tell me exactly what was blocked instead of working around it.

Do not commit anything yet.
```

What happened (my notes):

- Codex wrote download_data.py, but the download failed at the first file. The sandbox had no network access (DNS error), and after I approved a retry it failed with CERTIFICATE_VERIFY_FAILED.
- Codex stopped and reported the error instead of disabling certificate verification, which is what I had asked for in the prompt. I did not want to turn off SSL checks.
- I downloaded the four files myself with curl into data/raw/ (pg4094, pg216, pg1656, pg15877). The file sizes looked reasonable.
- I checked the header of pg15877.txt and confirmed that the translator is George Long.
- Looking at the files with grep and sed, I found that most of the Meditations file is not Marcus's text. It contains a biographical sketch, a philosophy essay and two indexes. The real text is only between "THE THOUGHTS" and "INDEXES." I need to exclude the rest before building the database.
- The files use Windows (CRLF) line endings, so the parsing code must normalize them.

### Step 3a: Chunking and parsers for the Apology and the Meditations

Tool: Codex (GPT-6.1 Sol, Medium, as shown in the app)

Prompt (verbatim):

```
I'm building a semantic search app over four public-domain classics. The raw Project Gutenberg files are already downloaded in data/raw/ (pg4094.txt, pg216.txt, pg1656.txt, pg15877.txt). Do NOT download anything and do NOT disable SSL verification. First read download_data.py and reuse its strip_boilerplate() (text between the "*** START OF" and "*** END OF" lines) if it works; make sure it runs without network access when the files already exist.
Important facts I verified in the files:

* All files use Windows (CRLF) line endings. Normalize "\r\n" to "\n" when loading.
* The embedding model I will use reads only about 256 tokens, so every chunk must be at most 150 words. Split longer text at sentence boundaries and never cut mid-sentence.

Task: create chunking.py (shared helpers: load_text, word_count, split_long_text(text, max_words=150)) and parsers.py with two functions. Each returns a list of dicts with the keys: text, tradition, work, section, translator.

1. parse_apology(): Plato's Apology, translator "Benjamin Jowett", tradition "greek", work "Apology". The file starts with a long scholarly Introduction by Jowett that is NOT Plato's text and must be excluded. Find where Socrates' speech actually begins (look for the "APOLOGY" heading after the introduction) and show me the 10 lines around the start you choose so I can verify. The text is plain paragraphs separated by blank lines. Each paragraph is a unit. Split paragraphs longer than 150 words at sentence boundaries. Merge consecutive paragraphs shorter than 40 words with their neighbour as long as the result stays under 150 words. section = "paragraph N", using the original paragraph numbering.
2. parse_meditations(): Marcus Aurelius, Meditations, translator "George Long", tradition "stoic", work "Meditations". The file contains a long Biographical Sketch, a Philosophy essay and indexes that are NOT Marcus's text. Only the section that starts at the line "THE THOUGHTS" which comes after "THE PHILOSOPHY" (about line 2120 in the CRLF-normalized file) and ends right before the line "INDEXES." (about line 7175) is the real text. Inside it, the 12 books are headed by a Roman numeral alone on a line ("I." ... "XII."), and items are numbered paragraphs such as "2. Let no act be done...". Note: my grep for lines starting with "1. " found nothing, so the first item of a book is formatted differently from the others. Inspect the start of several books, handle it, and tell me what you found. Each numbered item is one unit: do not merge items, and split items over 150 words at sentence boundaries. Clean the text: remove footnote markers like "[A]", remove footnote bodies (indented blocks that start with a "[A]"-style marker, plus their indented continuation lines), remove "[Greek: ...]" transliterations, and drop any colophon lines at the end of a book (for example one saying where it was written), but tell me which ones you dropped. Keep other bracketed words because they are the translator's insertions. section = "Book N, item M".

Then write build_chunks.py that runs the parsers, assigns deterministic ids (for example "meditations-0001"), writes data/processed/chunks.jsonl, and prints for each work: the number of chunks, the min/average/max word count, the first 3 chunks and 3 random chunks in full. Also assert: exactly 12 books are found in the Meditations, and no chunk contains "[Greek", "[A]" or the word "INDEX". Use .venv/bin/python. Do not commit anything.
```

What happened (my notes):

- Codex created chunking.py, parsers.py and build_chunks.py and generated data/processed/chunks.jsonl for the Apology and the Meditations.
- Codex stopped to ask me a question. My prompt required both a 150-word maximum per chunk and "never cut mid-sentence", but some sentences are longer than 150 words (one sentence in the Meditations has about 420 words), so both rules cannot hold. I chose to split oversized sentences at clause boundaries (semicolons first, then colons, then commas). I chose this because the embedding model only reads about 256 tokens, so keeping a long sentence intact would silently cut off its second half, and excluding it would lose Marcus's own words.
- Apology: the text starts at the "APOLOGY" heading on line 488 of the normalized file, so Jowett's introduction is excluded. Result: 105 chunks, 16 to 150 words, average 108.44.
- Meditations: the real text is the section from "THE THOUGHTS" (line 2120) to the line before "INDEXES." (line 7175). All 12 books have an unnumbered first item, followed by items numbered from 2, so the parser numbers the first item as item 1. There are 487 source items. Result: 615 chunks, 8 to 150 words, average 74.19.
- Codex dropped two colophon lines and told me about them: "Among the Quadi at the Granua.[D]" (Book 1) and "This in Carnuntum.[A]" (Book 2).
- Nine oversized sentences were split at clause boundaries.
- Codex reported that its checks passed, and that rebuilding offline produced an identical chunks.jsonl.

### Step 3b: Parsers for the Analects and the Tao Te Ching

Tool: Codex (GPT-6.1 Sol, Medium, as shown in the app)

Prompt (verbatim):

```
Continue the same project. Read chunking.py, parsers.py and build_chunks.py first and reuse them. Add two more parsers with the same output format (text, tradition, work, section, translator), the same 150-word maximum per chunk and the same CRLF normalization, and register them in build_chunks.py so chunks.jsonl contains all four works. Do not change the existing parsers.

3. parse_analects(): Confucian Analects, translator "James Legge", tradition "confucian", work "Analects". The file mixes Chinese and English. Facts I verified:

* Every line that contains any CJK character or fullwidth punctuation (for example 【 】 、 。) is Chinese and must be removed. Chinese lines can appear anywhere, even between two English paragraphs of the same chapter, and short Chinese fragments can sit on their own line.
* The English text is indented by 8 spaces on the first line of each numbered paragraph, but continuation lines are NOT indented. Do not rely on indentation to separate English from Chinese; use the CJK test.
* English headings look like "BOOK II. WEI CHANG." and chapters look like "CHAP. XIV. When he entered ..." with optional numbered sub-paragraphs ("1.", "2.") inside a chapter.
Start at the first "BOOK I." heading (there are digitizer notes before it), and show me what comes at the very end of the text after Book XX so I can tell whether anything that is not Analects is included. Each chapter is only about 20 to 60 words, so merge consecutive chapters of the SAME book into one chunk until adding another chapter would exceed 120 words. Never merge across books. section = "Book N, chapters X-Y". Assert that exactly 20 books are found and that no chunk contains CJK characters.

4. parse_tao_te_ching(): Tao Te Ching, translator "James Legge", tradition "daoist", work "Tao Te Ching". There are 81 chapters. Facts I verified:

* A chapter that has sub-paragraphs starts like "39. 1. The things which from of old ..." (chapter number, then "1."). Further sub-paragraphs inside the chapter are numbered "2.", "3." and so on at the start of a line, and the numbers restart in every chapter, so "3. text" does NOT necessarily mean chapter 3. A sub-paragraph number can also appear alone on a line before a verse ("2." followed by indented lines).
* Some chapters have no sub-paragraphs and start as "24. He who stands ..." or as the number alone on a line ("6." then verse).
* Verse lines are indented by 3 spaces. Many of them are the actual translation of the chapter (for example chapter 39), so KEEP them: join them into the chapter text, one verse line after another separated by spaces.
Approach: first find all unambiguous chapter starts of the form "N. 1." Then, for chapters whose number is missing from that sequence, search between the two neighbouring known chapters for the line that begins with the missing number. Validate that you get exactly chapters 1 through 81, each once, in order, and print every chapter you had to infer so I can check it. Exclude anything before chapter 1 and anything after chapter 81, and tell me what you excluded. Split chapters longer than 150 words at sentence or verse boundaries. Do not merge chapters. section = "Chapter N".

For any text longer than 150 words, use exactly the same rule as the existing code for oversized text (split at sentence boundaries first, then at semicolons, colons, commas, and only as a last resort at a word boundary), keep all content, and mark split pieces as "part 1/2" in the section field. At the end, report how many chunks were split this way in each work.
Update build_chunks.py so it prints the same per-work statistics plus the total number of chunks. Use .venv/bin/python. Do not commit anything.
```

What happened (my notes):

- I added the final paragraph about oversized text to this prompt because of the conflict Codex had found in Step 3a (the 150-word limit versus never cutting a sentence), so the same rule would apply to all four works.