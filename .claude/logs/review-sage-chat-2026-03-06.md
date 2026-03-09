# Code Review: Sage Chat
**Date**: 2026-03-06
**Scope**: api/ directory + sage_chat/ directory
**Focus**: Security, correctness, code quality

---

## Security

### CORS Configuration
**File**: `api/main.py`

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_origin_regex=r"https://.*\.vercel\.app",
    ...
)
```

PASS. No wildcard `allow_origins=["*"]`. Development origins (localhost:3000, 3001) and production (*.vercel.app) are both explicit. The regex is anchored to `https://` to prevent http downgrade attacks.

### Hardcoded Secrets
PASS. No API keys, tokens, or credentials are hardcoded anywhere. The GCP project number `YOUR_GCP_PROJECT_NUMBER` is a non-secret resource identifier (project numbers are not credentials). Actual auth flows through Application Default Credentials at runtime.

### Input Validation
PASS. `ChatRequest` uses Pydantic with:
- `query: str = Field(..., min_length=1, max_length=2000)` — prevents empty and excessively long queries
- `mode: Literal["ephemeral","conversation"]` — enum validation, rejects arbitrary values
- `history: list[Message]` — typed, schema-validated

`/api/videos` uses FastAPI `Query()` with `ge=1, le=200` bounds on `limit` and `ge=0` on `offset`.

**Concern**: The `channel` filter parameter uses `LIKE ?` with `f"%{channel.lstrip('@')}%"` — this is parameterized SQL, not string concatenation, so SQL injection is not possible. PASS.

### Database Access
PASS. ChromaDB and SQLite are strictly read-only from the API layer. `search.py` opens SQLite with `?mode=ro` URI parameter. No write operations exist in any api/ file.

### Error Information Leakage
**Minor concern**: `api/gemini.py` returns `f"(Error: {type(e).__name__})"` in the error response. This leaks the exception class name to the client. Not a significant risk for a personal tool, but worth noting for future hardening.

---

## Correctness

### Search Deduplication Logic
**File**: `api/main.py`, `_deduplicate_chunks()`

```python
def _deduplicate_chunks(results_by_variant: list[list[dict]]) -> list[dict]:
    best: dict[str, dict] = {}
    for results in results_by_variant:
        for chunk in results:
            cid = chunk["chunk_id"]
            if cid not in best or chunk["score"] > best[cid]["score"]:
                best[cid] = chunk
    return sorted(best.values(), key=lambda c: c["score"], reverse=True)
```

PASS. Correctly deduplicates by chunk_id, keeping the highest score across all query variants. Sorted descending. No off-by-one issues.

### Hybrid Score Formula
**File**: `api/search.py`

```python
v["combined_score"] = 0.7 * v["sem_score"] + 0.3 * v["bm25_norm"]
```

PASS. Matches the ADR specification (0.7 semantic + 0.3 BM25). BM25 scores are normalized to [0,1] before combining, preventing unbounded BM25 values from dominating.

### Semantic Score Normalization
```python
"sem_score": max(0.0, 1.0 - dist / 2.0),
```
PASS. ChromaDB uses cosine distance in [0, 2]. Dividing by 2 maps to [0, 1] with higher score = more similar. `max(0, ...)` prevents negative scores from floating point edge cases.

### Citation Enforcement
**File**: `api/gemini.py`

The system prompt rule "Every factual claim MUST cite at least one source using [SRC_N] notation" is correct. However, Gemini is an LLM and cannot be 100% guaranteed to follow instructions. The PRD acknowledges this. The enforcement is best-effort via prompt engineering, which is the correct approach.

### Ephemeral vs Conversation History
**File**: `api/main.py`

```python
answer = gemini_module.synthesize(
    query=request.query,
    chunks=top_chunks,
    history=request.history if request.mode == "conversation" else [],
    mode=request.mode,
)
```

PASS. History is conditionally passed based on mode. The `[]` default for ephemeral is correct.

**File**: `api/gemini.py`

```python
if mode == "conversation" and history:
    for msg in history:
        contents.append(...)
```

PASS. Double-guarded: mode check AND non-empty history check.

### Frontend History Building
**File**: `sage_chat/app/components/ChatInterface.tsx`

```typescript
const history: Message[] =
    state.mode === 'conversation'
        ? state.messages.map((m) => ({ role: m.role, content: m.content }))
        : [];
```

PASS. Ephemeral sends `[]`. Conversation mode sends all prior messages. Note: history is captured before the new user message is dispatched, so the user's current question is not duplicated in history (it's sent as the `query` param). This is correct.

### Word Reveal Interval
**File**: `sage_chat/app/components/ChatInterface.tsx`

```typescript
const interval = setInterval(() => {
    if (i < words.length) {
        dispatch({ type: 'APPEND_WORD', id: msgId, word: words[i] });
        i++;
    } else {
        clearInterval(interval);
        dispatch({ type: 'SET_SOURCES', ... });
        dispatch({ type: 'SET_LOADING', loading: false });
        dispatch({ type: 'INCREMENT_TURNS' });
    }
}, 30);
```

PASS. Interval is cleared when complete. The `revealWords` function is defined outside the component so it doesn't close over stale state — it only uses `dispatch` which is stable. `i` is a closure variable scoped to each call, preventing cross-call interference.

**Minor**: If the component unmounts while the interval is running (e.g., user navigates away), the interval will continue firing and `dispatch` calls to an unmounted component may cause React warnings. For a single-page app where this component is always mounted, the risk is minimal. A production-grade fix would use `useEffect` cleanup.

---

## Code Quality

### Dead Code
PASS. No dead code found. The `_msg_counter` variable removed (uid() function uses closure).

### Module Separation
PASS. Clean dependency graph: config → models → search/gemini → main. No circular imports.

### Type Safety
**Backend**: Pydantic v2 models with full typing. PASS.
**Frontend**: TypeScript strict mode enabled in tsconfig. All components and functions are typed. PASS.

### Error Handling
PASS. Both layers handle errors gracefully:
- Backend: `expand_query` falls back to `[query]` on Gemini failure
- Backend: BM25 failure falls back to semantic-only search
- Backend: SQLite unavailability returns empty lists (not 500 errors) for listing endpoints
- Frontend: `ApiError` caught in `handleSubmit`, dispatched to error state
- Frontend: Error banner shown with dismiss button

### Naming Conventions
PASS. Consistent snake_case in Python, camelCase in TypeScript. Component names match filenames.

### API Contract Adherence
PASS. All routes match the ADR API contract exactly. Pydantic models match JSON shapes specified in decisions.md.

---

## Summary

| Category | Rating | Notes |
|----------|--------|-------|
| Security | Good | No secrets, parameterized SQL, typed inputs, read-only DB |
| Correctness | Good | Deduplication, scoring, mode guards all correct |
| Code Quality | Good | Clean separation, no dead code, full typing |

**Open items (non-blocking)**:
1. Interval cleanup on component unmount (minor, React warning risk)
2. Error type name leakage in Gemini error response (cosmetic for personal tool)
3. BM25 startup time with 249K chunks — consider async init + health check endpoint polling in v2

**Verdict**: Ready for use. No blocking issues found.
