from benchmarks.correctness.run import run_cases


def test_governed_correctness_matrix_passes_and_has_explicit_case_count():
    result = run_cases()

    assert result["passed"] is True
    assert result["case_count"] == 14
    assert {case["id"] for case in result["cases"]} >= {
        "npm-pnpm-clean",
        "python-optional-clean",
        "npm-dynamic-generated-clean",
        "python-dynamic-generated-clean",
        "npm-pnpm-resolution-boundary",
    }
