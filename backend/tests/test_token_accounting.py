from app.agent.token_utils import extract_total_tokens


class _MsgUsageMeta:
    usage_metadata = {"total_tokens": 123}


class _MsgRespMeta:
    response_metadata = {"token_usage": {"total_tokens": 77}}


class _MsgNone:
    content = "x"


def test_extract_from_usage_metadata():
    assert extract_total_tokens(_MsgUsageMeta()) == 123


def test_extract_from_response_metadata():
    assert extract_total_tokens(_MsgRespMeta()) == 77


def test_extract_returns_none_when_absent():
    assert extract_total_tokens(_MsgNone()) is None
    assert extract_total_tokens(None) is None
