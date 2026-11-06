"""A throwaway herdr session in a fake terminal, for the opt-in live tests.

Everything here protects the user's real session: the session has its own name, the
environment drops every HERDR_, DROVER_ and CLAUDE variable (Claude turns transcripts off
when it inherits them), sound is off, and the registry goes to a temp folder.
"""
import fcntl, json, os, pty, shutil, signal, struct, subprocess, tempfile, termios, threading, time

DROP = ("HERDR_", "DROVER_", "CLAUDE")


def clean_env():
    return {k: v for k, v in os.environ.items() if not k.startswith(DROP)}


class Box:
    def __init__(self, helper, name=None, cols=200, rows=60, cwd=None, extra_env=None):
        self.helper = helper
        self.name = name or f"droverlive{os.getpid()}"
        if self.name == "default":
            raise ValueError("refusing to use the default herdr session")
        self.cwd = cwd or os.getcwd()
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="drover-live-"))
        self.state = os.path.join(self.tmp, "state")
        config = os.path.join(self.tmp, "herdr.toml")
        with open(config, "w") as f:
            f.write("[ui.sound]\nenabled = false\n")
        self.base = {**clean_env(), **(extra_env or {}), "HERDR_CONFIG_PATH": config}
        self.pid = None
        try:
            self._launch(cols, rows)
        except BaseException:
            self.stop()
            raise

    def _launch(self, cols, rows):
        if any(s.get("name") == self.name for s in self._sessions()):
            raise RuntimeError(f"herdr session {self.name} already exists")
        pid, fd = pty.fork()
        if pid == 0:
            fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
            os.chdir(self.cwd)
            os.execvpe("herdr", ["herdr", "--session", self.name], {**self.base, "TERM": "xterm-256color"})
        self.pid = pid

        def drain():
            try:
                while os.read(fd, 65536):
                    pass
            except OSError:
                pass
        threading.Thread(target=drain, daemon=True).start()
        sock = None
        for _ in range(40):
            time.sleep(0.5)
            for s in self._sessions():
                if s.get("name") == self.name and s.get("running"):
                    sock = s.get("socket_path")
            if sock:
                break
        if not sock:
            raise RuntimeError("herdr session did not start")
        self.env = {**self.base, "HERDR_SOCKET_PATH": sock}
        spaces = []
        for _ in range(20):
            r = self.run("workspace", "list")
            spaces = json.loads(r.stdout)["result"]["workspaces"] if r.returncode == 0 else []
            if spaces:
                break
            time.sleep(0.5)
        self.workspace = (spaces[0]["workspace_id"] if spaces else
                          self.j("workspace", "create", "--cwd", self.cwd)["workspace"]["workspace_id"])
        root = self.j("pane", "list", "--workspace", self.workspace)["panes"][0]
        self.primary, self.tab = root["pane_id"], root["tab_id"]
        self.drover_env = {**self.env, "HERDR_ENV": "1", "HERDR_PANE_ID": self.primary, "HERDR_TAB_ID": self.tab,
                         "HERDR_WORKSPACE_ID": self.workspace, "DROVER_STATE_DIR": self.state}

    def _sessions(self):
        r = subprocess.run(["herdr", "session", "list", "--json"], env=self.base, capture_output=True, text=True)
        return json.loads(r.stdout or "{}").get("sessions", [])

    def run(self, *args):
        return subprocess.run(["herdr", *args], env=self.env, capture_output=True, text=True)

    def j(self, *args):
        r = self.run(*args)
        if r.returncode != 0:
            raise RuntimeError(f"herdr {' '.join(args[:3])}: {r.stderr.strip()[:300]}")
        return json.loads(r.stdout)["result"]

    def h(self, *args, cwd=None, stdin=None, timeout=300, primary=None):
        """Run the helper as the primary, or as another pane, returning (exit code, stdout plus stderr)."""
        env = {**self.drover_env, "HERDR_PANE_ID": primary or self.primary}
        r = subprocess.run([self.helper, *args], env=env, capture_output=True, text=True,
                           cwd=cwd or self.cwd, input=stdin, timeout=timeout)
        return r.returncode, r.stdout + r.stderr

    def registry(self, primary=None):
        path = os.path.join(self.state, (primary or self.primary).replace(":", "_") + ".json")
        try:
            with open(path) as f:
                return json.load(f)
        except OSError:
            return {}

    def stop(self):
        subprocess.run(["herdr", "session", "stop", self.name], env=self.base, capture_output=True, text=True)
        time.sleep(1)
        subprocess.run(["herdr", "session", "delete", self.name], env=self.base, capture_output=True, text=True)
        if self.pid:
            try:
                os.kill(self.pid, signal.SIGKILL)
                os.waitpid(self.pid, 0)
            except OSError:
                pass
        shutil.rmtree(self.tmp, ignore_errors=True)
