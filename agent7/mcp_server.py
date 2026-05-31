"""
mcp_server.py
11 MCP tools exposed via stdio transport.

web_search      — Tavily primary, DuckDuckGo fallback, max 5 results
fetch_url       — crawl4ai headless Chromium → clean markdown
get_time        — current time in any IANA timezone
currency_convert — live FX via frankfurter.dev
read_file / list_dir / create_file / update_file / edit_file — sandboxed to ./workspace/
index_document  — chunk a file into FAISS-indexed fact records in Memory (Session 7)
search_knowledge — semantic vector search over previously indexed chunks (Session 7)
"""
from __future__ import annotations

import json
import os
import sys
import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from ddgs import DDGS
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv(Path(__file__).parent / ".env")

# Memory import — needed for index_document and search_knowledge
sys.path.insert(0, str(Path(__file__).parent))
import memory as _mem_module

MAX_RESULTS = 5
mcp = FastMCP("cognitive-agent-tools")

WORKSPACE = Path(__file__).parent / "workspace"
WORKSPACE.mkdir(exist_ok=True)

PAPERS_DIR = Path(__file__).parent / "papers"

_USAGE_FILE = Path(__file__).parent / "usage.json"
_MONTHLY_LIMIT = 950
_lock = threading.Lock()


def _bounded(path: str) -> Path:
    """Resolve a path within the workspace sandbox OR the papers/ read-only directory."""
    # Allow papers/ prefix (read-only view of the SEBI corpus)
    if path == "papers" or path.startswith("papers/") or path.startswith("papers\\"):
        sub = path[7:] if path.startswith("papers/") else path[len("papers\\"):]
        resolved = (PAPERS_DIR / sub).resolve() if sub else PAPERS_DIR.resolve()
        if resolved == PAPERS_DIR.resolve() or PAPERS_DIR.resolve() in resolved.parents:
            return resolved
        raise ValueError(f"'{path}' escapes the papers directory")
    resolved = (WORKSPACE / path).resolve()
    if resolved != WORKSPACE.resolve() and WORKSPACE.resolve() not in resolved.parents:
        raise ValueError(f"'{path}' is outside the workspace sandbox")
    return resolved


def _usage_now() -> dict:
    month = datetime.now().strftime("%Y-%m")
    if not _USAGE_FILE.exists():
        return {"month": month, "tavily": {"n": 0, "err": 0}, "ddg": {"n": 0, "err": 0}}
    try:
        d = json.loads(_USAGE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"month": month, "tavily": {"n": 0, "err": 0}, "ddg": {"n": 0, "err": 0}}
    if d.get("month") != month:
        return {"month": month, "tavily": {"n": 0, "err": 0}, "ddg": {"n": 0, "err": 0}}
    return d


def _save_usage(d: dict) -> None:
    _USAGE_FILE.write_text(json.dumps(d, indent=2), encoding="utf-8")


def _tick(provider: str, field: str = "n") -> None:
    with _lock:
        d = _usage_now()
        d[provider][field] = d[provider].get(field, 0) + 1
        _save_usage(d)


def _within_limit(provider: str) -> bool:
    return _usage_now()[provider]["n"] < _MONTHLY_LIMIT


def _tavily(query: str, n: int) -> list[dict]:
    from tavily import TavilyClient
    client = TavilyClient(os.environ["TAVILY_API_KEY"])
    resp = client.search(query=query, max_results=n, search_depth="advanced")
    return [{"title": r.get("title",""), "url": r.get("url",""), "snippet": r.get("content","")}
            for r in resp.get("results", [])]


def _ddg(query: str, n: int) -> list[dict]:
    hits: list[dict] = []
    with DDGS() as d:
        for backend in ("auto", "html", "lite"):
            try:
                hits = list(d.text(query, max_results=n, backend=backend))
            except Exception:
                hits = []
            if hits:
                break
    return [{"title": h.get("title",""), "url": h.get("href",""), "snippet": h.get("body","")}
            for h in hits]


async def _crawl(url: str) -> dict:
    from crawl4ai import AsyncWebCrawler
    saved = os.dup(1)
    os.dup2(2, 1)
    try:
        async with AsyncWebCrawler(verbose=False) as c:
            r = await c.arun(url=url)
    finally:
        os.dup2(saved, 1)
        os.close(saved)
    md = r.markdown
    raw = (getattr(md, "raw_markdown", None)
           or getattr(md, "fit_markdown", None)
           or md or r.cleaned_html or r.html or "")
    text = str(raw)
    return {
        "status": int(getattr(r, "status_code", None) or 200),
        "mime": "text/markdown",
        "bytes": len(text.encode("utf-8")),
        "text": text,
    }


