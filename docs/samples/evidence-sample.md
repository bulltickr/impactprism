# ImpactPrism Evidence Pack

- Generator: impactprism-evidence
- Version: 0.3.0
- Schema version: 2
- Map version: 1.0.0
- Legal source: Regulation (EU) 2024/2847 - Cyber Resilience Act
- Overall status: REVIEW_REQUIRED
- Timestamp: 2026-08-15T21:26:48.377321Z
- Source report: C:\Users\quint\Desktop\OPS\products\impactprism\report.json
- Package: impactprism-demo@1.0.0

## Findings

### undeclared: missingpkg

Status: REVIEW_REQUIRED
CRA clauses: Art 13(1)(b), Art 14(1), Annex I Part II, Annex VII
Rationale: Undeclared dependencies fall outside the SBOM/component transparency expected under Article 13(1)(b) and may expand the attack surface; this warrants manual review against Article 13(1)(b), Article 14(1) and Annex VII to determine whether any obligation applies.

### drift: react

Status: REVIEW_REQUIRED
CRA clauses: Art 13(1)(a), Annex I Part I
Rationale: Unnecessary installed components may expand the attack surface and warrants review against Article 13(1)(a) and Annex I Part I to confirm whether secure-by-default or minimisation expectations apply.

## CRA references

| Clause | Description |
| --- | --- |
| Art 13(1)(a) | Secure by default |
| Art 13(1)(b) | Component transparency |
| Art 14(1) | Vulnerability handling and remediation |
| Annex I Part I | Essential requirements - secure configuration and minimisation |
| Annex I Part II | Essential requirements - vulnerability handling documentation |
| Annex VII | Documented vulnerability-handling process |
