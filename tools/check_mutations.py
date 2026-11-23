"""Run four single-change faults against independent project copies."""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
EXISTING = ["tests/test_api.py", "tests/test_lifecycle.py"]
MODEL = "tests/test_state_model.py"
MUTATIONS = [
    ("reject_last_unit", "if quantity > remaining:", "if quantity >= remaining:"),
    ("retry_reports_new_booking", "status = 200", "status = 201"),
    ("cancel_affects_other_bookings",
     "SET state = 'cancelled' WHERE id = ?", "SET state = 'cancelled' WHERE id = ? OR state = 'active'"),
    ("unknown_cancel_reports_success",
     'return {"error": "unknown_reservation"}, 404',
     'return {"error": "unknown_reservation"}, 200 if request.method == "DELETE" else 404'),
]


def evaluate(parent, label, source):
    work = parent / label
    work.mkdir()
    shutil.copytree(ROOT / "tests", work / "tests", ignore=shutil.ignore_patterns("__pycache__"))
    (work / "app.py").write_text(source, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--junitxml=result.xml", *EXISTING, MODEL],
        cwd=work, capture_output=True, timeout=120,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stdout.decode(errors="replace"))
    xml = ElementTree.parse(work / "result.xml")
    cases = xml.findall(".//testcase")
    if not cases or xml.find(".//error") is not None or xml.find(".//skipped") is not None:
        raise RuntimeError(f"{label}: incomplete test run")
    failed = []
    for case in cases:
        failure = case.find("failure")
        if failure is not None:
            if "assert " not in failure.get("message", ""):
                raise RuntimeError(f"{label}: unexpected test error: {failure.get('message')}")
            failed.append(f"{case.get('classname')}.{case.get('name')}")
    return {"executed": len(cases),
            "existing_failures": [n for n in failed if ".test_state_model." not in n],
            "model_failures": [n for n in failed if ".test_state_model." in n]}


def main():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="reservation-mutations-") as temp:
        parent = Path(temp)
        baseline = evaluate(parent, "baseline", source)
        if baseline["existing_failures"] or baseline["model_failures"]:
            raise SystemExit("Unmodified baseline failed")
        outcomes = {}
        for label, old, new in MUTATIONS:
            if source.count(old) != 1:
                raise SystemExit(f"{label}: update mutation for current app.py")
            outcomes[label] = evaluate(parent, label, source.replace(old, new))
            if outcomes[label]["executed"] != baseline["executed"]:
                raise SystemExit(f"{label}: incomplete comparison")
    report = {"baseline": baseline, "mutations": outcomes}
    path = ROOT / "reports/mutations.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for label, r in outcomes.items():
        print(f"{label}: existing={len(r['existing_failures'])}, model={len(r['model_failures'])}")
    return int(any(not (r["existing_failures"] or r["model_failures"]) for r in outcomes.values()))


if __name__ == "__main__":
    sys.exit(main())
