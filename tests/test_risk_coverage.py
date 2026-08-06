"""AURC math: pinned on tiny hand-checkable cases."""
from examples.risk_coverage import aurc


def test_perfect_ranking_beats_worst():
    # 4 fields, 1 error; perfect ranking puts it last
    perfect = [(0.9, False), (0.8, False), (0.7, False), (0.1, True)]
    worst = [(0.9, True), (0.8, False), (0.7, False), (0.1, False)]
    # perfect: prefix risks 0/1, 0/2, 0/3, 1/4 -> mean = 1/16
    assert abs(aurc(perfect) - 1 / 16) < 1e-12
    # worst: 1/1, 1/2, 1/3, 1/4 -> mean = 25/48
    assert abs(aurc(worst) - 25 / 48) < 1e-12
    assert aurc(perfect) < aurc(worst)


def test_all_correct_is_zero_and_all_wrong_is_one():
    assert aurc([(0.5, False)] * 3) == 0.0
    assert aurc([(0.5, True)] * 3) == 1.0


def test_ties_use_stable_corpus_order_not_correctness():
    # identical scores: order must be input order, so AURC is deterministic
    a = [(0.5, True), (0.5, False)]
    b = [(0.5, False), (0.5, True)]
    assert aurc(a) == (1 / 1 + 1 / 2) / 2
    assert aurc(b) == (0 / 1 + 1 / 2) / 2
    assert aurc(a) != aurc(b)
