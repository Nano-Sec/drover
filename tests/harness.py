"""Shared setup for the fast tests: a sandbox folder, the fake herdr, and small helpers.

Each test gets its own HOME, state folder and projects folder, so nothing can reach the real
~/.claude. HERD_BIN points the tests at another copy of the helper.
"""
import json, os, shutil, subprocess, sys, tempfile, unittest

from tests.fake_herdr import close_pane

TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS)
HELPER = os.path.abspath(os.environ.get("HERD_BIN") or os.path.join(ROOT, "skills", "herd", "herd"))
FIXTURES = os.path.join(TESTS, "fixtures")
PRIMARY = "w1:p1"
HOME_TAB = "w1:t1"
OVERRIDES = ("HERD_STATE_DIR", "HERD_PROJECTS_DIR")


def fixture(*parts):
    with open(os.path.join(FIXTURES, *parts), encoding="utf-8", newline="") as f:
        return f.read()


def assistant_line(text, sidechain=False):
    return json.dumps({"type": "assistant", "isSidechain": sidechain,
                       "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}})


def job_line(job):
    return json.dumps({"type": "assistant", "isSidechain": False, "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": job, "name": "Bash", "input": {"command": "sleep 9", "run_in_background": True}}]}})


def notification_line(job):
    text = f"<task-notification>\n<task-id>x</task-id>\n<tool-use-id>{job}</tool-use-id>\n<status>completed</status>\n</task-notification>"
    return json.dumps({"type": "queue-operation", "operation": "enqueue", "content": text})


class Result:
    def __init__(self, code, out):
        self.code, self.out = code, out


