# Hard-case coverage contract

ImpactPrism performs bounded static analysis. This page records the repository
shapes that are explicitly exercised by the reviewed correctness fixtures and
the boundary that remains intentionally visible.

## Covered in the correctness matrix

- npm workspaces with package-local manifests and a root lockfile;
- pnpm workspaces declared in `pnpm-workspace.yaml`, including exclusion globs;
- npm workspace package `exports` and package-local `imports` aliases;
- static TypeScript `paths`/`baseUrl` aliases, including JSONC comments;
- repository-local relative TypeScript `extends` chains whose inherited
  `paths`/`baseUrl` values remain relative to their declaring config;
- literal Vite and webpack-style `resolve.alias` objects/arrays, including
  simple `path.resolve(__dirname, ...)` targets;
- a Vite alias array in a standalone app and a webpack alias wildcard inside
  an npm workspace with nested `apps/` and `packages/` roots;
- a governed dynamic-bundler boundary case proving function-generated alias
  configuration is neither executed nor guessed as a local target;
- a clean Go `go.work` repository with two independently managed modules and a
  local workspace dependency;
- npm workspaces containing literal dynamic imports;
- checked-in generated JavaScript that contributes a package import;
- Python literal `importlib.import_module("package")` and explicitly imported
  `import_module("package")` usage; and
- checked-in generated Python that contributes a package import.

These cases test parser and manifest ownership behavior. A passing fixture
means the expected normalized output is stable for that fixture; it does not
mean all workspaces, bundlers, generators, or runtime loaders are supported.

## Dynamic-resolution boundary

Literal dynamic imports are treated as source usage because the package name
is present in the source text. Python's qualified `importlib.import_module`
call and an explicitly imported `import_module` alias are recognized.
Non-literal forms such as `import(variable)`, `__import__(name)`, or
`importlib.import_module(name)` are not executed and do not become guessed
package findings. This avoids running untrusted repository code and avoids
presenting a guess as an observation.

Repositories that rely on runtime-only resolution should treat the scan as an
incomplete dependency-integrity signal and review that gap separately. The
scanner does not claim that a clean result proves runtime dependency
completeness.

Static local aliases and workspace package exports are resolved only when the
configured target can be verified from the checkout. A missing target or a
workspace subpath excluded by `exports` becomes an `UNRESOLVED_IMPORT` finding.
Bundler configuration files are not executed, and arbitrary JavaScript alias
logic remains outside the supported resolution boundary. The supported bundler
subset is deliberately limited to literal alias data; plugin-provided aliases,
regular expressions, environment-dependent values, and function-generated
configuration remain unresolved evidence gaps. The correctness matrix includes
an intentionally throwing function-generated alias to keep this non-execution
boundary regression-tested.

TypeScript config inheritance is limited to relative JSON/JSONC files inside the
checkout. Node-style package-based `extends` resolution, circular or malformed
chains, and project-reference build outputs remain outside the static resolver
boundary; the scanner does not install packages or run `tsc` to reconstruct
those paths.

## Generated-source boundary

Checked-in source under `generated/` is scanned by default because it is part
of the repository tree presented to the analyzer. A repository may explicitly
exclude a generated directory through the CLI or Action exclusion controls,
but that choice changes the evidence boundary and should be documented in the
review record.

The scanner never runs a generator, installs generated dependencies, or
reconstructs source that is absent from the checkout.

## Why this is separate from G2

These are small, reviewed regression fixtures. They are not a representative
sample and do not provide precision, recall, false-positive, or false-negative
rates. The governed G2 benchmark remains blocked until its independently
defined corpus, labels, adjudication, environment, and result bundle exist.
