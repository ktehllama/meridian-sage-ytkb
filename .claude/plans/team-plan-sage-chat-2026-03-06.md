# Team Plan: Sage Chat
**Date**: 2026-03-06
**PRD**: `.claude/plans/prd-sage-chat.md`
**Complexity**: Full (new system, full-stack, multi-file)

## Team Roster
| Agent | Role | Inputs | Outputs |
|-------|------|--------|---------|
| architect | Design ADR, finalize module interfaces | PRD, CLAUDE.md, existing .py files | ADR in decisions.md |
| implementer-backend | FastAPI + search + Gemini | ADR | api/ directory |
| implementer-frontend | Next.js chat UI | ADR + API contract | sage_chat/ directory |
| qa-engineer | Validate endpoints, UI smoke test | all code | QA report |
| code-reviewer | Async security/quality review | git diff | review report |

## Execution Sequence
```
Phase 1 (serial):   architect
Phase 2 (parallel): implementer-backend + implementer-frontend
Phase 3 (serial):   qa-engineer
Phase 4 (async):    code-reviewer
```

## Parallelization Plan
Safe to parallelize in Phase 2:
- `api/` (Python FastAPI) and `sage_chat/` (Next.js) touch completely different files
- Frontend uses a static API_URL env var — no runtime dependency on backend during build

Must serialize:
- architect must complete first to define the API contract (endpoints, request/response shapes)
- qa-engineer needs both implementers done

## Context Each Agent Needs
- **architect**: `.claude/plans/prd-sage-chat.md`, `CLAUDE.md`, `yt_knowledge_mcp.py` (for search patterns to port)
- **implementer-backend**: ADR + decisions.md, `yt_knowledge_mcp.py` (source of truth for search logic), `APIgeminiai.py` (Vertex AI auth pattern)
- **implementer-frontend**: ADR + API contract from decisions.md, PRD UI requirements
- **qa-engineer**: PRD acceptance criteria, both code outputs; run `pytest` on backend, `npm run build` on frontend

## Success Criteria
- [ ] QA report shows PASS on all acceptance criteria
- [ ] `/api/health` returns 200 with chroma chunk count
- [ ] `/api/chat` returns grounded response with `[SRC_N]` citations
- [ ] Next.js builds without errors (`npm run build`)
- [ ] Mode toggle works (ephemeral clears history, conversation retains it)
- [ ] `yt_knowledge_mcp.py` moved to `archive/mcp/`

## Key Constraints (do not forget)
- ChromaDB + SQLite: READ ONLY — never write from the chat API
- Vertex AI auth: `genai.Client(vertexai=True, project="YOUR_GCP_PROJECT_NUMBER", location="us-central1")`
- Embedding function: `SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")`
- Do NOT import `yt_knowledge_mcp.py` — copy the search core inline (BM25 thread side-effects)
- No AI calls in tests — $300 budget is precious
- Frontend: Next.js (App Router) + Tailwind CSS
- Fake streaming: batch response + CSS word-reveal animation
