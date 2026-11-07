"""Opt-in tests against real herdr and real Claude. They spend tokens, on haiku.

    DROVER_LIVE=1 python3 -m unittest tests.test_live

They run in a throwaway herdr session with the registry in a temp folder, so the user's own
session and registry are not touched. Claude must already trust the folder it starts in, and
these tests never answer its trust prompt. The plain tests start in this checkout, or
DROVER_TEST_TRUSTED_REPO if set, and skip if Claude stops at the prompt. The worktree tests need
DROVER_TEST_TRUSTED_REPO, a git repo the user has already trusted, and skip without it. They add
a branch and a worktree for the length of the test and remove both.
"""
import glob, json, os, shutil, subprocess, threading, time, unittest

from tests import formats
from tests.harness import HELPER, OVERRIDES, ROOT

LIVE = os.environ.get("DROVER_LIVE") == "1"
TRUSTED = os.environ.get("DROVER_TEST_TRUSTED_REPO")
HELD = "held at a startup prompt"
# Claude Code refuses a standalone sleep in the foreground, so a busy pane needs something else.
BUSY = """python3 -c 'import time; time.sleep(25)'"""


@unittest.skipUnless(LIVE, "set DROVER_LIVE=1 to run live tests, which use real Claude tokens")
class LiveCase(unittest.TestCase):
    cwd = None
    extra_env = None

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
        cls.box = Box(HELPER, cols=200, rows=60, cwd=cls.cwd, extra_env=cls.extra_env)
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

    def pane(self, name):
        return self.box.registry()[name]["pane"]

    def close_later(self, name):
        self.addCleanup(self.box.h, "close", name, "--force")

    def ready(self, name):
        """A settled pane with an empty input box, to type a draft into."""
        self.close_later(name)
        self.spawn(name, "Reply with exactly READY. No tools.")
        self.assertIn("READY", self.wait(name))
        return self.pane(name)

    def working(self, pane):
        for _ in range(60):
            if self.box.j("agent", "get", pane)["agent"]["agent_status"] == "working":
                return
            time.sleep(0.5)
        self.fail(f"{pane} never started working")

    def type_draft(self, pane, *lines):
        """Type lines into the input box without sending them. ctrl+j is Claude's newline."""
        for n, line in enumerate(lines):
            if n:
                self.box.run("agent", "send-keys", pane, "ctrl+j")
                time.sleep(0.3)
            if line:
                self.box.run("pane", "send-text", pane, line)
                time.sleep(0.3)
        time.sleep(0.7)

    def input_box(self, pane):
        """The text lines of the input box, from the ❯ line down to the rule under it."""
        lines = self.box.run("agent", "read", pane, "--source", "visible").stdout.splitlines()
        start = max(n for n, line in enumerate(lines) if line.lstrip().startswith("❯"))
        rows = []
        for line in lines[start:]:
            if line.strip().startswith("─"):
                break
            rows.append(line.replace("\xa0", " ").lstrip("❯ ").rstrip())
        return rows

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

    def test_run_spawns_waits_and_closes(self):
        self.close_later("live-r")
        code, out = self.box.h("run", "live-r", "Reply with exactly RUN_OK. No tools.", "--preset", "scout", "--timeout", "150000")
        if HELD in out:
            self.skipTest(f"Claude does not trust {self.cwd} yet, and tests never answer that prompt")
        self.assertEqual(code, 0, out)
        self.assertIn("effort low", out)
        self.assertIn("RUN_OK", out)
        self.assertIn("live-r: closed", out)
        self.assertNotIn("live-r", self.box.registry())

    def test_wait_on_several_panes_and_close(self):
        for name in ("live-m1", "live-m2"):
            self.close_later(name)
            self.spawn(name, f"Reply with exactly {name.upper()}_OK. No tools.")
        code, out = self.box.h("wait", "live-m1", "live-m2", "--close", "--timeout", "150000")
        self.assertEqual(code, 0, out)
        self.assertIn("LIVE-M1_OK", out)
        self.assertIn("LIVE-M2_OK", out)
        self.assertIn("live-m1: closed", out)
        self.assertIn("live-m2: closed", out)

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
        self.spawn("live-b", f"Use the Bash tool to run: {BUSY} . Then reply with BUSY_DONE.")
        pane = self.box.registry()["live-b"]["pane"]
        self.working(pane)
        time.sleep(5)
        self.assertEqual(self.box.j("agent", "get", pane)["agent"]["agent_status"], "working")
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


    def test_labelled_pane(self):
        self.close_later("live-l")
        self.spawn("live-l", "Reply with exactly LABEL_OK. No tools.", "--label", "Live label")
        pane = self.pane("live-l")
        self.assertEqual(self.box.j("pane", "get", pane)["pane"]["label"], "Live label")
        self.assertEqual(self.box.registry()["live-l"]["label"], "Live label")
        self.assertIn("LABEL_OK", self.wait("live-l"))
        code, out = self.box.h("rename", "live-l", "--pane", "New label")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.box.j("pane", "get", pane)["pane"]["label"], "New label")

    def test_two_line_draft_is_guarded_then_cleared(self):
        pane = self.ready("live-d")
        self.type_draft(pane, "DRAFT_ONE", "DRAFT_TWO")
        self.assertEqual(self.input_box(pane), ["DRAFT_ONE", "DRAFT_TWO"])
        code, out = self.box.h("send", "live-d", "Reply with exactly NOT_SENT. No tools.")
        self.assertEqual(code, 1, out)
        self.assertIn("unsent text", out)
        code, out = self.box.h("wrapup", "live-d")
        self.assertIn("live-d: unsent text in its input box, skipped", out)
        self.assertEqual(self.input_box(pane), ["DRAFT_ONE", "DRAFT_TWO"])
        code, out = self.box.h("send", "live-d", "Reply with exactly CLEARED_OK. No tools.", "--force")
        self.assertEqual(code, 0, out)
        self.assertIn("CLEARED_OK", self.wait("live-d"))
        self.assertNotIn("DRAFT_", self.transcript("live-d"))

    def test_draft_under_an_empty_first_line_is_guarded(self):
        pane = self.ready("live-e")
        self.type_draft(pane, "", "DRAFT_LOW")
        self.assertEqual(self.input_box(pane), ["", "DRAFT_LOW"])
        code, out = self.box.h("send", "live-e", "Reply with exactly NOT_SENT. No tools.")
        self.assertEqual(code, 1, out)

    def test_force_clears_lines_below_the_cursor(self):
        pane = self.ready("live-c")
        self.type_draft(pane, "DRAFT_TOP", "DRAFT_LOW")
        self.box.run("agent", "send-keys", pane, "up")
        time.sleep(0.5)
        code, out = self.box.h("send", "live-c", "Reply with exactly CLEARED_OK. No tools.", "--force")
        self.assertEqual(code, 0, out)
        self.wait("live-c")
        self.assertNotIn("DRAFT_LOW", self.transcript("live-c"))

    def wait_through_a_move(self, name, *where):
        """Move a working pane while a wait runs on it. Returns (wait output, old id, new id)."""
        self.close_later(name)
        self.spawn(name, f"Use the Bash tool to run: {BUSY} . Then reply with MOVED_DONE.")
        pane = self.pane(name)
        self.working(pane)
        got = []
        waiter = threading.Thread(target=lambda: got.append(self.box.h("wait", name, "--timeout", "120000")))
        waiter.start()
        time.sleep(3)
        moved = self.box.j("pane", "move", pane, *where, "--no-focus")["move_result"]
        waiter.join()
        self.assertEqual(moved["pane"]["agent_status"], "working")
        self.assertEqual(got[0][0], 0, got[0][1])
        return got[0][1], pane, moved["pane"]["pane_id"]

    def test_wait_follows_a_pane_moved_to_a_new_tab(self):
        """Any move ends herdr agent wait with agent_not_running, even when the pane id stays the same."""
        out, old, new = self.wait_through_a_move("live-t", "--new-tab")
        self.assertEqual(old, new)
        self.assertIn("MOVED_DONE", out)

    def test_wait_follows_a_pane_moved_to_a_new_workspace(self):
        """As for a new tab, and here the pane id changes as well."""
        out, old, new = self.wait_through_a_move("live-m", "--new-workspace")
        self.assertNotEqual(old, new)
        self.assertIn("MOVED_DONE", out)

    def test_wrapup_finds_a_pane_moved_to_a_new_workspace(self):
        """Known bug: cmd_wrapup uses load() and alive.get(pane), not synced() and locate(), so a
        live pane with a new id is skipped as gone."""
        pane = self.ready("live-w")
        moved = self.box.j("pane", "move", pane, "--new-workspace", "--no-focus")["move_result"]
        self.assertNotEqual(moved["pane"]["pane_id"], pane)
        code, out = self.box.h("wrapup", "live-w")
        self.assertIn("live-w: asked", out)

    def test_resume_from_a_pane_with_a_live_agent(self):
        box = self.box
        old = box.j("pane", "split", "--pane", box.primary, "--direction", "down", "--cwd", self.cwd,
                    "--no-focus")["pane"]["pane_id"]
        self.addCleanup(box.run, "pane", "close", old)
        for _ in range(10):
            time.sleep(1)
            if box.run("agent", "start", "live-old", "--kind", "claude", "--pane", old, "--timeout", "45000",
                       "--", "--model", "haiku").returncode == 0:
                break
        else:
            self.fail("could not start the old primary")
        self.close_later("live-r")
        code, out = box.h("spawn", "live-r", "Reply with exactly ADOPT_OK. No tools.", "--model", "haiku", primary=old)
        self.assertEqual(code, 0, out)
        self.assertIn("ADOPT_OK", box.h("wait", "live-r", "--timeout", "120000", primary=old)[1])

        code, out = box.h("resume", "--from", old)
        self.assertEqual(code, 1, out)
        self.assertIn("still hosts a live agent", out)
        self.assertIn("live-r", box.registry(old))
        self.assertNotIn("live-r", box.registry())

        code, out = box.h("resume", "--from", old, "--force")
        self.assertEqual(code, 0, out)
        self.assertIn("adopted 1 subagents", out)
        self.assertNotIn("live-r", box.registry(old))
        self.assertIn("live-r", box.registry())
        code, out = box.h("result", "live-r")
        self.assertEqual(code, 0, out)
        self.assertIn("ADOPT_OK", out)


