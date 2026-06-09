from app.utils.factory import get_chat_model


def test_get_chat_model_returns_instance_for_each_role():
    for role in ("coordinator", "knowledge_gap", "finalize"):
        m = get_chat_model(role)
        assert m is not None
        assert get_chat_model(role) is m


def test_unknown_role_falls_back_to_finalize():
    assert get_chat_model("不存在的角色") is get_chat_model("finalize")
