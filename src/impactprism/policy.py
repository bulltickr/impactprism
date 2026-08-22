"""Provider-neutral policy evaluation for scan and CI adapters.

The CLI and the reusable Action have different presentation concerns, but
they must agree on which findings are gated and how scanner or unsupported
repository states affect the process result.  This module owns that decision
without importing either adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


SEVERITY_ORDER = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

VALID_FAIL_ON = ("never", "finding", "all")

OUTCOME_CLEAN = "clean"
OUTCOME_FINDING = "finding"
OUTCOME_POLICY_FAILURE = "policy-failure"
OUTCOME_UNSUPPORTED_ECOSYSTEM = "unsupported-ecosystem"
OUTCOME_SCANNER_ERROR = "scanner-error"


def normalize_severity(value) -> str:
    """Normalize a finding severity, conservatively treating unknown values as info."""

    severity = str(value).lower() if value is not None else "info"
    return severity if severity in SEVERITY_ORDER else "info"


def normalize_threshold(value) -> str:
    """Normalize an internal threshold, defaulting invalid values to low."""

    threshold = str(value).lower() if value is not None else "low"
    return threshold if threshold in SEVERITY_ORDER else "low"


def validate_fail_on(value) -> str:
    """Validate and normalize a public fail-on value."""

    fail_on = str(value).lower() if value is not None else "finding"
    if fail_on not in VALID_FAIL_ON:
        raise ValueError("fail-on must be never, finding, or all")
    return fail_on


def validate_threshold(value) -> str:
    """Validate and normalize a public severity threshold."""

    threshold = str(value).lower() if value is not None else "low"
    if threshold not in SEVERITY_ORDER:
        raise ValueError(
            "severity threshold must be one of: " + ", ".join(SEVERITY_ORDER)
        )
    return threshold


@dataclass(frozen=True)
class PolicyDecision:
    """The normalized result of applying one policy to one finding set."""

    outcome: str
    exit_code: int
    fail_on: str
    severity_threshold: str
    gate_source: str
    finding_count: int
    triggered_count: int

    def as_dict(self) -> dict:
        """Return the additive machine-readable policy contract."""

        return {
            "fail_on": self.fail_on,
            "severity_threshold": self.severity_threshold,
            "gate_source": self.gate_source,
            "outcome": self.outcome,
            "exit_code": self.exit_code,
            "finding_count": self.finding_count,
            "triggered_count": self.triggered_count,
        }


def policy_exit_code_for_outcome(outcome: str, *, fail_on: str = "finding") -> int:
    """Map a normalized outcome to the shared process exit contract."""

    fail_on = validate_fail_on(fail_on)
    if outcome in (OUTCOME_CLEAN, OUTCOME_FINDING):
        return 0
    if outcome == OUTCOME_POLICY_FAILURE:
        return 0 if fail_on == "never" else 1
    if outcome == OUTCOME_UNSUPPORTED_ECOSYSTEM:
        return 1 if fail_on == "all" else 0
    if outcome == OUTCOME_SCANNER_ERROR:
        return 2
    return 0


def evaluate_policy(
    findings: Iterable[dict] | None,
    *,
    fail_on: str = "finding",
    severity_threshold: str = "low",
    error_kind: str = "none",
    gate_source: str = "findings",
) -> PolicyDecision:
    """Evaluate findings after any caller-specific baseline selection.

    Callers should pass the complete finding list for an ordinary scan and
    only the new findings for a baseline/delta gate.  The complete report can
    still retain every finding for review; ``gate_source`` records which set
    was used for the decision.
    """

    values = list(findings or ())
    fail_on = validate_fail_on(fail_on)
    threshold = validate_threshold(severity_threshold)

    has_scanner_error = error_kind == "scanner_error" or (
        error_kind != "unsupported"
        and any(item.get("finding_type") == "SCANNER_ERROR" for item in values)
    )
    if has_scanner_error:
        outcome = OUTCOME_SCANNER_ERROR
        triggered_count = 0
    elif error_kind == "unsupported":
        outcome = OUTCOME_UNSUPPORTED_ECOSYSTEM
        triggered_count = 0
    else:
        threshold_rank = SEVERITY_ORDER[threshold]
        triggered_count = sum(
            SEVERITY_ORDER[normalize_severity(item.get("severity"))]
            >= threshold_rank
            for item in values
        )
        outcome = (
            OUTCOME_POLICY_FAILURE
            if triggered_count
            else OUTCOME_FINDING
            if values
            else OUTCOME_CLEAN
        )

    return PolicyDecision(
        outcome=outcome,
        exit_code=policy_exit_code_for_outcome(outcome, fail_on=fail_on),
        fail_on=fail_on,
        severity_threshold=threshold,
        gate_source=gate_source,
        finding_count=len(values),
        triggered_count=triggered_count,
    )
