from scripts.validate_ci_examples import validate_examples


def test_provider_neutral_ci_examples_are_valid():
    assert validate_examples() == []
