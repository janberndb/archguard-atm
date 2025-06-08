#!/usr/bin/env python3
import json
import pathlib
import ast
import os
import xml.etree.ElementTree as ET
import sys

# --- Modell laden von JSON statt YAML ---
model = json.load(open("architecture.json"))
layers_rules = {k: v['allowed'] for k, v in model['logical']['layers'].items()}
comp_map = {c['folder']: c['layer'] for c in model['development']['components']}

def layer_of(path):
    rel = str(path).replace('\\', '/')
    for pattern, layer in comp_map.items():
        if pathlib.Path(rel).match(pattern):
            return layer
    return "Unknown"

deps = []
violations = []

for py in pathlib.Path("atm").rglob("*.py"):
    tree = ast.parse(open(py, encoding="utf-8").read())
    imports = []
    # erfasse sowohl "import foo" als auch "from foo.bar import Baz"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module.split('.')[0])

    src_layer = layer_of(py)
    for imp in imports:
        tgt_path = py.with_name(imp + ".py")
        tgt_layer = layer_of(tgt_path)
        deps.append((src_layer, tgt_layer, py.name, imp))
        if tgt_layer not in layers_rules.get(src_layer, []):
            violations.append((src_layer, tgt_layer, py.name, imp))

# Konsolenausgabe
print(f"[ArchGuard] Analysierte {len(deps)} Import-Kanten")
if violations:
    print(f"[ArchGuard] FAIL: {len(violations)} Verstöße gefunden")
    for v in violations:
        print(f"   FAIL: {v[2]} ({v[0]}) -> {v[3]} ({v[1]})")
    exit_code = 1
else:
    print("[ArchGuard] PASS: Keine Verstöße gefunden")
    exit_code = 0

# JUnit-kompatible XML-Ausgabe
os.makedirs("tests-results", exist_ok=True)
suite = ET.Element(
    "testsuite",
    name="ArchGuard",
    tests=str(len(deps) if len(deps) > 0 else 1),
    failures=str(len(violations))
)

# echte Testfälle
for d in deps:
    case = ET.SubElement(suite, "testcase", classname=d[0], name=f"{d[2]} -> {d[3]}")
    if d in violations:
        fail = ET.SubElement(case, "failure", message="Layer breach")
        fail.text = f"{d[2]} imports {d[3]} ({d[0]}→{d[1]} not allowed)"

# Dummy-Testcase, falls keine Imports gefunden wurden
if len(deps) == 0:
    ET.SubElement(suite, "testcase", classname="ArchGuard", name="no-imports")

ET.ElementTree(suite).write("tests-results/archguard.xml")

# HTML-Report mit Mermaid-Graph
html = ["<h2>ArchGuard Report</h2>", "<pre>"]
for d in deps:
    mark = "FAIL" if d in violations else "PASS"
    html.append(f"{mark} {d[2]} → {d[3]} ({d[0]}→{d[1]})")
html += ["</pre>", "<h3>Dependency graph</h3>", "<pre class='mermaid'>graph LR"]
for d in deps:
    html.append(f'{d[2]}["{d[2]}\\n({d[0]})"] --> {d[3]}["{d[3]}\\n({d[1]})"]')
html.append("</pre>")
open("archguard_report.html", "w", encoding="utf-8").write("\n".join(html))

sys.exit(exit_code)
