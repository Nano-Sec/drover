import fcntl, json, os, pty, shutil, struct, subprocess, sys, tempfile, termios, threading, time
H = os.environ.get("HERD_BIN", os.path.join(os.path.dirname(os.path.abspath(__file__)), "herd"))
base = {k: v for k, v in os.environ.items() if not k.startswith(("HERDR_", "HERD_", "CLAUDE_CODE_", "CLAUDECODE"))}
STATE = os.path.expanduser("~/.claude/herd")

def herdr(env, *a):
    return subprocess.run(["herdr", *a], env=env, capture_output=True, text=True)

class Box:
    """A throwaway herdr session in a fake terminal."""
    def __init__(self, name, cols=200, rows=60):
        self.name = name
        before = set(os.listdir(STATE))
        self.before = before
        pid, fd = pty.fork()
        if pid == 0:
            fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
            os.execvpe("herdr", ["herdr", "--session", name], {**base, "TERM": "xterm-256color"})
        self.pid = pid
        threading.Thread(target=lambda: [os.read(fd, 65536) for _ in iter(int, 1)], daemon=True).start()
        sock = None
        for _ in range(40):
            time.sleep(0.5)
            d = json.loads(herdr(base, "session", "list", "--json").stdout or "{}")
            for s in d.get("sessions", []):
                if s.get("name") == name and s.get("running"):
                    sock = s.get("socket") or s.get("socket_path")
            if sock: break
        assert sock, "no session"
        assert "default" not in name and sock != os.path.expanduser("~/.config/herdr/herdr.sock")
        self.env = {**base, "HERDR_SOCKET_PATH": sock}
        ws = []
        for _ in range(20):
            r = herdr(self.env, "workspace", "list")
            ws = json.loads(r.stdout)["result"]["workspaces"] if r.returncode == 0 else []
            if ws: break
            time.sleep(0.5)
        if ws:
            wid = ws[0]["workspace_id"]
        else:
            wid = json.loads(herdr(self.env, "workspace", "create", "--cwd", os.getcwd()).stdout)["result"]["workspace"]["workspace_id"]
        p = json.loads(herdr(self.env, "pane", "list", "--workspace", wid).stdout)["result"]["panes"][0]
        self.wid, self.pane, self.tab = wid, p["pane_id"], p["tab_id"]
        self.env.update(HERDR_ENV="1", HERDR_PANE_ID=self.pane, HERDR_TAB_ID=self.tab, HERDR_WORKSPACE_ID=wid)
        self.reg = os.path.join(STATE, self.pane.replace(":", "_") + ".json")
        assert not os.path.exists(self.reg), "would collide with a real registry: " + self.reg

    def h(self, *a, env=None, cwd=None, inp=None):
        r = subprocess.run([H, *a], env=env or self.env, capture_output=True, text=True, cwd=cwd or os.getcwd(), input=inp)
        return r.returncode, r.stdout + r.stderr

    def j(self, *a):
        r = herdr(self.env, *a)
        return json.loads(r.stdout)["result"] if r.returncode == 0 else r.stderr

    def stop(self):
        print("stop:", herdr(base, "session", "stop", self.name).stdout.strip()[:80])
        time.sleep(1); herdr(base, "session", "delete", self.name)
        for q in [self.reg] + getattr(self, "extra", []):
            if os.path.exists(q): os.remove(q)
        try: os.kill(self.pid, 9)
        except OSError: pass

def mkrepo(path):
    os.makedirs(path)
    g = lambda *a: subprocess.run(["git", "-C", path, *a], check=True, capture_output=True, text=True).stdout.strip()
    g("init", "-q", "-b", "main")
    g("config", "user.email", "t@example.com"); g("config", "user.name", "t")
    open(os.path.join(path, "a.txt"), "w").write("hello\n")
    open(os.path.join(path, ".gitignore"), "w").write("*.log\n")
    g("add", "."); g("commit", "-qm", "init")
    return g
