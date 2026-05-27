"""dict filter → Milvus boolean expression 转译器测试。"""
import pytest

from app.rag.vector_backend.milvus_filter import dict_to_milvus_expr


def test_none_or_empty_returns_empty_string():
    assert dict_to_milvus_expr(None) == ""
    assert dict_to_milvus_expr({}) == ""


def test_simple_string_equality_shorthand():
    assert dict_to_milvus_expr({"user_id": "u1"}) == 'user_id == "u1"'


def test_simple_int_equality_shorthand():
    assert dict_to_milvus_expr({"chunk_index": 3}) == 'chunk_index == 3'


def test_explicit_eq_operator():
    assert dict_to_milvus_expr({"user_id": {"$eq": "u1"}}) == 'user_id == "u1"'


def test_explicit_ne_operator():
    assert dict_to_milvus_expr({"user_id": {"$ne": "u1"}}) == 'user_id != "u1"'


def test_in_operator_with_strings():
    expr = dict_to_milvus_expr({"kb_id": {"$in": ["a", "b"]}})
    assert expr == 'kb_id in ["a", "b"]'


def test_nin_operator_with_strings():
    expr = dict_to_milvus_expr({"kb_id": {"$nin": ["a", "b"]}})
    assert expr == 'kb_id not in ["a", "b"]'


def test_multi_field_implicit_and():
    """同一层多个字段隐式 AND（与 Chroma 行为一致）"""
    expr = dict_to_milvus_expr({"user_id": "u1", "kb_id": "k1"})
    # 排序不保证，但两个条件都要在且用 and 连接
    assert "and" in expr
    assert 'user_id == "u1"' in expr
    assert 'kb_id == "k1"' in expr


def test_or_operator():
    expr = dict_to_milvus_expr({
        "$or": [
            {"user_id": "u1"},
            {"kb_id": {"$in": ["a", "b"]}},
        ]
    })
    assert expr == '(user_id == "u1") or (kb_id in ["a", "b"])'


def test_and_operator():
    expr = dict_to_milvus_expr({
        "$and": [
            {"user_id": "u1"},
            {"kb_id": "k1"},
        ]
    })
    assert expr == '(user_id == "u1") and (kb_id == "k1")'


def test_nested_or_inside_and():
    expr = dict_to_milvus_expr({
        "$and": [
            {"user_id": "u1"},
            {"$or": [
                {"kb_id": "k1"},
                {"kb_id": "k2"},
            ]},
        ]
    })
    assert expr == '(user_id == "u1") and ((kb_id == "k1") or (kb_id == "k2"))'


def test_real_world_rag_filter():
    """复现 agent_tools._build_rag_filter 的真实输出形态"""
    expr = dict_to_milvus_expr({
        "$or": [
            {"user_id": {"$eq": "user-uuid-123"}},
            {"kb_id": {"$in": ["kb-a", "kb-b", "kb-c"]}},
        ]
    })
    assert expr == (
        '(user_id == "user-uuid-123") '
        'or (kb_id in ["kb-a", "kb-b", "kb-c"])'
    )


def test_string_value_with_quotes_escaped():
    """字符串值里包含双引号要转义"""
    expr = dict_to_milvus_expr({"filename": 'he said "hi"'})
    assert expr == r'filename == "he said \"hi\""'


def test_empty_condition_dict_raises():
    """{"field": {}} 触发 ValueError，不允许静默崩溃"""
    with pytest.raises(ValueError, match="不能为空"):
        dict_to_milvus_expr({"field": {}})


def test_empty_in_list_raises():
    """$in [] 触发 ValueError，Milvus 不接受"""
    with pytest.raises(ValueError, match="空列表"):
        dict_to_milvus_expr({"kb_id": {"$in": []}})


def test_unsupported_operator_raises():
    """$gt 等未实现的操作符要报错"""
    with pytest.raises(ValueError, match="不支持的操作符"):
        dict_to_milvus_expr({"chunk_index": {"$gt": 5}})


def test_none_value_raises():
    """字段值为 None 时应 ValueError，避免生成无效的 'field == None'"""
    with pytest.raises(ValueError, match="不支持 None"):
        dict_to_milvus_expr({"user_id": None})
