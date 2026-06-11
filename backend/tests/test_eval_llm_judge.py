import pytest
from eval.judges.llm_judge import coverage_ratio, judge_coverage, CoverageVerdict


def test_coverage_ratio():
    assert coverage_ratio(["a", "b"], total=4) == 0.5
    assert coverage_ratio([], total=3) == 0.0
    assert coverage_ratio(["a"], total=0) is None   # 无 rubric 不适用


def test_coverage_verdict_reasoning_defaults_empty():
    v = CoverageVerdict(covered_points=[])
    assert v.reasoning == ""


class _FakeStruct:
    def __init__(self, verdict): self._v = verdict
    async def ainvoke(self, messages): return self._v


class _FakeJudge:
    def __init__(self, verdict): self._v = verdict
    def with_structured_output(self, schema): return _FakeStruct(self._v)


@pytest.mark.asyncio
async def test_judge_coverage_counts_covered():
    verdict = CoverageVerdict(covered_points=["审批额度5000→8000", "报销时限30→60天"],
                              reasoning="覆盖两点")
    model = _FakeJudge(verdict)
    ratio = await judge_coverage(model, "对比问题", "回答文本",
                                 ["审批额度5000→8000", "报销时限30→60天", "打款5→3工作日"])
    assert ratio == pytest.approx(2 / 3)
