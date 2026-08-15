from __future__ import annotations

import html
import json
import os
import subprocess
import sys
from pathlib import Path

from rich.console import Console


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
PYTHON = sys.executable


def run_real_scan() -> tuple[str, int]:
    report = OUT / "scan-report.json"
    evidence_json = OUT / "scan-evidence.json"
    command = [
        PYTHON,
        "main.py",
        "scan",
        "demo/npm-app",
        "--report",
        str(report),
        "--evidence",
        str(evidence_json),
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )

    console = Console(record=True, width=112, color_system="truecolor")
    console.print("[bold #7dd3fc]$[/] python main.py scan demo/npm-app --report docs/screenshots/scan-report.json --evidence docs/screenshots/scan-evidence.json")
    console.print(result.stdout, end="")
    console.print(f"\n[bold]Process exited with code[/] {result.returncode}")
    console.print("[dim]Transcript captured from the repository CLI; findings are not mocked.[/]")
    transcript = console.export_text(styles=False, clear=False)
    (OUT / "scan-terminal.txt").write_text(transcript, encoding="utf-8")

    # Re-run the evidence generator from the actual scan report so the Markdown
    # shown in the screenshots is the same artifact the workflow would upload.
    subprocess.run(
        [
            PYTHON,
            "main.py",
            "evidence",
            str(report),
            "--markdown",
            str(OUT / "evidence.md"),
            "--json",
            str(OUT / "evidence.json"),
        ],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return transcript, result.returncode


def md_to_html(markdown: str) -> str:
    lines = markdown.splitlines()
    out: list[str] = []
    in_table = False
    in_list = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    for line in lines:
        if line.startswith("| "):
            close_list()
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if all(set(cell) <= {"-", " "} for cell in cells):
                continue
            if not in_table:
                out.append("<table><thead><tr>" + "".join(f"<th>{html.escape(cell)}</th>" for cell in cells) + "</tr></thead><tbody>")
                in_table = True
            else:
                out.append("<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in cells) + "</tr>")
            continue
        if in_table:
            out.append("</tbody></table>")
            in_table = False
        if line.startswith("### "):
            close_list()
            title = html.escape(line[4:])
            out.append(f"<h3>{title}</h3>")
        elif line.startswith("## "):
            close_list()
            out.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("# "):
            close_list()
            out.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            item = html.escape(line[2:])
            if ": " in item:
                key, value = item.split(": ", 1)
                item = f"<strong>{key}:</strong> {value}"
            out.append(f"<li>{item}</li>")
        elif line.strip() == "":
            close_list()
        else:
            close_list()
            text = html.escape(line)
            if text.startswith("Status: "):
                text = '<span class="status">' + text + "</span>"
            elif text.startswith("CRA clauses: "):
                text = '<span class="clauses">' + text + "</span>"
            out.append(f"<p>{text}</p>")
    close_list()
    if in_table:
        out.append("</tbody></table>")
    return "\n".join(out)


BASE_CSS = """
* { box-sizing: border-box; }
html, body { margin: 0; background: #f6f8fa; color: #1f2328; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
body { padding: 36px; }
.shell { max-width: 1100px; margin: 0 auto; }
.eyebrow { color: #57606a; font-size: 12px; font-weight: 700; letter-spacing: .11em; text-transform: uppercase; margin-bottom: 9px; }
.title { font-size: 28px; line-height: 1.15; margin: 0; letter-spacing: -.02em; }
.subtitle { color: #57606a; font-size: 14px; margin: 10px 0 24px; }
.card { background: #fff; border: 1px solid #d0d7de; border-radius: 10px; box-shadow: 0 2px 6px rgba(31,35,40,.06); }
.terminal { background: #0d1117; border: 1px solid #30363d; border-radius: 12px; overflow: hidden; box-shadow: 0 16px 32px rgba(31,35,40,.14); }
.terminal-bar { background: #161b22; color: #8b949e; padding: 11px 16px; font-size: 12px; border-bottom: 1px solid #30363d; }
.dots { display: inline-flex; gap: 6px; margin-right: 10px; vertical-align: -1px; }
.dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; background: #484f58; }
pre { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; }
.terminal pre { padding: 22px 24px 26px; color: #e6edf3; font: 14px/1.65 "Cascadia Mono", Consolas, "SFMono-Regular", monospace; }
.terminal pre::first-line { color: #7dd3fc; }
.legend { padding: 13px 24px; background: #161b22; border-top: 1px solid #30363d; color: #8b949e; font-size: 12px; }
.markdown-body { padding: 34px 42px; }
.markdown-body h1 { font-size: 27px; border-bottom: 1px solid #d8dee4; padding-bottom: 14px; margin: 0 0 20px; }
.markdown-body h2 { font-size: 20px; margin: 28px 0 13px; padding-bottom: 7px; border-bottom: 1px solid #d8dee4; }
.markdown-body h3 { font-size: 16px; margin: 22px 0 8px; }
.markdown-body p, .markdown-body li { font-size: 13px; line-height: 1.55; }
.markdown-body ul { padding-left: 25px; margin: 8px 0 14px; }
.markdown-body strong { color: #24292f; }
.markdown-body .status { display: inline-block; color: #9a6700; background: #fff8c5; border: 1px solid #d4a72c; padding: 3px 8px; border-radius: 999px; font-weight: 700; font-size: 12px; }
.markdown-body .clauses { color: #57606a; font-size: 12px; }
table { width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 12px; }
th, td { text-align: left; padding: 8px 10px; border: 1px solid #d0d7de; }
th { background: #f6f8fa; font-weight: 700; }
.pr-header { background: #fff; border-bottom: 1px solid #d0d7de; padding: 20px 36px 18px; margin: -36px -36px 28px; }
.pr-kicker { color: #57606a; font-size: 12px; margin-bottom: 8px; }
.pr-title { font-size: 23px; margin: 0; }
.pr-meta { color: #57606a; margin-top: 7px; font-size: 13px; }
.status-strip { display: flex; gap: 12px; align-items: center; background: #fff; border: 1px solid #d0d7de; border-radius: 8px; padding: 12px 16px; margin-bottom: 16px; font-size: 13px; }
.failure { color: #cf222e; font-weight: 700; }
.comment { background: #fff; border: 1px solid #d0d7de; border-radius: 8px; overflow: hidden; }
.comment-head { padding: 13px 16px; border-bottom: 1px solid #d8dee4; font-size: 13px; }
.avatar { display: inline-flex; width: 24px; height: 24px; border-radius: 50%; align-items: center; justify-content: center; background: #24292f; color: #fff; font-size: 11px; font-weight: 700; margin-right: 7px; vertical-align: -7px; }
.bot { font-weight: 700; }
.bot-badge { color: #57606a; border: 1px solid #d0d7de; padding: 1px 5px; border-radius: 5px; font-size: 11px; margin-left: 4px; }
.comment-time { color: #57606a; margin-left: 6px; }
.comment-body { padding: 24px 28px 27px; }
.comment-body .markdown-body { padding: 0; }
.local-note { color: #57606a; font-size: 11px; margin-top: 14px; }
.code-card { background: #0d1117; border: 1px solid #30363d; border-radius: 11px; overflow: hidden; }
.code-head { background: #161b22; color: #8b949e; padding: 12px 16px; font-size: 12px; border-bottom: 1px solid #30363d; display: flex; justify-content: space-between; }
.code-body { padding: 22px 24px; color: #e6edf3; font: 13px/1.6 "Cascadia Mono", Consolas, monospace; }
.json-key { color: #79c0ff; }.json-string { color: #a5d6ff; }.json-number { color: #d2a8ff; }.json-label { color: #8b949e; }
.facts { display: flex; gap: 10px; flex-wrap: wrap; margin: 18px 0 22px; }
.fact { background: #fff; border: 1px solid #d0d7de; border-radius: 7px; padding: 8px 11px; color: #57606a; font-size: 12px; }
.fact strong { color: #1f2328; font-size: 13px; margin-right: 4px; }
"""


def page(title: str, body: str) -> str:
    return f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title><style>{BASE_CSS}</style></head><body>{body}</body></html>"


def write_html(transcript: str, report: dict, evidence_md: str) -> list[Path]:
    evidence_html = md_to_html(evidence_md)
    terminal_body = f"""
    <main class='shell'>
      <div class='eyebrow'>ImpactPrism · real CLI capture</div>
      <h1 class='title'>Dependency scan with findings</h1>
      <p class='subtitle'>The command below was executed against <code>demo/npm-app</code> in this repository.</p>
      <section class='terminal'>
        <div class='terminal-bar'><span class='dots'><i class='dot'></i><i class='dot'></i><i class='dot'></i></span>impactprism / scan</div>
        <pre>{html.escape(transcript)}</pre>
        <div class='legend'>Exit 1 is expected here: the fixture intentionally contains drift and an undeclared import.</div>
      </section>
    </main>"""

    evidence_body = f"""
    <main class='shell'>
      <div class='eyebrow'>ImpactPrism · rendered artifact</div>
      <h1 class='title'>Evidence pack Markdown</h1>
      <p class='subtitle'>Rendered from <code>docs/screenshots/evidence.md</code>, generated by the real evidence command.</p>
      <section class='card markdown-body'>{evidence_html}</section>
    </main>"""

    pr_body = f"""
    <main class='shell'>
      <div class='pr-header'>
        <div class='pr-kicker'>Pull request · local rendering of the repository workflow</div>
        <h1 class='pr-title'>CRA dependency check evidence</h1>
        <div class='pr-meta'>impactprism-demo · pull request validation</div>
      </div>
      <div class='status-strip'><span class='failure'>● CRA check failed</span><span>1 finding set requiring review · workflow exit code 1</span></div>
      <section class='comment'>
        <div class='comment-head'><span class='avatar'>CI</span><span class='bot'>github-actions</span><span class='bot-badge'>bot</span><span class='comment-time'>posted by the workflow</span></div>
        <div class='comment-body'><div class='markdown-body'>{evidence_html}</div><div class='local-note'>Local render of the Markdown body posted by <code>.github/workflows/cra-check.yml</code>; no live GitHub comment is claimed.</div></div>
      </section>
    </main>"""

    sbom = report["sbom"]
    component = sbom["components"][0]
    snippet = {
        "bomFormat": sbom["bomFormat"],
        "specVersion": sbom["specVersion"],
        "metadata": {
            "component": sbom["metadata"]["component"],
            "tools": sbom["metadata"]["tools"],
        },
        "components": [
            {
                "type": component["type"],
                "name": component["name"],
                "version": component["version"],
                "purl": component["purl"],
                "scope": component["scope"],
            }
        ],
    }
    snippet_html = html.escape(json.dumps(snippet, indent=2))
    for token in ["bomFormat", "specVersion", "metadata", "component", "tools", "components", "type", "name", "version", "purl", "scope"]:
        snippet_html = snippet_html.replace(f'&quot;{token}&quot;', f'<span class="json-key">&quot;{token}&quot;</span>')
    sbom_body = f"""
    <main class='shell'>
      <div class='eyebrow'>ImpactPrism · CycloneDX output</div>
      <h1 class='title'>Sample SBOM snippet</h1>
      <p class='subtitle'>A compact excerpt from the SBOM generated by the same scan; values are taken from the real report.</p>
      <div class='facts'><div class='fact'><strong>{html.escape(sbom['bomFormat'])}</strong> {html.escape(sbom['specVersion'])}</div><div class='fact'><strong>1</strong> component</div><div class='fact'><strong>required</strong> scope</div></div>
      <section class='code-card'><div class='code-head'><span>scan-report.json · sbom</span><span>generated by impactprism-cyclonedx</span></div><pre class='code-body'>{snippet_html}</pre></section>
    </main>"""

    pages = {
        "terminal.html": page("ImpactPrism scan terminal", terminal_body),
        "evidence-pack.html": page("ImpactPrism evidence pack", evidence_body),
        "github-action-pr-comment.html": page("ImpactPrism GitHub Action comment", pr_body),
        "sbom-snippet.html": page("ImpactPrism SBOM snippet", sbom_body),
    }
    paths = []
    for name, content in pages.items():
        path = OUT / name
        path.write_text(content, encoding="utf-8")
        paths.append(path)
    return paths


def main() -> None:
    transcript, _ = run_real_scan()
    report = json.loads((OUT / "scan-report.json").read_text(encoding="utf-8"))
    evidence_md = (OUT / "evidence.md").read_text(encoding="utf-8")
    write_html(transcript, report, evidence_md)


if __name__ == "__main__":
    main()
