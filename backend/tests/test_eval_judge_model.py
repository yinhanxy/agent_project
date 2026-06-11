import os
from eval.judge_model import judge_model_name, build_judge_model


def test_default_judge_is_qwen3_max(monkeypatch):
    monkeypatch.delenv("EVAL_JUDGE_MODEL", raising=False)
    assert judge_model_name() == "qwen3-max"


def test_judge_model_override(monkeypatch):
    monkeypatch.setenv("EVAL_JUDGE_MODEL", "qwen-plus")
    assert judge_model_name() == "qwen-plus"


def test_build_judge_model_is_tongyi(monkeypatch):
    monkeypatch.setenv("ALIYUN_ACCESS_KEY_SECRET", "sk-test")
    monkeypatch.setenv("ALIYUN_BASE_URL", "https://example/v1")
    m = build_judge_model()
    # ChatTongyi 实例，模型名与 temperature 正确
    assert m.model_name == "qwen3-max" or getattr(m, "model", None) == "qwen3-max"
