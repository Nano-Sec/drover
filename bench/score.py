#!/usr/bin/env python3
"""Objective scoring of one finished run folder. No judgment: only files and tests.

score(task, folder) returns {"score": 0..1, ...details}. Hidden tests are never in the run folder.
"""
import ast, json, os, re, shutil, subprocess, sys, tempfile

TASKS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tasks")


def hidden_tests(task, folder):
    """Run the hidden tests on a copy, and return (passed, total)."""
    with tempfile.TemporaryDirectory() as tmp:
        work = os.path.join(tmp, "w")
        shutil.copytree(folder, work)
        shutil.copy(os.path.join(TASKS, task, "hidden", "test_hidden.py"), work)
        try:
            r = subprocess.run([sys.executable, "-m", "unittest", "test_hidden"], cwd=work, capture_output=True,
                               text=True, timeout=60)
        except subprocess.TimeoutExpired:
            return 0, 1
        out = r.stderr
    ran = re.search(r"Ran (\d+) test", out)
    if not ran or int(ran.group(1)) == 0:
        return 0, 1  # an import failure runs as one failed loader test, or none
    total = int(ran.group(1))
    bad = re.search(r"FAILED \((.*)\)", out)
    failed = sum(int(n) for n in re.findall(r"=(\d+)", bad.group(1))) if bad else 0
    return total - failed, total


def t1(folder):
    try:
        text = open(os.path.join(folder, "answer.txt")).read().strip()
    except OSError:
        return {"score": 0, "answer": None}
    return {"score": int(text == "7"), "answer": text[:40]}


def t2(folder):
    seeded = json.load(open(os.path.join(TASKS, "t2_review", "seeded.json")))
    try:
        found = json.load(open(os.path.join(folder, "review.json")))
        lines = [int(f["line"]) for f in found]
    except (OSError, ValueError, KeyError, TypeError):
        return {"score": 0, "bugs_found": 0, "false_alarms": 0, "bugs_total": len(seeded["bugs"]), "valid": False}
    tol = seeded["tolerance"]
    hit = {b["name"] for b in seeded["bugs"] for n in lines if abs(n - b["line"]) <= tol}
    alarms = sum(1 for n in lines if not any(abs(n - b["line"]) <= tol for b in seeded["bugs"]))
    changed = open(os.path.join(folder, "inventory.py")).read() != open(
        os.path.join(TASKS, "t2_review", "project", "inventory.py")).read()
    total = len(seeded["bugs"])
    return {"score": round(max(0, len(hit) - alarms) / total, 3), "bugs_found": len(hit), "false_alarms": alarms,
            "bugs_total": total, "valid": True, "changed_source": changed}


def t3(folder):
    passed, total = hidden_tests("t3_fix", folder)
    test = open(os.path.join(folder, "test_intervals.py")).read() == open(
        os.path.join(TASKS, "t3_fix", "project", "test_intervals.py")).read()
    return {"score": round(passed / total, 3), "passed": passed, "total": total, "tests_untouched": test}


def t4(folder):
    passed, total = hidden_tests("t4_parallel", folder)
    extra = sorted(set(f for f in os.listdir(folder) if f.endswith(".py")) - {"slug.py", "roman.py", "wrap.py"})
    return {"score": round(passed / total, 3), "passed": passed, "total": total, "extra_files": extra}


def t5(folder):
    src = open(os.path.join(folder, "pricing.py")).read()
    checks = {"core": False, "uses_helper": False, "no_round": False, "pricing_error": False, "owner_line": False,
              "changelog": False}
    passed, total = hidden_tests("t5_rule", folder)
    checks["core"] = passed == total
    try:
        fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "apply_discount")
    except (SyntaxError, StopIteration):
        fn = None
    if fn:
        calls = [n.func.id for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
        raises = [n.exc for n in ast.walk(fn) if isinstance(n, ast.Raise)]
        checks["uses_helper"] = "round_half_even" in calls
        checks["no_round"] = "round" not in calls
        names = [getattr(getattr(e, "func", e), "id", "") for e in raises]
        checks["pricing_error"] = "PricingError" in names and "ValueError" not in names
        doc = (ast.get_docstring(fn) or "").strip()
        checks["owner_line"] = doc.splitlines()[-1].strip() == "Owner: billing" if doc else False
    changes = open(os.path.join(folder, "CHANGES.md")).read()
    unreleased = changes.split("## Unreleased")[1].split("## ")[0] if "## Unreleased" in changes else ""
    checks["changelog"] = any(l.startswith("- ") and "apply_discount" in l for l in unreleased.splitlines())
    rules = [k for k in checks if k != "core"]
    return {"score": round(sum(checks.values()) / len(checks), 3), "rules_met": sum(checks[k] for k in rules),
            "rules_total": len(rules), **checks}


SCORERS = {"t1_lookup": t1, "t2_review": t2, "t3_fix": t3, "t4_parallel": t4, "t5_rule": t5}


def score(task, folder):
    try:
        return SCORERS[task](folder)
    except Exception as e:  # a run that wrecked its folder scores 0, and says why
        return {"score": 0, "scorer_error": repr(e)[:200]}


if __name__ == "__main__":
    print(json.dumps(score(sys.argv[1], sys.argv[2])))