class HerdCase(unittest.TestCase):
    window = (200, 60)
    maxDiff = None

    def setUp(self):
        with open(HELPER, encoding="utf-8") as f:
            source = f.read()
        missing = [v for v in OVERRIDES if v not in source]
        if missing:
            self.fail(f"{HELPER} does not read {' or '.join(missing)}, which these tests need. "
                      "Set HERD_BIN to a helper that does.")
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="herd-test-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.home = self.mkdir("home")
        self.state_dir = self.mkdir("state")
        self.projects = self.mkdir("projects")
        self.work = self.mkdir("home", "work")
        bin_dir = self.mkdir("bin")
        # Started directly, because the macOS python3 shim costs more than the fake's whole run.
        launcher = f"#!{sys.executable} -S\nimport sys\nsys.path.insert(0, {TESTS!r})\nimport fake_herdr\nfake_herdr.main()\n"
        os.chmod(self.write(os.path.join(bin_dir, "herdr"), launcher), 0o755)
        self.state_file = os.path.join(self.root, "fake.json")
        self.save_fake({
            "window": list(self.window), "workspace": "w1", "next_pane": 2, "next_tab": 2, "sessions": 0,
            "tabs": {HOME_TAB: {"label": "main", "root": {"pane": PRIMARY}}},
            "panes": {PRIMARY: {"tab": HOME_TAB, "cwd": self.work, "env": [], "prompts": [], "keys": [], "draft": "",
                                "screen": None, "steps": [], "busy": False,
                                "agent": {"agent_status": "working", "name": None}}},
            "calls": [], "start": {}, "start_argv": {}, "prompt_fail": [], "close_stuck": [],
        })
        self.env = {
            "PATH": bin_dir + os.pathsep + os.environ.get("PATH", ""), "HOME": self.home, "PYTHONUTF8": "1",
            "HERDR_ENV": "1", "HERDR_PANE_ID": PRIMARY, "HERDR_TAB_ID": HOME_TAB, "HERDR_WORKSPACE_ID": "w1",
            "HERD_STATE_DIR": self.state_dir, "HERD_PROJECTS_DIR": self.projects,
            "FAKE_HERDR_STATE": self.state_file, "FAKE_HERD_HELPER": HELPER,
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
        }

    def mkdir(self, *parts):
        path = os.path.join(self.root, *parts)
        os.makedirs(path, exist_ok=True)
        return path

    def write(self, path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)
        return path

    # The fake's state

    def fake(self):
        with open(self.state_file) as f:
            return json.load(f)

    def save_fake(self, state):
        with open(self.state_file, "w") as f:
            json.dump(state, f)

    def change(self, fn):
        state = self.fake()
        fn(state)
        self.save_fake(state)

    def pane(self, name):
        return self.fake()["panes"][self.entry(name)["pane"]]

    def change_pane(self, name, **fields):
        pid = self.entry(name)["pane"]
        self.change(lambda s: s["panes"][pid].update(fields))

    def change_agent(self, name, **fields):
        pid = self.entry(name)["pane"]
        self.change(lambda s: s["panes"][pid]["agent"].update(fields))

    def set_status(self, name, status):
        self.change_agent(name, agent_status=status)

    def calls(self, *prefix):
        return [c for c in self.fake()["calls"] if tuple(c[:len(prefix)]) == prefix]

    def close_pane_outside(self, name):
        """The pane dies without the helper knowing."""
        pid = self.entry(name)["pane"]

        self.change(lambda state: close_pane(state, pid))

    def move_pane(self, name, new="w2:p1", tab="w2:t1"):
        """The user moved the pane to another workspace, which changes its id."""
        pid = self.entry(name)["pane"]

        def go(state):
            pane = dict(state["panes"][pid], tab=tab)
            close_pane(state, pid)
            state["panes"][new] = pane
            state["tabs"][tab] = {"label": "moved", "root": {"pane": new}}
        self.change(go)
        return new

    # The helper

    def herd(self, *args, stdin=None, cwd=None, env=None, patience=None):
        environ = {**self.env, **(env or {})}
        if patience is not None:
            environ["FAKE_JOB_PATIENCE"] = str(patience)
        p = subprocess.run([sys.executable, os.path.join(TESTS, "run_herd.py"), *args], env=environ, cwd=cwd or self.work,
                           input=stdin, capture_output=True, text=True, timeout=60)
        self.assertNotIn("Traceback", p.stderr, p.stderr)
        return Result(p.returncode, p.stdout + p.stderr)

    def ok(self, *args, **kw):
        r = self.herd(*args, **kw)
        self.assertEqual(r.code, 0, r.out)
        return r.out

    def refused(self, *args, **kw):
        r = self.herd(*args, **kw)
        self.assertNotEqual(r.code, 0, r.out)
        return r.out

    def spawn(self, name, *args, brief="Do the task."):
        return self.ok("spawn", name, brief, *args)

    def reg_file(self, pane=PRIMARY):
        return os.path.join(self.state_dir, pane.replace(":", "_") + ".json")

    def reg(self, pane=PRIMARY):
        try:
            with open(self.reg_file(pane)) as f:
                return json.load(f)
        except OSError:
            return {}

    def save_reg(self, reg, pane=PRIMARY):
        with open(self.reg_file(pane), "w") as f:
            json.dump(reg, f)

    def entry(self, name):
        return self.reg()[name]

    def brief(self, name):
        """The first prompt the subagent received."""
        return self.pane(name)["prompts"][0]

    # Transcripts

    def transcript(self, name):
        session = self.entry(name)["session"]
        path = os.path.join(self.projects, "-sandbox", f"{session}.jsonl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path

    def say(self, name, *lines):
        with open(self.transcript(name), "a") as f:
            for line in lines:
                f.write(line + "\n")

    def use_transcript(self, name, fixture_file):
        with open(self.transcript(name), "w", encoding="utf-8") as f:
            f.write(fixture("transcripts", fixture_file))

    # Git

    def repo(self, name="repo"):
        path = self.mkdir("home", "code", name)
        self.git(path, "init", "-q", "-b", "main")
        self.write(os.path.join(path, "a.txt"), "hello\n")
        self.write(os.path.join(path, ".gitignore"), "*.log\n")
        self.git(path, "add", ".")
        self.git(path, "commit", "-qm", "init")
        return path

    def git(self, cwd, *args):
        p = subprocess.run(["git", "-C", cwd, *args], env=self.env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, f"git {' '.join(args)}: {p.stderr}")
        return p.stdout.strip()

    def commit_file(self, cwd, name="work.txt"):
        self.write(os.path.join(cwd, name), "work\n")
        self.git(cwd, "add", name)
        self.git(cwd, "commit", "-qm", f"add {name}")

    def has_branch(self, repo, branch):
        return branch in self.git(repo, "branch", "--format=%(refname:short)").splitlines()

    def wt_path(self, repo, name):
        return os.path.join(self.state_dir, "worktrees", os.path.basename(repo), name)
