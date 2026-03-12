"""
meridian_sdk/example.py
=======================
Quick test script for the Meridian SDK.
Run from the project root:
    .\\venv\\Scripts\\python.exe meridian_sdk/example.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from meridian_sdk import Meridian

# ── Init ──────────────────────────────────────────────────────
print("Initialising Meridian (waiting for BM25 index) ...")
m = Meridian(wait_for_bm25=True)
print("Ready.\n")

QUERY = "how do you find product market fit"

print("=" * 60)
print(f"Query: {QUERY}")
print("=" * 60)

# ── RAW mode ─────────────────────────────────────────────────
print("\n[RAW] — chunk list, no LLM\n")
results = m.search(QUERY, mode="raw")
for i, r in enumerate(results, 1):
    print(f"  {i}. [{r['score']:.3f}] {r['title']} @ {r['timestamp_str']}")
    print(f"     {r['timestamp_url']}")
    print(f"     {r['text'][:120].strip()}...")
    print()

# ── SERIOUS mode — verbose, no sources ───────────────────────
print("\n[SERIOUS] — terse LLM answer (verbose)\n")
answer = m.search(QUERY, mode="serious", verbose=True)
print(f"\n{answer}\n")

# ── CHAT mode — with sources dict ────────────────────────────
print("\n[CHAT] — conversational answer + sources\n")
result = m.search(QUERY, mode="chat", show_sources=True)
print(result["answer"])
print("\nSources cited:")
for src, meta in result["sources"].items():
    print(f"  [{src}] {meta['title']}")
    print(f"          {meta['url']}")
