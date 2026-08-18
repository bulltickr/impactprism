import hashlib

from scripts.checksums import checksum_lines, write_checksums


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
