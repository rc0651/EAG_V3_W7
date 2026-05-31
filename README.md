# EAG W7 — SEBI Compliance RAG Agent

## Demo Video
https://youtu.be/Pv3RmCiXp3M

---

## What this builds

Agent6 (4-role cognitive loop) extended with **FAISS vector memory**. The agent answers SEBI compliance questions by semantic similarity — not keyword matching. The two headline queries ("misusing client funds" and "runaway algo trades") use words that do not appear anywhere in the source documents, yet the agent answers them correctly because FAISS retrieves chunks by *meaning*.

---

## Architecture

```
User Query
    │
    ▼
memory.read(query)  ←── FAISS index.faiss  (cosine similarity, threshold 0.15)
    │                        ↓ fallback: keyword overlap
    ▼
perception.observe()   — goal decomposition / update  (NO tool names in SYSTEM)
    │
    ▼
decision.next_step()   — tool_choice=auto; SYSTEM includes index/search_knowledge rules
    │
    ▼
action.execute()  →  11 MCP tools via stdio
    │
    ▼
memory.record_outcome()  →  embed + append to FAISS
```

**4 roles, each with a single responsibility:**
- **Memory** — FAISS vector search first, keyword fallback; `add_fact()` for indexed chunks
- **Perception** — goal decomposition and tracking, never sees tool names
- **Decision** — chooses one tool or synthesises a direct answer; anti-loop rule prevents repeated `search_knowledge` calls
- **Action** — pure MCP dispatch; results ≥ 4 KB stored as artifacts

**New in Session 7 vs Agent6:**

| Component | Agent6 | Agent7 |
|---|---|---|
| `schemas.py` | MemoryItem (11 fields) | +`embedding: list[float] \| None` |
| `memory.py` | keyword overlap only | FAISS vector search + keyword fallback; `add_fact()` |
| `mcp_server.py` | 9 tools | 11 tools (`index_document`, `search_knowledge`) |
| `llm_gatewayV3/main.py` | `/v1/chat` only | +`/v1/embed` (Ollama nomic-embed-text → Gemini fallback, 768-dim) |
| `decision.py` | 5 rules | +rules 6–8 (index/search guidance + anti-loop rule) |
| `agent7.py` | 5 queries | 13 queries (A–H + Q1–Q5) |
| `papers/` | — | 6 SEBI circulars (~9 700 words, 33 chunks) |

---

## SEBI Corpus — 6 Documents, 33 Chunks

Indexed with `index_document` (400-word chunks, 80-word overlap). Each chunk is embedded with `nomic-embed-text` (768-dim) via the gateway's `/v1/embed` endpoint and stored in FAISS.

| File | Document | Chunks indexed |
|---|---|---|
| sebi_master_circular_stockbrokers_2024.md | Master Circular on Stock Brokers 2024 | 5 |
| sebi_peak_margin_circular.md | Peak Margin & Intraday Leverage | 6 |
| sebi_algo_ibt_circular.md | Algo Trading & IBT Safeguards | 5 |
| sebi_fo_eligibility_retail_2024.md | F&O Eligibility for Retail Investors | 5 |
| sebi_kyc_nomination_circular.md | KYC & Nomination Requirements | 6 |
| sebi_scores_grievance_circular.md | Investor Grievance SCORES 2.0 | 6 |
| **Total** | | **33** |

**F1 indexing run — terminal excerpt:**
```
iter 1  index_document(sebi_master_circular_stockbrokers_2024.md) → indexed: 5
iter 2  index_document(sebi_peak_margin_circular.md)              → indexed: 6
iter 3  index_document(sebi_algo_ibt_circular.md)                 → indexed: 5
iter 4  index_document(sebi_fo_eligibility_retail_2024.md)        → indexed: 5
iter 5  index_document(sebi_kyc_nomination_circular.md)           → indexed: 6
iter 6  index_document(sebi_scores_grievance_circular.md)         → indexed: 6
[agent] all goals done  — total 33 chunks, all embedded and written to FAISS
```

---

## Semantic Proof — Words absent from papers, answers found by FAISS

### Query: "How does SEBI prevent brokers from misusing client funds?"

```
$ grep -ri "misusing" papers/
(no output — word does not exist in any paper)
```

FAISS retrieved chunk 4/5 of `sebi_master_circular_stockbrokers_2024.md` on the first `search_knowledge` call, which covers **Designated Client Bank Accounts** and fund segregation rules. The agent answered in 3 iterations:

> *"All client funds received must be held in designated client bank accounts maintained with Scheduled Commercial Banks... strictly separated from the broker's own funds... no overdrafts permitted... settled at least once every 30 days."*

### Query: "What safeguards exist to stop runaway algo trades?"

```
$ grep -ri "runaway" papers/
(no output — word does not exist in any paper)
```

FAISS surfaced **all 5 chunks** of `sebi_algo_ibt_circular.md` on iteration 1 (8 memory hits, 5 from the algo circular). The agent answered **directly from memory without calling any tool**:

> *"Hardware-Level Kill Switch... Redundancy and Failover for co-located systems... Self-Trade Prevention... Mandatory Reporting of malfunctions within 1 hour... Order-to-trade ratio limits (max 500 for derivatives)."*

Both answers come entirely from vector similarity — no keyword overlap with the query terms.

---

## Architecture Rule

Tool names (`index_document`, `search_knowledge`, `fetch_url`, etc.) appear **only** in Decision's SYSTEM prompt and in MCP tool docstrings — never in Perception.

```bash
grep -n "index_document\|search_knowledge\|fetch_url\|web_search\|read_file" perception.py
# Expected output: (nothing)
```

---

## Embedding Pipeline

```
index_document(path)
    │  chunk at 400 words / 80-word overlap
    ▼
POST http://localhost:8101/v1/embed
    │  primary: Ollama nomic-embed-text (768-dim)
    │  fallback: Gemini gemini-embedding-001 (outputDimensionality=768)
    ▼
FAISS IndexFlatIP  →  cosine similarity after L2 normalise
    │  saved to state/index.faiss + state/index_ids.json
    ▼
search_knowledge(query)
    │  embed query → FAISS search (threshold 0.10) → top-k chunks
    │  fallback: keyword scoring over in-memory items
    ▼
Decision sees full chunk text in history (1 500-char window per RAG result)
```

---

## Running Queries

```bash
# Start gateway first
uv run python llm_gatewayV3/main.py &

# Clear state, index all 6 papers
rm -rf state/ && mkdir state
uv run python agent7.py --run-f1

# Semantic queries (do NOT clear state — FAISS must be loaded)
uv run python agent7.py "How does SEBI prevent brokers from misusing client funds?"
uv run python agent7.py "What safeguards exist to stop runaway algo trades?"

# Full query suite
uv run python agent7.py --run-f2   # cross-run FAISS recall
uv run python agent7.py --run-g    # broker/client money controls
uv run python agent7.py --run-h    # grievance vs onboarding comparison
uv run python agent7.py --run-q1   # retail client options eligibility
uv run python agent7.py --run-q2   # margin collection consequences
uv run python agent7.py --run-q3   # client fund protection (semantic)
uv run python agent7.py --run-q4   # algo order safeguards (semantic)
uv run python agent7.py --run-q5   # complaints vs onboarding failures
```

---

## Traces

```
traces/base/    — A (Claude Shannon), B (Tokyo weekend), C1/C2 (memory persistence),
                  D (asyncio), E (single doc index), F1 (index all), F2 (cross-run recall),
                  G (broker money), H (grievance vs onboarding)
traces/custom/  — Q1–Q5 (SEBI compliance queries)
```
