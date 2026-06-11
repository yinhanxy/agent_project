from eval.system_under_test import parse_events


def test_parse_events_extracts_answer_citations_tokens():
    events = [
        {"type": "token", "data": "住宿"},
        {"type": "token", "data": "上限550元"},
        {"type": "done", "steps": [{"agent": "knowledge"}, {"agent": "finalize"}],
         "tokens": 1234, "citations": [
             {"filename": "02-差旅与报销管理办法-2025版.md", "score": 0.92},
             {"filename": "01-差旅与报销管理办法-2023版.md", "score": 0.55}]},
    ]
    r = parse_events(events)
    assert r["answer"] == "住宿上限550元"
    assert r["ranked_filenames"] == ["02-差旅与报销管理办法-2025版.md",
                                     "01-差旅与报销管理办法-2023版.md"]
    assert r["tokens"] == 1234
    assert r["trace_agents"] == ["knowledge", "finalize"]


def test_parse_events_handles_missing_done():
    r = parse_events([{"type": "token", "data": "x"}])
    assert r["answer"] == "x"
    assert r["ranked_filenames"] == []
    assert r["tokens"] == 0
