from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LANDING_PAGE = REPO_ROOT / "site" / "index.html"
README = REPO_ROOT / "README.md"
ACTION_README = REPO_ROOT / "action" / "README.md"
TRUST_DOC = REPO_ROOT / "docs" / "TRUST_AND_VERIFICATION.md"


def _public_docs():
    return {
        "landing page": LANDING_PAGE.read_text(encoding="utf-8"),
        "README": README.read_text(encoding="utf-8"),
    }


def test_public_docs_state_supported_ecosystems_and_limitations():
    docs = _public_docs()

    shared_required_phrases = (
        "selected npm, Python, and Go supply-chain controls",
        "Findings require review",
        "Evidence may be incomplete",
        "scope is unassessed outside",
        "not legal advice, certification, an audit opinion, or a compliance determination",
    )
    for document_name, content in docs.items():
        for phrase in shared_required_phrases:
            assert phrase in content, f"{phrase!r} missing from {document_name}"

    readme = docs["README"]
    for phrase in (
        "The CLI auto-detects supported project inputs.",
        "npm uses `package.json` and supported lockfiles",
        "Python uses supported `pyproject.toml`, `Pipfile`, or `requirements.txt` inputs and lockfiles",
        "Go uses `go.mod`, `go.work`, `go.sum`, and vendored module metadata",
        "The GitHub Action can force `npm`, `python`, or `go` via its `ecosystem` input",
    ):
        assert phrase in readme, f"{phrase!r} missing from README"


def test_public_docs_omit_superseded_unqualified_claims():
    docs = _public_docs()

    superseded_claims = (
        "CRA-grounded",
        "the gap in every SBOM tool",
        "six finding types, not just a component list",
        "Every finding mapped to its EU Cyber Resilience Act clause",
        "Clean scans are <em>PASS</em>",
        "proof, not promises",
        "Six finding types cover the gap every manifest-only SBOM tool misses.",
        "evidence pack mapped to the EU Cyber Resilience Act",
        "a clean report is `PASS`",
        "every finding carries its mapped CRA clauses and rationale",
        "each finding annotated with its CRA clause mapping and rationale",
        "fully offline · npm &amp; Go · MIT",
        "The ecosystem is auto-detected from the presence of `package.json` (npm) or `go.mod` (Go)",
    )
    for document_name, content in docs.items():
        for claim in superseded_claims:
            assert claim not in content, f"superseded claim {claim!r} found in {document_name}"


def test_public_docs_state_maturity_and_offline_boundary():
    readme = README.read_text(encoding="utf-8")
    action_readme = ACTION_README.read_text(encoding="utf-8")
    trust = TRUST_DOC.read_text(encoding="utf-8")
    landing = LANDING_PAGE.read_text(encoding="utf-8")

    assert "early-stage" in readme
    assert "no independent security audit" in readme
    assert "Scan execution is offline after installation" in readme
    assert "managed" in action_readme and "package index" in action_readme
    assert "early-stage OSS" in action_readme
    assert "Current maturity boundary" in trust
    assert "Offline boundary" in trust
    assert "early-stage OSS" in landing
    assert "offline scan after installation" in landing
