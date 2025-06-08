#!/usr/bin/env python3
import json
import pathlib
import ast
import os
import xml.etree.ElementTree as ET
import sys

# --- Modell laden von JSON (UTF-8) ---
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

# Alle .py-Dateien im Verzeichnis atm/ scannen
for py in pathlib.Path("atm").rglob("*.py"):
    # analyzer.py nicht gegen sich selbst laufen lassen
    if py.name == "analyzer.py":
        continue

    src_layer = layer_of(py)
    tree = ast.parse(open(py, encoding="utf-8").read())

    # Sammle alle Imports
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend([n.name.split(".")[0] for n in node.names])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module.split(".")[0])

    # Prüfe jede Import-Kante
    for imp in imports:
        tgt_path = py.with_name(f"{imp}.py")
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

# JUnit-XML erzeugen
os.makedirs("tests-results", exist_ok=True)
suite = ET.Element(
    "testsuite",
    name="ArchGuard",
    tests=str(len(deps) if deps else 1),
    failures=str(len(violations))
)

for d in deps:
    case = ET.SubElement(
        suite,
        "testcase",
        classname=d[0],
        name=f"{d[2]} -> {d[3]}"
    )
    if d in violations:
        fail = ET.SubElement(case, "failure", message="Layer breach")
        fail.text = f"{d[2]} imports {d[3]} ({d[0]}->{d[1]} not allowed)"

# Dummy-Test, falls gar keine Imports gefunden
if not deps:
    ET.SubElement(
        suite,
        "testcase",
        classname="ArchGuard",
        name="no-imports"
    )

ET.ElementTree(suite).write("tests-results/archguard.xml", encoding="utf-8")

# HTML-Report mit Mermaid
html = [
    "<h2>ArchGuard Report</h2>",
    "<pre>"
]
for d in deps:
    mark = "FAIL" if d in violations else "PASS"
    html.append(f"{mark} {d[2]} -> {d[3]} ({d[0]}->{d[1]})")
html += [
    "</pre>",
    "<h3>Dependency graph</h3>",
    "<pre class='mermaid'>",
    "graph LR"
]
for d in deps:
    html.append(
        f'{d[2]}["{d[2]}\\n({d[0]})"] --> {d[3]}["{d[3]}\\n({d[1]})"]'
    )
html.append("</pre>")

with open("archguard_report.html", "w", encoding="utf-8") as f:
    f.write("\n".join(html))

sys.exit(exit_code)
