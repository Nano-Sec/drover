"""run, multi-pane wait, wait --close, presets, effort, and lean tools."""
import unittest

from tests.harness import DroverCase, assistant_line

LEAN = ["--tools", "Bash,Read,Edit,Write,Glob,Grep,ToolSearch,WebFetch,WebSearch", "--strict-mcp-config"]


class Run(DroverCase):
    def finish_next(self, text="ALL DONE", session="session-1"):
        """Write the transcript the next spawn will have, since run leaves no gap to do it after."""
        self.write(f"{self.projects}/-sandbox/{session}.jsonl", assistant_line(text) + "\n")

    def test_spawns_waits_prints_and_closes(self):
        self.finish_next()
        out = self.ok("run", "a", "Do the task.")
        self.assertIn("a started in w1:p2", out)
        self.assertIn("a: idle", out)
        self.assertIn("--- final message ---\nALL DONE", out)
        self.assertIn("a: closed", out)
        self.assertEqual(self.reg(), {})
        self.assertNotIn("w1:p2", self.fake()["panes"])

    def test_brief_from_stdin(self):
        self.finish_next()
        self.ok("run", "a", "-", stdin="line one\nline two\n")
        self.assertIn("line one\nline two", self.fake()["calls"] and self.brief_of_closed())

    def brief_of_closed(self):
        return next(c[3] for c in self.fake()["calls"] if c[:2] == ["agent", "prompt"])

    def test_keep_skips_the_close(self):
        self.finish_next()
        out = self.ok("run", "a", "Do the task.", "--keep")
        self.assertIn("a: left open (--keep)", out)
        self.assertIn("a", self.reg())
        self.assertIn("w1:p2", self.fake()["panes"])

    def test_blocked_pane_stays_open_and_shows_its_prompt(self):
        self.change(lambda s: s.update(block_on_prompt=["a"]))
        out = self.ok("run", "a", "Do the task.")
        self.assertIn("--- waiting on this prompt ---", out)
        self.assertIn("Do you want to proceed?", out)
        self.assertIn("a: left open, blocked", out)
        self.assertIn("a", self.reg())
        self.assertIn("w1:p2", self.fake()["panes"])
        self.assertEqual(self.calls("pane", "close"), [])

    def test_timed_out_wait_leaves_the_pane_open(self):
        self.change(lambda s: s.update(busy_on_prompt=["a"]))
        out = self.ok("run", "a", "Do the task.", "--timeout", "3000")
        self.assertIn("a: working", out)
        self.assertIn("a: left open, the wait timed out", out)
        self.assertIn("a", self.reg())

    def test_pane_held_at_trust_stays_open(self):
        self.change(lambda s: s["start"].update(a="held"))
        out = self.ok("run", "a", "Do the task.", "--timeout", "3000")
        self.assertIn("held at a startup prompt", out)
        self.assertIn("a: left open, held at a startup prompt", out)
        self.assertIn("pending", self.entry("a"))

    def test_worktree_with_nothing_new_is_removed_on_close(self):
        repo = self.repo()
        self.finish_next()
        out = self.ok("run", "a", "Do the task.", "--worktree", "--cwd", repo)
        self.assertIn("a: closed, worktree removed", out)
        self.assertFalse(self.has_branch(repo, "drover/a"))

    def test_worktree_with_work_is_kept_by_the_close_rules(self):
        repo = self.repo()
        self.finish_next()
        self.ok("run", "a", "Do the task.", "--worktree", "--cwd", repo, "--keep")
        self.commit_file(self.wt_path(repo, "a"))
        out = self.ok("wait", "a", "--close")
        self.assertIn("a: pane closed, work kept", out)
        self.assertTrue(self.entry("a")["kept"])

    def test_gone_pane_is_not_closed(self):
        self.change(lambda s: s["start"].update(a="ok"))
        self.finish_next()
        self.ok("run", "a", "Do the task.", "--keep")
        self.close_pane_outside("a")
        out = self.ok("wait", "a", "--close")
        self.assertIn("a: left open, gone", out)

    def test_refused_inside_a_subagent(self):
        self.assertIn("cannot spawn", self.refused("run", "a", "x", env={"DROVER_CHILD": "1"}))


