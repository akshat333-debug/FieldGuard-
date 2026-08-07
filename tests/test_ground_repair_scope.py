"""The repair rule must never blank a value the document actually supports.

Found live: on Kleister doc 2 the repair blanked a CORRECT effective_date.
Investigation showed the gold date is absent from the (clause-truncated)
document — the model answered without evidence and happened to be right, so
grounding judged its input correctly. That is the only failure mode the rule
is allowed to have, and this test pins the boundary.
"""
from fieldguard.backends import MockBackend
from fieldguard.ground import support
from fieldguard.pipeline import run
from fieldguard.schemas import FieldSpec, Schema

TERM = FieldSpec("term", "string", required=False)
SCHEMA = Schema("s", (TERM,))


class Echo(MockBackend):
    """Both paths return the same fixed answer — a correlated, agreeing pair."""

    def __init__(self, answer: str, field: str = "term"):
        super().__init__()
        self.answer = answer
        self.field = field

    def generate(self, prompt, *, force_json=False):
        self.calls += 1
        return (f'{{"{self.field}": "{self.answer}"}}' if force_json
                else f"{self.field}: {self.answer}")


GROUNDED_DOC = "This agreement shall remain in effect for a term of 2 years."


def test_repair_leaves_supported_values_alone():
    (record,), report = run(Echo("2 years"), [GROUNDED_DOC], SCHEMA,
                            ground_repair=True)
    assert record["term"] == "2 years"      # present in the document, untouched
    assert report.ungrounded == 0


def test_repair_blanks_only_unsupported_values():
    doc = "This agreement contains no term clause whatsoever."
    (record,), report = run(Echo("2 years"), [doc], SCHEMA, ground_repair=True)
    assert record["term"] == ""
    assert report.ungrounded == 1


def test_support_is_the_only_thing_the_rule_consults():
    """A correct-vs-gold value with no source support is still blanked.

    This is the documented, accepted failure: when gold is not derivable from
    the input we were given, the rule cannot be expected to preserve it.
    """
    doc = "This agreement contains no term clause whatsoever."
    assert support(TERM, "2 years", doc) < 0.5
    (record,), _ = run(Echo("2 years"), [doc], SCHEMA, ground_repair=True)
    assert record["term"] == ""  # even though "2 years" might match gold


def test_required_fields_are_never_blanked():
    req = Schema("s", (FieldSpec("total", "number"),))
    doc = "Nothing numeric here."
    (record,), report = run(Echo("54.20", field="total"), [doc], req,
                            ground_repair=True)
    assert record["total"] == "54.20"   # required -> reported, never erased
    assert report.ungrounded == 1
