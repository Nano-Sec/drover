import fcntl, json, os, pty, shutil, struct, subprocess, sys, termios, threading, time
HERE = os.path.dirname(os.path.abspath(__file__))
H = os.path.join(HERE, "herd_t.py")
SESS = "herdwrapupt"
REG = os.path.join(HERE, "test_reg.json")
HOFF = os.path.expanduser("~/.claude/herd/handoffs")
NAMES = ["wt-wd", "wt-named", "wt-idle", "wt-main", "wt-work", "wt-block", "wt-gone", "wt-draft"]
FILES = [os.path.join(HOFF, n + ".md") + s for n in NAMES for s in ("", ".prev")]
base = {k: v for k, v in os.environ.items() if not k.startswith(("HERDR_", "HERD_")) and k != "CLAUDE_CODE_CHILD_SESSION"}
base["HERDR_CONFIG_PATH"] = "/private/tmp/claude-501/-Users-example-Documents-claude-workspace/1d5a53bf-4fa7-4d4e-8b77-2c5b29ad23e4/scratchpad/quiet-herdr.toml"
# Inside the trusted workspace, so Claude does not stop on its folder trust dialog.
T = os.path.expanduser(f"~/Documents/claude_workspace/.herd-wrapup-test-{os.getpid()}")
RES = []

def herdr(env, *a):
    return subprocess.run(["herdr", *a], env=env, capture_output=True, text=True)
def sh(cmd, cwd=None):
    return subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True).stdout.strip()
def check(label, ok, detail=""):
    RES.append((label, bool(ok)))
    print(f"[{'PASS' if ok else 'FAIL'}] {label} {detail}", flush=True)

assert not any(os.path.exists(f) for f in FILES), "handoff name collision, aborting"
assert herdr(base, "session", "list", "--json").stdout.count(f'"{SESS}"') == 0, "session exists"
assert not os.path.exists(T); os.makedirs(T + "/plain")
sh(f"""git init -q --bare origin.git && git init -q -b main repo && cd repo && git config user.email t@t && git config user.name t &&
echo x > README && git add . && git commit -qm init && git remote add origin ../origin.git && git push -q origin main &&
git worktree add -q ../wtree -b task/wt""", cwd=T)

pid, fd = pty.fork()
if pid == 0:
    fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", 70, 292, 0, 0))
    os.execvpe("herdr", ["herdr", "--session", SESS], {**base, "TERM": "xterm-256color"})
