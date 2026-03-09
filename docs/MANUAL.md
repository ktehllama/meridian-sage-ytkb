# Command Manual

## Global flags
These apply to every command and go before the subcommand.

```
python pipeline.py --db <path/to/knowledge.db> --vectors <path/to/yc_vectors> <command>
```

| Flag | Default | Description |
|---|---|---|
| `--db` | `knowledge.db` | Path to SQLite database |
| `--vectors` | `yc_vectors` | Path to ChromaDB directory |

---

## Commands

### `add-channel`
Scrapes a YouTube channel into SQLite, then embeds any new videos into ChromaDB. Incremental — skips videos already in the DB.

```
python pipeline.py add-channel <@handle_or_url>
python pipeline.py add-channel <@handle_or_url> --limit <int>
python pipeline.py add-channel <@handle_or_url> --delay <float>
python pipeline.py add-channel <@handle_or_url> --min-duration <seconds>
python pipeline.py add-channel <@handle_or_url> --max-duration <seconds>
python pipeline.py add-channel <@handle_or_url> --skip-keywords <"keyword1,keyword2">
```

| Flag | Default | Description |
|---|---|---|
| `--limit` | none | Max number of videos to scrape |
| `--delay` | `1.0` | Seconds between transcript fetch requests |
| `--min-duration` | `300` | Minimum video duration in seconds |
| `--max-duration` | `7200` | Maximum video duration in seconds |
| `--skip-keywords` | `"shorts"` | Comma-separated title keywords that auto-skip a video |

---

### `sync`
Embeds any videos that are in SQLite but missing from ChromaDB. Use this to resume after an interrupted `add-channel` run without re-scraping.

```
python pipeline.py sync
python pipeline.py sync --db <path> --vectors <path>
```

---

### `status`
Shows current state of both the SQLite DB and ChromaDB: channel names, video counts, transcript counts, word counts, and chunk counts.

```
python pipeline.py status
python pipeline.py status --db <path> --vectors <path>
```

---

### `rebuild`
Wipes ChromaDB entirely and re-embeds all videos from SQLite. Prompts for confirmation before proceeding.

```
python pipeline.py rebuild
python pipeline.py rebuild --db <path> --vectors <path>
```

---

### `rechunk`
Same as `rebuild` but named for intent: wipes ChromaDB and re-embeds everything at the current `CHUNK_WORDS` size. Use this after changing the chunk size constant. No re-scraping — reads from SQLite only.

```
python pipeline.py rechunk
python pipeline.py rechunk --db <path> --vectors <path>
```

---

### `search`
Runs a raw semantic search against ChromaDB from the terminal. Bypasses the full MCP retrieval pipeline (no BM25, no cross-encoder) — useful for quick debugging.

```
python pipeline.py search "<query>"
python pipeline.py search "<query>" --top <int>
python pipeline.py search "<query>" --vectors <path>
```

| Flag | Default | Description |
|---|---|---|
| `--top` | `5` | Number of results to return |
