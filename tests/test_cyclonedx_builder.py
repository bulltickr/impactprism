import base64
import hashlib
import json
from datetime import datetime, timezone

import pytest

from cyclonedx.output import OutputFormat
from cyclonedx.schema import SchemaVersion
from cyclonedx.validation import make_schemabased_validator

from impactprism.sbom.cyclonedx_builder import build_cyclonedx_sbom


def assert_valid_sbom(sbom):
    validator = make_schemabased_validator(OutputFormat.JSON, SchemaVersion.V1_6)
    assert validator.validate_str(json.dumps(sbom)) is None


def component_by_purl(sbom, purl):
    return next(component for component in sbom["components"] if component["purl"] == purl)


def properties_by_name(component):
    return {prop["name"]: prop.get("value") for prop in component["properties"]}


def dependencies_by_ref(sbom):
    return {dependency["ref"]: dependency for dependency in sbom["dependencies"]}


def test_header_and_metadata():
    timestamp = "2024-01-02T03:04:05+00:00"
    sbom = build_cyclonedx_sbom(
        [],
        metadata={
            "name": "impactprism-app",
            "version": "2.4.1",
            "tool_name": "dependency-scanner",
            "tool_version": "7.8.9",
            "timestamp": timestamp,
        },
    )

    assert_valid_sbom(sbom)
    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["specVersion"] == "1.6"
    assert sbom["version"] == 1
    assert sbom["metadata"]["component"] == {
        "bom-ref": "impactprism-app@2.4.1",
        "name": "impactprism-app",
        "type": "application",
        "version": "2.4.1",
    }
    assert sbom["metadata"]["tools"] == [
        {
            "vendor": "impactprism",
            "name": "dependency-scanner",
            "version": "7.8.9",
        }
    ]
    assert sbom["metadata"]["timestamp"] == timestamp


def test_components_scopes_and_dependency_properties():
    required_purl = "pkg:pypi/requests@2.31.0"
    optional_purl = "pkg:pypi/urllib3@2.0.0"
    sbom = build_cyclonedx_sbom(
        [
            {
                "name": "requests",
                "version": "2.31.0",
                "purl": required_purl,
                "scope": "required",
                "direct": True,
                "transitive": False,
            },
            {
                "name": "urllib3",
                "version": "2.0.0",
                "purl": optional_purl,
                "scope": "development",
                "direct": False,
                "transitive": True,
            },
        ],
        metadata={"name": "app", "version": "1.0.0"},
    )

    assert_valid_sbom(sbom)
    required = component_by_purl(sbom, required_purl)
    optional = component_by_purl(sbom, optional_purl)
    assert required["name"] == "requests"
    assert required["version"] == "2.31.0"
    assert required["purl"] == required_purl
    assert required["scope"] == "required"
    assert properties_by_name(required) == {
        "impactprism:direct": "true",
        "impactprism:transitive": "false",
        "impactprism:scope": "required",
    }
    assert optional["name"] == "urllib3"
    assert optional["version"] == "2.0.0"
    assert optional["purl"] == optional_purl
    assert optional["scope"] == "optional"
    assert properties_by_name(optional) == {
        "impactprism:direct": "false",
        "impactprism:transitive": "true",
        "impactprism:scope": "development",
    }


def test_valid_hash_is_emitted_and_invalid_hashes_are_dropped():
    valid_purl = "pkg:pypi/valid@1.0.0"
    invalid_purl = "pkg:pypi/invalid@1.0.0"
    unknown_purl = "pkg:pypi/unknown@1.0.0"
    sbom = build_cyclonedx_sbom(
        [
            {
                "name": "valid",
                "version": "1.0.0",
                "purl": valid_purl,
                "direct": True,
                "hashes": [{"alg": "SHA-256", "content": "a" * 64}],
            },
            {
                "name": "invalid",
                "version": "1.0.0",
                "purl": invalid_purl,
                "direct": True,
                "hashes": [{"alg": "SHA-256", "content": "z" * 64}],
            },
            {
                "name": "unknown",
                "version": "1.0.0",
                "purl": unknown_purl,
                "direct": True,
                "hashes": [{"alg": "MD5", "content": "a" * 32}],
            },
        ],
        metadata={"name": "app", "version": "1.0.0"},
    )

    assert_valid_sbom(sbom)
    assert component_by_purl(sbom, valid_purl)["hashes"] == [
        {"alg": "SHA-256", "content": "a" * 64}
    ]
    assert "hashes" not in component_by_purl(sbom, invalid_purl)
    assert "hashes" not in component_by_purl(sbom, unknown_purl)


