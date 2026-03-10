"""
api/gemini.py
=============
Vertex AI Gemini client — query expansion and grounded synthesis.

Auth: Application Default Credentials (ADC).
Run `gcloud auth application-default login` before starting the server.
No API key file needed — the genai SDK reads ADC from the environment automatically.
"""

import logging
from typing import Optional

from google import genai

from api.config import config
from api.models import Message

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# LLMProvider implementation
# ─────────────────────────────────────────────────────────────

class GeminiProvider:
    """
    Implements the LLMProvider protocol using Vertex AI Gemini.
    Delegates to the module-level functions below so all logic lives in one place.
    """

    def expand_query(self, query: str) -> tuple[list[str], dict | None]:
        return expand_query(query)

    def synthesize(
        self,
        query: str,
        chunks: list[dict],
        history: list[Message],
        mode: str,
    ) -> tuple[str, dict | None]:
        return synthesize(query, chunks, history, mode)

# ─────────────────────────────────────────────────────────────
# Lazy client singleton
# ─────────────────────────────────────────────────────────────

_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(
            vertexai=True,
            project=config.GCP_PROJECT,
            location=config.GCP_LOCATION,
        )
    return _client


# ─────────────────────────────────────────────────────────────
# System prompt
# ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are Sage — a thoughtful, direct knowledge assistant built on a curated library of video content.

PERSONALITY:
- Warm but not sycophantic. Skip "Great question!" — just answer it.
- Speak like a knowledgeable friend: clear, honest, occasionally a touch of dry wit.
- When something is genuinely interesting or counterintuitive, say so briefly.
- If you don't have good sources on something, be upfront and helpful: point toward what you *do* know.

RULES:
- Every factual claim MUST cite at least one source using [SRC_N] notation
- If no sources support a claim, say "I don't have sources on this, but here's what I do know..."
- Never invent quotes, timestamps, or video titles
- Synthesize and connect ideas across sources — don't just summarize each chunk
- For comparisons, structure your answer with clear sections per perspective
- Keep answers concise and actionable — 2-4 paragraphs unless a detailed breakdown is needed
- When citing the same source multiple times in a response, use the citation only once at the end of the relevant section"""


# ─────────────────────────────────────────────────────────────
# Query expansion
# ─────────────────────────────────────────────────────────────

def expand_query(query: str) -> tuple[list[str], dict | None]:
    """
    Correct typos and generate 3 paraphrased variants of the query using Gemini.
    Returns (variants, usage) where variants = [original, corrected?, paraphrase1, ...].

    On Gemini failure, returns ([query], None) so the pipeline can still run.
    """
    prompt = (
        "Output exactly 4 lines for the search query below:\n"
        "Line 1: the query with ONLY spelling typos fixed (e.g. 'coed'→'code', 'sentce'→'sentence', 'borris'→'Boris') — keep the same words and meaning otherwise\n"
        "Line 2: a paraphrase of line 1 using different wording\n"
        "Line 3: another paraphrase of line 1\n"
        "Line 4: another paraphrase of line 1\n"
        "No labels, no numbering, no explanation. Just 4 lines.\n\n"
        f"Query: {query}"
    )

    try:
        client = _get_client()
        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                max_output_tokens=400,
                temperature=0.4,
            ),
        )
        raw = response.text.strip()
        lines = [line.strip() for line in raw.split("\n") if line.strip()]

        corrected = lines[0] if lines else query
        if corrected.lower() != query.lower():
            logger.info(f"Query corrected: '{query}' → '{corrected}'")

        variants: list[str] = [query]
        if corrected.lower() != query.lower():
            variants.append(corrected)
        variants.extend(lines[1:4])

        usage = None
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            usage = {
                "prompt_tokens": getattr(response.usage_metadata, 'prompt_token_count', 0) or 0,
                "completion_tokens": getattr(response.usage_metadata, 'candidates_token_count', 0) or 0,
            }

        return variants, usage

    except Exception as e:
        logger.warning(f"Query expansion failed (using original only): {e}")
        return [query], None


# ─────────────────────────────────────────────────────────────
# Grounded synthesis
# ─────────────────────────────────────────────────────────────

def synthesize(
    query: str,
    chunks: list[dict],
    history: list[Message],
    mode: str,
) -> tuple[str, Optional[dict]]:
    """
    Synthesize an answer grounded in retrieved chunks.

    Args:
        query:   The user's original question.
        chunks:  List of search result dicts (from hybrid_search).
                 Each dict has: title, text, timestamp_str, timestamp_url, chunk_id.
        history: Prior conversation messages. Passed to Gemini only if mode == 'conversation'.
        mode:    'ephemeral' | 'conversation'

    Returns:
        Tuple of (answer string with [SRC_N] citations, usage dict or None).
        On failure, returns an error message string and None (never raises).
    """
    # Format chunks as grounding context
    if chunks:
        formatted_chunks = "\n\n".join(
            f'[SRC_{i + 1}] {c["title"]} — {c["timestamp_str"]}\n"{c["text"]}"'
            for i, c in enumerate(chunks)
        )
        sources_block = f"SOURCES:\n{formatted_chunks}"
    else:
        sources_block = "SOURCES: (none — no relevant content found in knowledge base)"

    user_message = f"{sources_block}\n\nQUESTION: {query}"

    # Build contents list — include history only in conversation mode
    contents: list[dict] = []
    if mode == "conversation" and history:
        for msg in history:
            contents.append({
                "role": msg.role,
                "parts": [{"text": msg.content}],
            })

    contents.append({
        "role": "user",
        "parts": [{"text": user_message}],
    })

    try:
        client = _get_client()
        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=contents,
            config=genai.types.GenerateContentConfig(
                system_instruction=_SYSTEM_PROMPT,
                max_output_tokens=1024,
                temperature=0.3,  # low temp for factual, grounded answers
            ),
        )
        text = response.text
        usage = None
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            usage = {
                "prompt_tokens": getattr(response.usage_metadata, 'prompt_token_count', 0) or 0,
                "completion_tokens": getattr(response.usage_metadata, 'candidates_token_count', 0) or 0,
            }
        return text, usage
    except Exception as e:
        logger.error(f"Gemini synthesis failed: {e}")
        return (
            f"I encountered an error while generating a response. "
            f"Please check the Vertex AI credentials and try again. "
            f"(Error: {type(e).__name__})",
            None,
        )
