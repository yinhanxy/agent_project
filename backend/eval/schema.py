import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class EvalCase:
    id: str
    question: str
    type: str                              # knowledge_qa / document_compare / ...
    expected_doc: Optional[str] = None     # 检索命中标尺（文件名）
    answer_assertions: dict = field(default_factory=dict)  # {"must_include":[], "must_not_include":[]}
    should_refuse: bool = False
    history: list = field(default_factory=list)            # [[user, assistant], ...]
    expected_route: Optional[str] = None          # coordinator 预期路由
    expect_gap_triggered: Optional[bool] = None    # 是否预期触发知识缺口
    rubric_points: list = field(default_factory=list)   # 开放式输出的逐点评分要点


def load_cases(path) -> list[EvalCase]:
    """从 jsonl 加载评估用例，跳过空行。"""
    cases: list[EvalCase] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        raw = json.loads(line)
        cases.append(EvalCase(
            id=raw["id"],
            question=raw["question"],
            type=raw["type"],
            expected_doc=raw.get("expected_doc"),
            answer_assertions=raw.get("answer_assertions", {}),
            should_refuse=raw.get("should_refuse", False),
            history=raw.get("history", []),
            expected_route=raw.get("expected_route"),
            expect_gap_triggered=raw.get("expect_gap_triggered"),
            rubric_points=raw.get("rubric_points", []),
        ))
    return cases
