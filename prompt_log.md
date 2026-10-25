# Prompt Log

## Tools

I used Codex to write and run the code. I used Claude to discuss project topics, plan the steps, and draft the prompts that I gave to Codex.

## Development log

### Step 1: Chroma persistent smoke test

Tool: Codex (GPT-6.1 Sol, Medium, as shown in the app)

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