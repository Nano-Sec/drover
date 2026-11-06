import fcntl, json, os, pty, shutil, struct, subprocess, sys, termios, threading, time
H = os.path.expanduser("~/.claude/skills/herd/herd")
base = {k: v for k, v in os.environ.items() if not k.startswith(("HERDR_", "HERD_", "CLAUDE"))}
ROOT = os.path.expanduser(f"~/Documents/claude_workspace/.herd-integ-{os.getpid()}")
PRIM, OTHER = f"{ROOT}/primary", f"{ROOT}/other"
HOFF = os.path.expanduser("~/.claude/herd/handoffs/t-hand.md")
fails = []
def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name, detail if not ok else "", flush=True)
    if not ok: fails.append(name)
def herdr(env, *a): return subprocess.run(["herdr", *a], env=env, capture_output=True, text=True)
for d in (PRIM + "/sub", OTHER): os.makedirs(d)
open(PRIM + "/CLAUDE.md", "w").write("The project codeword is CTXTOKEN77.\n")
open(HOFF, "w").write("Status: the handoff codeword is HANDTOKEN55.\n")
sess = "herdinteg2"
pid, fd = pty.fork()
if pid == 0:
    fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", 70, 270, 0, 0))
    os.chdir(PRIM)
    os.execvpe("herdr", ["herdr", "--session", sess], {**base, "TERM": "xterm-256color"})
threading.Thread(target=lambda: [os.read(fd, 65536) for _ in iter(int, 1)], daemon=True).start()
reg = None
try:
    sock = None
    for _ in range(40):
        time.sleep(0.5)
        for s in json.loads(herdr(base, "session", "list", "--json").stdout or "{}").get("sessions", []):
            if s["name"] == sess and s.get("running"): sock = s["socket_path"]
        if sock: break
    env = {**base, "HERDR_SOCKET_PATH": sock}
    for _ in range(20):
        r = herdr(env, "workspace", "list")
        ws = json.loads(r.stdout)["result"]["workspaces"] if r.returncode == 0 else []
        if ws: break
        time.sleep(0.5)
    wid = ws[0]["workspace_id"] if ws else json.loads(herdr(env, "workspace", "create", "--cwd", PRIM).stdout)["result"]["workspace"]["workspace_id"]
    p = json.loads(herdr(env, "pane", "list", "--workspace", wid).stdout)["result"]["panes"][0]
    p = json.loads(herdr(env, "pane", "split", "--pane", p["pane_id"], "--direction", "right", "--cwd", PRIM, "--no-focus").stdout)["result"]["pane"]
    env.update(HERDR_ENV="1", HERDR_PANE_ID=p["pane_id"], HERDR_TAB_ID=p["tab_id"], HERDR_WORKSPACE_ID=wid)
    reg = os.path.expanduser("~/.claude/herd/" + p["pane_id"].replace(":", "_") + ".json")
    def h(*a, stdin=None):
        return subprocess.run([H, *a], env=env, capture_output=True, text=True, cwd=PRIM, input=stdin)
    def spawn(n, brief, *x):
        r = h("spawn", n, brief, "--model", "haiku", *x); print("  ", (r.stdout or r.stderr).strip()[:120], flush=True); return r
    def paneof(n): return json.load(open(reg))[n]["pane"]
    def first_prompt(n):
        sid = json.load(open(reg))[n]["session"]
        import glob
        t = glob.glob(os.path.expanduser(f"~/.claude/projects/*/{sid}.jsonl"))
        return open(t[0]).read() if t else ""
    # A: send to a busy pane
    spawn("busy", "Use the Bash tool to run: sleep 25 . Then reply with BUSY_DONE.")
    time.sleep(6)
    t0 = time.time(); r = h("send", "busy", "Also finish your reply with the word STEERED.")
    check("send busy: no false timeout", r.returncode == 0 and time.time() - t0 < 8, r.stderr)
    r = h("wait", "busy", "--timeout", "90000")
    time.sleep(8); r2 = h("wait", "busy", "--timeout", "60000")
    check("send busy: message acted on", "STEERED" in r.stdout + r2.stdout, (r.stdout + r2.stdout)[-300:])
    # B: send --force
    spawn("draft", "Reply with READY. No tools."); h("wait", "draft", "--timeout", "60000")
    herdr(env, "pane", "send-text", paneof("draft"), "half typed thought"); time.sleep(1)
    r = h("send", "draft", "Reply with REFUSEDTOKEN.")
    check("send: refuses over unsent text", r.returncode != 0, r.stdout)
    r = h("send", "draft", "Reply with exactly FORCE_OK. No tools.", "--force")
    check("send --force: accepted", r.returncode == 0, r.stderr)
    r = h("wait", "draft", "--timeout", "60000")
    check("send --force: acted on, draft gone", "FORCE_OK" in r.stdout and "half typed" not in first_prompt("draft"), r.stdout[-300:])
    # C: wait across a pause
    spawn("paused", "Use the Bash tool with run_in_background set to true to run: sleep 35 . End your turn immediately after launching it, saying only LAUNCHED. When you are later notified the job finished, reply with PAUSE_FINAL.")
    t0 = time.time(); r = h("wait", "paused", "--timeout", "150000"); took = time.time() - t0
    check("wait: holds through a pause", "PAUSE_FINAL" in r.stdout and took > 20, f"{took:.0f}s {r.stdout[-300:]}")
    print(f"   wait took {took:.0f}s", flush=True)
    # D: handoff pasted
    spawn("t-hand", "Reply with the handoff codeword only. No tools.")
    r = h("wait", "t-hand", "--timeout", "60000")
    check("handoff: pasted and used, no read needed", "HANDTOKEN55" in r.stdout, r.stdout[-300:])
    # E: CLAUDE.md
    spawn("ctx-out", "Reply with the project codeword only. No tools.", "--cwd", OTHER)
    r = h("wait", "ctx-out", "--timeout", "60000")
    check("context: outside pane gets it", "CTXTOKEN77" in r.stdout, r.stdout[-300:])
    spawn("ctx-in", "Reply with the project codeword only. No tools.", "--cwd", PRIM + "/sub")
    r = h("wait", "ctx-in", "--timeout", "60000")
    check("context: inside pane loads it natively", "CTXTOKEN77" in r.stdout, r.stdout[-300:])
    check("context: inside pane not pasted twice", "Project context from" not in first_prompt("ctx-in"))
    h("close", "--all", "--force")
finally:
    print("  ", herdr(base, "session", "stop", sess).stdout.strip()[:60]); time.sleep(1); herdr(base, "session", "delete", sess)
    if reg and os.path.exists(reg): os.remove(reg)
    for f in (HOFF,):
        if os.path.exists(f): os.remove(f)
    shutil.rmtree(ROOT, ignore_errors=True)
    try: os.kill(pid, 9)
    except OSError: pass
print("RESULT", "all passed" if not fails else f"failed: {fails}")