def test_base64_integrity_is_converted_to_hex_hash():
    digest = hashlib.sha512(b"some-constant").digest()
    b64 = base64.b64encode(digest).decode("ascii")
    purl = "pkg:npm/react@18.3.1"
    sbom = build_cyclonedx_sbom(
        [
            {
                "name": "react",
                "version": "18.3.1",
                "purl": purl,
                "direct": True,
                "hashes": [{"alg": "SHA-512", "content": b64}],
            }
        ],
        metadata={"name": "app", "version": "1.0.0"},
    )

    assert_valid_sbom(sbom)
    assert component_by_purl(sbom, purl)["hashes"] == [
        {"alg": "SHA-512", "content": digest.hex()}
    ]


def test_malformed_base64_hash_is_dropped():
    purl = "pkg:npm/bad@1.0.0"
    sbom = build_cyclonedx_sbom(
        [
            {
                "name": "bad",
                "version": "1.0.0",
                "purl": purl,
                "direct": True,
                "hashes": [{"alg": "SHA-512", "content": "!!!notbase64!!!"}],
            }
        ],
        metadata={"name": "app", "version": "1.0.0"},
    )

    assert_valid_sbom(sbom)
    assert "hashes" not in component_by_purl(sbom, purl)


def test_dependencies_include_component_edges_and_direct_root_edges():
    root_ref = "app@1.0.0"
    first_purl = "pkg:pypi/first@1.0.0"
    second_purl = "pkg:pypi/second@2.0.0"
    third_purl = "pkg:pypi/third@3.0.0"
    sbom = build_cyclonedx_sbom(
        [
            {
                "name": "first",
                "version": "1.0.0",
                "purl": first_purl,
                "direct": True,
                "depends_on": [second_purl, third_purl],
            },
            {
                "name": "second",
                "version": "2.0.0",
                "purl": second_purl,
                "direct": False,
            },
            {
                "name": "third",
                "version": "3.0.0",
                "purl": third_purl,
                "direct": True,
                "depends_on": [second_purl],
            },
        ],
        metadata={"name": "app", "version": "1.0.0"},
    )

    assert_valid_sbom(sbom)
    dependencies = dependencies_by_ref(sbom)
    assert dependencies[first_purl]["dependsOn"] == [second_purl, third_purl]
    assert dependencies[third_purl]["dependsOn"] == [second_purl]
    assert dependencies[second_purl] == {"ref": second_purl}
    assert dependencies[root_ref]["dependsOn"] == [first_purl, third_purl]


def test_components_without_valid_purls_are_skipped():
    valid_purl = "pkg:pypi/valid@1.0.0"
    sbom = build_cyclonedx_sbom(
        [
            {"name": "missing", "version": "1.0.0"},
            {"name": "non-string", "version": "1.0.0", "purl": 42},
            {"name": "not-a-purl", "version": "1.0.0", "purl": "not-a-purl"},
            {"name": "http", "version": "1.0.0", "purl": "http://x"},
            {
                "name": "valid",
                "version": "1.0.0",
                "purl": valid_purl,
                "direct": True,
            },
        ],
        metadata={"name": "app", "version": "1.0.0"},
    )

    assert_valid_sbom(sbom)
    assert [component["purl"] for component in sbom["components"]] == [valid_purl]


def test_empty_components_produces_only_root_dependency():
    root_ref = "app@1.0.0"
    sbom = build_cyclonedx_sbom(
        [], metadata={"name": "app", "version": "1.0.0"}
    )

    assert_valid_sbom(sbom)
    assert sbom.get("components", []) == []
    assert sbom["dependencies"] == [{"ref": root_ref}]


def test_components_without_direct_dependency_raise_clear_graph_error():
    with pytest.raises(ValueError, match="at least one component must be marked direct"):
        build_cyclonedx_sbom(
            [
                {
                    "name": "transitive",
                    "version": "1.0.0",
                    "purl": "pkg:pypi/transitive@1.0.0",
                    "direct": False,
                }
            ],
            metadata={"name": "app", "version": "1.0.0"},
        )


def test_missing_timestamp_defaults_to_current_utc_time():
    before = datetime.now(timezone.utc)
    sbom = build_cyclonedx_sbom(
        [], metadata={"name": "app", "version": "1.0.0", "timestamp": None}
    )
    after = datetime.now(timezone.utc)

    assert_valid_sbom(sbom)
    timestamp = datetime.fromisoformat(sbom["metadata"]["timestamp"])
    assert before <= timestamp <= after
    assert timestamp.tzinfo is not None


def test_schema_validation_failure_raises_value_error():
    with pytest.raises(ValueError):
        build_cyclonedx_sbom(
            [], metadata={"name": None, "version": "1.0.0"}
        )
