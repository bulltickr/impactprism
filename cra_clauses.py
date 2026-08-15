import argparse
import sys
from pathlib import Path


DEFAULT_PATH = Path(__file__).resolve().with_name("cra_clauses.yaml")
EXPECTED_SCHEMA_VERSION = 1


class _ParseError(ValueError):
    pass


def _parse_scalar(raw):
    raw = raw.strip()
    if not raw:
        return None
    if raw in ("true", "True", "TRUE"):
        return True
    if raw in ("false", "False", "FALSE"):
        return False
    if raw in ("null", "Null", "~"):
        return None
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    try:
        return int(raw)
    except ValueError:
        return raw


def _split_key_value(content):
    in_single = False
    in_double = False
    for index, char in enumerate(content):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == ":" and not in_single and not in_double:
            return content[:index].strip(), content[index + 1 :].strip()
    raise _ParseError("expected 'key: value' entry but found: " + content)


def _parse_yaml(text):
    lines = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if "\t" in raw[:indent]:
            raise _ParseError("tab indentation is not allowed (line %d)" % lineno)
        lines.append((indent, stripped, lineno))

    position = [0]
    total = len(lines)

    def peek():
        return lines[position[0]] if position[0] < total else None

    def child_block(parent_indent):
        entry = peek()
        if entry is None:
            return None
        indent, content, _ = entry
        if indent <= parent_indent:
            return None
        return parse_block(indent, content.startswith("-"))

    def parse_block(level, is_sequence):
        result = [] if is_sequence else {}
        while True:
            entry = peek()
            if entry is None:
                break
            indent, content, lineno = entry
            if indent < level:
                break
            if indent > level:
                raise _ParseError("unexpected indentation (line %d)" % lineno)
            if is_sequence:
                if not content.startswith("-"):
                    raise _ParseError("expected list item (line %d)" % lineno)
                rest = content[1:].strip()
                position[0] += 1
                result.append(_sequence_item(level, rest, lineno))
            else:
                if content.startswith("-"):
                    raise _ParseError("unexpected list item in mapping (line %d)" % lineno)
                key, value_text = _split_key_value(content)
                position[0] += 1
                value = None if not value_text else _parse_scalar(value_text)
                if not value_text:
                    value = child_block(indent)
                result[str(_parse_scalar(key))] = value
        return result

    def _sequence_item(level, rest, lineno):
        if not rest:
            return child_block(level)
        try:
            key, value_text = _split_key_value(rest)
        except _ParseError:
            return _parse_scalar(rest)
        value = None if not value_text else _parse_scalar(value_text)
        if not value_text:
            value = child_block(level)
        item = {str(_parse_scalar(key)): value}
        while True:
            entry = peek()
            if entry is None:
                break
            indent, content, _ = entry
            if indent <= level:
                break
            if content.startswith("-"):
                break
            key, value_text = _split_key_value(content)
            position[0] += 1
            value = None if not value_text else _parse_scalar(value_text)
            if not value_text:
                value = child_block(indent)
            item[str(_parse_scalar(key))] = value
        return item

    return parse_block(0, False)


def _validate(data, path):
    if data.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        raise ValueError("unsupported schema_version in " + str(path))
    clauses = data.get("clauses")
    if not isinstance(clauses, dict) or not clauses:
        raise ValueError("'clauses' must be a non-empty mapping: " + str(path))
    for clause_id, clause in clauses.items():
        if not isinstance(clause, dict):
            raise ValueError("clause %r must be a mapping: %s" % (clause_id, path))
        if clause.get("id") != clause_id:
            raise ValueError("clause key/id mismatch for %r: %s" % (clause_id, path))
        if not clause.get("title"):
            raise ValueError("clause %r is missing a title: %s" % (clause_id, path))
        checks = clause.get("checks")
        if not isinstance(checks, list) or not checks:
            raise ValueError("clause %r must list at least one check: %s" % (clause_id, path))
        detectors = set()
        for check in checks:
            if not isinstance(check, dict):
                raise ValueError("clause %r has a non-mapping check: %s" % (clause_id, path))
            detector = check.get("detector")
            requirement = check.get("requirement")
            if not detector or not requirement:
                raise ValueError(
                    "clause %r has a check missing 'detector' or 'requirement': %s"
                    % (clause_id, path)
                )
            if detector in detectors:
                raise ValueError(
                    "duplicate detector %r in clause %r: %s" % (detector, clause_id, path)
                )
            detectors.add(detector)


def load_cra_clauses(path=None):
    path = Path(path) if path is not None else DEFAULT_PATH
    if not path.is_file():
        raise FileNotFoundError("clause mapping file not found: " + str(path))
    text = path.read_text(encoding="utf-8")
    try:
        data = _parse_yaml(text)
    except _ParseError as error:
        raise ValueError("invalid YAML in " + str(path) + ": " + str(error))
    if not isinstance(data, dict):
        raise ValueError("clause mapping must contain a mapping: " + str(path))
    _validate(data, path)
    return data


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Load and validate the CRA clause-to-requirement mapping."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="path to cra_clauses.yaml (default: next to this module)",
    )
    args = parser.parse_args(argv)
    path = Path(args.path) if args.path else DEFAULT_PATH
    try:
        data = load_cra_clauses(args.path)
    except Exception as error:
        print("error: " + str(error), file=sys.stderr)
        return 2
    clauses = data["clauses"]
    total_checks = sum(len(clause["checks"]) for clause in clauses.values())
    print("Loaded " + str(len(clauses)) + " clauses / " + str(total_checks) + " checks from " + str(path))
    for clause_id, clause in clauses.items():
        detectors = ", ".join(check["detector"] for check in clause["checks"])
        print("  " + clause_id + ": " + detectors)
    return 0


if __name__ == "__main__":
    sys.exit(main())
