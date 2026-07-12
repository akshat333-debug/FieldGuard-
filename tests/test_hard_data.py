"""Hard dataset: distractors present, gold consistent, deterministic."""
from fieldguard.data import make_hard_dataset


def test_hard_docs_contain_distractors():
    ex = make_hard_dataset(n=3)[0]
    doc = ex.document
    assert "PO Number" in doc            # id lookalike
    assert "Bill To" in doc              # name distractor
    assert "Subtotal" in doc and "Tax" in doc and "Shipping" in doc
    assert "Payment due" in doc          # date distractor
    # gold total is the TOTAL DUE line value, formatted with separators
    total = float(ex.gold["total"])
    assert f"{total:,.2f}" in doc


def test_hard_dataset_deterministic():
    a = make_hard_dataset(n=5, seed=21)
    b = make_hard_dataset(n=5, seed=21)
    assert [x.gold for x in a] == [x.gold for x in b]
