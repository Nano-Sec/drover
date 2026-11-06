#!/usr/bin/env python3
"""Part 2: the same tasks through native subagents (A), drover panes (B), and trimmed panes (C).

Every primary is the same: interactive sonnet, auto mode, default flags, its own tab in an isolated
herdr session, its own fresh folder. Only the delegation instruction differs.

Usage: env -u HERD_CHILD python3 bench/run_part2.py [--reps N] [--tasks a,b] [--arms A,B,C]
                                                    [--jobs N] [--seed N] [--out name] [--budget tokens]
"""
import argparse, json, os, queue, random, re, shutil, sys, threading, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib, score as scoring

MODEL = "sonnet"
TIMEOUT = 900  # seconds a run may take before it counts as unfinished
# The Arm C flags, from Part 1. Bash, files, and web through ToolSearch stay. See REPORT.md for what goes.
TRIM = ["--tools", "Bash,Read,Edit,Write,Glob,Grep,ToolSearch,WebFetch,WebSearch", "--strict-mcp-config"]
SPLIT = {"t4_parallel": 3}  # subagents a task asks for, default 1

ARM_A = ("Delegate this work to {who}, using the built-in Agent tool with model sonnet. "
         "Do not use herd, drover, or herdr panes, and do not do the work yourself.")
ARM_P = ("Delegate this work to {who}, using drover panes: load the drover skill and follow it. Pass --model sonnet "
         "to every spawn. Do not use the herd skill or the Agent tool, and do not do the work yourself.")
TAIL = ("When the work is finished and every subagent is done or closed, run `touch .bench_done` in this folder as your "
        "very last action. Nobody will answer questions during this task.")


def prompt_for(task, arm):
    body = open(os.path.join(scoring.TASKS, task, "task.md")).read().strip()
    n = SPLIT.get(task, 1)
    who = "one subagent" if n == 1 else f"{n} subagents"
    how = (ARM_A if arm == "A" else ARM_P).format(who=who)
    return f"{body}\n\n{how}\n\n{TAIL}"


def make_helpers(root):
    """Scratch copies, so the repo stays as it is. Only the C copy changes, by one line."""
    dirs = {}
    src = open(lib.HELPER).read()
    old = 'native = ["--permission-mode", mode, "-n", name] + (["--model", model] if model else [])'
    if old not in src:
        sys.exit("start_claude changed, update the Arm C patch")
    for arm, flags in (("B", []), ("C", TRIM)):
        d = os.path.join(root, f"helper_{arm.lower()}")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "drover"), "w") as f:
            f.write(src.replace(old, old + (f"\n    native += {flags!r}" if flags else "")))
        os.chmod(os.path.join(d, "drover"), 0o755)
        shutil.copy(os.path.join(os.path.dirname(lib.HELPER), "SKILL.md"), d)
        dirs[arm] = d
    return dirs


def status(b, name):
    r = b.run("agent", "get", name)
    return json.loads(r.stdout)["result"]["agent"] if r.returncode == 0 else None


def tools_used(path):
    seen = {}
    for d in lib.lines(path):
        if d.get("type") == "assistant":
            for c in d["message"].get("content", []):
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    seen[c["id"]] = c["name"]
    out = {}
    for n in seen.values():
        out[n] = out.get(n, 0) + 1
    return out


def bash_mentions(path, word):
    n = 0
    for d in lib.lines(path):
        if d.get("type") == "assistant":
            for c in d["message"].get("content", []):
                if isinstance(c, dict) and c.get("type") == "tool_use" and c["name"] == "Bash" and word in c["input"].get("command", ""):
                    n += 1
    return n


def saw_rule(path):
    """Did this subagent's context hold the CLAUDE.md rule, through any route, before its first response?"""
    for d in lib.lines(path):
        if d.get("type") == "assistant":
            return False
        if "Owner: billing" in json.dumps(d.get("message", "")):
            return True
    return False


def measure(cwd, primary_session, t0, t_done):
    top, subs = lib.transcripts(cwd)
    primary = [t for t in top if primary_session and primary_session in t]
    panes = [t for t in top if t not in primary]
    p_rows = [r for t in primary for r in lib.messages(t)]
    per_sub = [(t, lib.messages(t)) for t in panes + subs]
    s_rows = [r for _, rs in per_sub for r in rs]
    models = sorted({r["model"] for r in p_rows + s_rows})
    first = [lib.prompt_size(rs[0]) for _, rs in per_sub if rs]
    return {
        "primary": lib.add(p_rows), "subagents": lib.add(s_rows), "total": lib.add(p_rows + s_rows),
        "n_panes": len(panes), "n_native": len(subs), "models": models, "sub_first_prompt": first,
        "sub_turns": [len(rs) for _, rs in per_sub],
        "primary_tools": {k: v for t in primary for k, v in tools_used(t).items()},
        "primary_drover_calls": sum(bash_mentions(t, "drover") for t in primary),
        "sub_saw_rule": [saw_rule(t) for t, _ in per_sub],
        "primary_rows": p_rows, "sub_rows": [rs for _, rs in per_sub],
    }


