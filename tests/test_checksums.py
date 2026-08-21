import hashlib

import pytest

from scripts.checksums import (
    checksum_lines,
    validate_release_directory,
    write_checksums,
    write_file_checksum,
)


def test_checksums_are_sorted_and_exclude_the_manifest(tmp_path):
    (tmp_path / "z.txt").write_text("z", encoding="utf-8")
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "SHA256SUMS").write_text("stale\n", encoding="utf-8")

    output = write_checksums(tmp_path)
    lines = output.read_text(encoding="utf-8").splitlines()

    assert [line.rsplit("  ", 1)[1] for line in lines] == ["a.txt", "z.txt"]
    assert lines[0].startswith(hashlib.sha256(b"a").hexdigest())
    assert lines[1].startswith(hashlib.sha256(b"z").hexdigest())
    assert checksum_lines(tmp_path) == lines


def test_strict_release_directory_requires_one_wheel_and_sdist(tmp_path):
    wheel = tmp_path / "impactprism-0.4.1-py3-none-any.whl"
    sdist = tmp_path / "impactprism-0.4.1.tar.gz"
    wheel.write_bytes(b"wheel")
    sdist.write_bytes(b"sdist")

    assert validate_release_directory(tmp_path) == [wheel, sdist]

    (tmp_path / "notes.txt").write_text("unexpected", encoding="utf-8")
    with pytest.raises(ValueError, match="exactly one"):
        validate_release_directory(tmp_path)


def test_file_checksum_sidecar_uses_the_source_filename(tmp_path):
    evidence = tmp_path / "compatibility-result.json"
    evidence.write_bytes(b'{"passed": true}\n')

    sidecar = write_file_checksum(evidence)

    assert sidecar == tmp_path / "compatibility-result.json.sha256"
    assert sidecar.read_text(encoding="utf-8") == (
        f"{hashlib.sha256(evidence.read_bytes()).hexdigest()}  compatibility-result.json\n"
    )


def test_file_checksum_sidecar_supports_a_separate_output_path(tmp_path):
    evidence = tmp_path / "compatibility-result.json"
    evidence.write_bytes(b"evidence")
    sidecar = tmp_path / "release" / "compatibility-result.json.sha256"

    assert write_file_checksum(evidence, sidecar) == sidecar.resolve()
    assert sidecar.read_text(encoding="utf-8").endswith("  compatibility-result.json\n")
