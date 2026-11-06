"""wait and result: final messages, blocked prompts, and pauses on background jobs."""
import unittest

from tests.harness import HerdCase, assistant_line, job_line, notification_line


class Result(HerdCase):
    def setUp(self):
        super().setUp()
        self.spawn("a")

    def test_final_message_is_the_last_text(self):
        self.say("a", assistant_line("first"), assistant_line("the end"))
        out = self.ok("wait", "a")
        self.assertIn("a: idle", out)
        self.assertIn("--- final message ---\nthe end", out)
        self.assertNotIn("first", out)

    def test_sidechain_text_is_ignored(self):
        self.say("a", assistant_line("main"), assistant_line("from a sidechain", sidechain=True))
        self.assertIn("main", self.ok("wait", "a"))

    def test_damaged_lines_are_skipped(self):
        self.say("a", assistant_line("good"), '{"type": "assistant", "mess')
        self.assertIn("good", self.ok("wait", "a"))

    def test_empty_transcript(self):
        self.say("a", '{"type": "custom-title"}')
        self.assertIn("(none yet)", self.ok("wait", "a"))

    def test_missing_transcript_falls_back_to_the_screen(self):
        self.change_pane("a", screen="what the pane shows\n")
        out = self.ok("wait", "a")
        self.assertIn("no transcript found", out)
        self.assertIn("what the pane shows", out)

    def test_working_pane_reports_only_its_state(self):
        self.set_status("a", "working")
        self.say("a", assistant_line("old message"))
        out = self.ok("result", "a")
        self.assertIn("a: working", out)
        self.assertNotIn("old message", out)

    def test_blocked_pane_shows_its_prompt(self):
        self.set_status("a", "blocked")
        self.change_pane("a", screen="Do you want to proceed?\n 1. Yes\n")
        out = self.ok("wait", "a")
        self.assertIn("--- waiting on this prompt ---", out)
        self.assertIn("Do you want to proceed?", out)

    def test_gone_pane_gives_its_last_message(self):
        self.say("a", assistant_line("before it died"))
        self.close_pane_outside("a")
        out = self.ok("wait", "a")
        self.assertIn("a: gone", out)
        self.assertIn("before it died", out)

    def test_pane_dying_mid_wait_reports_gone(self):
        self.change_pane("a", steps=[{"gone": True}])
        self.assertIn("a: gone", self.ok("wait", "a"))

    def test_timed_out_wait_reports_working(self):
        self.change_pane("a", busy=True)
        self.assertIn("a: working", self.ok("wait", "a", "--timeout", "1000"))

    def test_unknown_name(self):
        self.assertIn("no subagent named nope", self.refused("wait", "nope"))
        self.assertIn("no subagent named nope", self.refused("result", "nope"))


class Pause(HerdCase):
    """An agent can end its turn with background jobs running. That is a pause, not the end."""

    def setUp(self):
        super().setUp()
        self.spawn("a")
        self.path = self.transcript("a")

    def launched(self, *jobs):
        self.say("a", *[job_line(j) for j in jobs], assistant_line("LAUNCHED"))
        self.set_status("a", "idle")

    def wakes(self, *lines):
        """The pane goes back to work and writes these lines, then settles."""
        return {"status": "working", "append": [[self.path, line] for line in lines]}

    def test_holds_through_a_pause_until_the_job_reports(self):
        self.launched("job1")
        self.change_pane("a", steps=[{}, self.wakes(notification_line("job1"), assistant_line("FINAL"))])
        out = self.ok("wait", "a")
        self.assertIn("FINAL", out)
        self.assertNotIn("LAUNCHED", out)
        self.assertNotIn("paused", out)
        self.assertEqual(len(self.calls("agent", "wait", self.entry("a")["pane"], "--until")), 1)

    def test_keeps_checking_while_nothing_happens(self):
        self.launched("job1")
        self.change_pane("a", steps=[{}, {}, {}, self.wakes(notification_line("job1"), assistant_line("FINAL"))])
        self.assertIn("FINAL", self.ok("wait", "a"))

    def test_job_that_finished_between_looks(self):
        self.launched("job1")
        self.change_pane("a", steps=[{}, {"append": [[self.path, notification_line("job1")],
                                                     [self.path, assistant_line("FINAL")]]}])
        self.assertIn("FINAL", self.ok("wait", "a"))

    def test_counts_every_job(self):
        self.launched("job1", "job2")
        self.change_pane("a", steps=[{}, self.wakes(notification_line("job1"), assistant_line("HALF")), {"status": "idle"},
                                     self.wakes(notification_line("job2"), assistant_line("FINAL"))])
        self.assertIn("FINAL", self.ok("wait", "a"))

    def test_job_already_reported_does_not_hold(self):
        self.launched("job1")
        self.say("a", notification_line("job1"), assistant_line("FINAL"))
        self.assertIn("FINAL", self.ok("wait", "a"))
        self.assertEqual(self.calls("agent", "wait", self.entry("a")["pane"], "--until"), [])

    def test_sidechain_jobs_do_not_count(self):
        line = job_line("job1").replace('"isSidechain": false', '"isSidechain": true')
        self.say("a", line, assistant_line("FINAL"))
        self.assertIn("FINAL", self.ok("wait", "a"))

    def test_foreground_tools_do_not_count(self):
        self.say("a", job_line("job1").replace('"run_in_background": true', '"run_in_background": false'), assistant_line("FINAL"))
        self.assertIn("FINAL", self.ok("wait", "a"))

    def test_gives_up_after_its_patience_and_says_so(self):
        self.launched("job1")
        out = self.ok("wait", "a", patience=3)
        self.assertIn("paused with 1 background job(s) still running", out)
        self.assertIn("LAUNCHED", out)

    def test_activity_resets_the_patience(self):
        self.launched("job1")
        self.change_pane("a", steps=[{}, {}, {}, {"status": "working"}, {"status": "idle"}, {}, {},
                                     self.wakes(notification_line("job1"), assistant_line("FINAL"))])
        self.assertIn("FINAL", self.ok("wait", "a", patience=4))

    def test_deadline_ends_the_pause(self):
        self.launched("job1")
        out = self.ok("wait", "a", "--timeout", "3000")
        self.assertIn("paused with 1 background job(s)", out)

    def test_blocked_during_a_pause_is_reported(self):
        self.launched("job1")
        self.change_pane("a", steps=[{}, {"status": "working"}, {"status": "blocked"}])
        self.assertIn("a: blocked", self.ok("wait", "a"))

    def test_pane_closed_during_a_pause_is_reported(self):
        self.launched("job1")
        self.change_pane("a", steps=[{}, {"status": "working"}, {"gone": True}])
        self.assertIn("a: gone", self.ok("wait", "a"))

    @unittest.expectedFailure
    def test_timed_wait_never_waits_past_its_deadline(self):
        """Known bug: each check during a pause lasts 30 seconds whatever is left, so a real
        wait --timeout 5000 took 32 seconds."""
        self.launched("job1")
        self.ok("wait", "a", "--timeout", "5000")
        checks = self.calls("agent", "wait", self.entry("a")["pane"], "--until")
        self.assertTrue(checks)
        for call in checks:
            self.assertLessEqual(int(call[call.index("--timeout") + 1]), 5000)


if __name__ == "__main__":
    unittest.main()
