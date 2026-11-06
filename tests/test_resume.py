"""resume after a restart: reconciling state and adopting another pane's registry."""
import os, re, unittest

from tests.harness import DroverCase, PRIMARY, assistant_line

OTHER = "w1:p50"


class Resume(DroverCase):
    def states(self, out):
        return {m[0]: m[1] for m in re.findall(r"^(\S+)\s+(running|settled|blocked|gone|kept)\s", out, re.M)}

    def test_reports_each_state_and_what_to_do(self):
        repo = self.repo()
        for name in ("run", "idle", "done", "block", "dead"):
            self.spawn(name)
        self.spawn("kept", "--cwd", repo, "--worktree")
        self.ok("wait", "kept")
        self.commit_file(self.wt_path(repo, "kept"))
        self.ok("close", "kept")
        self.set_status("idle", "idle")
        self.set_status("done", "done")
        self.set_status("block", "blocked")
        self.close_pane_outside("dead")
        out = self.ok("resume")
        self.assertEqual(self.states(out), {"run": "running", "idle": "settled", "done": "settled", "block": "blocked",
                                            "dead": "gone", "kept": "kept"})
        self.assertRegex(out, r"wait run\n")
        self.assertNotRegex(out, r"wait (idle|done|block|dead|kept)")
        for name in ("idle", "done", "block"):
            self.assertRegex(out, rf"result {name}\n")
        self.assertRegex(out, r"close dead kept\n")

    def test_commands_use_the_helper_path(self):
        self.spawn("run")
        self.assertRegex(self.ok("resume"), r"  /\S+drover wait run")

    def test_nothing_running(self):
        self.spawn("a")
        self.set_status("a", "idle")
        self.assertIn("no background waits are needed", self.ok("resume"))

    def test_unknown_agent_state_counts_as_running(self):
        self.spawn("a")
        self.set_status("a", "unknown")
        self.assertEqual(self.states(self.ok("resume")), {"a": "running"})

    def test_follows_a_moved_pane(self):
        self.spawn("a")
        new = self.move_pane("a")
        self.assertIn(new, self.ok("resume"))
        self.assertEqual(self.entry("a")["pane"], new)

    def test_gone_worktree_stays_findable(self):
        repo = self.repo()
        self.spawn("a", "--cwd", repo, "--worktree")
        path = self.wt_path(repo, "a")
        self.write(os.path.join(path, "lost.txt"), "x")
        self.close_pane_outside("a")
        out = self.ok("resume")
        self.assertIn(path, out)
        self.assertIn("holds: 1 uncommitted changes", out)

    def test_clean_gone_worktree_says_it_is_safe(self):
        repo = self.repo()
        self.spawn("a", "--cwd", repo, "--worktree")
        self.close_pane_outside("a")
        self.assertIn("nothing new, safe to close", self.ok("resume"))

    def test_gone_entry_points_at_its_transcript(self):
        self.spawn("a")
        self.say("a", assistant_line("bye"))
        path = self.transcript("a")
        self.close_pane_outside("a")
        self.assertIn(f"transcript: {path}", self.ok("resume"))
        self.assertIn("bye", self.ok("result", "a"))

    def test_pane_that_resolves_nowhere(self):
        self.save_reg({"ghost": {"pane": "w99:p9", "session": "nope", "cwd": "/nonexistent", "mode": "auto",
                                 "model": None, "group": None}})
        self.assertEqual(self.states(self.ok("resume")), {"ghost": "gone"})

    def test_refused_inside_a_subagent(self):
        self.assertIn("no subagents to resume", self.refused("resume", env={"DROVER_CHILD": "1"}))


class Adopt(DroverCase):
    def setUp(self):
        super().setUp()
        self.spawn("a")
        self.spawn("b")

    def as_other(self, *args):
        return self.drover(*args, env={"HERDR_PANE_ID": OTHER})

    def test_empty_pane_lists_other_registries(self):
        r = self.as_other("resume")
        self.assertEqual(r.code, 0)
        self.assertIn(f"No subagents on record for this pane ({OTHER})", r.out)
        self.assertRegex(r.out, rf"{PRIMARY}\s+2 subagents, 2 live")
        self.assertIn("a, b", r.out)
        self.assertIn("pane still hosts a live agent", r.out)

    def test_nothing_to_list(self):
        os.remove(self.reg_file())
        self.assertIn("No other registries found", self.ok("resume"))

    def test_missing_source(self):
        r = self.as_other("resume", "--from", "w98:p98")
        self.assertNotEqual(r.code, 0)
        self.assertIn("no registry for w98:p98", r.out)

    def test_own_pane(self):
        self.assertIn("is this pane", self.refused("resume", "--from", PRIMARY))

    def test_live_owner_needs_force(self):
        r = self.as_other("resume", "--from", PRIMARY)
        self.assertNotEqual(r.code, 0)
        self.assertIn("still hosts a live agent", r.out)
        self.assertTrue(os.path.exists(self.reg_file()))

    def test_force_adopts_from_a_live_owner(self):
        r = self.as_other("resume", "--from", PRIMARY, "--force")
        self.assertEqual(r.code, 0, r.out)
        self.assertIn("adopted 2 subagents", r.out)
        self.assertFalse(os.path.exists(self.reg_file()))
        self.assertEqual(sorted(self.reg(OTHER)), ["a", "b"])

    def dead_owner(self):
        self.change(lambda s: s["panes"][PRIMARY].update(agent=None))

    def test_dead_owner_is_adopted_without_force(self):
        self.dead_owner()
        r = self.as_other("resume", "--from", PRIMARY)
        self.assertEqual(r.code, 0, r.out)
        self.assertRegex(r.out, r"wait a\n")
        self.assertEqual(sorted(self.reg(OTHER)), ["a", "b"])

    def test_adopted_entries_can_be_closed(self):
        self.dead_owner()
        self.as_other("resume", "--from", PRIMARY)
        r = self.as_other("close", "a", "--force")
        self.assertIn("a: closed", r.out)

    def test_name_clash_leaves_that_entry_behind(self):
        self.dead_owner()
        mine = {"a": {"pane": "w1:p77", "session": "s", "cwd": "/x", "mode": "auto", "model": None, "group": None}}
        self.save_reg(mine, OTHER)
        r = self.as_other("resume", "--from", PRIMARY)
        self.assertIn("not adopted, name already in use here: a", r.out)
        self.assertIn("adopted 1 subagents", r.out)
        self.assertEqual(self.reg(OTHER)["a"]["pane"], "w1:p77")
        self.assertEqual(sorted(self.reg(PRIMARY)), ["a"])


if __name__ == "__main__":
    unittest.main()