class NoTranscript(LiveCase):
    """Claude turns transcripts off when it inherits this variable, so results come off the screen."""
    extra_env = {"CLAUDE_CODE_CHILD_SESSION": "1"}

    def test_result_falls_back_to_the_screen(self):
        self.close_later("live-n")
        self.spawn("live-n", "Reply with exactly SCREEN_OK. No tools.")
        session = self.box.registry()["live-n"]["session"]
        result = self.wait("live-n")
        self.assertEqual(glob.glob(os.path.expanduser(f"~/.claude/projects/*/{session}.jsonl")), [])
        self.assertIn("no transcript found", result)
        self.assertIn("this is the pane's screen", result)
        self.assertIn("SCREEN_OK", result)


@unittest.skipUnless(TRUSTED, "set DROVER_TEST_TRUSTED_REPO to a git repo Claude already trusts")
class Worktree(LiveCase):
    def setUp(self):
        self.name = f"live-wt{os.getpid()}"
        self.branch = f"drover/{self.name}"
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

    def settle(self, name):
        """Wait out a manual mode pane, approving its prompts. Only safe in a throwaway worktree."""
        for _ in range(8):
            out = self.wait(name)
            if f"{name}: blocked" not in out:
                return out
            self.assertNotIn("git push", out)
            self.box.run("agent", "send-keys", self.pane(name), "enter")
            time.sleep(2)
        self.fail(f"{name} kept stopping at prompts:\n{out}")

    def test_wrapup_of_a_blocked_pane_once_answered(self):
        marker = os.path.join(self.box.tmp, "answered")
        self.spawn(self.name, f"Use the Bash tool to run: touch {marker} . Then reply with exactly MARKED.",
                   "--cwd", self.cwd, "--worktree", "--mode", "manual")
        blocked = self.wait(self.name)
        self.assertIn(f"{self.name}: blocked", blocked)
        self.assertIn("waiting on this prompt", blocked)

        code, out = self.box.h("wrapup", self.name)
        self.assertIn(f"{self.name}: blocked on a prompt, skipped", out)
        self.assertIn("no panes were asked", out)

        self.box.run("agent", "send-keys", self.pane(self.name), "enter")
        time.sleep(2)
        self.assertIn("MARKED", self.settle(self.name))
        self.assertTrue(os.path.exists(marker))

        code, out = self.box.h("wrapup", self.name)
        self.assertIn(f"{self.name}: asked", out)
        handoff = os.path.join(self.box.state, "handoffs", f"{self.name}.md")
        self.assertIn(handoff, self.settle(self.name))
        self.assertTrue(os.path.isfile(handoff))

    def test_wrapup_of_panes_started_inside_a_worktree(self):
        """Panes given a worktree with --cwd: drover has no worktree on record, and the agents commit there."""
        head = self.git("rev-parse", "HEAD").stdout
        panes = {}
        for tag in ("a", "b"):
            name, path = f"{self.name}-{tag}", os.path.join(self.box.tmp, f"direct-{tag}")
            self.addCleanup(self.git, "branch", "-D", f"drover/{name}")
            self.addCleanup(self.git, "worktree", "remove", "--force", path)
            self.close_later(name)
            added = self.git("worktree", "add", "-b", f"drover/{name}", path)
            self.assertEqual(added.returncode, 0, added.stderr)
            self.spawn(name, "Use the Write tool to create live-note.txt in your folder, holding the word NOTE. "
                             "Then reply with exactly NOTE_DONE.", "--cwd", path)
            panes[name] = path
        for name in panes:
            self.assertIn("NOTE_DONE", self.wait(name))
            self.assertNotIn("worktree", self.box.registry()[name])

        code, out = self.box.h("wrapup", *panes)
        self.assertEqual(code, 0, out)
        for name, path in panes.items():
            self.assertIn(f"{name}: asked", out)
            handoff = os.path.join(self.box.state, "handoffs", f"{name}.md")
            result = self.wait(name)
            self.assertIn(handoff, result)
            self.assertIn(f"drover/{name}", result)
            self.assertTrue(os.path.isfile(handoff), result)
            tree = subprocess.run(["git", "-C", path, "ls-tree", "-r", "--name-only", f"drover/{name}"],
                                  capture_output=True, text=True).stdout
            self.assertIn("live-note.txt", tree, result)
        self.assertEqual(self.git("rev-parse", "HEAD").stdout, head)


del LiveCase  # it has no tests of its own


if __name__ == "__main__":
    unittest.main()
