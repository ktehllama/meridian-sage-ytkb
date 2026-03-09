"""
Smoke test for the Sage YTKB pipeline.
Run after any major change to verify DB / vector DB consistency.

Usage:
    python smoke_test.py
    python smoke_test.py --db knowledge.db --vectors yc_vectors
"""

import sys
import re
import argparse
import sqlite3
from pathlib import Path

# Optional: use venv chromadb
try:
    import chromadb
except ImportError:
    chromadb = None

PASS = "[PASS]"
FAIL = "[FAIL]"

_CHAT_PATTERN = re.compile(r'\b[a-z][a-z0-9_]{2,}: [A-Za-z]')

def _is_twitch_chat(text: str) -> bool:
    if not text or len(text) < 200:
        return False
    sample  = text[:2000]
    matches = len(_CHAT_PATTERN.findall(sample))
    return (matches / len(sample) * 1000) > 8


def run(db_path: str, vectors_path: str):
    results = []
    all_pass = True

    def check(label: str, passed: bool, detail: str = ""):
        nonlocal all_pass
        tag = PASS if passed else FAIL
        msg = f"{tag} {label}"
        if detail:
            msg += f"  ({detail})"
        print(msg)
        results.append(passed)
        if not passed:
            all_pass = False

    # ── 1. SQLite connects and required tables exist ───────────────────────
    if not Path(db_path).exists():
        check("SQLite: DB file exists", False, f"not found at {db_path}")
        print("\n1 check failed — cannot continue without DB.")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    required = {"videos", "transcripts", "channels"}
    missing  = required - tables
    check("SQLite: required tables exist", not missing,
          f"missing: {missing}" if missing else f"found: {', '.join(sorted(tables))}")

    # ── 2. Video and transcript counts ─────────────────────────────────────
    total_v = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    with_t  = conn.execute("SELECT COUNT(*) FROM videos WHERE has_transcript=1").fetchone()[0]
    trans_t = conn.execute("SELECT COUNT(*) FROM transcripts").fetchone()[0]
    check(f"SQLite: {total_v} videos, {with_t} with transcripts, {trans_t} transcript rows",
          trans_t == with_t,
          "transcript row count matches has_transcript=1" if trans_t == with_t
          else f"MISMATCH: {trans_t} transcript rows vs {with_t} has_transcript=1 videos")

    # ── 3. No UC... channel handles ────────────────────────────────────────
    uc_count = conn.execute(
        "SELECT COUNT(*) FROM videos WHERE channel_handle LIKE 'UC%'"
    ).fetchone()[0]
    check("SQLite: no UC... channel handles", uc_count == 0,
          f"{uc_count} videos still have UC... handles" if uc_count else "all handles are @handles")

    # ── 4. Twitch chat detection ───────────────────────────────────────────
    chat_videos = []
    rows = conn.execute("SELECT video_id, full_text FROM transcripts").fetchall()
    for vid_id, full_text in rows:
        if _is_twitch_chat(full_text or ""):
            chat_videos.append(vid_id)
    check("SQLite: no Twitch chat transcripts", len(chat_videos) == 0,
          f"chat detected in: {chat_videos}" if chat_videos else f"scanned {len(rows)} transcripts")

    conn.close()

    # ── 5. ChromaDB connects and has chunks ────────────────────────────────
    if chromadb is None:
        check("ChromaDB: module available", False, "chromadb not installed")
        print("\nSkipping vector DB checks.")
        sys.exit(1 if not all_pass else 0)

    if not Path(vectors_path).exists():
        check("ChromaDB: directory exists", False, f"not found at {vectors_path}")
        print("\nSkipping vector DB checks.")
        sys.exit(1 if not all_pass else 0)

    try:
        client     = chromadb.PersistentClient(path=vectors_path)
        collection = client.get_collection(name="transcripts")
        chunk_count = collection.count()
        check("ChromaDB: connects and collection exists", True, f"{chunk_count:,} chunks")
    except Exception as e:
        check("ChromaDB: connects and collection exists", False, str(e))
        sys.exit(1)

    check("ChromaDB: chunk count > 0", chunk_count > 0, f"{chunk_count:,} chunks")

    # ── 6. Chunk / transcript ratio ────────────────────────────────────────
    if trans_t > 0:
        ratio = chunk_count / trans_t
        ok    = 10 <= ratio <= 500
        check("ChromaDB: chunk/transcript ratio plausible",
              ok, f"{ratio:.1f} chunks/video (expected 10–500)")

    # ── 7. Basic semantic search returns results ───────────────────────────
    try:
        results_q = collection.query(
            query_texts=["startup advice fundraising"],
            n_results=3,
            include=["metadatas"],
        )
        n = len(results_q["metadatas"][0])
        check("ChromaDB: semantic search returns results", n > 0,
              f"returned {n} result(s)" if n > 0 else "returned 0 results")
    except Exception as e:
        check("ChromaDB: semantic search returns results", False, str(e))

    # ── Summary ────────────────────────────────────────────────────────────
    passed = sum(results)
    total  = len(results)
    print(f"\n{'All ' + str(total) + ' checks passed.' if all_pass else str(passed) + '/' + str(total) + ' checks passed — see FAIL lines above.'}")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sage YTKB smoke test")
    parser.add_argument("--db",      default="knowledge.db", help="SQLite DB path")
    parser.add_argument("--vectors", default="yc_vectors",   help="ChromaDB path")
    args = parser.parse_args()
    run(args.db, args.vectors)
