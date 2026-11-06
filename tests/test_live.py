"""Opt-in tests against real herdr and real Claude. They spend tokens, on haiku.

    HERD_LIVE=1 python3 -m unittest tests.test_live

They run in a throwaway herdr session with the registry in a temp folder, so the user's own
session and registry are not touched. Claude must already trust the folder it starts in, and
these tests never answer its trust prompt. The plain tests start in this checkout, or
HERD_TEST_TRUSTED_REPO if set, and skip if Claude stops at the prompt. The worktree tests need
HERD_TEST_TRUSTED_REPO, a git repo the user has already trusted, and skip without it. They add
a branch and a worktree for the length of the test and remove both.
"""
import glob, json, os, shutil, subprocess, time, unittest

from tests import formats
from tests.harness import HELPER, OVERRIDES, ROOT

LIVE = os.environ.get("HERD_LIVE") == "1"
TRUSTED = os.environ.get("HERD_TEST_TRUSTED_REPO")
HELD = "held at a startup prompt"


@unittest.skipUnless(LIVE, "set HERD_LIVE=1 to run live tests, which use real Claude tokens")
class LiveCase(unittest.TestCase):
    cwd = None

    @classmethod
    def setUpClass(cls):
        from tests.live_box import Box  # pty and termios are not needed unless this runs
        for tool in ("herdr", "claude"):
            if not shutil.which(tool):
                raise unittest.SkipTest(f"{tool} is not installed")
        with open(HELPER, encoding="utf-8") as f:
            source = f.read()
        if not all(v in source for v in OVERRIDES):
            raise AssertionError(f"{HELPER} does not read {OVERRIDES}, so the registry cannot be redirected")
        cls.cwd = os.path.realpath(TRUSTED or ROOT)
        cls.box = Box(HELPER, cols=200, rows=60, cwd=cls.cwd)
        cls.addClassCleanup(cls.box.stop)

    def spawn(self, name, brief, *args):
        code, out = self.box.h("spawn", name, brief, "--model", "haiku", *args)
        if HELD in out:
            self.box.h("close", name, "--force")
            self.skipTest(f"Claude does not trust {self.cwd} yet, and tests never answer that prompt")
        self.assertEqual(code, 0, out)
        return out

    def wait(self, name, timeout=120000):
        code, out = self.box.h("wait", name, "--timeout", str(timeout))
        self.assertEqual(code, 0, out)
        return out

    def transcript(self, name):
        session = self.box.registry()[name]["session"]
        hits = glob.glob(os.path.expanduser(f"~/.claude/projects/*/{session}.jsonl"))
        self.assertTrue(hits, "no transcript. Did a CLAUDE variable reach the pane?")
        with open(hits[0], encoding="utf-8") as f:
            return f.read()


class Plain(LiveCase):
    def test_spawn_and_wait(self):
        out = self.spawn("live-a", "Reply with exactly LIVE_OK. No tools.")
        self.assertIn("started in", out)
        self.assertIn("session", out)
        self.assertNotIn("session pending", out)
        result = self.wait("live-a")
        self.assertIn("LIVE_OK", result)
        code, closed = self.box.h("close", "live-a")
        self.assertEqual(code, 0)
        self.assertIn("live-a: closed", closed)
        self.assertNotIn("live-a", self.box.registry())

    def test_real_formats_still_match(self):
        self.spawn("live-f", "Reply with exactly FORMAT_OK. No tools.")
        self.assertIn("FORMAT_OK", self.wait("live-f"))
        pane = self.box.registry()["live-f"]["pane"]
        agent = self.box.j("agent", "get", pane)["agent"]
        self.assertEqual(formats.agent_problems(agent), [])
        self.assertEqual(formats.layout_problems(self.box.j("pane", "layout", "--pane", pane)["layout"]), [])
        self.assertEqual(formats.transcript_problems(self.transcript("live-f")), [])
        screen = self.box.run("agent", "read", pane, "--source", "visible", "--format", "ansi").stdout
        self.assertEqual(formats.screen_problems(screen), [])
        self.box.h("close", "live-f", "--force")

    def test_send_to_a_busy_pane(self):
        self.spawn("live-b", "Use the Bash tool to run: sleep 25 . Then reply with BUSY_DONE.")
        pane = self.box.registry()["live-b"]["pane"]
        for _ in range(30):
            if self.box.j("agent", "get", pane)["agent"]["agent_status"] == "working":
                break
            time.sleep(0.5)
        time.sleep(5)
        started = time.time()
        code, out = self.box.h("send", "live-b", "Also finish your reply with the word STEERED.")
        self.assertEqual(code, 0, out)
        self.assertLess(time.time() - started, 8, "send must not wait for a busy pane")
        result = self.wait("live-b")
        time.sleep(8)  # the queued message starts a second turn once the first one settles
        result += self.wait("live-b", 60000)
        self.assertIn("STEERED", result)
        self.box.h("close", "live-b", "--force")

    def test_wait_holds_through_a_pause(self):
        self.spawn("live-p", "Use the Bash tool with run_in_background set to true to run: sleep 20 . End your turn "
                             "immediately after launching it, saying only LAUNCHED. When you are later notified the "
                             "job finished, reply with PAUSE_FINAL.")
        started = time.time()
        result = self.wait("live-p", 150000)
        self.assertIn("PAUSE_FINAL", result)
        self.assertGreater(time.time() - started, 10)
        self.assertEqual(formats.transcript_problems(self.transcript("live-p")), [])
        self.box.h("close", "live-p", "--force")


@unittest.skipUnless(TRUSTED, "set HERD_TEST_TRUSTED_REPO to a git repo Claude already trusts")
class Worktree(LiveCase):
    def setUp(self):
        self.name = f"live-wt{os.getpid()}"
        self.branch = f"herd/{self.name}"
        self.addCleanup(self.tidy)

    def git(self, *args):
        return subprocess.run(["git", "-C", self.cwd, *args], capture_output=True, text=True)

    def path(self):
        top = self.git("rev-parse", "--show-toplevel").stdout.strip()
        return os.path.join(self.box.state, "worktrees", os.path.basename(top), self.name)

    def tidy(self):
        """Remove only what this test made, even if it failed halfway."""
        self.box.h("close", self.name, "--force")
        if os.path.isdir(self.path()):
            self.git("worktree", "remove", "--force", self.path())
        self.git("branch", "-D", self.branch)
        self.box.h("close", self.name, "--force")

    def test_worktree_spawn_close_keeps_then_removes(self):
        out = self.spawn(self.name, "Reply with exactly TREE_OK. No tools.", "--cwd", self.cwd, "--worktree")
        self.assertIn("worktree created", out)
        path = self.path()
        self.assertTrue(os.path.isdir(path))
        self.assertIn("TREE_OK", self.wait(self.name))
        agent = self.box.j("agent", "get", self.box.registry()[self.name]["pane"])["agent"]
        self.assertEqual(os.path.realpath(agent["cwd"]), os.path.realpath(path))

        extra = os.path.join(path, "live-test-file.txt")
        with open(extra, "w") as f:
            f.write("keep me\n")
        code, out = self.box.h("close", self.name, "--force")
        self.assertIn("work kept", out)
        self.assertTrue(os.path.exists(extra))

        os.remove(extra)
        code, out = self.box.h("close", self.name)
        self.assertIn("worktree removed", out)
        self.assertFalse(os.path.exists(path))
        self.assertEqual(self.git("branch", "--list", self.branch).stdout.strip(), "")


del LiveCase  # it has no tests of its own


if __name__ == "__main__":
    unittest.main()