def run_one(b, helpers, job, log):
    task, arm, rep = job["task"], job["arm"], job["rep"]
    rid = f"{task[:2]}{arm.lower()}{rep}x{job['idx']}"
    cwd = os.path.join(lib.WORK_ROOT, job["batch"], rid)
    shutil.copytree(os.path.join(scoring.TASKS, task, "project"), cwd)
    if arm in helpers:  # a project skill, so the primary loads it as an installed skill would load
        shutil.copytree(helpers[arm], os.path.join(cwd, ".claude", "skills", "drover"))
    row = {**{k: job[k] for k in ("task", "arm", "rep", "idx")}, "run": rid, "started": time.strftime("%H:%M:%S")}
    tab = b.j("tab", "create", "--workspace", b.workspace, "--cwd", cwd, "--label", rid, "--no-focus")
    tab_id, pane = tab["tab"]["tab_id"], tab["root_pane"]["pane_id"]
    time.sleep(2)
    r = b.run("agent", "start", rid, "--kind", "claude", "--pane", pane, "--timeout", "45000", "--",
              "--permission-mode", "auto", "-n", rid, "--model", MODEL)
    if r.returncode != 0:
        row.update(outcome="primary_failed_to_start", error=(r.stderr or r.stdout)[:300])
        b.run("tab", "close", tab_id)
        return row
    ag = json.loads(r.stdout)["result"]["agent"]
    session = (ag.get("agent_session") or {}).get("value")
    time.sleep(2)
    t0 = time.time()
    b.run("agent", "prompt", rid, prompt_for(task, arm))
    done = os.path.join(cwd, ".bench_done")
    outcome, blocked_since = "timeout", None
    while time.time() - t0 < TIMEOUT:
        time.sleep(2)
        if os.path.exists(done):
            outcome = "finished"
            break
        a = status(b, rid)
        if a is None:
            outcome = "primary_gone"
            break
        if a.get("agent_status") == "blocked":  # never answered: it counts against the run
            blocked_since = blocked_since or time.time()
            if time.time() - blocked_since > 45:
                outcome = "primary_blocked"
                break
        else:
            blocked_since = None
    t_done = os.path.getmtime(done) if os.path.exists(done) else time.time()
    settle = time.time()
    while time.time() - settle < 45:  # let the closing message land in the transcript
        a = status(b, rid)
        if not a or a.get("agent_status") != "working":
            break
        time.sleep(2)
    time.sleep(3)
    row["screen_tail"] = b.run("agent", "read", rid, "--source", "visible").stdout[-1400:] if outcome != "finished" else ""
    row["outcome"] = outcome
    row["wall_s"] = round(t_done - t0, 1)
    row["score"] = scoring.score(task, cwd)
    row.update(measure(cwd, session, t0, t_done))
    keep = os.path.join(lib.RESULTS, "outputs", job["batch"], rid)
    for name in ("answer.txt", "review.json"):
        if os.path.exists(os.path.join(cwd, name)):
            os.makedirs(keep, exist_ok=True)
            shutil.copy(os.path.join(cwd, name), keep)
    b.run("tab", "close", tab_id)
    return row


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--reps", type=int, default=3)
    p.add_argument("--tasks", default=",".join(scoring.SCORERS))
    p.add_argument("--arms", default="A,B,C")
    p.add_argument("--jobs", type=int, default=3)
    p.add_argument("--seed", type=int, default=20261107)
    p.add_argument("--out", default="part2")
    p.add_argument("--budget", type=int, default=14_000_000, help="stop starting runs past this many tokens")
    p.add_argument("--spent", type=int, default=0, help="tokens already spent before this batch")
    a = p.parse_args()
    rng = random.Random(a.seed)
    jobs = []
    for rep in range(1, a.reps + 1):  # whole repeats first, so stopping early leaves the arms balanced
        block = [{"task": t, "arm": arm, "rep": rep} for t in a.tasks.split(",") for arm in a.arms.split(",")]
        rng.shuffle(block)
        jobs += block
    for i, j in enumerate(jobs):
        j.update(idx=i, batch=a.out)
    batch_root = os.path.join(lib.WORK_ROOT, a.out)
    os.makedirs(batch_root, exist_ok=True)
    state = os.path.join(lib.WORK_ROOT, a.out + "_state")
    helpers = make_helpers(os.path.join(lib.WORK_ROOT, a.out + "_helpers"))
    b = lib.box(f"droverbench{os.getpid()}", state_dir=state)
    out = os.path.join(lib.RESULTS, a.out + ".jsonl")
    q = queue.Queue()
    for j in jobs:
        q.put(j)
    lock = threading.Lock()
    spent = [a.spent]
    stop = threading.Event()

    def worker(w):
        time.sleep(w * 7)  # stagger, so all jobs do not hit startup at once
        while not stop.is_set():
            try:
                j = q.get_nowait()
            except queue.Empty:
                return
            try:
                row = run_one(b, helpers, j, None)
            except Exception as e:
                row = {**{k: j[k] for k in ("task", "arm", "rep", "idx")}, "outcome": "harness_error", "error": repr(e)[:300]}
            with lock:
                with open(out, "a") as f:
                    f.write(json.dumps(row) + "\n")
                spent[0] += (row.get("total") or {}).get("all_tokens", 0)
                print(f"{time.strftime('%H:%M:%S')} {row.get('run', j['idx'])} {row.get('outcome')} score={(row.get('score') or {}).get('score')} "
                      f"wall={row.get('wall_s')} tok={(row.get('total') or {}).get('all_tokens')} cost={(row.get('total') or {}).get('cost')} "
                      f"panes={row.get('n_panes')} native={row.get('n_native')} spent={spent[0]} left={q.qsize()}", flush=True)
                if spent[0] > a.budget:
                    print("BUDGET REACHED, no new runs", flush=True)
                    stop.set()

    threads = [threading.Thread(target=worker, args=(w,)) for w in range(a.jobs)]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        b.stop()
    print("ALL DONE", flush=True)


if __name__ == "__main__":
    main()
