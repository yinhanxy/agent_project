from app.tools import compare_tool, report_tool, form_tool


def _assert_common_shape(messages, query, doc):
    assert isinstance(messages, list) and len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert doc in messages[1]["content"]
    assert query in messages[1]["content"]


def test_compare_tool_builds_table_prompt():
    msgs = compare_tool.build_messages("新旧报销制度区别", ["旧版500", "新版600"])
    _assert_common_shape(msgs, "新旧报销制度区别", "旧版500")
    assert "表格" in msgs[0]["content"]


def test_report_tool_builds_report_prompt():
    msgs = report_tool.build_messages("售后处理流程报告", ["售后政策内容"])
    _assert_common_shape(msgs, "售后处理流程报告", "售后政策内容")
    assert "报告" in msgs[0]["content"]


def test_form_tool_builds_form_prompt():
    msgs = form_tool.build_messages("出差申请说明", ["差旅制度内容"])
    _assert_common_shape(msgs, "出差申请说明", "差旅制度内容")
    assert "申请" in msgs[0]["content"] or "说明" in msgs[0]["content"]


def test_tools_handle_empty_documents():
    for tool in (compare_tool, report_tool, form_tool):
        msgs = tool.build_messages("任意问题", [])
        assert len(msgs) == 2 and msgs[0]["role"] == "system"
