#!/usr/bin/env python3
"""Prove the scorers before spending tokens: a starter project scores low, a reference answer scores 1."""
import json, os, shutil, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import score

REFERENCE = {
    "t1_lookup": {"answer.txt": "7\n"},
    "t2_review": {"review.json": json.dumps([{"line": n, "problem": "x"} for n in (7, 14, 19, 29, 34, 39, 45)])},
    "t3_fix": {"intervals.py": '''def merge(bookings):
    merged = []
    for start, end in sorted(bookings):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def free_slots(bookings, day_start, day_end):
    slots = []
    cursor = day_start
    for start, end in merge(bookings):
        if start >= day_end:
            break
        if start > cursor:
            slots.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < day_end:
        slots.append((cursor, day_end))
    return slots
'''},
    "t4_parallel": {"slug.py": '''import re


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
''', "roman.py": '''PAIRS = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
         (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]


def to_roman(n):
    if not 1 <= n <= 3999:
        raise ValueError(n)
    out = ""
    for v, s in PAIRS:
        while n >= v:
            out += s
            n -= v
    return out


def from_roman(s):
    for n in range(1, 4000):
        if to_roman(n) == s:
            return n
    raise ValueError(s)
''', "wrap.py": '''def wrap(text, width):
    if width < 1:
        raise ValueError(width)
    lines, cur = [], ""
    for word in text.split():
        if cur and len(cur) + 1 + len(word) <= width:
            cur += " " + word
            continue
        if cur:
            lines.append(cur)
            cur = ""
        while len(word) > width:
            lines.append(word[:width])
            word = word[width:]
        cur = word
    if cur:
        lines.append(cur)
    return lines
'''},
    "t5_rule": {"pricing.py": None, "CHANGES.md": None},
}
T5_FN = '''

def apply_discount(price_cents, percent):
    """Return the price after taking off percent.
    Owner: billing"""
    if not 0 <= percent <= 100:
        raise PricingError("bad percent")
    return round_half_even(price_cents * (100 - percent) / 100)
'''
ok = True
for task, files in REFERENCE.items():
    with tempfile.TemporaryDirectory() as tmp:
        d = os.path.join(tmp, "p")
        shutil.copytree(os.path.join(score.TASKS, task, "project"), d)
        before = score.score(task, d)
        for name, text in files.items():
            if text is not None:
                open(os.path.join(d, name), "w").write(text)
        if task == "t5_rule":
            open(os.path.join(d, "pricing.py"), "a").write(T5_FN)
            c = open(os.path.join(d, "CHANGES.md")).read()
            open(os.path.join(d, "CHANGES.md"), "w").write(c.replace("- add_tax: first version", "- add_tax: first version\n- apply_discount: new"))
        after = score.score(task, d)
        good = before["score"] <= 0.5 and after["score"] == 1
        ok = ok and good
        print(task, "OK" if good else "BAD", "starter", before["score"], "reference", after["score"], after if not good else "")
sys.exit(not ok)
