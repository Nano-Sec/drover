import fcntl, glob, json, os, pty, struct, subprocess, sys, termios, threading, time
H = os.path.expanduser("~/.claude/skills/herd/herd")
base = {k: v for k, v in os.environ.items() if not k.startswith(("HERDR_", "HERD_"))}
def herdr(env, *a):
    return subprocess.run(["herdr", *a], env=env, capture_output=True, text=True)
def trial(cols, rows):
    sess = f"herdsize{cols}"
    pid, fd = pty.fork()
    if pid == 0:
        fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        os.execvpe("herdr", ["herdr", "--session", sess], {**base, "TERM": "xterm-256color"})
    threading.Thread(target=lambda: [os.read(fd, 65536) for _ in iter(int, 1)], daemon=True).start()
    reg = None
    try:
        sock = None
        for _ in range(40):
            time.sleep(0.5)
            d = json.loads(herdr(base, "session", "list", "--json").stdout or "{}")
            for s in d.get("sessions", d if isinstance(d, list) else []):
                if s.get("name") == sess and s.get("running"):
                    sock = s.get("socket") or s.get("socket_path")
            if sock: break
        if not sock: print("no session", d); return
        env = {**base, "HERDR_SOCKET_PATH": sock}
        for _ in range(20):
            r = herdr(env, "workspace", "list")
            ws = json.loads(r.stdout)["result"]["workspaces"] if r.returncode == 0 else []
            if ws: break
            time.sleep(0.5)
        if not ws:
            print("creating workspace"); w = json.loads(herdr(env, "workspace", "create", "--cwd", os.getcwd()).stdout)["result"]
            wid = w["workspace"]["workspace_id"]
        else: wid = ws[0]["workspace_id"]
        p = json.loads(herdr(env, "pane", "list", "--workspace", wid).stdout)["result"]["panes"][0]
        env.update(HERDR_ENV="1", HERDR_PANE_ID=p["pane_id"], HERDR_TAB_ID=p["tab_id"], HERDR_WORKSPACE_ID=wid)
        reg = os.path.expanduser("~/.claude/herd/" + p["pane_id"].replace(":", "_") + ".json")
        hd = subprocess.run([H, "status"], env=env, capture_output=True, text=True)
        print(f"=== {cols}x{rows}:", hd.stdout.splitlines()[0] if hd.stdout else hd.stderr)
        n = int(hd.stdout.split(", ")[1].split()[0]) + 1
        for i in range(n):
            r = subprocess.run([H, "spawn", f"s{i}", "Reply with OK. No tools.", "--model", "haiku"], env=env, capture_output=True, text=True, cwd=os.getcwd())
            print("  ", (r.stdout or r.stderr).strip().split(" (auto")[0])
        lay = json.loads(herdr(env, "pane", "layout", "--pane", p["pane_id"]).stdout)["result"]["layout"]
        print("   primary tab:", [f'{x["rect"]["width"]}x{x["rect"]["height"]}' for x in lay["panes"]])
        subprocess.run([H, "close", "--all", "--force"], env=env, capture_output=True)
    finally:
        print("  ", herdr(base, "session", "stop", sess).stdout.strip()[:80])
        time.sleep(1); herdr(base, "session", "delete", sess)
        if reg and os.path.exists(reg): os.remove(reg)
        try: os.kill(pid, 9)
        except OSError: pass
for c, r in [(270, 70), (162, 44), (292, 50), (100, 30), (100, 62)]:
    trial(c, r)
