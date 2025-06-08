#!/usr/bin/env python3
import json
import pathlib
import ast
import os
import xml.etree.ElementTree as ET
import sys

# --- Modell laden von JSON statt YAML ---
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

# ──────────────────────────────────────────────────────────────────────────
# Modul-Katalog anlegen: modulename → (layer, filepath)          ### NEU ###
module_catalog = {}
for py in pathlib.Path("atm").rglob("*.py"):
    name = py.stem
    module_catalog[name] = (layer_of(py), py)
# ──────────────────────────────────────────────────────────────────────────

deps = []
violations = []

# Alle .py-Dateien unterhalb des Projekt-Roots durchsuchen
for py in pathlib.Path(".").rglob("*.py"):
    if py.name == "analyzer.py":
        continue

    src_layer = layer_of(py)
    tree = ast.parse(py.read_text(encoding="utf-8"))

    # sowohl import als auch from-import erfassen
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

        # Regelverstöße merken – und gleich Vorschläge sammeln   ### NEU ###
        if tgt_layer not in layers_rules.get(src_layer, []):
            # sammle alle möglichen Alternativen aus dem Katalog
            allowed = layers_rules.get(src_layer, [])
            alts = [
                name
                for name, (layer, _) in module_catalog.items()
                if layer in allowed and name != imp
            ]
            violations.append((src_layer, tgt_layer, py.name, imp, alts))
# ──────────────────────────────────────────────────────────────────────────

# Konsolenausgabe
print(f"[ArchGuard] Analysierte {len(deps)} Import-Kanten")
exit_code = 0
if violations:
    print(f"[ArchGuard] FAIL: {len(violations)} Verstöße gefunden")
    for src, tgt, fname, imp, alts in violations:
        print(f"   FAIL: {fname} ({src}) -> {imp} ({tgt})")
    exit_code = 1
else:
    print("[ArchGuard] PASS: Keine Verstöße gefunden")

# JUnit-XML erzeugen
os.makedirs("tests-results", exist_ok=True)
suite = ET.Element(
    "testsuite",
    name="ArchGuard",
    tests=str(len(deps) if deps else 1),
    failures=str(len(violations))
)
for d in deps:
    case = ET.SubElement(suite, "testcase", classname=d[0], name=f"{d[2]} -> {d[3]}")
    if any(v[2] == d[2] and v[3] == d[3] for v in violations):
        fail = ET.SubElement(case, "failure", message="Layer breach")
        fail.text = f"{d[2]} imports {d[3]} ({d[0]}->{d[1]} not allowed)"
if not deps:
    ET.SubElement(suite, "testcase", classname="ArchGuard", name="no-imports")
ET.ElementTree(suite).write("tests-results/archguard.xml", encoding="utf-8")

# HTML-Report mit Mermaid und Vorschlägen           ### NEU ###
html = [
    "<h2>ArchGuard Report</h2>",
    "<h3>Erklärung der Verstöße</h3>",
]

if violations:
    html += [
        "<p>Folgende Verstöße gegen das Architekturmodell wurden gefunden:</p>",
        "<ul>"
    ]
    for src, tgt, fname, imp, alts in violations:
        line = (
            f"Die Datei <b>{fname}</b> im Layer <i>{src}</i> importiert "
            f"<b>{imp}.py</b> im Layer <i>{tgt}</i>, was nicht erlaubt ist."
        )
        if alts:
            line += (
                f" Stattdessen könntest du importieren: "
                f"<b>{', '.join(alts)}.py</b>."
            )
        html.append(f"<li>{line}</li>")
    html.append("</ul>")
else:
    html.append("<p>Keine Verstöße gefunden — alle Abhängigkeiten entsprechen dem Modell.</p>")

# Detailübersicht & Dependency-Graph wie gehabt
html += [
    "<h3>Detailübersicht</h3>",
    "<pre>"
]
for d in deps:
    mark = "FAIL" if any(v[2] == d[2] and v[3] == d[3] for v in violations) else "PASS"
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
