from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime, timezone

try:
    from cyclonedx.model import BomRef, HashAlgorithm, HashType, Property
    from cyclonedx.model.bom import Bom, BomMetaData, Dependency, Tool
    from cyclonedx.model.component import Component, ComponentScope, ComponentType
    from cyclonedx.output import OutputFormat, make_outputter
    from cyclonedx.schema import SchemaVersion
    from cyclonedx.validation import make_schemabased_validator
    from packageurl import PackageURL
except ImportError as exc:
    raise ImportError(
        "cyclonedx-python-lib[validation] is required to build CycloneDX SBOMs"
    ) from exc


_HASH_ALGORITHMS = {
    "SHA-1": HashAlgorithm.SHA_1,
    "SHA-256": HashAlgorithm.SHA_256,
    "SHA-384": HashAlgorithm.SHA_384,
    "SHA-512": HashAlgorithm.SHA_512,
}

_HASH_DIGEST_LENGTHS = {
    "SHA-1": 20,
    "SHA-256": 32,
    "SHA-384": 48,
    "SHA-512": 64,
}


def _timestamp(value: str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _hashes(values: object) -> list[HashType]:
    if not isinstance(values, list):
        return []

    result = []
    for value in values:
        if not isinstance(value, dict):
            continue
        algorithm = _HASH_ALGORITHMS.get(value.get("alg"))
        expected_length = _HASH_DIGEST_LENGTHS.get(value.get("alg"))
        content = value.get("content")
        if (
            algorithm is None
            or expected_length is None
            or not isinstance(content, str)
            or not content
        ):
            continue
        try:
            if all(character in "0123456789abcdefABCDEF" for character in content):
                decoded = bytes.fromhex(content)
                if len(decoded) == expected_length:
                    result.append(HashType(alg=algorithm, content=content.lower()))
                    continue
            decoded = base64.b64decode(content, validate=True)
            if len(decoded) == expected_length:
                result.append(
                    HashType(
                        alg=algorithm,
                        content=binascii.hexlify(decoded).decode("ascii").lower(),
                    )
                )
        except Exception:
            continue
    return result


def build_cyclonedx_sbom(
    components: list[dict], *, metadata: dict | None = None
) -> dict:
    metadata = metadata or {}
    name = metadata.get("name", "unknown")
    version = metadata.get("version", "0.0.0")
    tool_name = metadata.get("tool_name", "impactprism-cyclonedx")
    tool_version = metadata.get("tool_version", "0.1.0")
    root_ref = BomRef(f"{name}@{version}")
    root_component = Component(
        type=ComponentType.APPLICATION,
        name=name,
        version=version,
        bom_ref=root_ref,
    )
    bom_components = []
    component_items = []
    emitted_refs = set()
    dependencies = []
    direct_refs = []

    for item in components:
        purl = item.get("purl")
        if not isinstance(purl, str):
            continue
        try:
            package_url = PackageURL.from_string(purl)
        except (TypeError, ValueError):
            continue
        if purl in emitted_refs:
            continue

        scope = item.get("scope")
        component = Component(
            type=ComponentType.LIBRARY,
            group=package_url.namespace,
            name=package_url.name,
            version=item["version"],
            bom_ref=purl,
            purl=package_url,
            hashes=_hashes(item.get("hashes")),
            scope=(
                ComponentScope.REQUIRED
                if scope == "required"
                else ComponentScope.OPTIONAL
            ),
            properties=[
                Property(
                    name="impactprism:direct",
                    value="true" if item.get("direct") else "false",
                ),
                Property(
                    name="impactprism:transitive",
                    value="true" if item.get("transitive") else "false",
                ),
                Property(name="impactprism:scope", value=scope),
            ],
        )
        bom_components.append(component)
        emitted_refs.add(purl)
        component_items.append((purl, item))

    dependency_orders = {}
    for purl, item in component_items:
        component_ref = BomRef(purl)
        child_purls = item.get("depends_on")
        child_refs = []
        if isinstance(child_purls, list):
            seen_child_refs = set()
            for child in child_purls:
                if not isinstance(child, str):
                    continue
                if child != str(root_ref) and child not in emitted_refs:
                    continue
                if child in seen_child_refs:
                    continue
                seen_child_refs.add(child)
                child_refs.append(child)
            dependency_orders[purl] = child_refs
        child_dependencies = [
            Dependency(ref=BomRef(child)) for child in child_refs
        ]
        dependencies.append(
            Dependency(ref=component_ref, dependencies=child_dependencies)
        )
        if item.get("direct") is True:
            direct_refs.append(Dependency(ref=component_ref))

    if bom_components and not direct_refs:
        raise ValueError(
            "Cannot build a complete dependency graph: at least one component "
            "must be marked direct"
        )

    dependencies.append(Dependency(ref=root_ref, dependencies=direct_refs))
    bom = Bom(
        metadata=BomMetaData(
            timestamp=_timestamp(metadata.get("timestamp")),
            tools=[Tool(vendor="impactprism", name=tool_name, version=tool_version)],
            component=root_component,
        ),
        components=bom_components,
        dependencies=dependencies,
    )
    outputter = make_outputter(
        bom=bom,
        output_format=OutputFormat.JSON,
        schema_version=SchemaVersion.V1_6,
    )
    output = outputter.output_as_string()
    validator = make_schemabased_validator(OutputFormat.JSON, SchemaVersion.V1_6)
    error = validator.validate_str(output)
    if error is not None:
        raise ValueError(error)
    sbom = json.loads(output)
    for dependency in sbom.get("dependencies", []):
        ref = dependency.get("ref")
        if ref in dependency_orders:
            dependency["dependsOn"] = dependency_orders[ref]
    return sbom
