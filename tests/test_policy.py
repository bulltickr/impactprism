import pytest

from impactprism.policy import (
    OUTCOME_CLEAN,
    OUTCOME_FINDING,
    OUTCOME_POLICY_FAILURE,
    OUTCOME_SCANNER_ERROR,
    OUTCOME_UNSUPPORTED_ECOSYSTEM,
    evaluate_policy,
    validate_fail_on,
    validate_threshold,
)


@pytest.mark.parametrize(
    ("severity", "threshold", "expected"),
    [
        ("info", "info", OUTCOME_POLICY_FAILURE),
        ("low", "medium", OUTCOME_FINDING),
        ("medium", "medium", OUTCOME_POLICY_FAILURE),
        ("HIGH", "high", OUTCOME_POLICY_FAILURE),
        ("unknown", "high", OUTCOME_FINDING),
    ],
)
def test_shared_policy_uses_inclusive_threshold_and_safe_unknown_severity(
    severity, threshold, expected
):
    decision = evaluate_policy(
        [{"finding_type": "TEST", "severity": severity}],
        severity_threshold=threshold,
    )

    assert decision.outcome == expected
    assert decision.finding_count == 1
    assert decision.triggered_count == (1 if expected == OUTCOME_POLICY_FAILURE else 0)


def test_shared_policy_records_baseline_gate_source_and_only_considers_new_findings():
    decision = evaluate_policy(
        [{"finding_type": "UNDECLARED_DIRECT_USE", "severity": "high"}],
        severity_threshold="medium",
        gate_source="baseline-new-findings",
    )

    assert decision.as_dict() == {
        "fail_on": "finding",
        "severity_threshold": "medium",
        "gate_source": "baseline-new-findings",
        "outcome": "policy-failure",
        "exit_code": 1,
        "finding_count": 1,
        "triggered_count": 1,
    }


@pytest.mark.parametrize("fail_on", ["never", "finding", "all"])
def test_scanner_errors_always_exit_two_and_precede_policy(fail_on):
    decision = evaluate_policy(
        [{"finding_type": "SCANNER_ERROR", "severity": "critical"}],
        fail_on=fail_on,
        severity_threshold="info",
        error_kind="scanner_error",
    )

    assert decision.outcome == OUTCOME_SCANNER_ERROR
    assert decision.exit_code == 2
    assert decision.triggered_count == 0


@pytest.mark.parametrize(
    ("fail_on", "expected_code"),
    [("never", 0), ("finding", 0), ("all", 1)],
)
def test_unsupported_ecosystem_only_fails_under_all(fail_on, expected_code):
    decision = evaluate_policy(
        [], fail_on=fail_on, error_kind="unsupported"
    )

    assert decision.outcome == OUTCOME_UNSUPPORTED_ECOSYSTEM
    assert decision.exit_code == expected_code


def test_empty_and_below_threshold_results_are_distinguishable_but_successful():
    clean = evaluate_policy([])
    finding = evaluate_policy([{"severity": "low"}], severity_threshold="high")

    assert clean.outcome == OUTCOME_CLEAN
    assert clean.exit_code == 0
    assert finding.outcome == OUTCOME_FINDING
    assert finding.exit_code == 0


def test_policy_inputs_have_one_validation_contract():
    assert validate_fail_on("ALL") == "all"
    assert validate_threshold("HIGH") == "high"
    with pytest.raises(ValueError, match="fail-on"):
        validate_fail_on("unexpected")
    with pytest.raises(ValueError, match="severity threshold"):
        validate_threshold("urgent")
