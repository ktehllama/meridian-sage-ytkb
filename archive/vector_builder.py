"""
YouTube Knowledge Base - Phase 2: Vector DB Builder
=====================================================
Takes the SQLite DB from Phase 1 and builds a ChromaDB vector database
with smart chunking, embeddings, and semantic search.

Usage:
    python vector_builder.py build --db yc.db --vectors yc_vectors
    python vector_builder.py search --vectors yc_vectors --query "how to get first customers"
    python vector_builder.py search --vectors yc_vectors --query "AI agents replacing apps" --top 5
    python vector_builder.py stats --vectors yc_vectors

Requirements (install once):
    pip install chromadb sentence-transformers
"""

import sqlite3
import json
import argparse
import sys
import time
from pathlib import Path

try:
    import chromadb
except ImportError:
    print("❌ chromadb not installed. Run: pip install chromadb")
    sys.exit(1)


# ─────────────────────────────────────────
# CHUNKING ENGINE
# ─────────────────────────────────────────

def chunk_transcript(segments: list, target_words: int = 250, overlap_words: int = 50) -> list:
    """
    Smart chunking that respects timestamp boundaries.

    Each chunk ≈ target_words with overlap_words overlap between consecutive chunks.
    Preserves start_time and end_time so we can deep-link to the exact video moment.

    Args:
        segments: List of {'text': str, 'start': float, 'duration': float}
        target_words: Target word count per chunk
        overlap_words: Words to repeat between chunks for context continuity

    Returns:
        List of {'text': str, 'start_time': float, 'end_time': float, 'word_count': int}
    """
    if not segments:
        return []

    chunks = []
    current_texts = []
    current_word_count = 0
    chunk_start_time = segments[0]['start']

    for i, seg in enumerate(segments):
        text = seg['text'].strip()
        if not text:
            continue

        word_count = len(text.split())
        current_texts.append(text)
        current_word_count += word_count

        if current_word_count >= target_words:
            chunk_end_time = seg['start'] + seg.get('duration', 0)
            chunk_text = ' '.join(current_texts)

            chunks.append({
                'text': chunk_text,
                'start_time': chunk_start_time,
                'end_time': chunk_end_time,
                'word_count': len(chunk_text.split()),
            })

            # Overlap: keep last N words worth of segments
            overlap_texts = []
            overlap_count = 0
            overlap_start = chunk_end_time

            for j in range(len(current_texts) - 1, -1, -1):
                seg_words = len(current_texts[j].split())
                if overlap_count + seg_words > overlap_words:
                    break
                overlap_texts.insert(0, current_texts[j])
                overlap_count += seg_words
                seg_idx = i - (len(current_texts) - 1 - j)
                if seg_idx >= 0:
                    overlap_start = segments[seg_idx]['start']

            current_texts = overlap_texts
            current_word_count = overlap_count
            chunk_start_time = overlap_start

    # Last chunk
    if current_texts:
        last_seg = segments[-1]
        chunks.append({
            'text': ' '.join(current_texts),
            'start_time': chunk_start_time,
            'end_time': last_seg['start'] + last_seg.get('duration', 0),
            'word_count': len(' '.join(current_texts).split()),
        })

    return chunks


