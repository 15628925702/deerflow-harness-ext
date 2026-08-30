"""D5 read-only review tests. Host-agnostic."""
from deerflow_harness_ext.coding.result import CodingResult
from deerflow_harness_ext.review.reviewer import review_coding_result


def test_review_pass_on_complete():
    r = CodingResult(success=True, changed_files=["a.py"], tests_run=["t"],
                     test_results={"t": "pass"})
    vr = review_coding_result(r)
    assert vr.passed is True


def test_review_fails_on_not_success():
    r = CodingResult(success=False)
    vr = review_coding_result(r)
    assert vr.passed is False


def test_review_warns_no_tests_but_passes():
    r = CodingResult(success=True, changed_files=["a.py"])
    vr = review_coding_result(r)
    assert vr.passed is True
    assert any(f.severity == "warning" for f in vr.findings)


def test_review_flags_failing_test_as_warning():
    r = CodingResult(success=True, changed_files=["a.py"], tests_run=["t"],
                     test_results={"t": "FAILED"})
    vr = review_coding_result(r)
    assert any(f.severity == "warning" for f in vr.findings)
    assert vr.passed is True        # warning only, not blocking


def test_review_errors_block_pass():
    r = CodingResult(success=True)  # no changed_files -> error
    vr = review_coding_result(r)
    assert vr.passed is False
    assert any(f.severity == "error" for f in vr.findings)
