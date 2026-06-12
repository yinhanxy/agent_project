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


def test_parse_events_extracts_route_and_gap():
    from eval.system_under_test import parse_events
    events = [
        {"type": "token", "data": "已记录缺口"},
        {"type": "done", "steps": [{"agent": "coordinator"}, {"agent": "knowledge"},
                                   {"agent": "knowledge_gap"}],
         "tokens": 100, "citations": [], "plan": {"task_type": "knowledge_gap"}},
    ]
    r = parse_events(events)
    assert r["route"] == "knowledge_gap"
    assert r["gap_triggered"] is True


def test_parse_events_no_gap_when_absent():
    from eval.system_under_test import parse_events
    events = [{"type": "done", "steps": [{"agent": "coordinator"}, {"agent": "knowledge"},
                                         {"agent": "finalize"}],
              "tokens": 50, "citations": [], "plan": {"task_type": "knowledge_qa"}}]
    r = parse_events(events)
    assert r["route"] == "knowledge_qa"
    assert r["gap_triggered"] is False


def test_parse_events_exposes_doc_previews():
    from eval.system_under_test import parse_events
    events = [{"type": "done", "steps": [], "tokens": 1, "plan": {"task_type": "document_compare"},
               "citations": [{"filename": "a.md", "chunk_preview": "片段A", "score": 0.9}]}]
    r = parse_events(events)
    assert r["doc_previews"] == ["片段A"]


def test_parse_events_exposes_max_score():
    from eval.system_under_test import parse_events
    events = [{"type": "done", "steps": [], "tokens": 1, "plan": {"task_type": "knowledge_qa"},
               "citations": [{"filename": "a.md", "score": 0.83},
                             {"filename": "b.md", "score": 0.41}]}]
    r = parse_events(events)
    assert r["max_score"] == 0.83


def test_parse_events_max_score_none_when_no_citations():
    from eval.system_under_test import parse_events
    r = parse_events([{"type": "done", "steps": [], "tokens": 1, "citations": [],
                       "plan": {"task_type": "knowledge_gap"}}])
    assert r["max_score"] is None
