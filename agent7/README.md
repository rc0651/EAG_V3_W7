# Agent7 — SEBI Compliance RAG Agent

EAG V3 Week 7 Assignment. Built on top of Agent6 (4-role cognitive loop) by adding:
- **FAISS vector memory** for persistent cross-run semantic search
- **/v1/embed** gateway endpoint (Ollama `nomic-embed-text` → Gemini fallback, 768-dim)
- **`index_document`** MCP tool: chunks any file into FAISS-indexed fact records
- **`search_knowledge`** MCP tool: semantic vector search over indexed chunks

---

## Architecture

```
User Query
    │
    ▼
memory.read(query)  ←── FAISS index.faiss (cosine similarity > 0.3)
    │                        ↓ fallback: keyword overlap
    ▼
perception.observe()   (goal decomposition / update — NO tool names in SYSTEM)
    │
    ▼
decision.next_step()   (tool_choice=auto; SYSTEM includes index_document + search_knowledge guidance)
    │
    ▼
action.execute()  →  MCP tools via stdio
    │
    ▼
memory.record_outcome()  →  embed + append to FAISS
```

---

## SEBI Corpus — 6 Documents

| File | Circular ID | Topic | Approx. Chunks |
|---|---|---|---|
| `sebi_master_circular_stockbrokers_2024.md` | SEBI/HO/MIRSD/MIRSD-PoD-1/P/CIR/2024/37 | Broker obligations, client funds, KYC, grievances | ~10 |
| `sebi_peak_margin_circular.md` | SEBI/HO/MRD/DRMNP/CIR/P/2020/220 | Upfront margin collection, client collateral rules | ~10 |
| `sebi_algo_ibt_circular.md` | SEBI/HO/MRD/DOP/P/CIR/2021/577 | Kill switch, order-rate limits, IBT safeguards | ~10 |
| `sebi_fo_eligibility_retail_2024.md` | SEBI/HO/MRD-1/DOP/P/CIR/2024/23 | F&O eligibility: income ≥ 5L or net worth ≥ 10L | ~10 |
| `sebi_kyc_nomination_circular.md` | SEBI/HO/MIRSD/MIRSD-PoD-1/P/CIR/2023/058 | KYC norms, nomination requirements | ~11 |
| `sebi_scores_grievance_circular.md` | SEBI/HO/OIAE/IGRD/CIR/P/2023/156 | SCORES 2.0: complaint timelines, ODR | ~11 |

**Total target: ~62 chunks** (400-word chunks, 80-word overlap).

---

## Setup

```bash
# Install dependencies (faiss-cpu + numpy added in Session 7)
uv add faiss-cpu numpy

# Copy your .env from agent6 — same variables apply
# Ensure GEMINI_API_KEY is set for embedding fallback

# Start the gateway (Session 7 adds /v1/embed endpoint)
uv run python llm_gatewayV3/main.py &
```

---

## Running the Queries

### State Management

| Scenario | Action before running |
|---|---|
| Starting fresh | `rm -rf state/ && mkdir state` |
| Query E (single doc) | clear state first |
| Query F1 (index all) | clear state first |
| Query F2 (cross-run recall) | **DO NOT clear** after F1 |
| Query G, H (SEBI synthesis) | **DO NOT clear** after F1/F2 |
| Query C1 → C2 | **DO NOT clear** between them |

### Base Queries

```bash
uv run python agent7.py --run-a    # Claude Shannon biography
uv run python agent7.py --run-b    # Tokyo weekend + weather
uv run python agent7.py --run-c1   # Mom's birthday memory write
uv run python agent7.py --run-c2   # Mom's birthday FAISS recall
uv run python agent7.py --run-d    # asyncio best practices
uv run python agent7.py --run-e    # index single SEBI doc
uv run python agent7.py --run-f1   # index all 6 papers
uv run python agent7.py --run-f2   # cross-run: client fund settlement
uv run python agent7.py --run-g    # semantic: broker client money controls
uv run python agent7.py --run-h    # cross-doc: grievances vs onboarding
```

### Custom SEBI Queries

```bash
uv run python agent7.py --run-q1   # new retail client + options eligibility
uv run python agent7.py --run-q2   # margin pre-collection consequences
uv run python agent7.py --run-q3   # semantic: client fund protection
uv run python agent7.py --run-q4   # semantic: algo order safeguards
uv run python agent7.py --run-q5   # cross-doc: complaints vs onboarding
```

### Grep Proofs (include in Q3/Q4 traces)

```bash
grep -ri "misuse\|misusing" papers/
# Expected: (nothing)

grep -ri "runaway" papers/
# Expected: (nothing)
```

---

## Architecture Rule

```bash
grep -n "index_document\|search_knowledge\|fetch_url\|web_search\|read_file" perception.py
# Must return: (nothing)
```

Tool names live only in Decision's SYSTEM and in tool docstrings — never in Perception.

---

## What's New vs Agent6

| Component | Agent6 | Agent7 |
|---|---|---|
| `schemas.py` | MemoryItem (11 fields) | +`embedding: list[float] \| None` |
| `memory.py` | keyword overlap only | FAISS vector search + keyword fallback; `add_fact()` |
| `mcp_server.py` | 9 tools | 11 tools (+`index_document`, +`search_knowledge`) |
| `llm_gatewayV3/main.py` | `/v1/chat` only | +`/v1/embed` (Ollama/Gemini, 768-dim) |
| `decision.py` | 5 rules | +rules 6 & 7 (index/search_knowledge guidance) |
| `agent7.py` | 5 queries | 13 queries (A-H + Q1-Q5) |
| `papers/` | — | 6 SEBI circulars (~9700 words total) |
