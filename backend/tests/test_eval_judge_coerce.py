"""judge 结构化输出容错：不同 judge 模型可能把 list 字段返回成字符串化 JSON 数组
（如 qwen3.7-max），Verdict 模型须能归一化成 list[str]，否则 runner 在开放题 judge 阶段崩。"""
from eval.judges.grounding_judge import GroundingVerdict
from eval.judges.llm_judge import CoverageVerdict


def test_grounding_coerces_stringified_list():
    # 复现 qwen3.7-max 实际返回的字符串化数组 + 字符串数字
    v = GroundingVerdict(total_claims="2", unsupported_claims='\n["a","b"]\n')
    assert v.unsupported_claims == ["a", "b"]
    assert v.total_claims == 2


def test_grounding_accepts_real_list():
    v = GroundingVerdict(total_claims=1, unsupported_claims=["x"])
    assert v.unsupported_claims == ["x"]


def test_grounding_handles_empty_and_garbage():
    assert GroundingVerdict(total_claims=0, unsupported_claims="").unsupported_claims == []
    assert GroundingVerdict(total_claims=0, unsupported_claims="not json").unsupported_claims == ["not json"]
    assert GroundingVerdict(total_claims="oops", unsupported_claims=[]).total_claims == 0


def test_coverage_coerces_stringified_list():
    v = CoverageVerdict(covered_points='["p1","p2"]')
    assert v.covered_points == ["p1", "p2"]


def test_coverage_accepts_real_list():
    assert CoverageVerdict(covered_points=["p1"]).covered_points == ["p1"]