def format_timestamp(seconds: float) -> str:
    """Convert seconds to H:MM:SS or M:SS format."""
    seconds = int(seconds)
    h, remainder = divmod(seconds, 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def youtube_url_at_time(video_id: str, seconds: float) -> str:
    """Generate a YouTube URL that starts at a specific timestamp."""
    return f"https://www.youtube.com/watch?v={video_id}&t={int(seconds)}s"


# ─────────────────────────────────────────
# VECTOR DB BUILDER
# ─────────────────────────────────────────

def build_vectors(db_path: str, vectors_path: str, target_words: int = 250, overlap_words: int = 50):
    """Read SQLite DB, chunk transcripts, embed and store in ChromaDB."""

    if not Path(db_path).exists():
        print(f"❌ Database not found: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Fetch all videos with transcripts
    rows = conn.execute("""
        SELECT v.id AS video_id, v.title, v.url, v.channel_handle, v.duration,
               v.published_at, v.description, t.segments
        FROM transcripts t
        JOIN videos v ON t.video_id = v.id
        WHERE t.segments IS NOT NULL
    """).fetchall()

    if not rows:
        print("❌ No transcripts with segments found in the database.")
        sys.exit(1)

    # Get channel info
    channels = {}
    for ch in conn.execute("SELECT * FROM channels").fetchall():
        channels[ch['handle']] = dict(ch)

    print(f"{'='*60}")
    print(f"🔨  BUILDING VECTOR DATABASE")
    print(f"{'='*60}")
    print(f"  Source DB:     {db_path}")
    print(f"  Output:        {vectors_path}/")
    print(f"  Videos:        {len(rows)}")
    print(f"  Chunk size:    ~{target_words} words, {overlap_words} word overlap")
    print(f"{'='*60}\n")

    # Initialize ChromaDB (persistent storage)
    client = chromadb.PersistentClient(path=vectors_path)

    # Delete existing collection if rebuilding
    try:
        client.delete_collection("transcripts")
        print("  ♻️  Cleared existing collection\n")
    except Exception:
        pass

    collection = client.create_collection(
        name="transcripts",
        metadata={"description": "YouTube transcript chunks with semantic embeddings"}
    )

    all_documents = []
    all_metadatas = []
    all_ids = []
    total_chunks = 0

    for row in rows:
        video_id = row['video_id']
        title = row['title']
        segments = json.loads(row['segments'])
        channel = channels.get(row['channel_handle'], {})
        channel_name = channel.get('handle', row['channel_handle'] or 'Unknown')

        chunks = chunk_transcript(segments, target_words, overlap_words)
        total_chunks += len(chunks)

        print(f"  📹 {title[:55]}")
        print(f"     → {len(chunks)} chunks")

        for idx, chunk in enumerate(chunks):
            chunk_id = f"{video_id}_chunk_{idx:04d}"

            # The document text that gets embedded
            # Prepend title for better semantic matching
            doc_text = f"{title}\n\n{chunk['text']}"

            metadata = {
                "video_id": video_id,
                "video_title": title,
                "video_url": row['url'] or f"https://www.youtube.com/watch?v={video_id}",
                "channel_name": channel_name,
                "start_time": chunk['start_time'],
                "end_time": chunk['end_time'],
                "timestamp_display": f"{format_timestamp(chunk['start_time'])} → {format_timestamp(chunk['end_time'])}",
                "timestamp_url": youtube_url_at_time(video_id, chunk['start_time']),
                "chunk_index": idx,
                "total_chunks": len(chunks),
                "word_count": chunk['word_count'],
                "published_at": row['published_at'] or "",
                "duration": row['duration'] or 0,
            }

            all_documents.append(doc_text)
            all_metadatas.append(metadata)
            all_ids.append(chunk_id)

    # Add all at once (ChromaDB handles batching internally)
    print(f"\n  ⏳ Embedding {total_chunks} chunks... ", end="", flush=True)
    start = time.time()

    # Batch in groups of 100 to show progress
    batch_size = 100
    for i in range(0, len(all_documents), batch_size):
        end = min(i + batch_size, len(all_documents))
        collection.add(
            documents=all_documents[i:end],
            metadatas=all_metadatas[i:end],
            ids=all_ids[i:end],
        )
        if len(all_documents) > batch_size:
            print(f"{end}/{len(all_documents)}... ", end="", flush=True)

    elapsed = time.time() - start
    print(f"done! ({elapsed:.1f}s)")

    print(f"\n{'='*60}")
    print(f"✅  VECTOR DATABASE READY")
    print(f"{'='*60}")
    print(f"  Total chunks:  {total_chunks}")
    print(f"  Stored in:     {vectors_path}/")
    print(f"  Collection:    transcripts")
    print(f"\n  Try a search:")
    print(f"    python vector_builder.py search --vectors {vectors_path} --query \"your question here\"")
    print(f"{'='*60}")

    conn.close()


# ─────────────────────────────────────────
# SEMANTIC SEARCH
# ─────────────────────────────────────────

def search(vectors_path: str, query: str, top_n: int = 3):
    """Search the vector DB with a natural language query."""

    if not Path(vectors_path).exists():
        print(f"❌ Vector DB not found: {vectors_path}")
        print(f"   Run: python vector_builder.py build --db yc.db --vectors {vectors_path}")
        sys.exit(1)

    client = chromadb.PersistentClient(path=vectors_path)
    collection = client.get_collection("transcripts")

    print(f"\n🔍 Searching: \"{query}\"\n")

    results = collection.query(
        query_texts=[query],
        n_results=top_n,
        include=["documents", "metadatas", "distances"]
    )

    if not results['documents'][0]:
        print("  No results found.")
        return results

    for i, (doc, meta, dist) in enumerate(zip(
        results['documents'][0],
        results['metadatas'][0],
        results['distances'][0]
    )):
        # Convert distance to similarity score (Chroma uses L2 by default)
        # Lower distance = more similar
        similarity = max(0, 1 - (dist / 2))  # rough normalization

        print(f"{'─'*60}")
        print(f"  📌 Result {i+1} (relevance: {similarity:.0%})")
        print(f"  📹 {meta['video_title']}")
        print(f"  ⏱️  {meta['timestamp_display']}")
        print(f"  🔗 {meta['timestamp_url']}")
        print(f"  📝 Chunk {meta['chunk_index']+1}/{meta['total_chunks']} | {meta['word_count']} words")
        print()

        # Show text preview (skip the prepended title)
        text_lines = doc.split('\n\n', 1)
        preview = text_lines[1] if len(text_lines) > 1 else doc
        # Truncate for display
        if len(preview) > 400:
            preview = preview[:400] + "..."
        print(f"  \"{preview}\"")
        print()

    print(f"{'─'*60}")
    return results


# ─────────────────────────────────────────
# STATS
# ─────────────────────────────────────────

def stats(vectors_path: str):
    """Show stats about the vector database."""

    if not Path(vectors_path).exists():
        print(f"❌ Vector DB not found: {vectors_path}")
        sys.exit(1)

    client = chromadb.PersistentClient(path=vectors_path)
    collection = client.get_collection("transcripts")

    count = collection.count()

    # Get all metadata to compute stats
    all_data = collection.get(include=["metadatas"])
    metas = all_data['metadatas']

    videos = set()
    channels = set()
    total_words = 0

    for m in metas:
        videos.add(m['video_id'])
        channels.add(m.get('channel_name', 'Unknown'))
        total_words += m.get('word_count', 0)

    print(f"\n{'='*60}")
    print(f"📊  VECTOR DATABASE STATS")
    print(f"{'='*60}")
    print(f"  Location:        {vectors_path}/")
    print(f"  Channels:        {', '.join(channels)}")
    print(f"  Videos:          {len(videos)}")
    print(f"  Total chunks:    {count}")
    print(f"  Total words:     ~{total_words:,}")
    print(f"  Avg words/chunk: ~{total_words // max(count, 1)}")
    print(f"{'='*60}")


# ─────────────────────────────────────────
# CLI
# ─────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="YouTube Knowledge Base - Vector DB Builder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python vector_builder.py build  --db yc.db --vectors yc_vectors
  python vector_builder.py search --vectors yc_vectors --query "how to validate a startup idea"
  python vector_builder.py search --vectors yc_vectors --query "AI tools for developers" --top 5
  python vector_builder.py stats  --vectors yc_vectors
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # Build
    build_p = subparsers.add_parser('build', help='Build vector DB from SQLite')
    build_p.add_argument('--db', required=True, help='Path to SQLite database (from Phase 1)')
    build_p.add_argument('--vectors', default='yc_vectors', help='Output directory for ChromaDB (default: yc_vectors)')
    build_p.add_argument('--chunk-size', type=int, default=250, help='Target words per chunk (default: 250)')
    build_p.add_argument('--overlap', type=int, default=50, help='Overlap words between chunks (default: 50)')

    # Search
    search_p = subparsers.add_parser('search', help='Semantic search')
    search_p.add_argument('--vectors', default='yc_vectors', help='Path to ChromaDB directory')
    search_p.add_argument('--query', '-q', required=True, help='Natural language search query')
    search_p.add_argument('--top', '-n', type=int, default=3, help='Number of results (default: 3)')

    # Stats
    stats_p = subparsers.add_parser('stats', help='Show vector DB stats')
    stats_p.add_argument('--vectors', default='yc_vectors', help='Path to ChromaDB directory')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == 'build':
        build_vectors(args.db, args.vectors, args.chunk_size, args.overlap)
    elif args.command == 'search':
        search(args.vectors, args.query, args.top)
    elif args.command == 'stats':
        stats(args.vectors)


if __name__ == '__main__':
    main()