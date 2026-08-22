from benchmarks.correctness.run import run_cases


def test_governed_correctness_matrix_passes_and_has_explicit_case_count():
    result = run_cases()

    assert result["passed"] is True
    assert result["case_count"] == 20
    cases = {case["id"]: case for case in result["cases"]}
    assert set(cases) >= {
        "npm-pnpm-clean",
        "python-optional-clean",
        "npm-dynamic-generated-clean",
        "python-dynamic-generated-clean",
        "npm-pnpm-resolution-boundary",
        "npm-vite-alias-clean",
        "npm-tsconfig-extends-clean",
        "npm-webpack-monorepo-clean",
        "go-workspace-clean",
        "go-workspace-roots-clean",
        "go-workspace-roots-unscoped",
    }
    assert cases["go-workspace-roots-clean"]["roots"] == ["apps/app"]
    assert cases["go-workspace-roots-clean"]["actual_counts"] == {}
    assert cases["go-workspace-roots-unscoped"]["actual_counts"] == {
        "DECLARED_UNUSED_CANDIDATE": 1
    }