@mcp.tool()
def web_search(query: str, max_results: int = 5) -> list[dict]:
    """Search the web. Tavily primary, DuckDuckGo fallback. Max 5 results."""
    n = max(1, min(max_results, MAX_RESULTS))
    if os.environ.get("TAVILY_API_KEY") and _within_limit("tavily"):
        try:
            out = _tavily(query, n)
            if out:
                _tick("tavily")
                return out
        except Exception:
            _tick("tavily", "err")
    out = _ddg(query, n)
    _tick("ddg")
    return out


@mcp.tool()
async def fetch_url(url: str, timeout: int = 20) -> dict:
    """Fetch a URL and return clean markdown via headless Chromium (crawl4ai)."""
    return await _crawl(url)


@mcp.tool()
def get_time(timezone: str = "UTC") -> dict:
    """Return current time in the given IANA timezone. Example: get_time('Asia/Kolkata')."""
    tz = ZoneInfo(timezone)
    now = datetime.now(tz)
    offset = now.utcoffset()
    return {
        "iso": now.isoformat(),
        "human": now.strftime("%A, %d %B %Y %H:%M:%S %Z"),
        "timezone": timezone,
        "offset_hours": offset.total_seconds() / 3600 if offset else 0.0,
    }


@mcp.tool()
def currency_convert(amount: float, from_currency: str, to_currency: str) -> dict:
    """Convert between currencies using live rates from frankfurter.dev."""
    f, t = from_currency.upper(), to_currency.upper()
    url = f"https://api.frankfurter.dev/v1/latest?amount={amount}&base={f}&symbols={t}"
    with httpx.Client(timeout=20, follow_redirects=True) as client:
        r = client.get(url)
        r.raise_for_status()
        data = r.json()
    converted = data["rates"][t]
    return {"amount": amount, "from": f, "to": t,
            "rate": converted / amount if amount else 0.0,
            "converted": converted, "date": data["date"]}


@mcp.tool()
def read_file(path: str) -> dict:
    """Read a file from the workspace sandbox."""
    p = _bounded(path)
    text = p.read_text(encoding="utf-8")
    return {"path": path, "bytes": p.stat().st_size, "content": text}


@mcp.tool()
def list_dir(path: str = ".") -> list[dict]:
    """List contents of a workspace directory."""
    p = _bounded(path)
    return [{"name": c.name, "type": "dir" if c.is_dir() else "file",
             "bytes": 0 if c.is_dir() else c.stat().st_size}
            for c in sorted(p.iterdir())]


@mcp.tool()
def create_file(path: str, content: str) -> dict:
    """Create a new file in the workspace. Fails if it already exists."""
    p = _bounded(path)
    if p.exists():
        raise ValueError(f"'{path}' already exists")
    if not p.parent.exists():
        raise ValueError(f"Parent dir of '{path}' does not exist")
    p.write_text(content, encoding="utf-8")
    return {"ok": True, "path": path, "bytes": p.stat().st_size}


@mcp.tool()
def update_file(path: str, content: str) -> dict:
    """Overwrite an existing workspace file."""
    p = _bounded(path)
    if not p.exists():
        raise ValueError(f"'{path}' does not exist")
    p.write_text(content, encoding="utf-8")
    return {"ok": True, "path": path, "bytes": p.stat().st_size}


@mcp.tool()
def edit_file(path: str, find: str, replace: str, replace_all: bool = False) -> dict:
    """Find-and-replace within a workspace file."""
    p = _bounded(path)
    text = p.read_text(encoding="utf-8")
    count = text.count(find)
    if count == 0:
        raise ValueError(f"'{find}' not found in '{path}'")
    if count > 1 and not replace_all:
        raise ValueError(f"'{find}' occurs {count} times — pass replace_all=True")
    new_text = text.replace(find, replace) if replace_all else text.replace(find, replace, 1)
    p.write_text(new_text, encoding="utf-8")
    return {"ok": True, "path": path, "replacements": count if replace_all else 1,
            "bytes": p.stat().st_size}


def _read_artifact(artifact_id: str) -> str:
    """Load artifact bytes as text — used by index_document when path starts with 'art:'."""
    art_dir = Path(__file__).parent / "state" / "artifacts"
    bin_path = art_dir / f"{artifact_id}.bin"
    if not bin_path.exists():
        raise FileNotFoundError(f"artifact {artifact_id} not found")
    return bin_path.read_bytes().decode("utf-8", errors="replace")


