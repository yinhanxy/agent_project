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
