from app.utils.factory import get_chat_model


def test_get_chat_model_returns_instance_for_each_role():
    for role in ("coordinator", "knowledge_gap", "finalize"):
        m = get_chat_model(role)
        assert m is not None
        assert get_chat_model(role) is m


def test_unknown_role_falls_back_to_finalize():
    assert get_chat_model("不存在的角色") is get_chat_model("finalize")


def test_deepseek_role_mapping_uses_flash_and_pro(monkeypatch):
    """LLM_TYPE=DEEPSEEK 时按角色分配：coordinator/knowledge_gap→flash，finalize→pro。

    覆盖盲区：上面两个用例在非 DEEPSEEK 环境下三角色都退回同一个 chat_model，
    并未真正验证 flash/pro 映射；本用例显式切到 DEEPSEEK 验证映射正确。
    """
    import app.utils.factory as factory

    monkeypatch.setenv("LLM_TYPE", "DEEPSEEK")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    # 清掉可能存在的模型名覆盖，确保走默认 flash/pro
    monkeypatch.delenv("DEEPSEEK_MODEL_COORDINATOR", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL_FINALIZE", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL_RAG", raising=False)
    # get_chat_model 用 lru_cache，先清缓存再按新环境构造，结束后再清避免污染其他用例
    factory.get_chat_model.cache_clear()
    try:
        assert factory.get_chat_model("coordinator").model_name == "deepseek-v4-flash"
        assert factory.get_chat_model("knowledge_gap").model_name == "deepseek-v4-flash"
        assert factory.get_chat_model("finalize").model_name == "deepseek-v4-pro"
        # RAG 摘要 / HyDE 等内部轻量任务用 flash
        assert factory.get_chat_model("rag").model_name == "deepseek-v4-flash"
        # critic 证据评估：与 coordinator 同档（flash）
        assert factory.get_chat_model("critic").model_name == "deepseek-v4-flash"
    finally:
        factory.get_chat_model.cache_clear()