class Options(DroverCase):
    def argv(self, name):
        return self.fake()["start_argv"][name]

    def test_effort_is_passed_and_recorded(self):
        out = self.spawn("a", "--effort", "high")
        self.assertEqual(self.argv("a"), ["--permission-mode", "auto", "-n", "a", "--effort", "high"])
        self.assertEqual(self.entry("a")["effort"], "high")
        self.assertIn("effort high", out)

    def test_unknown_effort_is_refused(self):
        self.assertIn("invalid choice", self.refused("spawn", "a", "x", "--effort", "extreme"))

    def test_scout_preset_is_haiku_with_low_effort(self):
        self.spawn("a", "--preset", "scout")
        self.assertEqual(self.argv("a"), ["--permission-mode", "auto", "-n", "a", "--model", "haiku", "--effort", "low"])
        self.assertEqual((self.entry("a")["model"], self.entry("a")["effort"]), ("haiku", "low"))

    def test_build_preset_is_sonnet_with_medium_effort(self):
        self.spawn("a", "--preset", "build")
        self.assertEqual(self.argv("a")[-4:], ["--model", "sonnet", "--effort", "medium"])

    def test_explicit_flags_override_the_preset(self):
        self.spawn("a", "--preset", "scout", "--model", "sonnet", "--effort", "high")
        self.assertEqual(self.argv("a")[-4:], ["--model", "sonnet", "--effort", "high"])
        self.spawn("b", "--preset", "build", "--effort", "max")
        self.assertEqual(self.argv("b")[-4:], ["--model", "sonnet", "--effort", "max"])
        self.spawn("c", "--preset", "build", "--model", "haiku")
        self.assertEqual(self.argv("c")[-4:], ["--model", "haiku", "--effort", "medium"])

    def test_preset_applies_to_run(self):
        self.ok("run", "a", "x", "--preset", "scout", "--keep")
        self.assertEqual(self.argv("a")[-4:], ["--model", "haiku", "--effort", "low"])

    def test_lean_tools_adds_the_flags(self):
        out = self.spawn("a", "--tools", "lean")
        self.assertEqual(self.argv("a"), ["--permission-mode", "auto", "-n", "a"] + LEAN)
        self.assertEqual(self.entry("a")["tools"], "lean")
        self.assertIn("lean tools", out)

    def test_lean_tools_on_run(self):
        self.ok("run", "a", "x", "--tools", "lean", "--keep")
        self.assertEqual(self.argv("a")[-3:], LEAN)

    def test_default_has_no_lean_flags_and_no_extra_registry_keys(self):
        self.spawn("a")
        self.assertNotIn("--tools", self.argv("a"))
        self.assertNotIn("--strict-mcp-config", self.argv("a"))
        self.assertNotIn("tools", self.entry("a"))
        self.assertNotIn("effort", self.entry("a"))

    def test_only_lean_is_accepted(self):
        self.assertIn("invalid choice", self.refused("spawn", "a", "x", "--tools", "Bash"))

    def test_help_says_what_lean_loses(self):
        for cmd in ("spawn", "run"):
            out = self.ok(cmd, "--help")
            flat = " ".join(out.split())
            self.assertIn("cannot use Agent, Skill", flat)
            self.assertIn("any MCP server", flat)
            self.assertIn("Never the default", flat)

    def test_brief_tells_the_pane_not_to_poll(self):
        self.spawn("a")
        brief = self.brief("a")
        self.assertIn("Never poll", brief)
        self.assertIn("one blocking command or start one background job, then end your turn", brief)

    def test_resume_does_not_relaunch_panes(self):
        """Resume only reports state, so effort and tools are recorded for the registry's sake."""
        self.spawn("a", "--effort", "low", "--tools", "lean")
        self.close_pane_outside("a")
        self.ok("resume")
        self.assertEqual(len(self.fake()["start_argv"]), 1)
        self.assertEqual(self.entry("a")["effort"], "low")


