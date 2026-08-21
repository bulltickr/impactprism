from scripts.validate_ci_examples import validate_examples
from scripts.validate_demos import validate_demos


def test_provider_neutral_ci_examples_are_valid():
    assert validate_examples() == []


def test_public_demo_matrix_is_valid():
    assert validate_demos() == []
