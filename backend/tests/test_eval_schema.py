import json
from pathlib import Path
from eval.schema import EvalCase, load_cases


def test_load_cases_parses_fields(tmp_path):
    p = tmp_path / "d.jsonl"
    p.write_text(json.dumps({
        "id": "qa-001",
        "question": "一线城市出差住宿费每晚上限是多少？",
        "type": "knowledge_qa",
        "expected_doc": "02-差旅与报销管理办法-2025版.md",
        "answer_assertions": {"must_include": ["550"], "must_not_include": ["450"]},
        "should_refuse": False,
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    cases = load_cases(p)
    assert len(cases) == 1
    c = cases[0]
    assert isinstance(c, EvalCase)
    assert c.id == "qa-001"
    assert c.expected_doc == "02-差旅与报销管理办法-2025版.md"
    assert c.answer_assertions["must_include"] == ["550"]
    assert c.should_refuse is False


def test_load_cases_skips_blank_lines(tmp_path):
    p = tmp_path / "d.jsonl"
    p.write_text('\n\n{"id":"x","question":"q","type":"knowledge_qa"}\n\n', encoding="utf-8")
    cases = load_cases(p)
    assert len(cases) == 1
    assert cases[0].answer_assertions == {}   # 缺字段给默认


def test_real_dataset_loads_and_is_nonempty():
    cases = load_cases(Path(__file__).parent.parent / "eval" / "datasets" / "retrieval.jsonl")
    assert len(cases) >= 8
    assert all(c.id and c.question and c.type for c in cases)


def test_load_cases_parses_routing_fields(tmp_path):
    import json
    from eval.schema import load_cases
    p = tmp_path / "r.jsonl"
    p.write_text(json.dumps({
        "id": "rt-001", "question": "对比2023和2025版报销差异",
        "type": "document_compare", "expected_route": "document_compare",
        "expect_gap_triggered": False,
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    c = load_cases(p)[0]
    assert c.expected_route == "document_compare"
    assert c.expect_gap_triggered is False


def test_routing_dataset_loads():
    from pathlib import Path
    from eval.schema import load_cases
    cases = load_cases(Path(__file__).parent.parent / "eval" / "datasets" / "routing.jsonl")
    assert len(cases) >= 10
    assert all(c.expected_route for c in cases)
    # 至少覆盖 5 类路由
    assert {c.expected_route for c in cases} >= {
        "knowledge_qa", "document_compare", "report_generation",
        "document_generation", "knowledge_gap"}
