import pytest
from eval.judges.grounding_judge import faithfulness_score, judge_faithfulness, GroundingVerdict


def test_faithfulness_score():
    assert faithfulness_score(total_claims=4, unsupported=1) == 0.75
    assert faithfulness_score(total_claims=0, unsupported=0) is None  # 无可判 → 不适用


def test_grounding_verdict_reasoning_defaults_empty():
    v = GroundingVerdict(total_claims=1, unsupported_claims=[])
    assert v.reasoning == ""


class _FakeStruct:
    def __init__(self, v): self._v = v
    async def ainvoke(self, m): return self._v


class _FakeJudge:
    def __init__(self, v): self._v = v
    def with_structured_output(self, s): return _FakeStruct(self._v)


@pytest.mark.asyncio
async def test_judge_faithfulness():
    v = GroundingVerdict(total_claims=4, unsupported_claims=["编造的第5条规定"], reasoning="一条无依据")
    score = await judge_faithfulness(_FakeJudge(v), "回答", ["文档片段1", "文档片段2"])
    assert score == 0.75
