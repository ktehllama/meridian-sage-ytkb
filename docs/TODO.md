# Sage YTKB — TODO & Pending Work

_Last updated: 2026-03-10_

---

## ⚠️ High Priority

- [ ] Build Telegram bot to replace CLI tool (`add-channel`, `sync`, `status`, etc.) — eventually make one source of truth DB (Pi), always add to that

---

## Pending: Token Reduction Plan (v2.8)

**Context:** Claude Pro quota drains fast with the current MCP setup because:
1. Claude Desktop accumulates every tool result in conversation context — 5 searches = ~10K tokens in context permanently
2. `yt_search_knowledge_base` default `n_results=8` returns ~1,900 tokens/call
3. Verbose per-chunk headers add unnecessary overhead

### Tier 1: MCP Quick Wins (~5 min)
**File: `yt_knowledge_mcp.py`**

- [ ] Lower default `n_results` from **8 → 4** in `yt_search_knowledge_base` signature
- [ ] Compact `_format_chunk()` output format:
  - **Before:** 7-line block (`--- EXCERPT N ---`, `Video:`, `Timestamp:`, `YouTube Link:`, `Chunk: X/Y`, blank, text)
  - **After:** 1-line header + text: `[N] "Title" · 5:30→8:45 · https://youtu.be/ID?t=330\n{text}`
  - Saves ~20 tokens/chunk, ~80 tokens/call
- [ ] Update `yt_search_knowledge_base` docstring: add guidance to start with `n_results=3–4`

After changes: restart Claude Desktop MCP. Expected: ~50% fewer tokens per search.

---

### Tier 2: `sage_query.py` Standalone CLI (architectural fix)

**New file: `sage_query.py`** — bypasses Claude Desktop entirely.

```
python sage_query.py "how do startups find product market fit"
python sage_query.py "fundraising advice" --results 6
python sage_query.py "YC tips" --raw    # no AI, just raw chunks
```

**Architecture:** Question → hybrid search (existing ChromaDB + BM25 + rerank) → Claude API (Haiku) → printed answer. Each query is fully stateless, no context accumulation.

**Cost:** ~$0.004/query vs Pro subscription. ~$1 for 250 queries.

**Key implementation notes:**
- Do NOT import `yt_knowledge_mcp.py` directly (module-level BM25 thread side effects). Duplicate the ~60-line search core inline.
- Reuse same env vars: `CHROMA_DB_PATH`, `BM25_CACHE_PATH` (already in claude_desktop_config.json)
- ANTHROPIC_API_KEY from env; auto-fallback to `--raw` mode if missing
- Model: `claude-haiku-4-5-20251001`
- `pip install anthropic` needed

---

## Completed This Session (v2.7 — 2026-03-06)

- [x] Merged @CGPGrey → @cgpgrey (1 video, duplicate casing)
- [x] Registered 5 missing channels in `channels` table: @TED, @TEDx, @NeuralNine, @eucroix, @lexfridman
- [x] `pipeline.py sync` — embedded 228 missing videos / 16,157 new chunks (total: 249,641)
- [x] Migrated 338 stale `chunk_count=0` entries in `video_metadata` collection — all channels now show correct counts in `yt_list_videos`
- [x] Updated CHANGELOG.md with v2.7 entry

---

## Other Notes

- BM25 cache will rebuild on next Claude Desktop restart (new chunks from sync)
- All channels verified: 0 remaining truly-missing chunks, 0 stale chunk_count entries
- smoke_test.py passes all 8 checks
