"""Real samples of Claude's and herdr's output, run through the helper.

Everything in fixtures/ was captured from Claude Code 2.1.319 and herdr 0.8.0, with paths and
ids replaced, except the screens named synthetic_. If Claude changes a format, recapture the
sample: a failure here then shows which assumption in the helper no longer holds.
"""
import json, subprocess, unittest

from tests import formats
from tests.harness import HerdCase, fixture

TRANSCRIPTS = ["background_running.jsonl", "background_finished.jsonl", "background_stopped.jsonl",
               "background_moved.jsonl", "background_moved_finished.jsonl"]
EMPTY_BOX = ["idle_empty", "idle_shell_running", "synthetic_ghost_suggestion", "synthetic_cursor_only",
             "synthetic_footer_text"]
TYPED_BOX = ["draft_one_line", "draft_two_lines", "draft_long_scrolled", "draft_empty_first_line",
             "draft_box_cut_off", "synthetic_blank_window"]
NO_BOX = ["draft_box_off_screen", "synthetic_old_prompt_above", "synthetic_box_cut_off_empty"]


def herdr_sample(name):
    return json.loads(fixture("herdr", name + ".json"))["result"]


def entries(name):
    return [json.loads(line) for line in fixture("transcripts", name).splitlines()]


def tool_use(name, tool):
    return next(c for d in entries(name) if d["type"] == "assistant" for c in d["message"]["content"]
                if c["type"] == "tool_use" and c["name"] == tool)


def result_of(name, use):
    """The entry and tool_result block answering one tool_use."""
    return next((d, c) for d in entries(name) if d["type"] == "user" and isinstance(d["message"]["content"], list)
                for c in d["message"]["content"] if c.get("tool_use_id") == use["id"])


class Transcripts(HerdCase):
    def setUp(self):
        super().setUp()
        self.spawn("a")
        self.set_status("a", "idle")

    def test_samples_have_the_expected_shape(self):
        for name in TRANSCRIPTS:
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

    def test_stopped_job_is_not_a_pause(self):
        self.use_transcript("a", "background_stopped.jsonl")
        self.assertNotIn("paused", self.ok("wait", "a", "--timeout", "3000"))

    def test_rejected_job_is_not_a_pause(self):
        self.use_transcript("a", "background_rejected.jsonl")
        self.assertNotIn("paused", self.ok("wait", "a", "--timeout", "3000"))

    def test_moved_job_is_a_pause(self):
        self.use_transcript("a", "background_moved.jsonl")
        out = self.ok("wait", "a", "--timeout", "3000")
        self.assertIn("paused with 1 background job(s)", out)
        self.assertIn("--- final message ---\nLAUNCHED", out)

    def test_finished_moved_job_is_not_a_pause(self):
        self.use_transcript("a", "background_moved_finished.jsonl")
        out = self.ok("wait", "a", "--timeout", "3000")
        self.assertNotIn("paused", out)
        self.assertIn("MOVED_FINAL", out)

    def test_samples_have_the_fields_jobs_are_read_from(self):
        job = tool_use("background_stopped.jsonl", "Bash")
        self.assertTrue(job["input"]["run_in_background"])
        task = result_of("background_stopped.jsonl", job)[0]["toolUseResult"]["backgroundTaskId"]
        stop = result_of("background_stopped.jsonl", tool_use("background_stopped.jsonl", "TaskStop"))[0]
        self.assertEqual(stop["toolUseResult"]["task_id"], task, "TaskStop result no longer names the job's task id")

        rejected = result_of("background_rejected.jsonl", tool_use("background_rejected.jsonl", "Bash"))[1]
        self.assertIs(rejected["is_error"], True, "a rejected command's tool_result is no longer is_error true")

        moved = tool_use("background_moved.jsonl", "Bash")
        self.assertNotIn("run_in_background", moved["input"])
        task = result_of("background_moved.jsonl", moved)[0]["toolUseResult"]["backgroundTaskId"]
        notes = fixture("transcripts", "background_moved_finished.jsonl")
        self.assertIn(f"<task-id>{task}</task-id>", notes)
        self.assertIn(f"<tool-use-id>{moved['id']}</tool-use-id>", notes)

    def test_a_renamed_field_falls_back_to_counting_as_before(self):
        """If Claude renames a field, a job that ended still counts as running, which only costs
        time, and a moved job goes unseen, as it did before herd read that field."""
        for sample, field in [("background_stopped.jsonl", "task_id"), ("background_stopped.jsonl", "backgroundTaskId"),
                              ("background_rejected.jsonl", "is_error")]:
            self.say_changed(sample, field)
            self.assertIn("paused with 1 background job(s)", self.ok("wait", "a", "--timeout", "3000"), field)
        self.say_changed("background_moved.jsonl", "backgroundTaskId")
        self.assertNotIn("paused", self.ok("wait", "a", "--timeout", "3000"))

    def say_changed(self, sample, field):
        with open(self.transcript("a"), "w", encoding="utf-8") as f:
            f.write(fixture("transcripts", sample).replace(f'"{field}"', '"renamed"'))


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

    def test_box_out_of_view_refuses_a_message(self):
        for name in NO_BOX:
            self.show(name)
            self.assertIn("could not find the input box", self.refused("send", "a", "hi"), name)
        self.assertEqual(len(self.pane("a")["prompts"]), 1)

    def test_force_clears_a_draft_under_an_empty_line(self):
        self.change_pane("a", draft="\n  lower line")
        self.assertIn("unsent text", self.refused("send", "a", "hi"))
        self.ok("send", "a", "hi", "--force")
        self.assertEqual(self.pane("a")["prompts"][-1], "hi")

    def test_force_gives_up_on_a_line_that_stays_below_the_cursor(self):
        self.show("draft_empty_first_line")
        self.assertIn("could not clear", self.refused("send", "a", "hi", "--force"))
        self.assertEqual(len(self.pane("a")["prompts"]), 1)
        keys = self.pane("a")["keys"]
        self.assertEqual(len(keys), 20)
        self.assertIn("ctrl+k", keys[0], "nothing deletes the lines below the cursor")

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