@mcp.tool()
def index_document(path: str, chunk_size: int = 400, overlap: int = 80) -> dict:
    """Chunk a sandbox file or artifact and write the chunks into Memory as
    fact records, where they become FAISS-searchable for later queries.
    Use this when the content must be searchable across later turns or runs.
    For one-shot inspection of a file's contents, use read_file instead."""
    import re as _re

    # Resolve path — supports 'art:<id>' for stored artifacts, relative paths
    # from papers/ or sandbox/, or absolute paths.
    if path.startswith("art:"):
        content = _read_artifact(path[4:])
    else:
        # Try papers/ first, then sandbox/, then absolute
        papers_path = Path(__file__).parent / "papers" / path
        sandbox_path = Path(__file__).parent / "sandbox" / path
        abs_path = Path(path)
        if papers_path.exists():
            full = papers_path
        elif sandbox_path.exists():
            full = sandbox_path
        elif abs_path.is_absolute() and abs_path.exists():
            full = abs_path
        else:
            # Last resort — try relative to agent dir
            full = Path(__file__).parent / path
        with open(full, encoding="utf-8") as f:
            content = f.read()

    words = content.split()
    chunks: list[str] = []
    i, n = 0, 0
    while i < len(words):
        chunk_words = words[i : i + chunk_size]
        chunks.append(" ".join(chunk_words))
        i += chunk_size - overlap
        n += 1

    run_id = "index_doc"
    for idx, chunk in enumerate(chunks):
        descriptor = f"[{path} chunk {idx+1}/{n}] {chunk[:80]}"
        keywords = list(set(_re.findall(r'\b[a-zA-Z]{4,}\b', chunk.lower())))[:15]
        _mem_module.memory.add_fact(
            descriptor=descriptor,
            value={"chunk": chunk, "source": path, "chunk_idx": idx + 1, "total": n},
            keywords=keywords,
            source=f"index_document:{path}",
            run_id=run_id,
        )
    return {"indexed": n, "path": path, "chunk_size": chunk_size}


@mcp.tool()
def search_knowledge(query: str, k: int = 5) -> list[dict]:
    """Vector search over previously indexed fact chunks in Memory.
    Use this rather than re-reading source files when Memory already
    contains indexed chunks for the topic. Returns chunk text with provenance."""
    import re as _re
    import numpy as np
    import faiss as _faiss

    q_lower = query.lower()
    q_words = [w for w in _re.findall(r'[a-zA-Z]{4,}', q_lower)]

    def _score_chunk(item) -> int:
        text = (item.descriptor + " " + item.value.get("chunk", "")).lower()
        return sum(1 for w in q_words if w in text)

    # ── Gather all fact chunks (in-memory first, then disk for cross-run recall) ──
    all_facts = [
        r for r in _mem_module.memory._items
        if r.kind == "fact" and r.value.get("chunk")
    ]
    if not all_facts:
        # Cross-run recall: reload from disk
        all_disk = _mem_module.memory._load_all()
        all_facts = [r for r in all_disk if r.kind == "fact" and r.value.get("chunk")]

    if not all_facts:
        return [{"descriptor": "No indexed chunks found. Use index_document first.",
                 "chunk": "", "source": "", "chunk_idx": None}]

    # ── Path 1: FAISS vector search (semantic, most accurate) ───────────────────
    try:
        q_emb = _mem_module._try_embed(query, task_type="retrieval_query")
        if q_emb:
            index, ids = _mem_module._load_faiss()
            if index is not None and index.ntotal > 0:
                q_vec = np.array([q_emb], dtype="float32")
                _faiss.normalize_L2(q_vec)
                n_search = min(max(k, 10), index.ntotal)
                scores, positions = index.search(q_vec, n_search)
                # Build lookup: id → item
                id_to_item = {item.id: item for item in all_facts}
                hit_items = []
                for pos, score in zip(positions[0], scores[0]):
                    if pos >= 0 and score > 0.1 and pos < len(ids):
                        item = id_to_item.get(ids[pos])
                        if item:
                            hit_items.append(item)
                if hit_items:
                    return [
                        {
                            "descriptor": item.descriptor,
                            "chunk": item.value.get("chunk", "")[:500],
                            "source": item.value.get("source", ""),
                            "chunk_idx": item.value.get("chunk_idx"),
                        }
                        for item in hit_items[:k]
                    ]
    except Exception:
        pass

    # ── Path 2: keyword scoring fallback ────────────────────────────────────────
    scored = sorted(all_facts, key=_score_chunk, reverse=True)
    return [
        {
            "descriptor": item.descriptor,
            "chunk": item.value.get("chunk", "")[:500],
            "source": item.value.get("source", ""),
            "chunk_idx": item.value.get("chunk_idx"),
        }
        for item in scored[:k]
    ]


if __name__ == "__main__":
    mcp.run(transport="stdio")
