#!/usr/bin/env python3
import json
import pathlib
import ast
import os
import xml.etree.ElementTree as ET
import sys

# --- Load model from JSON instead of YAML ---
model = json.load(open("architecture.json", encoding="utf-8"))
layers_rules = {
    layer_name: data["allowed"]
    for layer_name, data in model["logical"]["layers"].items()
}
comp_map = {
    comp["folder"]: comp["layer"]
    for comp in model["development"]["components"]
}

def layer_of(path: pathlib.Path) -> str:
    rel = str(path).replace("\\", "/")
    for pattern, layer in comp_map.items():
        if pathlib.Path(rel).match(pattern):
            return layer
    return "Unknown"

deps = []
violations = []

# Search all .py files under project root
for py in pathlib.Path(".").rglob("*.py"):
    if py.name == "analyzer.py":
        continue

    src_layer = layer_of(py)
    tree = ast.parse(py.read_text(encoding="utf-8"))

    # capture both import and from-import statements
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module.split(".")[-1])

    for imp in imports:
        tgt_path = py.with_name(imp + ".py")
        tgt_layer = layer_of(tgt_path)
        deps.append((src_layer, tgt_layer, py.name, imp))
        if tgt_layer not in layers_rules.get(src_layer, []):
            violations.append((src_layer, tgt_layer, py.name, imp))

# Console output
print(f"[ArchGuard] Analyzed {len(deps)} import edges")
exit_code = 0
if violations:
    print(f"[ArchGuard] FAIL: {len(violations)} violations found")
    for v in violations:
        print(f"   FAIL: {v[2]} ({v[0]}) -> {v[3]} ({v[1]})")
    exit_code = 1
else:
    print("[ArchGuard] PASS: No violations found")

# Generate JUnit XML
os.makedirs("tests-results", exist_ok=True)
suite = ET.Element(
    "testsuite",
    name="ArchGuard",
    tests=str(len(deps) if deps else 1),
    failures=str(len(violations))
)
for d in deps:
    case = ET.SubElement(
        suite, "testcase", classname=d[0], name=f"{d[2]} -> {d[3]}"
    )
    if d in violations:
        fail = ET.SubElement(case, "failure", message="Layer breach")
        fail.text = f"{d[2]} imports {d[3]} ({d[0]}->{d[1]} not allowed)"
if not deps:
    ET.SubElement(suite, "testcase", classname="ArchGuard", name="no-imports")
ET.ElementTree(suite).write("tests-results/archguard.xml", encoding="utf-8")

# HTML report with Mermaid, explanation and remediation suggestions
html_lines = [
    "<!DOCTYPE html>",
    "<html lang=\"en\">",
    "<head>",
    "  <meta charset=\"utf-8\">",
    "  <title>ArchGuard Report</title>",
    "  <script src=\"https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js\"></script>",
    "  <script>mermaid.initialize({ startOnLoad: true });</script>",
    "  <style>",
    "    body { font-family: sans-serif; padding: 1rem; }",
    "    pre.mermaid { background: #f9f9f9; padding: 1rem; border-radius: 4px; }",
    "  </style>",
    "</head>",
    "<body>",
    "  <h2>ArchGuard Report</h2>",
    "  <h3>Violation Details</h3>",
]

if violations:
    html_lines += [
        "  <p>The following architectural violations were found:</p>",
        "  <ul>",
    ]
    for src, tgt, fname, imp in violations:
        html_lines.append(
            f"    <li>The file <b>{fname}</b> in layer <i>{src}</i> imports "
            f"<b>{imp}.py</b> in layer <i>{tgt}</i>, which is not allowed by the model.</li>"
        )
    html_lines.append("  </ul>")
else:
    html_lines.append(
        "  <p>No violations found — all dependencies comply with the model.</p>"
    )

# Remediation Suggestions
html_lines += [
    "  <h3>Remediation Suggestions</h3>",
]
if violations:
    html_lines.append("  <ul>")
    for src, tgt, fname, imp in violations:
        allowed = layers_rules.get(src, [])
        html_lines.append(
            f"    <li>In <b>{fname}</b> ({src}), only imports to layers "
            f"<i>{', '.join(allowed)}</i> are allowed. Please adjust your import.</li>"
        )
    html_lines.append("  </ul>")
else:
    html_lines.append("  <p>—</p>")

# Detailed overview and dependency graph
html_lines += [
    "  <h3>Detailed Overview</h3>",
    "  <pre>",
]
for d in deps:
    mark = "FAIL" if d in violations else "PASS"
    html_lines.append(f"    {mark} {d[2]} -> {d[3]} ({d[0]}->{d[1]})")
html_lines += [
    "  </pre>",
    "  <h3>Dependency Graph</h3>",
    "  <pre class=\"mermaid\">",
    "    graph LR",
]
for src, tgt, fname, imp in deps:
    html_lines.append(
        f"    {fname}[\"{fname}\\n({src})\"] --> {imp}[\"{imp}\\n({tgt})\"]"
    )
html_lines += [
    "  </pre>",
    "</body>",
    "</html>",
]

with open("archguard_report.html", "w", encoding="utf-8") as f:
    f.write("\n".join(html_lines))

sys.exit(exit_code)
