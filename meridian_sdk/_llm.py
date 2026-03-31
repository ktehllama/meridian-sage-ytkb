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
- Answer ONLY from the provided SOURCES. Do not supplement with your own training knowledge.
- The SOURCES were retrieved by a search system that already interpreted the user's intent — trust them. Do not suggest the user meant a different product, company, or topic when sources were returned.
- Read the sources carefully for names, attributions, dates, and specific facts — extract them directly. If a source names a person as a creator or mentions a key fact, that IS the answer. Never say "I don't have information" when the answer is present in the SOURCES.
- Every factual claim MUST cite at least one source using [SRC_N] notation.
- Never invent quotes, timestamps, or video titles.
- Synthesize and connect ideas across sources — don't just summarize each chunk.
- Keep answers concise and actionable — 2-4 paragraphs unless a detailed breakdown is needed.
- Respond in flowing prose paragraphs. Use bullet points only when the question explicitly asks for a list or when enumerating sequential steps."""

_SERIOUS_PROMPT = """You are a knowledge retrieval engine. Output only dense, direct facts.

RULES:
- Write 1-3 tight paragraphs of pure information. No headers, no bullet points, no lists.
- Zero framing sentences. Never write "There are several ways...", "X can be defined as...", "Some approaches include:" — just state the facts directly.
- Start the answer with the actual answer, not a setup for it.
- Cite sources inline using [SRC_N] notation. Every claim needs one.
- If sources don't cover the question, say so in one sentence and stop.
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
) -> tuple[list[str], str | None]:
    """
    Correct typos and generate 3 paraphrased variants.
    Returns (variants, corrected) where:
      - variants = [original, corrected?, paraphrase1, paraphrase2, paraphrase3]
      - corrected = typo-corrected form if different from original, else None
    On failure returns ([query], None).
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
        typo_fix = corrected if corrected.lower() != query.lower() else None
        variants = [query]
        if typo_fix:
            variants.append(corrected)
        variants.extend(lines[1:4])
        return variants, typo_fix
    except Exception as e:
        logger.warning(f"Query expansion failed: {e}")
        return [query], None


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
