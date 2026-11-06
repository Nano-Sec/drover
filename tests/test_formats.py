"""Real samples of Claude's and herdr's output, run through the helper.

Everything in fixtures/ was captured from Claude Code 2.1.319 and herdr 0.8.0, with paths and
ids replaced, except the screens named synthetic_. If Claude changes a format, recapture the
sample: a failure here then shows which assumption in the helper no longer holds.
"""
import json, subprocess, unittest

from tests import formats
from tests.harness import HerdCase, fixture

TRANSCRIPTS = ["background_running.jsonl", "background_finished.jsonl", "background_stopped.jsonl", "background_rejected.jsonl"]
EMPTY_BOX = ["idle_empty", "idle_shell_running", "synthetic_ghost_suggestion", "synthetic_cursor_only"]
TYPED_BOX = ["draft_one_line", "draft_two_lines", "draft_long_scrolled"]


def herdr_sample(name):
    return json.loads(fixture("herdr", name + ".json"))["result"]


class Transcripts(HerdCase):
    def setUp(self):
        super().setUp()
        self.spawn("a")
        self.set_status("a", "idle")

    def test_samples_have_the_expected_shape(self):
        for name in TRANSCRIPTS[:3]:
            self.assertEqual(formats.transcript_problems(fixture("transcripts", name)), [], name)

    def test_shape_check_catches_a_change(self):
        changed = json.dumps({"type": "assistant", "isSidechain": False, "message": {"content": "plain string"}})
        self.assertIn("transcript line 1: assistant message.content is not a list", formats.transcript_problems(changed))
        self.assertIn("no <tool-use-id>", formats.transcript_problems('{"x": "<task-notification>"}')[0])

    def test_running_job_is_a_pause(self):
        self.use_transcript("a", "background_running.jsonl")
        out = self.ok("wait", "a", "--timeout", "3000")
        self.assertIn("paused with 1 background job(s)", out)
        self.assertIn("--- final message ---\nLAUNCHED", out)

    def test_finished_job_is_not_a_pause(self):
        self.use_transcript("a", "background_finished.jsonl")
        out = self.ok("wait", "a", "--timeout", "3000")
        self.assertNotIn("paused", out)
        self.assertIn("PAUSE_FINAL", out)

    def test_text_is_found_after_tool_blocks(self):
        self.use_transcript("a", "background_stopped.jsonl")
        self.assertIn("STOPPED", self.ok("result", "a"))

    @unittest.expectedFailure
    def test_stopped_job_is_not_a_pause(self):
        """Known bug: TaskStop writes no task notification, so a job the agent stopped itself
        counts as running and a real wait holds for the full 30 minutes."""
        self.use_transcript("a", "background_stopped.jsonl")
        self.assertNotIn("paused", self.ok("wait", "a", "--timeout", "3000"))

    @unittest.expectedFailure
    def test_rejected_job_is_not_a_pause(self):
        """Known bug: a background command the user rejected never ran, but it counts as
        running because its tool_result (is_error true) is not read."""
        self.use_transcript("a", "background_rejected.jsonl")
        self.assertNotIn("paused", self.ok("wait", "a", "--timeout", "3000"))


class Screens(HerdCase):
    def setUp(self):
        super().setUp()
        self.spawn("a")
        self.ok("wait", "a")

    def show(self, name):
        self.change_pane("a", screen=fixture("screens", name + ".ansi"))

    def test_samples_have_an_input_line(self):
        for name in EMPTY_BOX + TYPED_BOX:
            self.assertEqual(formats.screen_problems(fixture("screens", name + ".ansi")), [], name)

    def test_shape_check_catches_a_change(self):
        self.assertTrue(formats.screen_problems("> typed\n"))

    def test_empty_box_lets_a_message_through(self):
        for name in EMPTY_BOX:
            self.show(name)
            self.assertIn("sent to a", self.ok("send", "a", "hi"), name)
            self.set_status("a", "idle")

    def test_typed_text_refuses_a_message(self):
        for name in TYPED_BOX:
            self.show(name)
            self.assertIn("unsent text", self.refused("send", "a", "hi"), name)

    def test_permission_prompt_is_shown(self):
        self.show("permission_prompt")
        self.set_status("a", "blocked")
        out = self.ok("result", "a")
        self.assertIn("Do you want to proceed?", out)
        self.assertIn("4. No", out)

    def test_trust_prompt_is_shown(self):
        self.show("trust_prompt")
        self.set_status("a", "blocked")
        self.assertIn("Yes, I trust this folder", self.ok("result", "a"))


class Herdr(HerdCase):
    def fake_says(self, *args):
        p = subprocess.run(["herdr", *args], env=self.env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)["result"]

    def test_real_samples_have_the_expected_shape(self):
        self.assertEqual(formats.agent_problems(herdr_sample("agent_list")["agents"][0]), [])
        self.assertEqual(formats.agent_problems(herdr_sample("agent_start")["agent"]), [])
        self.assertEqual(formats.layout_problems(herdr_sample("pane_layout")["layout"]), [])
        self.assertIn("pane_id", herdr_sample("pane_split")["pane"])
        self.assertIn("pane_id", herdr_sample("tab_create")["root_pane"])

    def test_held_agent_has_no_session(self):
        agent = herdr_sample("agent_list_held")["agents"][0]
        self.assertEqual(formats.agent_problems(agent, session=False), [])
        self.assertNotIn("agent_session", agent)
        self.assertEqual(agent["agent_status"], "blocked")

    def test_fake_answers_in_the_same_shape(self):
        self.spawn("a")
        self.assertEqual(formats.agent_problems(self.fake_says("agent", "list")["agents"][1]), [])
        self.assertEqual(formats.agent_problems(self.fake_says("agent", "get", "a")["agent"]), [])
        self.assertEqual(formats.layout_problems(self.fake_says("pane", "layout", "--pane", "w1:p1")["layout"]), [])
        real = set(herdr_sample("agent_list")["agents"][0]) - {"terminal_title", "terminal_title_stripped"}
        self.assertLessEqual(real, set(self.fake_says("agent", "get", "a")["agent"]))

    def test_shape_check_catches_a_change(self):
        self.assertIn("agent record has no agent_session.value", formats.agent_problems({"agent_status": "idle"}))
        self.assertIn("layout has no panes", formats.layout_problems({"area": {"width": 1, "height": 1}}))


if __name__ == "__main__":
    unittest.main()
