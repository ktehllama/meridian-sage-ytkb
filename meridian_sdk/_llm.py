"""
meridian_sdk/_llm.py
====================
Gemini client for query expansion and grounded synthesis.
Standalone — no dependency on api/.

Auth: Application Default Credentials (gcloud auth application-default login).
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# System prompts
# ─────────────────────────────────────────────────────────────

_CHAT_PROMPT = """You are Sage — a thoughtful, direct knowledge assistant built on a curated library of video content.

PERSONALITY:
- Warm but not sycophantic. Skip "Great question!" — just answer it.
- Speak like a knowledgeable friend: clear, honest, occasionally a touch of dry wit.
- When something is genuinely interesting or counterintuitive, say so briefly.
- If you don't have good sources on something, be upfront and helpful.

RULES:
- Every factual claim MUST cite at least one source using [SRC_N] notation.
- Never invent quotes, timestamps, or video titles.
- Synthesize and connect ideas across sources — don't just summarize each chunk.
- Keep answers concise and actionable — 2-4 paragraphs unless a detailed breakdown is needed."""

_SERIOUS_PROMPT = """You are Sage — a direct knowledge retrieval assistant.

RULES:
- Answer in 1-3 short paragraphs. No more.
- Every factual claim MUST cite at least one source using [SRC_N] notation.
- No filler, no warmth markers, no "great question", no "I hope this helps".
- Lead with the direct answer. Evidence second.
- If sources don't cover the question, say so in one sentence.
- Never invent quotes, timestamps, or video titles."""

# ─────────────────────────────────────────────────────────────
# Lazy client
# ─────────────────────────────────────────────────────────────

_client = None


def _get_client(project: str, location: str):
    global _client
    if _client is None:
        from google import genai
        _client = genai.Client(vertexai=True, project=project, location=location)
    return _client


# ─────────────────────────────────────────────────────────────
# Query expansion
# ─────────────────────────────────────────────────────────────

def expand_query(
    query: str,
    project: str,
    location: str,
    model: str,
) -> list[str]:
    """
    Correct typos and generate 3 paraphrased variants.
    Returns [original, corrected?, paraphrase1, paraphrase2, paraphrase3].
    On failure returns [query].
    """
    prompt = (
        "Output exactly 4 lines for the search query below:\n"
        "Line 1: the query with ONLY spelling typos fixed — keep the same words and meaning otherwise\n"
        "Line 2: a paraphrase of line 1 using different wording\n"
        "Line 3: another paraphrase of line 1\n"
        "Line 4: another paraphrase of line 1\n"
        "No labels, no numbering, no explanation. Just 4 lines.\n\n"
        f"Query: {query}"
    )
    try:
        from google import genai
        client = _get_client(project, location)
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=genai.types.GenerateContentConfig(max_output_tokens=200, temperature=0.4),
        )
        lines = [l.strip() for l in response.text.strip().split("\n") if l.strip()]
        corrected = lines[0] if lines else query
        variants = [query]
        if corrected.lower() != query.lower():
            variants.append(corrected)
        variants.extend(lines[1:4])
        return variants
    except Exception as e:
        logger.warning(f"Query expansion failed: {e}")
        return [query]


# ─────────────────────────────────────────────────────────────
# Synthesis
# ─────────────────────────────────────────────────────────────

def synthesize(
    query: str,
    chunks: list[dict],
    style: str,
    project: str,
    location: str,
    model: str,
) -> str:
    """
    Synthesize an answer grounded in retrieved chunks.
    style: "chat" | "serious"
    Returns answer string with [SRC_N] citations.
    """
    if chunks:
        sources_block = "SOURCES:\n" + "\n\n".join(
            f'[SRC_{i+1}] {c["title"]} — {c["timestamp_str"]}\n"{c["text"]}"'
            for i, c in enumerate(chunks)
        )
    else:
        sources_block = "SOURCES: (none — no relevant content found)"

    prompt = _SERIOUS_PROMPT if style == "serious" else _CHAT_PROMPT

    try:
        from google import genai
        client = _get_client(project, location)
        response = client.models.generate_content(
            model=model,
            contents=[{"role": "user", "parts": [{"text": f"{sources_block}\n\nQUESTION: {query}"}]}],
            config=genai.types.GenerateContentConfig(
                system_instruction=prompt,
                max_output_tokens=1024,
                temperature=0.3,
            ),
        )
        return response.text
    except Exception as e:
        logger.error(f"Synthesis failed: {e}")
        return f"Error generating response: {type(e).__name__}: {e}"
