"""Source-grounding signal: supported values pass, fabrications fire."""
from fieldguard.backends import MockBackend
from fieldguard.data import INVOICE_SCHEMA, make_dataset
from fieldguard.ground import support, ungrounded
from fieldguard.pipeline import run
from fieldguard.schemas import FieldSpec, Schema

DOC = ("This Agreement is entered into on the 30th day of April, 2009 "
       "by ACME Holdings Inc. and shall remain in effect for a term of "
       "two (2) years. Total due RM 1,234.50.")


def test_values_present_in_document_are_grounded():
    assert support(FieldSpec("d", "date"), "2009-04-30", DOC) == 1.0
    assert support(FieldSpec("t", "number"), "1234.50", DOC) == 1.0
    assert support(FieldSpec("p", "string"), "ACME Holdings Inc", DOC) == 1.0
    # normalization is symmetric: "2 years" grounds against "two (2) years"
    assert support(FieldSpec("term", "string"), "2 years", DOC) == 1.0


def test_fabricated_values_are_ungrounded():
    assert ungrounded(FieldSpec("d", "date"), "2011-01-01", DOC)
    assert ungrounded(FieldSpec("t", "number"), "9999.00", DOC)
    assert ungrounded(FieldSpec("j", "string"), "Delaware", DOC)


def test_absence_claims_nothing_so_grounds_trivially():
    opt = FieldSpec("term", "string", required=False)
    assert support(opt, "", DOC) == 1.0
    assert support(opt, "NONE", DOC) == 1.0


def test_multi_uses_weakest_element():
    party = FieldSpec("party", "string", multi=True)
    assert support(party, "ACME Holdings Inc", DOC) == 1.0
    # one fabricated element drags the score down
    assert support(party, "ACME Holdings Inc; Globex GmbH", DOC) < 0.5


def test_pipeline_reports_ungrounded_rate_without_repairing_by_default():
    ex = make_dataset(n=4)
    docs = [e.document for e in ex]
    _, report = run(MockBackend(), docs, INVOICE_SCHEMA,
                    gold=[e.gold for e in ex])
    # mock backend copies values straight out of the document -> all grounded
    assert report.ungrounded == 0
    assert report.ungrounded_rate == 0.0


def test_ground_repair_only_touches_optional_fields():
    opt = FieldSpec("jurisdiction", "string", required=False)
    req = FieldSpec("total", "number")
    schema = Schema("s", (opt, req))

    class Fabricator(MockBackend):
        def generate(self, prompt, *, force_json=False):
            self.calls += 1
            if force_json:
                return '{"jurisdiction": "Delaware", "total": "9999"}'
            return "jurisdiction: Delaware\ntotal: 9999"

    doc = "Agreement total 12.00. No governing law stated."
    finals, report = run(Fabricator(), [doc], schema, ground_repair=True)
    assert report.ungrounded == 2                 # both values invented
    assert finals[0]["jurisdiction"] == ""        # optional -> absent
    assert finals[0]["total"] == "9999"           # required -> left alone
