"""wait and result: final messages, blocked prompts, and pauses on background jobs."""
import json, unittest

from tests.harness import HerdCase, assistant_line, job_line, notification_line


def tool_use_line(tool, name="Bash", **inputs):
    return json.dumps({"type": "assistant", "isSidechain": False, "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": tool, "name": name, "input": inputs}]}})


def tool_result_line(tool, outcome=None, sidechain=False, **fields):
    return json.dumps({"type": "user", "isSidechain": sidechain, "toolUseResult": outcome, "message": {
        "role": "user", "content": [{"type": "tool_result", "tool_use_id": tool, "content": "text", **fields}]}})


def task_notification_line(task):
    """A notification that names only the task id."""
    return json.dumps({"type": "queue-operation", "content": f"<task-notification>\n<task-id>{task}</task-id>\n</task-notification>"})


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
        self.say("a")
        self.assertIn("(none yet)", self.ok("wait", "a"))

    def test_reply_without_text_is_none_yet(self):
        self.say("a", tool_use_line("t1", command="ls"))
        self.assertIn("(none yet)", self.ok("wait", "a"))

    def test_no_assistant_entries_falls_back_to_the_screen(self):
        """This may be no reply yet or a changed format, and herd cannot tell which, so it says so."""
        self.say("a", '{"type": "custom-title"}')
        self.change_pane("a", screen="what the pane shows\n")
        out = self.ok("wait", "a")
        self.assertIn("there is no reply yet", out)
        self.assertIn("what the pane shows", out)
        self.assertNotIn("(none yet)", out)

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

    def looks(self):
        checks = self.calls("agent", "wait", self.entry("a")["pane"], "--until")
        self.assertTrue(checks)
        return [int(call[call.index("--timeout") + 1]) for call in checks]

    def test_timed_wait_never_waits_past_its_deadline(self):
        self.launched("job1")
        self.ok("wait", "a", "--timeout", "5000")
        self.assertLessEqual(max(self.looks()), 5000)

    def test_untimed_wait_looks_in_full_slices(self):
        self.launched("job1")
        self.ok("wait", "a", patience=3)
        self.assertEqual(set(self.looks()), {30000})

    def test_deadline_covers_the_wait_for_a_held_brief(self):
        self.launched("job1")
        self.change(lambda s: s["panes"][self.entry("a")["pane"]]["agent"].update(agent_status="blocked"))
        reg = self.reg()
        reg["a"]["pending"] = "the brief"
        self.save_reg(reg)
        self.ok("wait", "a", "--timeout", "4000")
        for call in self.calls("agent", "wait", self.entry("a")["pane"]):
            self.assertLessEqual(int(call[call.index("--timeout") + 1]), 1)


class JobEnds(HerdCase):
    """The ways a job ends without the notification naming its tool use id, and the shapes that must
    not count as an end, because a wait that stops early loses the agent's real final message."""

    def setUp(self):
        super().setUp()
        self.spawn("a")
        self.set_status("a", "idle")

    def holds(self, *lines):
        self.say("a", *lines, assistant_line("LAST"))
        self.assertIn("paused with 1 background job(s)", self.ok("wait", "a", "--timeout", "3000"))

    def done(self, *lines):
        self.say("a", *lines, assistant_line("LAST"))
        self.assertNotIn("paused", self.ok("wait", "a", "--timeout", "3000"))

    started = [job_line("j1"), tool_result_line("j1", {"backgroundTaskId": "b1"}, is_error=False)]
    stop = [tool_use_line("s1", "TaskStop", task_id="b1")]

    def test_stopped_job_ends(self):
        self.done(*self.started, *self.stop, tool_result_line("s1", {"task_id": "b1", "message": "stopped"}))

    def test_stop_of_another_task_does_not_end_it(self):
        self.holds(*self.started, *self.stop, tool_result_line("s1", {"task_id": "b2"}))

    def test_failed_stop_does_not_end_it(self):
        self.holds(*self.started, *self.stop, tool_result_line("s1", "Error: no such task", is_error=True))

    def test_task_id_from_another_tool_does_not_end_it(self):
        self.holds(*self.started, tool_use_line("o1", "TaskOutput"), tool_result_line("o1", {"task_id": "b1"}))

    def test_stop_without_the_task_id_field_falls_back_to_running(self):
        self.holds(*self.started, *self.stop, tool_result_line("s1", {"id": "b1"}))

    def test_stop_cannot_match_a_job_with_no_recorded_task_id(self):
        self.holds(job_line("j1"), tool_result_line("j1", {"id": "b1"}), *self.stop, tool_result_line("s1", {"task_id": "b1"}))

    def test_rejected_job_ends(self):
        self.done(job_line("j1"), tool_result_line("j1", "User rejected tool use", is_error=True))

    def test_error_on_another_tool_does_not_end_it(self):
        self.holds(*self.started, tool_result_line("x1", "failed", is_error=True))

    def test_truthy_is_error_of_another_type_falls_back_to_running(self):
        self.holds(job_line("j1"), tool_result_line("j1", "odd", is_error="true"))

    def test_moved_job_is_a_pause(self):
        self.holds(tool_use_line("j1", command="make test"), tool_result_line("j1", {"backgroundTaskId": "b1", "timedOutAfterMs": 120000}))

    def test_moved_job_ends_by_tool_use_id(self):
        self.done(tool_use_line("j1", command="make"), tool_result_line("j1", {"backgroundTaskId": "b1"}), notification_line("j1"))

    def test_moved_job_ends_by_task_id(self):
        self.done(tool_use_line("j1", command="make"), tool_result_line("j1", {"backgroundTaskId": "b1"}), task_notification_line("b1"))

    def test_moved_job_ends_when_stopped(self):
        self.done(tool_use_line("j1", command="make"), tool_result_line("j1", {"backgroundTaskId": "b1"}),
                  *self.stop, tool_result_line("s1", {"task_id": "b1"}))

    def test_job_is_counted_once_with_both_marks(self):
        self.holds(*self.started)

    def test_sidechain_moved_job_does_not_count(self):
        self.done(tool_result_line("j1", {"backgroundTaskId": "b1"}, sidechain=True))

    def test_foreground_result_is_not_a_job(self):
        self.done(tool_use_line("j1", command="ls"), tool_result_line("j1", {"stdout": "x"}, is_error=False))

    def test_text_about_jobs_in_a_result_is_not_a_job(self):
        quoted = '"backgroundTaskId": "b9" <tool-use-id>j1</tool-use-id>'
        self.done(tool_use_line("r1", "Read"), tool_result_line("r1", {"file": quoted}))

    def test_unknown_result_shapes_are_skipped(self):
        odd = [json.dumps({"type": "user", "toolUseResult": {"backgroundTaskId": ["b1"], "task_id": 7},
                           "message": {"content": [{"type": "tool_result", "tool_use_id": ["j1"]}]}}),
               json.dumps({"type": "user", "toolUseResult": {"backgroundTaskId": 7},
                           "message": {"content": [{"type": "tool_result", "tool_use_id": "j2"}]}}),
               json.dumps({"type": "user", "message": {"content": 7}, "x": "tool_result"})]
        self.holds(*self.started, *odd)


if __name__ == "__main__":
    unittest.main()
