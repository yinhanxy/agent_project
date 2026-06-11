from eval.judges.assertion_judge import check_assertions


def test_must_include_all_present_passes():
    assert check_assertions("住宿上限为550元", {"must_include": ["550"]}) is True


def test_must_include_missing_fails():
    assert check_assertions("住宿上限较高", {"must_include": ["550"]}) is False


def test_must_not_include_hit_fails():
    assert check_assertions("旧版是450元", {"must_include": [], "must_not_include": ["450"]}) is False


def test_empty_assertions_passes():
    assert check_assertions("任意回答", {}) is True


def test_multiple_must_include_partial_fails():
    assert check_assertions("只有8000", {"must_include": ["8000", "60"]}) is False
