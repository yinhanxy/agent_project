from typing import Optional


def recall_at_k(ranked_filenames: list, expected_doc: Optional[str], k: int) -> Optional[float]:
    """expected_doc 是否落在 top-k 召回内。expected_doc 为 None 时返回 None（不适用）。"""
    if expected_doc is None:
        return None
    return 1.0 if expected_doc in (ranked_filenames or [])[:k] else 0.0


def mrr(ranked_filenames: list, expected_doc: Optional[str]) -> Optional[float]:
    """expected_doc 在召回排名的倒数。未命中得 0；expected_doc 为 None 返回 None。"""
    if expected_doc is None:
        return None
    for i, f in enumerate(ranked_filenames or [], 1):
        if f == expected_doc:
            return 1.0 / i
    return 0.0


def _mean_ignore_none(values: list) -> Optional[float]:
    nums = [v for v in values if v is not None]
    return sum(nums) / len(nums) if nums else None


def aggregate(per_case: list) -> dict:
    """把每题指标聚合成数据集级指标。None 不计入均值。"""
    return {
        "n": len(per_case),
        "recall@3": _mean_ignore_none([c.get("recall@3") for c in per_case]),
        "mrr": _mean_ignore_none([c.get("mrr") for c in per_case]),
        "assert_pass_rate": (
            sum(1 for c in per_case if c.get("assert_pass")) / len(per_case)
            if per_case else None
        ),
    }
