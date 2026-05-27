"""把 Chroma 风格 dict filter 转成 Milvus 布尔表达式字符串。

支持：
- 简写等于：{field: value}
- $eq / $ne / $in / $nin
- $or / $and（顶层或任意嵌套位置）
- 同层多字段隐式 AND

限制：
- $in / $nin 不接受空列表（Milvus 不支持）
- 操作符 dict 不能为空
- 不支持 None 值（Milvus 无 IS NULL 等价表达）
"""
from typing import Optional, Any


def _format_value(value: Any) -> str:
    """格式化标量值，字符串加引号并转义双引号。"""
    if value is None:
        raise ValueError(
            "filter 值不支持 None（Milvus 无 IS NULL 等价表达），"
            "请在上层过滤掉 None 条件"
        )
    if isinstance(value, str):
        escaped = value.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _format_list(values: list) -> str:
    if not values:
        raise ValueError("$in / $nin 不接受空列表，Milvus 无法解析 `field in []`")
    return "[" + ", ".join(_format_value(v) for v in values) + "]"


def _convert_field(field: str, condition: Any) -> str:
    """单个字段的条件转换。"""
    if isinstance(condition, dict):
        if not condition:
            raise ValueError(f"字段 {field!r} 的条件 dict 不能为空")
        # 操作符形式
        parts: list[str] = []
        for op, operand in condition.items():
            if op == "$eq":
                parts.append(f"{field} == {_format_value(operand)}")
            elif op == "$ne":
                parts.append(f"{field} != {_format_value(operand)}")
            elif op == "$in":
                parts.append(f"{field} in {_format_list(operand)}")
            elif op == "$nin":
                parts.append(f"{field} not in {_format_list(operand)}")
            else:
                raise ValueError(f"不支持的操作符: {op}")
        return " and ".join(parts) if len(parts) > 1 else parts[0]
    # 简写
    return f"{field} == {_format_value(condition)}"


def dict_to_milvus_expr(filter_meta: Optional[dict]) -> str:
    """把 dict filter 转成 Milvus expression。空输入返回空串。"""
    if not filter_meta:
        return ""

    clauses: list[str] = []
    for key, value in filter_meta.items():
        if key == "$or":
            sub = [dict_to_milvus_expr(item) for item in value]
            clauses.append(" or ".join(f"({s})" for s in sub if s))
        elif key == "$and":
            sub = [dict_to_milvus_expr(item) for item in value]
            clauses.append(" and ".join(f"({s})" for s in sub if s))
        else:
            clauses.append(_convert_field(key, value))

    if len(clauses) == 1:
        return clauses[0]
    # 多字段一律加括号，避免依赖"子句含空格"的脆弱启发式
    return " and ".join(f"({c})" for c in clauses)