threading.Thread(target=lambda: [os.read(fd, 65536) for _ in iter(int, 1)], daemon=True).start()
try:
    sock = None
    for _ in range(40):
        time.sleep(0.5)
        for s in json.loads(herdr(base, "session", "list", "--json").stdout)["sessions"]:
            if s["name"] == SESS and s["running"]:
                sock = s["socket_path"]
        if sock: break
    assert sock, "no session"
    env = {**base, "HERDR_SOCKET_PATH": sock}
    ws = []
    for _ in range(20):
        r = herdr(env, "workspace", "list")
        ws = json.loads(r.stdout)["result"]["workspaces"] if r.returncode == 0 else []
        if ws: break
        time.sleep(0.5)
    wid = ws[0]["workspace_id"] if ws else json.loads(herdr(env, "workspace", "create", "--cwd", T).stdout)["result"]["workspace"]["workspace_id"]
    p = json.loads(herdr(env, "pane", "list", "--workspace", wid).stdout)["result"]["panes"][0]
    env.update(HERDR_ENV="1", HERDR_PANE_ID=p["pane_id"], HERDR_TAB_ID=p["tab_id"], HERDR_WORKSPACE_ID=wid, REG_OVERRIDE=REG)
    def herd(*a, timeout=300):
        r = subprocess.run([H, *a], env=env, capture_output=True, text=True, cwd=T, timeout=timeout)
        out = (r.stdout + r.stderr).strip()
        print(f"$ herd {' '.join(x if len(x) < 50 else x[:50] + '...' for x in a)}  [rc={r.returncode}]\n{out}\n", flush=True)
        return r.returncode, out
    def reg(): return json.load(open(REG))
    def state(n):
        return {a["pane_id"]: a["agent_status"] for a in json.loads(herdr(env, "agent", "list").stdout)["result"]["agents"]}.get(reg()[n]["pane"])
    def pane_text(n):
        return herdr(env, "agent", "read", reg()[n]["pane"], "--source", "recent").stdout
    hf = lambda n: os.path.join(HOFF, n + ".md")
    mk = lambda f, d: f"Your work is in the git checkout at {d}. Create {f} there containing the word hello. Do not commit. Then reply OK."

    herd("spawn", "wt-named", "Reply with OK. No tools.", "--model", "haiku", "--cwd", T + "/plain")
    herd("spawn", "wt-idle", mk("idle.txt", T + "/wtree"), "--model", "haiku", "--cwd", T + "/plain")
    herd("spawn", "wt-main", mk("main.txt", T + "/repo"), "--model", "haiku", "--cwd", T + "/plain")
    herd("spawn", "wt-gone", "Reply with OK. No tools.", "--model", "haiku", "--cwd", T + "/plain")
    herd("spawn", "wt-draft", "Reply with OK. No tools.", "--model", "haiku", "--cwd", T + "/plain")
    herd("spawn", "wt-block", f"Use the Bash tool to run exactly: touch {T}/plain/blocked.txt  Then reply OK.", "--model", "haiku", "--mode", "manual", "--cwd", T + "/plain")
    assert len(reg()) == 6, "spawn failed"
    for n in ["wt-named", "wt-idle", "wt-main", "wt-gone", "wt-draft", "wt-block"]:
        herd("wait", n, "--timeout", "120000")
    herd("status")

    print("### unknown name refuses everything")
    rc, out = herd("wrapup", "wt-idle", "nosuch")
    time.sleep(2)
    check("unknown name dies before sending", rc != 0 and "wrap up" not in pane_text("wt-idle").split("Then reply OK")[-1], out[:80])

    print("### wrapup by name, with a stale handoff present")
    os.makedirs(HOFF, exist_ok=True)
    open(hf("wt-named"), "w").write("STALE\n")
    rc, out = herd("wrapup", "wt-named")
    check("by name: only that pane asked", "wt-named: asked" in out and "wt-idle" not in out)
    check("by name: stale moved aside", open(hf("wt-named") + ".prev").read() == "STALE\n")
    herd("wait", "wt-named", "--timeout", "180000")
    rc, res = herd("result", "wt-named")
    check("by name: fresh handoff written", os.path.exists(hf("wt-named")) and "STALE" not in open(hf("wt-named")).read())
    check("by name: final message names handoff path", "handoffs/wt-named.md" in res)
    check("by name: other pane got nothing", "wrap up and hand off" not in pane_text("wt-idle"))
    herd("close", "wt-named")

    print("### set up working, gone, draft")
    herd("spawn", "wt-work", "Use the Bash tool to run exactly: python3 -c 'import time; time.sleep(40)'  Then reply OK.", "--model", "haiku", "--cwd", T + "/plain")
    herd("spawn", "wt-wd", "Use the Bash tool to run exactly: python3 -c 'import time; time.sleep(60)'  Then reply OK.", "--model", "haiku", "--cwd", T + "/plain")
    for _ in range(40):
        time.sleep(1)
        if "time.sleep(40)" in pane_text("wt-work") and state("wt-work") == "working" and "Bash" in pane_text("wt-work"): break
    time.sleep(5)
    herdr(env, "pane", "close", reg()["wt-gone"]["pane"])
    dp = reg()["wt-draft"]["pane"]
    print(herdr(env, "pane", "send-text", dp, "my unsent draft words").stderr)
    print(herdr(env, "agent", "send-keys", dp, "ctrl+j").stderr)
    print(herdr(env, "pane", "send-text", dp, "second draft line").stderr)
    print(herdr(env, "pane", "send-text", reg()["wt-wd"]["pane"], "draft while working").stderr)
    time.sleep(2)
    herd("status")
    print("states before:", {n: state(n) for n in reg()})

    print("### wrapup all")
    was_working = state("wt-work")
    open(hf("wt-work"), "w").write("STALE\n")
    t0 = time.time()
    rc, out = herd("wrapup")
    print("wrapup took", round(time.time() - t0, 1), "s")
    check("working state confirmed at send", was_working == "working", was_working)
    for n in ["wt-idle", "wt-main", "wt-work"]:
        check(f"all: {n} asked", f"{n}: asked" in out)
    check("all: gone skipped", "wt-gone: gone, skipped" in out)
    check("all: blocked skipped", "wt-block: blocked" in out)
    check("all: draft skipped", "wt-draft: unsent text" in out)
    check("all: working pane with draft skipped", "wt-wd: unsent text" in out)
    check("all: working pane stale handoff stayed moved aside", os.path.exists(hf("wt-work") + ".prev"))
    check("all: wait hint lists exactly the asked panes", "for each of: wt-idle, wt-main, wt-work" in out)
    check("blocked pane did not receive it", "wrap up and hand off" not in pane_text("wt-block"))
    check("draft pane did not receive it", "wrap up and hand off" not in pane_text("wt-draft"))

    print("### refused then --force")
    rc, out = herd("wrapup", "wt-draft")
    check("draft refused without --force", "unsent text" in out and "no panes were asked" in out)
    rc, out = herd("wrapup", "wt-draft", "--force")
    check("draft asked with --force", "wt-draft: asked" in out)
    rc, out = herd("wrapup", "wt-wd")
    check("working draft refused", "unsent text" in out)
    was = state("wt-wd")
    rc, out = herd("wrapup", "wt-wd", "--force")
    check("working draft asked with --force", "wt-wd: asked" in out, f"state at send {was}")

    print("### collect")
    for n in ["wt-idle", "wt-main", "wt-work", "wt-draft", "wt-wd"]:
        herd("wait", n, "--timeout", "240000")
        rc, res = herd("result", n)
        check(f"{n}: final message names handoff", f"handoffs/{n}.md" in res)
        check(f"{n}: handoff file exists", os.path.exists(hf(n)))
        if os.path.exists(hf(n)):
            t = open(hf(n)).read()
            check(f"{n}: handoff has the four sections", all(k.lower() in t.lower() for k in ["status", "decisions", "next steps", "open questions"]))
            print("-----", n, "\n" + t[:700], "\n-----", flush=True)
    print("wtree log:", sh("git log --oneline -3; git status --short", cwd=T + "/wtree"))
    print("repo log:", sh("git log --oneline -3; git status --short", cwd=T + "/repo"))
    check("worktree task branch: committed", "idle.txt" in sh("git show --stat --format= HEAD", cwd=T + "/wtree"))
    check("main branch: no commit", sh("git rev-list --count main", cwd=T + "/repo") == "1")
    check("main branch: file left uncommitted", "main.txt" in sh("git status --short", cwd=T + "/repo"))
    check("nothing pushed", sh("git for-each-ref --format='%(refname)'", cwd=T + "/origin.git") == "refs/heads/main" and sh("git rev-list --count main", cwd=T + "/origin.git") == "1")
    check("--force draft was not submitted", "my unsent draft words" not in pane_text("wt-draft") and "second draft line" not in pane_text("wt-draft"))
    check("--force working draft was not submitted", "draft while working" not in pane_text("wt-wd"))
    print("--- draft pane tail ---\n" + "\n".join(pane_text("wt-draft").splitlines()[-30:]))
    herd("status")
finally:
    if os.path.exists(REG):
        subprocess.run([H, "close", "--all", "--force"], env=locals().get("env", base), capture_output=True)
    print(herdr(base, "session", "stop", SESS).stdout.strip()[:80])
    time.sleep(1); herdr(base, "session", "delete", SESS)
    for f in FILES:
        if os.path.exists(f): os.remove(f)
    if os.path.exists(REG): os.remove(REG)
    shutil.rmtree(T, ignore_errors=True)
    try: os.kill(pid, 9)
    except OSError: pass
    print("SUMMARY", sum(ok for _, ok in RES), "/", len(RES))
    for l, ok in RES:
        if not ok: print("  FAILED:", l)
