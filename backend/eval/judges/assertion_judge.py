def check_assertions(answer: str, assertions: dict) -> bool:
    """事实型回答的程序化断言：must_include 全中且 must_not_include 全不中。

    空 assertions 视为通过（该题不做事实断言，交其它裁判）。
    """
    text = answer or ""
    must = assertions.get("must_include", []) or []
    must_not = assertions.get("must_not_include", []) or []
    if not all(s in text for s in must):
        return False
    if any(s in text for s in must_not):
        return False
    return True
