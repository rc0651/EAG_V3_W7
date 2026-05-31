"""
memory.py
Agent memory service. Persists to state/memory.json across runs.

Session 7 upgrade: FAISS vector index (state/index.faiss + state/index_ids.json).
  - Embeddings via /v1/embed gateway endpoint (nomic-embed-text via Ollama; Gemini fallback).
  - read() tries vector search first (cosine similarity > 0.3), falls through to keyword.
  - remember() and record_outcome() embed on write for fact/preference/tool_outcome.
  - add_fact() — new helper used by index_document MCP tool.

Read methods  — pure Python (+ optional FAISS), no LLM cost, called every iteration.
Write methods — one gateway call to classify (remember) or zero calls (record_outcome).
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import faiss
import httpx
import numpy as np

from schemas import MemoryItem, ToolCall

_GW_PATH = Path(__file__).parent / "llm_gatewayV3"
if str(_GW_PATH) not in sys.path:
    sys.path.insert(0, str(_GW_PATH))

from client import LLM  # noqa: E402

_MEM_PATH = Path(__file__).parent / "state" / "memory.json"

# ── FAISS paths ───────────────────────────────────────────────────────────────
FAISS_INDEX_PATH = str(Path(__file__).parent / "state" / "index.faiss")
FAISS_IDS_PATH   = str(Path(__file__).parent / "state" / "index_ids.json")
EMBED_URL        = "http://localhost:8101/v1/embed"

_STOPWORDS = {
    "a","an","the","is","are","was","were","be","been","have","has","had",
    "do","does","did","will","would","could","should","may","might","to",
    "of","in","on","at","for","with","from","by","and","or","but","if",
    "that","this","i","me","my","you","your","we","our","he","she","it",
    "they","what","when","where","how","not","no","get","find","show",
    "search","check","read","list","make","create","can","please","want",
    "need","help","use","just","so","now","which","who","there","here",
    "all","any","some","other","more","its","then","than","also","up","out",
}


def _tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-zA-Z0-9]+", text.lower())
            if t not in _STOPWORDS and len(t) > 2]


def _llm_retry(llm: LLM, prompt: str, retries: int = 3, **kw) -> dict:
    for i in range(retries):
        try:
            return llm.chat(prompt, **kw)
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (429, 502, 503) and i < retries - 1:
                wait = 10 * (2 ** i)
                print(f"  [memory] throttled, retry in {wait}s")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("retries exhausted")


# ── FAISS helpers ─────────────────────────────────────────────────────────────

def _try_embed(text: str, task_type: str = "retrieval_document") -> list[float] | None:
    """Call gateway /v1/embed; returns 768-dim float list or None on failure."""
    try:
        r = httpx.post(EMBED_URL, json={"text": text, "task_type": task_type}, timeout=10.0)
        return r.json()["embedding"]
    except Exception:
        return None


def _load_faiss() -> tuple[faiss.Index | None, list[str]]:
    """Load FAISS index from disk. Called on every read for cross-process safety."""
    if not os.path.exists(FAISS_INDEX_PATH):
        return None, []
    try:
        index = faiss.read_index(FAISS_INDEX_PATH)
        with open(FAISS_IDS_PATH) as f:
            ids = json.load(f)
        return index, ids
    except Exception:
        return None, []


def _append_faiss(item_id: str, embedding: list[float]) -> None:
    """Append one vector to the FAISS index and persist both files."""
    index, ids = _load_faiss()
    vec = np.array([embedding], dtype="float32")
    faiss.normalize_L2(vec)
    if index is None:
        index = faiss.IndexFlatIP(768)
    index.add(vec)
    ids.append(item_id)
    os.makedirs(os.path.dirname(FAISS_INDEX_PATH), exist_ok=True)
    faiss.write_index(index, FAISS_INDEX_PATH)
    with open(FAISS_IDS_PATH, "w") as f:
        json.dump(ids, f)


# ── Classify schema ───────────────────────────────────────────────────────────

_CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["fact", "preference", "tool_outcome", "scratchpad"]},
        "keywords": {"type": "array", "items": {"type": "string"}},
        "descriptor": {"type": "string"},
        "value": {"type": "object"},
        "confidence": {"type": "number"},
    },
    "required": ["kind", "keywords", "descriptor", "value", "confidence"],
}

_CLASSIFY_SYSTEM = """\
You are a memory classifier for an AI agent.

kind:
  fact        — durable truths: dates, names, places, factual statements
  preference  — user preferences, reminders, stated wishes
  scratchpad  — working notes, ambiguous content, or run-scoped state
  tool_outcome — result of a tool call (do not use here)

Return:
  keywords  : 3-8 lowercase search keywords, no stopwords
  descriptor: one line, max 100 chars
  value     : structured dict of key entities extracted
  confidence: 0.0-1.0
