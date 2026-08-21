from impactprism.drift.models import FindingType
from impactprism.guidance import get_remediation_guidance


def test_every_public_finding_type_has_review_first_guidance():
    for finding_type in FindingType:
        guidance = get_remediation_guidance(finding_type.name)
        assert guidance["summary"]
        assert guidance["steps"]
        assert all(step for step in guidance["steps"])
        assert guidance["caution"]


def test_guidance_returns_independent_data():
    first = get_remediation_guidance("UNDECLARED_DIRECT_USE")
    first["steps"].append("test mutation")

    second = get_remediation_guidance("UNDECLARED_DIRECT_USE")
    assert "test mutation" not in second["steps"]


def test_unknown_finding_type_gets_safe_generic_guidance():
    guidance = get_remediation_guidance("future-finding")

    assert "review" in guidance["summary"].lower()
    assert guidance["steps"]
    assert "clean" in guidance["caution"].lower()