class WaitMany(DroverCase):
    def setUp(self):
        super().setUp()
        for name in ("a", "b"):
            self.spawn(name)

    def test_prints_each_result_under_its_name(self):
        self.say("a", assistant_line("A DONE"))
        self.say("b", assistant_line("B DONE"))
        out = self.ok("wait", "a", "b")
        self.assertIn("a: idle\n--- final message ---\nA DONE", out)
        self.assertIn("b: idle\n--- final message ---\nB DONE", out)
        self.assertLess(out.index("A DONE"), out.index("B DONE"))
        self.assertNotIn("Returned early", out)

    def test_waits_for_a_slow_sibling(self):
        self.say("a", assistant_line("A DONE"))
        self.say("b", assistant_line("B DONE"))
        self.change_pane("b", steps=[{}, {}, {"status": "idle"}])
        self.set_status("b", "working")
        out = self.ok("wait", "a", "b")
        self.assertIn("A DONE", out)
        self.assertIn("B DONE", out)

    def test_returns_early_when_one_pane_blocks(self):
        self.say("a", assistant_line("A DONE"))
        self.set_status("a", "working")
        self.change_pane("a", busy=True)
        self.set_status("b", "blocked")
        self.change_pane("b", screen="Do you want to proceed?\n 1. Yes\n")
        out = self.ok("wait", "a", "b")
        self.assertIn("b: blocked", out)
        self.assertIn("--- waiting on this prompt ---", out)
        self.assertIn("Do you want to proceed?", out)
        self.assertIn("Returned early: b need(s) the user. Still running: a.", out)
        self.assertIn("drover wait b a", out)
        self.assertNotIn("A DONE", out)

    def test_settled_siblings_are_printed_when_another_blocks(self):
        self.say("a", assistant_line("A DONE"))
        self.set_status("a", "idle")
        self.set_status("b", "blocked")
        out = self.ok("wait", "a", "b")
        self.assertIn("A DONE", out)
        self.assertIn("Returned early: b need(s) the user.", out)
        self.assertNotIn("Still running", out)

    def test_close_closes_settled_panes_and_leaves_a_blocked_one(self):
        self.say("a", assistant_line("A DONE"))
        self.set_status("a", "idle")
        self.set_status("b", "blocked")
        out = self.ok("wait", "a", "b", "--close")
        self.assertIn("a: closed", out)
        self.assertIn("b: left open, blocked", out)
        self.assertEqual(list(self.reg()), ["b"])
        self.assertIn("w1:p3", self.fake()["panes"])
        self.assertNotIn("w1:p2", self.fake()["panes"])

    def test_close_after_all_settle(self):
        out = self.ok("wait", "a", "b", "--close")
        self.assertIn("a: closed", out)
        self.assertIn("b: closed", out)
        self.assertEqual(self.reg(), {})

    def test_timeout_leaves_working_panes_open(self):
        self.set_status("a", "working")
        self.change_pane("a", busy=True)
        self.set_status("b", "idle")
        out = self.ok("wait", "a", "b", "--timeout", "3000", "--close")
        self.assertIn("a: working", out)
        self.assertIn("a: left open, the wait timed out", out)
        self.assertIn("b: closed", out)
        self.assertEqual(list(self.reg()), ["a"])

    def test_gone_pane_is_reported_with_its_last_message(self):
        self.say("a", assistant_line("BEFORE IT DIED"))
        self.close_pane_outside("a")
        out = self.ok("wait", "a", "b")
        self.assertIn("a: gone", out)
        self.assertIn("BEFORE IT DIED", out)
        self.assertIn("b: idle", out)

    def test_unknown_name_is_refused_before_waiting(self):
        self.assertIn("no subagent named nope", self.refused("wait", "a", "nope"))

    def test_pane_held_at_trust_returns_early(self):
        self.change(lambda s: s["start"].update(c="held"))
        self.spawn("c")
        out = self.ok("wait", "a", "c", "--timeout", "5000")
        self.assertIn("c: held at a startup prompt", out)
        self.assertIn("Returned early: c need(s) the user.", out)

    def test_pane_that_moved_is_followed(self):
        self.say("a", assistant_line("A DONE"))
        self.move_pane("a")
        out = self.ok("wait", "a", "b")
        self.assertIn("A DONE", out)

    def test_background_jobs_keep_the_wait_holding(self):
        from tests.harness import job_line
        self.say("a", assistant_line("starting"), job_line("job1"))
        self.set_status("a", "idle")
        self.set_status("b", "idle")
        out = self.ok("wait", "a", "b", "--timeout", "40000", "--close")
        self.assertIn("a: paused with 1 background job(s) still running", out)
        self.assertIn("a: left open, paused with background jobs", out)
        self.assertEqual(list(self.reg()), ["a"])


class SingleWait(DroverCase):
    def test_one_name_prints_exactly_what_it_did_before(self):
        self.spawn("a")
        self.say("a", assistant_line("THE END"))
        self.assertEqual(self.ok("wait", "a"), "a: idle\n--- final message ---\nTHE END\n")

    def test_one_name_blocked_has_no_early_return_note(self):
        self.spawn("a")
        self.set_status("a", "blocked")
        out = self.ok("wait", "a")
        self.assertIn("--- waiting on this prompt ---", out)
        self.assertNotIn("Returned early", out)

    def test_one_name_close(self):
        self.spawn("a")
        out = self.ok("wait", "a", "--close")
        self.assertIn("a: idle", out)
        self.assertIn("a: closed", out)


if __name__ == "__main__":
    unittest.main()