"""

_RELEVANT_SYSTEM = """\
You are a relevance scorer. Given a query and candidate memory items,
return only a JSON array of the most relevant item IDs.
Example output: ["abc123", "def456"]
"""


# ── Memory ID helper ──────────────────────────────────────────────────────────

def new_id(prefix: str = "mem") -> str:
    import uuid
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


# ── Memory class ──────────────────────────────────────────────────────────────

class Memory:
    def __init__(self, path: Path = _MEM_PATH) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._items: list[MemoryItem] = self._load()
        self._llm = LLM()

    def _load(self) -> list[MemoryItem]:
        if not self._path.exists():
            return []
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return [MemoryItem.model_validate(x) for x in raw.get("items", [])]
        except Exception:
            return []

    def _flush(self) -> None:
        # Merge with any items written to disk by other processes (e.g. MCP subprocess)
        # so that fact chunks indexed by index_document survive agent-loop flushes.
        existing = self._load()
        in_mem_ids = {m.id for m in self._items}
        # Items on disk not yet in memory
        disk_only = [m for m in existing if m.id not in in_mem_ids]
        # Items in memory not yet on disk (written by this process)
        merged = disk_only + self._items
        # Sync self._items so future flushes stay consistent
        if disk_only:
            self._items = merged
        out = {"items": [m.model_dump(mode="json") for m in self._items]}
        self._path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")

    def _persist_item(self, item: MemoryItem) -> None:
        """Append item to in-memory list and flush to disk."""
        self._items.append(item)
        self._flush()

    def _load_all(self) -> list[MemoryItem]:
        """Re-read items from disk (cross-process safety for FAISS recall)."""
        return self._load()

    # ── Read ──────────────────────────────────────────────────────────────────

    def read(
        self,
        query: str,
        history: list[dict] | None = None,
        kinds: list[str] | None = None,
        top_k: int = 8,
    ) -> list[MemoryItem]:
        """Vector search (FAISS) first, keyword overlap fallback. No LLM."""
        if history is None:
            history = []

        # ── Vector path: try FAISS first ──────────────────────────────────────
        index, ids = _load_faiss()
        if index is not None and index.ntotal > 0:
            q_emb = _try_embed(query, task_type="retrieval_query")
            if q_emb:
                q_vec = np.array([q_emb], dtype="float32")
                faiss.normalize_L2(q_vec)
                k = min(max(top_k, 10), index.ntotal)
                scores, positions = index.search(q_vec, k)
                hit_ids: set[str] = set()
                for pos, score in zip(positions[0], scores[0]):
                    # threshold 0.15 — generous enough for regulatory text chunks
                    # whose embeddings spread semantics across 400-word windows.
                    if pos >= 0 and score > 0.15:
                        hit_ids.add(ids[pos])
                if hit_ids:
                    all_items = self._load_all()
                    results = [item for item in all_items if item.id in hit_ids]
                    if kinds:
                        results = [r for r in results if r.kind in kinds]
                    return results[:top_k]
        # ── Fall through to keyword search if vector path returns nothing ─────

        q_words = set(_tokenize(query))
        for ev in history[-6:]:
            if ev.get("kind") == "action":
                q_words.update(_tokenize(ev.get("result_descriptor", "")))
            elif ev.get("kind") == "answer":
                q_words.update(_tokenize(ev.get("text", "")))

        pool = [m for m in self._items if m.kind in kinds] if kinds else self._items

        scored: list[tuple[int, MemoryItem]] = []
        for item in pool:
            item_words = set(item.keywords) | set(_tokenize(item.descriptor))
            overlap = len(q_words & item_words)
            if overlap > 0:
                scored.append((overlap, item))

        scored.sort(key=lambda x: (-x[0], x[1].created_at.isoformat()))
        return [m for _, m in scored[:top_k]]

    def filter(
        self,
        *,
        kinds: list[str] | None = None,
        goal_id: str | None = None,
        recent: int | None = None,
    ) -> list[MemoryItem]:
        """Structured filter by kind, goal, recency. No LLM."""
        out = self._items
        if kinds:
            out = [m for m in out if m.kind in kinds]
        if goal_id:
            out = [m for m in out if m.goal_id == goal_id]
        if recent:
            out = sorted(out, key=lambda m: m.created_at, reverse=True)[:recent]
        return out

    def relevant(
        self,
        query: str,
        kinds: list[str] | None = None,
        top_k: int = 5,
    ) -> list[MemoryItem]:
        """LLM-scored relevance. Used when keyword recall is weak."""
        pool = [m for m in self._items if m.kind in kinds] if kinds else self._items
        if not pool:
            return []

        item_lines = "\n".join(f"  [{m.id}] {m.descriptor}" for m in pool[:40])
        prompt = (
            f"QUERY: {query}\n\nMEMORY ITEMS:\n{item_lines}\n\n"
            f"Return a JSON array of the {top_k} most relevant IDs."
        )
        try:
            resp = _llm_retry(
                self._llm, prompt,
                system=_RELEVANT_SYSTEM,
                auto_route="memory",
                max_tokens=256,
                temperature=0.0,
            )
            ids = json.loads(resp.get("text", "[]"))
            id_set = set(ids[:top_k])
            return [m for m in pool if m.id in id_set]
        except Exception:
            return pool[:top_k]

    # ── Write ─────────────────────────────────────────────────────────────────

    def remember(
        self,
        raw_text: str,
        *,
        source: str,
        run_id: str,
        goal_id: str | None = None,
    ) -> MemoryItem:
        """One LLM call to classify and extract. auto_route='memory'."""
        try:
            resp = _llm_retry(
                self._llm, raw_text,
                system=_CLASSIFY_SYSTEM,
                auto_route="memory",
                response_format={"type": "json_schema", "schema": _CLASSIFY_SCHEMA},
                temperature=0.0,
                max_tokens=512,
            )
            data = resp.get("parsed") or json.loads(resp.get("text", "{}"))
        except Exception:
            data = {
                "kind": "scratchpad",
                "keywords": _tokenize(raw_text)[:6],
                "descriptor": raw_text[:80],
                "value": {"raw": raw_text},
                "confidence": 0.5,
            }

        item = MemoryItem(
            kind=data.get("kind", "scratchpad"),
            keywords=data.get("keywords", _tokenize(raw_text)[:6]),
            descriptor=data.get("descriptor", raw_text[:80]),
            value=data.get("value", {"raw": raw_text}),
            source=source,
            run_id=run_id,
            goal_id=goal_id,
            confidence=float(data.get("confidence", 1.0)),
        )
        # Embed on insert for fact/preference kinds
        if item.kind in ("fact", "preference", "tool_outcome"):
            item.embedding = _try_embed(item.descriptor)
            if item.embedding:
                _append_faiss(item.id, item.embedding)

        self._items.append(item)
        self._flush()
        return item

    def record_outcome(
        self,
        *,
        tool_call: ToolCall,
        result_text: str,
        artifact_id: str | None,
        run_id: str,
        goal_id: str | None,
    ) -> MemoryItem:
        """No LLM. kind is always tool_outcome."""
        keywords = _tokenize(tool_call.name)
        for v in tool_call.arguments.values():
            keywords.extend(_tokenize(str(v)))
        keywords = list(dict.fromkeys(keywords))[:10]

        param_preview = ", ".join(
            f"{k}={str(v)[:30]!r}" for k, v in list(tool_call.arguments.items())[:2]
        )
        descriptor = f"{tool_call.name}({param_preview}) → {result_text[:80]}"
        value: dict = {
            "tool": tool_call.name,
            "arguments": tool_call.arguments,
            "result_preview": result_text[:500],
        }
        if artifact_id:
            value["artifact_id"] = artifact_id

        item = MemoryItem(
            kind="tool_outcome",
            keywords=keywords,
            descriptor=descriptor,
            value=value,
            artifact_id=artifact_id,
            source="action",
            run_id=run_id,
            goal_id=goal_id,
        )
        # Embed tool_outcome items
        if item.kind in ("fact", "preference", "tool_outcome"):
            item.embedding = _try_embed(item.descriptor)
            if item.embedding:
                _append_faiss(item.id, item.embedding)

        self._items.append(item)
        self._flush()
        return item

    # ── New: add_fact (used by index_document MCP tool) ───────────────────────

    def add_fact(
        self,
        descriptor: str,
        *,
        value: dict,
        keywords: list[str],
        source: str,
        run_id: str,
        goal_id: str | None = None,
    ) -> MemoryItem:
        """Insert a pre-classified fact directly (no LLM). Embeds and indexes.

        For document chunks (value has a non-empty 'chunk' key), we embed the
        full chunk text rather than the descriptor so that semantic search finds
        content by meaning, not by the metadata prefix in the descriptor.
        """
        # Prefer embedding the full chunk content when available so FAISS search
        # matches on actual document text rather than the "[file chunk X/Y] ..."
        # descriptor prefix (which dilutes the semantic signal).
        chunk_text = value.get("chunk") if isinstance(value, dict) else None
        embed_text = chunk_text if chunk_text else descriptor
        embedding = _try_embed(embed_text, task_type="retrieval_document")
        item = MemoryItem(
            id=new_id("mem"),
            kind="fact",
            keywords=[k.lower() for k in keywords],
            descriptor=descriptor,
            value=value,
            embedding=embedding,
            source=source,
            run_id=run_id,
            goal_id=goal_id,
            confidence=1.0,
            created_at=datetime.utcnow(),
        )
        self._persist_item(item)
        if embedding:
            _append_faiss(item.id, embedding)
        return item


# Module-level singleton
memory = Memory()


# Module-level shortcut so mcp_server can call memory.add_fact directly
def add_fact(
    descriptor: str,
    *,
    value: dict,
    keywords: list[str],
    source: str,
    run_id: str,
    goal_id: str | None = None,
) -> MemoryItem:
    """Module-level alias for memory.add_fact — used by mcp_server tools."""
    return memory.add_fact(
        descriptor,
        value=value,
        keywords=keywords,
        source=source,
        run_id=run_id,
        goal_id=goal_id,
    )
