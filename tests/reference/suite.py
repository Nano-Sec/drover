import sys, os, time, tempfile, threading, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import *
HERE = os.path.dirname(os.path.abspath(__file__))
tmp = os.path.join(HERE, "herdt6iz27pys")  # reused so its trust entry is reused too
rname = "herdtest-6iz27pys"
repo = os.path.join(tmp, rname); shutil.rmtree(repo, ignore_errors=True); g = mkrepo(repo)
for d in os.listdir(tmp):
    if d != rname: shutil.rmtree(os.path.join(tmp, d), ignore_errors=True)
WT = os.path.expanduser(f"~/.claude/herd/worktrees/{rname}")
res = []
def check(name, ok, detail=""):
    res.append((name, bool(ok))); print(("PASS " if ok else "FAIL ") + name, "::", str(detail).strip()[:900], flush=True)
def status(b, name):
    return b.h("status")[1]
def ask(b, n, brief, *extra):
    return b.h("spawn", n, brief, "--model", "haiku", "--cwd", repo, "--worktree", *extra)
def settle(b, n):
    return b.h("wait", n, "--timeout", "120000")
def reg(b): return json.load(open(b.reg))
b = Box("herdwtsuite")
try:
    # 1 not a git repo, nothing opened
    nongit = os.path.join(tmp, "plain"); os.makedirs(nongit)
    before = len(b.j("pane", "list", "--workspace", b.wid)["panes"])
    c, o = b.h("spawn", "ng", "x", "--cwd", nongit, "--worktree")
    after = len(b.j("pane", "list", "--workspace", b.wid)["panes"])
    check("not a git repo refused before any pane", c != 0 and "not in one" in o and before == after, o)

    # 2 worktree spawn + inherited trust + status branch
    c, o = ask(b, "wa", "Reply with OK. No tools.")
    check("worktree spawn, trust inherited from base repo", c == 0 and "pending" not in o and os.path.isdir(f"{WT}/wa"), o)
    e = reg(b).get("wa", {}); w = e.get("worktree", {})
    check("registry has path, branch, base repo", w.get("path") == f"{WT}/wa" and w.get("branch") == "herd/wa" and w.get("base_repo") and e.get("cwd") == f"{WT}/wa", w)
    pane_cwd = b.j("agent", "get", "wa")["agent"]["cwd"]
    check("pane runs in the worktree", pane_cwd == f"{WT}/wa", pane_cwd)
    check("status shows branch", "[herd/wa]" in status(b, "wa"), status(b, "wa"))

    # 3 second worktree on the same repo, custom branch
    c, o = ask(b, "wb", "Create file b.txt containing hi, then commit it to the current branch with git. Reply DONE.", "feature/b")
    check("two worktree subagents on one repo", c == 0 and os.path.isdir(f"{WT}/wb") and "feature/b" in g("worktree", "list"), g("worktree", "list"))
    c, o = settle(b, "wa"); check("wait returns final message", "OK" in o, o)
    c, o = settle(b, "wb"); print(o[:300])
    # 4 close keeps unmerged commits, even with --force
    ahead = g("rev-list", "--count", "feature/b", "--not", "main")
    c, o = b.h("close", "wb", "--force")
    check("close --force keeps unmerged commits", ahead != "0" and os.path.isdir(f"{WT}/wb") and "commits not on main" in o and g("rev-parse", "--verify", "feature/b"), f"ahead={ahead} {o}")
    check("kept entry stays on record", reg(b).get("wb", {}).get("kept") is True and "kept" in status(b, "wb"), status(b, "wb"))
    c, o = b.h("spawn", "wb", "x", "--model", "haiku"); check("name with kept work refused", c != 0 and "on record" in o, o)
    # merging then closing again cleans up
    g("merge", "-q", "--ff-only", "feature/b")
    c, o = b.h("close", "wb")
    check("close after merge removes worktree and branch", not os.path.exists(f"{WT}/wb") and "feature/b" not in g("branch") and "wb" not in reg(b), o)

    # reattach tests
    g("branch", "herd/ra")
    subprocess.run(f"git -C {repo} worktree add -q {tmp}/seed herd/ra && echo r > {tmp}/seed/r.txt && git -C {tmp}/seed add . && git -C {tmp}/seed commit -qm r && git -C {repo} worktree remove {tmp}/seed", shell=True, check=True)
    c, o = ask(b, "ra", "Reply with OK. No tools.")
    check("reattach: existing branch, no worktree", c == 0 and "reattached existing branch" in o and os.path.exists(f"{WT}/ra/r.txt"), o)
    settle(b, "ra")
    open(f"{WT}/ra/wip.txt", "w").write("wip")
    c, o = b.h("close", "ra"); check("close keeps reattached work", os.path.exists(f"{WT}/ra/wip.txt"), o)
    c, o = b.h("spawn", "ra", "x", "--model", "haiku", "--cwd", repo)
    check("kept name without --worktree refused", c != 0 and "Pass --worktree" in o, o)
    c, o = ask(b, "ra", "Reply with OK. No tools.")
    check("reattach: worktree of closed subagent reused", c == 0 and "reattached to existing worktree" in o and os.path.exists(f"{WT}/ra/wip.txt") and reg(b)["ra"].get("cwd") == f"{WT}/ra" and not reg(b)["ra"].get("kept"), o)
    c, o = ask(b, "rb", "x", "herd/ra"); check("reattach refused while a live agent is there", c != 0 and "live agent" in o, o)
    settle(b, "ra")
    c, o = b.h("close", "ra", "--force"); check("kept again", "work kept" in o, o)
    r0 = reg(b); del r0["ra"]; json.dump(r0, open(b.reg, "w"))
    c, o = ask(b, "rb", "Reply with OK. No tools.", "herd/ra")
    check("reattach: unrecorded worktree found by branch", c == 0 and "reattached to existing worktree" in o and reg(b)["rb"]["cwd"] == f"{WT}/ra", o)
    settle(b, "rb")
    c, o = b.h("close", "rb", "--force"); print(o)
    subprocess.run(f"git -C {repo} worktree remove --force {WT}/ra; git -C {repo} branch -D herd/ra", shell=True, capture_output=True)
    c, o = b.h("close", "rb"); check("cleared", "rb" not in reg(b), o)
    n0 = len(b.j("pane", "list", "--workspace", b.wid)["panes"])
    c, o = ask(b, "rm", "x", "main")
    check("branch in main copy refused before any pane", c != 0 and "main working copy" in o and n0 == len(b.j("pane", "list", "--workspace", b.wid)["panes"]), o)

    # handoff, with and without worktree
    hd = os.path.join(STATE, "handoffs"); os.makedirs(hd, exist_ok=True)
    hfiles = [os.path.join(hd, f"{n}.md") for n in ("hoa-t", "hob-t")]
    for f in hfiles: open(f, "w").write("The code word is MANGOSTEEN.\n")
    brief = "Reply with only the code word. If you have none, reply NONE."
    c, o = b.h("spawn", "hoa-t", brief, "--model", "haiku", "--cwd", repo); check("handoff noted", "handoff:" in o, o)
    c, o2 = ask(b, "hob-t", brief); check("handoff noted with worktree", "handoff:" in o2, o2)
    c, o = settle(b, "hoa-t"); check("handoff line reaches subagent, no worktree", "MANGOSTEEN" in o or "Allow this read" in o, o[-300:])
    print("HOA:", o[-200:])
    c, o = settle(b, "hob-t"); check("handoff line reaches subagent, worktree", "MANGOSTEEN" in o or "Allow this read" in o, o[-300:])
    for f in hfiles: os.remove(f)
    print(b.h("close", "hoa-t", "hob-t", "--force")[1])
    c, o = b.h("spawn", "hoc-t", brief, "--model", "haiku", "--cwd", repo); c, o = settle(b, "hoc-t")
    check("no handoff line without a file", "NONE" in o, o); b.h("close", "hoc-t", "--force")

    # 5 close keeps dirty work; 5b ignored file; 6 clean removal
    open(f"{WT}/wa/dirty.txt", "w").write("x")
    c, o = b.h("close", "wa", "--force")
    check("close --force keeps uncommitted file", os.path.exists(f"{WT}/wa/dirty.txt") and "uncommitted" in o and "herd/wa" in g("branch"), o)
    os.remove(f"{WT}/wa/dirty.txt"); open(f"{WT}/wa/notes.log", "w").write("x")
    c, o = b.h("close", "wa")
    check("close keeps ignored file", os.path.exists(f"{WT}/wa/notes.log") and "ignored" in o, o)
    os.remove(f"{WT}/wa/notes.log")
    c, o = b.h("close", "wa")
    check("close removes clean worktree and branch", not os.path.exists(f"{WT}/wa") and "herd/wa" not in g("branch") and "herd/wa" not in g("worktree", "list"), o)

    # 7 detached/other branch commit in worktree is still protected
    c, o = ask(b, "wc", "Reply with OK. No tools."); settle(b, "wc")
    wc = f"{WT}/wc"
    subprocess.run(f"git -C {wc} checkout -q --detach && echo y > {wc}/c.txt && git -C {wc} add . && git -C {wc} -c user.email=t@e -c user.name=t commit -qm c", shell=True, check=True)
    c, o = b.h("close", "wc", "--force")
    check("detached commits in worktree are kept", os.path.isdir(wc) and "commits not on" in o, o)
    # 8 base branch deleted: fail closed
    g("branch", "tmpbase"); 
    r0 = reg(b); r0["wc"]["worktree"]["base_ref"] = "refs/heads/nonexistent"; json.dump(r0, open(b.reg, "w"))
    c, o = b.h("close", "wc")
    check("check failure keeps worktree", os.path.isdir(wc) and "cannot compare" in o, o)
    subprocess.run(f"git -C {repo} worktree remove --force {wc}; git -C {repo} branch -D herd/wc", shell=True, capture_output=True)
    c, o = b.h("close", "wc"); check("entry clears after manual discard", "wc" not in reg(b), o)

    # 9 resume with live, settled, blocked-free, gone, moved
    c, o = b.h("spawn", "rlive", "Use the Bash tool in the foreground to run exactly: python3 -c 'import time; time.sleep(240)'. Then reply DONE.", "--model", "haiku", "--cwd", repo); check("spawn plain live", c == 0, o)
    c, o = b.h("spawn", "rblk", "Use the Read tool on /etc/hosts and reply with its first line.", "--model", "haiku", "--cwd", repo); settle(b, "rblk")
    c, o = ask(b, "rset", "Reply with OK. No tools."); settle(b, "rset")
    c, o = ask(b, "rgone", "Reply with OK. No tools."); settle(b, "rgone")
    c, o = b.h("spawn", "rgone2", "Reply with OK. No tools.", "--model", "haiku", "--cwd", repo); settle(b, "rgone2")
    open(f"{WT}/rgone/lost.txt", "w").write("x")
    for n in ("rgone", "rgone2"):
        herdr(b.env, "pane", "close", reg(b)[n]["pane"])
    time.sleep(1)
    old = reg(b)["rset"]["pane"]
    mv = b.j("pane", "move", old, "--new-workspace", "--no-focus")
    new = mv["move_result"]["pane"]["pane_id"] if isinstance(mv, dict) else None
    time.sleep(1)
    c, o = b.h("resume"); print(o)
    lines = {l.split()[0]: l.split()[1] for l in o.splitlines() if l[:1].isalpha() and len(l.split()) > 2}
    check("resume states", lines.get("rlive") == "running" and lines.get("rset") == "settled" and lines.get("rblk") == "blocked" and lines.get("rgone") == "gone" and lines.get("rgone2") == "gone", lines)
    check("resume lists wait for running only", re.search(r"herd wait rlive", o) and not re.search(r"herd wait r(set|gone)", o), "")
    check("resume follows moved pane", new and new != old and reg(b)["rset"]["pane"] == new, f"{old} -> {new}")
    check("gone worktree stays findable", "rgone" in reg(b) and f"{WT}/rgone" in o and "1 uncommitted" in o, "")
    c, o = b.h("result", "rgone2"); check("gone entry still gives last message", "gone" in o and "OK" in o, o)
    c, o = b.h("result", "rset"); check("result works on moved pane", "settled" in o or "idle" in o or "done" in o, o)

    # 10 stale pane id that resolves nowhere, session unknown
    r0 = reg(b); r0["ghost"] = {"pane": "w99:p9", "session": "nope", "cwd": "/nonexistent", "mode": "auto", "model": None, "group": None}
    json.dump(r0, open(b.reg, "w"))
    c, o = b.h("resume"); check("unresolvable pane does not crash", c == 0 and "ghost" in o, o[-200:])

    # 11 resume --from
    p2 = b.j("pane", "split", "--pane", b.pane, "--direction", "down", "--no-focus")["pane"]["pane_id"]
    env2 = {**b.env, "HERDR_PANE_ID": p2}
    c, o = b.h("resume", env=env2)
    check("empty registry lists others", "No subagents" in o and b.pane in o and "rlive" in o, o)
    c, o = b.h("resume", "--from", "w98:p98", env=env2); check("resume --from missing fails clearly", c != 0 and "no registry" in o, o)
    c, o = b.h("resume", "--from", b.pane, env=env2)
    newreg = os.path.join(STATE, p2.replace(":", "_") + ".json")
    b.extra = [newreg]
    check("resume --from adopts", c == 0 and "adopted" in o and os.path.exists(newreg) and not os.path.exists(b.reg) and "rlive" in json.load(open(newreg)), o)
    c, o = b.h("close", "rlive", "--force", env=env2); check("adopted entry can be closed", "closed" in o, o)
    # live owner guard: run a claude in p2 and try to adopt from another pane
    c, o = b.h("resume", env={**b.env, "HERD_CHILD": "1"}); check("resume refused in a subagent", c != 0, o)
    c, o = b.h("close", "--all", "--force", env=env2); print(o)
    subprocess.run(f"git -C {repo} worktree remove --force {WT}/rgone; git -C {repo} branch -D herd/rgone", shell=True, capture_output=True)
    c, o = b.h("close", "--all", env=env2); print(o)

    # 12 trust dialog left unanswered: no key is ever sent to it
    repo2 = os.path.join(tmp, f"held{os.getpid()}"); mkrepo(repo2)
    for label, n, extra in (("worktree", "tp", ["--worktree"]), ("plain", "tq", [])):
        c, o = b.h("spawn", n, "Reply with PINEAPPLE. No tools.", "--model", "haiku", "--cwd", repo2, *extra, env=env2)
        e = json.load(open(newreg)).get(n, {})
        screen = herdr(b.env, "pane", "read", e.get("pane", "x"), "--source", "visible").stdout
        check(f"held at dialog, no crash ({label})", c == 0 and "Traceback" not in o and "Only the user should answer" in o, o[-260:])
        check(f"registered, brief stored not sent ({label})", e.get("session") is None and "PINEAPPLE" in e.get("pending", "") and "trust this folder" in screen and "PINEAPPLE" not in screen, e.get("pane"))
    c, o = b.h("send", "tp", "hello", env=env2); check("send refused while held", c != 0 and "startup prompt" in o, o)
    c, o = b.h("status", env=env2); check("status shows blocked", re.search(r"tp\s+blocked", o), o[-200:])
    c, o = b.h("resume", env=env2); check("resume lists wait for held agents", "wait tp" in o and "wait tq" in o and "brief not delivered" in o, "")
    c, o = b.h("wait", "tp", "--timeout", "6000", env=env2)
    e = json.load(open(newreg))["tp"]
    check("timed wait reports the prompt, keeps brief", "trust this folder" in o and e.get("pending"), o[-200:])
    herdr(b.env, "pane", "close", json.load(open(newreg))["tq"]["pane"]); time.sleep(1)
    c, o = b.h("wait", "tq", "--timeout", "6000", env=env2); check("held pane closed reports gone", "gone" in o, o[-120:])
    c, o = b.h("close", "tp", "tq", "--force", env=env2)
    check("held clean worktree removed on close", "worktree removed" in o and "tp" not in json.load(open(newreg)), o)
    # stored brief delivery, on a live agent in the already trusted repo with no dialog involved
    c, o = b.h("spawn", "td", "Reply with OK. No tools.", "--model", "haiku", "--cwd", repo, env=env2)
    b.h("wait", "td", "--timeout", "60000", env=env2)
    r0 = json.load(open(newreg)); r0["td"]["pending"] = "Reply with only the word PINEAPPLE. No tools."; json.dump(r0, open(newreg, "w"))
    c, o = b.h("wait", "td", "--timeout", "90000", env=env2)
    check("wait delivers a stored brief", "PINEAPPLE" in o and not json.load(open(newreg))["td"].get("pending"), o[-200:])
    b.h("close", "td", "--force", env=env2)
    os.path.exists(newreg) and os.remove(newreg)
finally:
    b.stop()
    subprocess.run(f"rm -rf {WT} {WT}-b ~/.claude/herd/worktrees/held{os.getpid()} ~/.claude/herd/worktrees/decl{os.getpid()}", shell=True)
    wtd = os.path.expanduser("~/.claude/herd/worktrees")
    if os.path.isdir(wtd) and not os.listdir(wtd): os.rmdir(wtd)
    print("left in state dir:", os.listdir(STATE))
    print(f"{sum(x[1] for x in res)}/{len(res)} passed; failed:", [x[0] for x in res if not x[1]])
    print("tmp", tmp)
