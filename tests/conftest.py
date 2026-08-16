import os
import shutil
import sys


# Keep the requested src-path setup local to the test configuration.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "src"))

import pytest


@pytest.fixture
def npm_fixture_repo(tmp_path):
    source = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "remediation", "npm_repo")
    destination = tmp_path / "npm_repo"
    shutil.copytree(source, destination)
    yield destination


@pytest.fixture
def sbom_fixture_repo(tmp_path):
    source = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "sbom", "npm_repo")
    destination = tmp_path / "sbom-fixture"
    shutil.copytree(source, destination)
    yield destination


@pytest.fixture
def go_fixture_repo(tmp_path):
    source = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "remediation", "go_repo")
    destination = tmp_path / "go_repo"
    shutil.copytree(source, destination)
    yield destination
