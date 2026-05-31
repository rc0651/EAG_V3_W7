"""
agent7.py
Entry point and agent loop — EAG V3 Week 7: SEBI Compliance RAG Agent.

Wires: Memory → Perception → Decision → Action in a fixed iteration order.
Each iteration:
  1. memory.read()        — FAISS vector search first, keyword fallback (no LLM)
  2. perception.observe() — update goal list, mark done, attach artifacts
  3. decision.next_step() — answer or invoke a tool
  4. action.execute()     — dispatch MCP tool, store large results as artifacts
  5. memory.record_outcome() — persist outcome + embed (no LLM)

New in Session 7:
  - /v1/embed gateway endpoint (Ollama nomic-embed-text / Gemini fallback)
  - FAISS index at state/index.faiss for vector recall
  - index_document MCP tool: chunk any file into searchable memory
  - search_knowledge MCP tool: semantic search over indexed chunks

Usage:
  uv run python agent7.py "your query"
  uv run python agent7.py --run-a   through --run-h  (base queries A-H)
  uv run python agent7.py --run-q1  through --run-q5 (custom SEBI queries)

State management:
  Clear state between independent test groups:
    rm -rf state/ && mkdir state
  Do NOT clear state between:
    --run-c1 and --run-c2   (memory persistence test)
    --run-f1 and --run-f2   (cross-run FAISS recall)
    --run-g  and --run-h    (need indexed corpus)
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import action as act
import decision
import perception
from artifacts import ArtifactStore, artifacts
from memory import Memory, memory
from schemas import Goal

_DIR = Path(__file__).parent
_MCP_SERVER = _DIR / "mcp_server.py"
_GW_URL = "http://localhost:8101"
_MAX_ITER = 20

QUERIES: dict[str, str] = {
    # ── Base queries A-H ────────────────────────────────────────────────────
    "--run-a": (
        "Fetch https://en.wikipedia.org/wiki/Claude_Shannon and tell me his "
        "birth date, death date, and three key contributions to information theory."
    ),
    "--run-b": (
        "Find 3 family-friendly things to do in Tokyo this weekend. "
        "Check Saturday's weather forecast there and tell me which one is most appropriate."
    ),
    "--run-c1": (
        "My mom's birthday is 15 May 2026. Remember that and create reminders "
        "for two weeks before and on the day."
    ),
    "--run-c2": "When is mom's birthday?",
    "--run-d": (
        "Search for Python asyncio best practices, read the top 3 results, "
        "and give me a short numbered list of the advice they agree on."
    ),
    "--run-e": (
        "Index the file papers/sebi_master_circular_stockbrokers_2024.md and tell me "
        "what the three main obligations of a stockbroker towards clients are."
    ),
    "--run-f1": (
        "Index all six SEBI papers using index_document. "
        "Index these files in order: "
        "papers/sebi_master_circular_stockbrokers_2024.md, "
        "papers/sebi_peak_margin_circular.md, "
        "papers/sebi_algo_ibt_circular.md, "
        "papers/sebi_fo_eligibility_retail_2024.md, "
        "papers/sebi_kyc_nomination_circular.md, "
        "papers/sebi_scores_grievance_circular.md. "
        "After indexing all six files, report the total chunk count."
    ),
    "--run-f2": (
        "Across the papers I have indexed, what do they say about "
        "client fund settlement and running accounts?"
    ),
    "--run-g": (
        "Across these papers, how does SEBI prevent brokers from misusing client money?"
    ),
    "--run-h": (
        "Compare how SEBI handles investor grievance timelines versus "
        "broker onboarding obligations."
    ),
    # ── Custom SEBI queries Q1-Q5 ─────────────────────────────────────────
    "--run-q1": (
        "Can a new retail client start trading options on their first day?"
    ),
    "--run-q2": (
        "What happens if a broker forgets to collect margin before placing a trade?"
    ),
    "--run-q3": (
        "How does SEBI prevent brokers from misusing client funds?"
    ),
    "--run-q4": (
        "What safeguards exist to stop runaway algo trades?"
    ),
    "--run-q5": (
        "Compare how SEBI handles investor complaints versus broker onboarding failures."
    ),
}


def _gateway_up() -> bool:
    import httpx
    try:
        return httpx.get(f"{_GW_URL}/v1/providers", timeout=3).status_code == 200
    except Exception:
        return False


def ensure_gateway() -> None:
    if _gateway_up():
        print("[gateway] up at", _GW_URL)
        return
    print("[gateway] not found — starting llm_gatewayV3 ...")
    gw = _DIR / "llm_gatewayV3" / "main.py"
    if not gw.exists():
        print(f"[gateway] ERROR: {gw} not found. Start it manually.")
        sys.exit(1)
    subprocess.Popen([sys.executable, str(gw)], cwd=str(gw.parent))
    for _ in range(10):
        time.sleep(3)
        if _gateway_up():
            print("[gateway] started")
            return
    print("[gateway] ERROR: did not start within 30s")
    sys.exit(1)


def mcp_tools_for_decision(mcp_tools: list) -> list[dict]:
    """Convert MCP Tool objects to the dict format the gateway expects."""
    result = []
    for t in mcp_tools:
        schema = getattr(t, "inputSchema", None)
        if schema is None:
            schema = getattr(t, "input_schema", {}) or {}
        if hasattr(schema, "model_dump"):
            schema = schema.model_dump()
        result.append({
            "name": t.name,
            "description": t.description or "",
            "input_schema": schema if isinstance(schema, dict) else {},
        })
    return result


def final_answer_from(history: list[dict]) -> str:
    answers = [ev for ev in history if ev.get("kind") == "answer"]
    if answers:
        return answers[-1]["text"]
    actions = [ev for ev in history if ev.get("kind") == "action"]
    if actions:
        return f"Done: {actions[-1]['tool']} → {actions[-1].get('result_descriptor', '')[:500]}"
    return "No answer produced."


async def run(
    query: str,
    *,
    mem: Memory = memory,
    store: ArtifactStore = artifacts,
) -> str:
    ensure_gateway()

    run_id = uuid.uuid4().hex[:8]
    history: list[dict] = []
    prior_goals: list[Goal] = []

    print(f"\n[agent:{run_id}] {query[:120]}")
    print("[memory] classifying query ...")
    mem.remember(query, source="user_query", run_id=run_id)

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(_MCP_SERVER)],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            raw_tools = (await session.list_tools()).tools
            mcp_tools = mcp_tools_for_decision(raw_tools)
            print(f"[tools] {len(mcp_tools)} available: {[t['name'] for t in mcp_tools]}")

            for it in range(1, _MAX_ITER + 1):
                print(f"\n── iter {it} ──")

                # 1. Memory recall
                hits = mem.read(query, history)
                print(f"[memory] {len(hits)} hits: {[h.descriptor[:50] for h in hits]}")

                # 2. Perception
                obs = perception.observe(
                    query=query,
                    hits=hits,
                    history=history,
                    prior_goals=prior_goals,
                    run_id=run_id,
                )
                prior_goals = obs.goals

                for g in obs.goals:
                    status = "[done]" if g.done else "[open]"
                    attach = f"  attach={g.attach_artifact_id}" if g.attach_artifact_id else ""
                    print(f"  [perception] {status} {g.id}: {g.text}{attach}")

                if obs.all_done:
                    print("[agent] all goals done")
                    # If nothing was done this run (all from memory), ask Decision
                    # for a confirmatory summary so we never return "No answer produced."
                    if not history:
                        print("[agent] all from memory — generating summary answer")
                        from schemas import Goal as _Goal
                        summary_goal = _Goal(id="summary", text=query, done=False)
                        out = decision.next_step(
                            goal=summary_goal,
                            hits=hits,
                            attached=[],
                            history=history,
                            mcp_tools=mcp_tools,
                        )
                        if out.is_answer:
                            print(f"  [decision] ANSWER: {out.answer[:300]}")
                            history.append({
                                "iter": it, "kind": "answer",
                                "goal_id": "summary", "text": out.answer,
                            })
                    break

                goal = obs.next_unfinished()
                if goal is None:
                    break

                # 3. Load artifact attachment if needed
                attached: list[tuple[str, bytes]] = []
                if goal.attach_artifact_id:
                    if store.exists(goal.attach_artifact_id):
                        data = store.get_bytes(goal.attach_artifact_id)
                        attached.append((goal.attach_artifact_id, data))
                        print(f"  [artifact] loaded {goal.attach_artifact_id} ({len(data):,} bytes)")
                    else:
                        print(f"  [artifact] WARNING: {goal.attach_artifact_id} not found")

                # 4. Decision
                out = decision.next_step(
                    goal=goal,
                    hits=hits,
                    attached=attached,
                    history=history,
                    mcp_tools=mcp_tools,
                )

                if out.is_answer:
                    print(f"  [decision] ANSWER: {out.answer[:300]}")
                    history.append({
                        "iter": it, "kind": "answer",
                        "goal_id": goal.id, "text": out.answer,
                    })
                    goal.done = True  # skip extra Perception round-trip
                    if obs.all_done:
                        print("[agent] all goals done")
                        break
                    continue

                tc = out.tool_call
                print(f"  [decision] TOOL: {tc.name}({tc.arguments})")

                # 5. Action
                result_text, art_id = await act.execute(
                    session=session,
                    tool_call=tc,
                    store=store,
                )
                print(f"  [action] → {result_text[:300]}")

                mem.record_outcome(
                    tool_call=tc,
                    result_text=result_text,
                    artifact_id=art_id,
                    run_id=run_id,
                    goal_id=goal.id,
                )
                # Store more chars for RAG tools so Decision sees full chunk content
                _hist_trunc = 2000 if tc.name in ("search_knowledge", "index_document") else 300
                history.append({
                    "iter": it, "kind": "action",
                    "goal_id": goal.id,
                    "tool": tc.name,
                    "arguments": tc.arguments,
                    "result_descriptor": result_text[:_hist_trunc],
                    "artifact_id": art_id,
                })

            else:
                print(f"[agent] max iterations ({_MAX_ITER}) reached")

    final = final_answer_from(history)
    border = "=" * 60
    print(f"\n{border}\nFINAL ANSWER:\n{final}\n{border}")
    return final


def _get_query() -> str:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)
    for flag, text in QUERIES.items():
        if flag in args:
            return text
    return " ".join(args)


if __name__ == "__main__":
    asyncio.run(run(_get_query()))
