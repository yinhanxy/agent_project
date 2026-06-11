import time


def parse_events(events: list) -> dict:
    """把 GraphRunner.stream 的事件流解析成结构化结果。"""
    answer = "".join(e["data"] for e in events if e.get("type") == "token")
    done = next((e for e in reversed(events) if e.get("type") == "done"), {})
    citations = done.get("citations", []) or []
    trace_agents = [s.get("agent") for s in (done.get("steps", []) or [])]
    return {
        "answer": answer,
        "ranked_filenames": [c.get("filename") for c in citations],
        "tokens": done.get("tokens", 0) or 0,
        "trace_agents": trace_agents,
        "route": (done.get("plan") or {}).get("task_type"),
        "gap_triggered": "knowledge_gap" in trace_agents,
        "doc_previews": [c.get("chunk_preview", "") for c in citations],
    }


async def run_one(runner, question: str, history: list) -> dict:
    """用已编译的 runner 跑一题，附带延迟。"""
    t0 = time.perf_counter()
    events = [e async for e in runner.stream(question, history=history or [], identity=None)]
    result = parse_events(events)
    result["latency_s"] = time.perf_counter() - t0
    return result


async def run_dataset(cases: list) -> list:
    """对一组 EvalCase 真实驱动被测系统（当前进程的 env 决定配置）。
    每个配置在子进程内调用本函数，故这里只建一次 GraphRunner（按当前 env 编译）。
    """
    from app.agent.graph.runner import GraphRunner
    runner = GraphRunner()
    out = []
    for c in cases:
        r = await run_one(runner, c.question, c.history)
        out.append({"id": c.id, **r})
    return out
