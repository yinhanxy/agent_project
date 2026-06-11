from eval.calibrate import agreement


def test_agreement_within_tolerance():
    # (judge_score, human_score) 对，容差 0.25 内算一致
    pairs = [(1.0, 1.0), (0.5, 0.6), (0.0, 0.5)]   # 第三对差 0.5 不一致
    assert agreement(pairs, tol=0.25) == 2 / 3
