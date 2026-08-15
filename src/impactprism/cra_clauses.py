import argparse
import sys
from pathlib import Path

import yaml


DEFAULT_PATH = Path(__file__).resolve().with_name("cra_clauses.yaml")
EXPECTED_SCHEMA_VERSION = 2


class _UniqueKeyLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise ValueError("duplicate key %r in mapping" % (key,))
            seen.add(key)
        return super().construct_mapping(node, deep=True)


def _validate(data, path):
    if data.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        raise ValueError("unsupported schema_version in " + str(path))
    if not data.get("map_version"):
        raise ValueError("'map_version' must be a non-empty string: " + str(path))
    if not data.get("legal_source"):
        raise ValueError("'legal_source' must be a non-empty string: " + str(path))
    if not data.get("description"):
        raise ValueError("'description' must be a non-empty string: " + str(path))
    clauses = data.get("clauses")
    if not isinstance(clauses, dict) or not clauses:
        raise ValueError("'clauses' must be a non-empty mapping: " + str(path))
    for clause_id, clause in clauses.items():
        if not isinstance(clause, dict):
            raise ValueError("clause %r must be a mapping: %s" % (clause_id, path))
        if clause.get("id") != clause_id:
            raise ValueError("clause key/id mismatch for %r: %s" % (clause_id, path))
        if not clause.get("legal_reference"):
            raise ValueError("clause %r is missing 'legal_reference': %s" % (clause_id, path))
        if not clause.get("title"):
            raise ValueError("clause %r is missing a title: %s" % (clause_id, path))
        if not clause.get("applicability"):
            raise ValueError("clause %r is missing 'applicability': %s" % (clause_id, path))
        detectors = clause.get("detectors")
        if not isinstance(detectors, list) or not detectors:
            raise ValueError(
                "clause %r must list at least one detector: %s" % (clause_id, path)
            )
        if any(not isinstance(detector, str) or not detector for detector in detectors):
            raise ValueError(
                "clause %r has an empty detector entry: %s" % (clause_id, path)
            )
        if len(detectors) != len(set(detectors)):
            raise ValueError(
                "duplicate detector in clause %r: %s" % (clause_id, path)
            )
        evidence_requirements = clause.get("evidence_requirements")
        if not isinstance(evidence_requirements, list) or not evidence_requirements:
            raise ValueError(
                "clause %r must list at least one evidence requirement: %s"
                % (clause_id, path)
            )
        if any(
            not isinstance(requirement, str) or not requirement
            for requirement in evidence_requirements
        ):
            raise ValueError(
                "clause %r has an empty evidence requirement: %s" % (clause_id, path)
            )
        limitations = clause.get("limitations")
        if not isinstance(limitations, list):
            raise ValueError(
                "clause %r must have a 'limitations' list: %s" % (clause_id, path)
            )
        if any(not isinstance(limitation, str) for limitation in limitations):
            raise ValueError(
                "clause %r has a non-string limitation: %s" % (clause_id, path)
            )
        status = clause.get("status")
        if status not in ("ACTIVE", "PLANNED", "DEPRECATED"):
            raise ValueError(
                "clause %r has invalid status %r: %s" % (clause_id, status, path)
            )
    categories = data.get("categories")
    if categories is not None:
        if not isinstance(categories, dict) or not categories:
            raise ValueError(
                "'categories' must be a non-empty mapping when present: " + str(path)
            )
        for category, entry in categories.items():
            if not isinstance(entry, dict):
                raise ValueError(
                    "category %r must be a mapping: %s" % (category, path)
                )
            category_clauses = entry.get("clauses")
            if (
                not isinstance(category_clauses, list)
                or not category_clauses
                or any(
                    not isinstance(clause_id, str) or not clause_id
                    for clause_id in category_clauses
                )
            ):
                raise ValueError(
                    "category %r must list at least one non-empty clause id: %s"
                    % (category, path)
                )
            unknown = [
                clause_id for clause_id in category_clauses if clause_id not in clauses
            ]
            if unknown:
                raise ValueError(
                    "category %r references unknown clause(s) %r: %s"
                    % (category, unknown, path)
                )


def load_cra_clauses(path=None):
    path = Path(path) if path is not None else DEFAULT_PATH
    if not path.is_file():
        raise FileNotFoundError("clause mapping file not found: " + str(path))
    text = path.read_text(encoding="utf-8")
    try:
        data = yaml.load(text, Loader=_UniqueKeyLoader)
    except (yaml.YAMLError, ValueError) as error:
        raise ValueError("invalid YAML in " + str(path) + ": " + str(error))
    if not isinstance(data, dict):
        raise ValueError("clause mapping must contain a mapping: " + str(path))
    _validate(data, path)
    return data


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Load and validate the versioned CRA clause-to-evidence mapping."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="path to the CRA clause map YAML (default: next to this module)",
    )
    args = parser.parse_args(argv)
    path = Path(args.path) if args.path else DEFAULT_PATH
    try:
        data = load_cra_clauses(args.path)
    except Exception as error:
        print("error: " + str(error), file=sys.stderr)
        return 2
    clauses = data["clauses"]
    total_detectors = sum(len(clause["detectors"]) for clause in clauses.values())
    print(
        "Loaded "
        + str(len(clauses))
        + " clauses / "
        + str(total_detectors)
        + " detectors from "
        + str(path)
    )
    print(
        "  schema: "
        + str(data["schema_version"])
        + " / map: "
        + data["map_version"]
    )
    print("  legal source: " + data["legal_source"])
    for clause_id, clause in clauses.items():
        print("  " + clause_id + ": " + ", ".join(clause["detectors"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
