"""wrapup: who gets asked, who is skipped, and what happens to older handoffs."""
import os, unittest

from tests.harness import HerdCase


class Wrapup(HerdCase):
    def setUp(self):
        super().setUp()
        self.handoffs = os.path.join(self.state_dir, "handoffs")

    def settled(self, *names):
        for name in names:
            self.spawn(name)
            self.ok("wait", name)

    def handoff(self, name):
        return os.path.join(self.handoffs, name + ".md")

    def told(self, name):
        return [p for p in self.pane(name)["prompts"] if "wrap up and hand off" in p]

    def test_by_name_asks_only_that_pane(self):
        self.settled("a", "b")
        out = self.ok("wrapup", "a")
        self.assertIn(f"a: asked, handoff due at {self.handoff('a')}", out)
        self.assertNotIn("b:", out)
        self.assertEqual(len(self.told("a")), 1)
        self.assertEqual(self.told("b"), [])

    def test_message_names_the_handoff_path_and_the_rules(self):
        self.settled("a")
        self.ok("wrapup", "a")
        text = self.told("a")[0]
        self.assertIn(f"Write a handoff to {self.handoff('a')}", text)
        self.assertIn("Never push", text)
        self.assertIn("Status, Decisions and why, Next steps, Open questions", text)

    def test_default_is_everyone(self):
        self.settled("a", "b")
        out = self.ok("wrapup")
        self.assertIn("for each of: a, b", out)

    def test_repeated_names_are_asked_once(self):
        self.settled("a")
        self.ok("wrapup", "a", "a")
        self.assertEqual(len(self.told("a")), 1)

    def test_unknown_name_stops_before_anything_is_sent(self):
        self.settled("a")
        self.assertIn("no subagent named nope", self.refused("wrapup", "a", "nope"))
        self.assertEqual(self.told("a"), [])

    def test_no_subagents(self):
        self.assertIn("no subagents", self.refused("wrapup"))

    def test_older_handoff_moves_aside(self):
        self.settled("a")
        self.write(self.handoff("a"), "STALE\n")
        self.ok("wrapup", "a")
        self.assertFalse(os.path.exists(self.handoff("a")))
        with open(self.handoff("a") + ".prev") as f:
            self.assertEqual(f.read(), "STALE\n")

    def test_failed_send_restores_the_handoff(self):
        self.settled("a")
        self.write(self.handoff("a"), "STALE\n")
        pane = self.entry("a")["pane"]
        self.change(lambda s: s["prompt_fail"].append(pane))
        out = self.ok("wrapup", "a")
        self.assertIn("a: send failed, skipped", out)
        self.assertIn("no panes were asked", out)
        with open(self.handoff("a")) as f:
            self.assertEqual(f.read(), "STALE\n")

    def test_gone_pane_is_skipped(self):
        self.settled("a")
        self.close_pane_outside("a")
        out = self.ok("wrapup")
        self.assertIn("a: gone, skipped", out)
        self.assertIn("no panes were asked", out)

    def test_blocked_pane_is_skipped_even_with_force(self):
        self.settled("a")
        self.set_status("a", "blocked")
        self.write(self.handoff("a"), "STALE\n")
        self.assertIn("a: blocked on a prompt, skipped", self.ok("wrapup", "--force"))
        self.assertEqual(self.pane("a")["keys"], [])
        self.assertNotIn("answered", self.pane("a"))
        self.assertTrue(os.path.exists(self.handoff("a")))

    def test_held_pane_is_skipped(self):
        self.change(lambda s: s["start"].update(held="held"))
        self.spawn("held")
        self.assertIn("held: blocked on a prompt, skipped", self.ok("wrapup"))
        self.assertEqual(self.pane("held")["prompts"], [])

    def test_unsent_text_is_skipped(self):
        self.settled("a")
        self.change_pane("a", draft="my thought")
        self.write(self.handoff("a"), "STALE\n")
        self.assertIn("a: unsent text in its input box, skipped", self.ok("wrapup"))
        self.assertEqual(self.pane("a")["draft"], "my thought")
        self.assertTrue(os.path.exists(self.handoff("a")))

    def test_force_discards_unsent_text_first(self):
        self.settled("a")
        self.change_pane("a", draft="my thought")
        self.assertIn("a: asked", self.ok("wrapup", "--force"))
        self.assertNotIn("my thought", self.told("a")[0])

    def test_draft_that_will_not_clear_is_skipped(self):
        self.settled("a")
        self.change_pane("a", draft="stuck", stuck_draft=True)
        self.assertIn("a: could not clear its unsent text, skipped", self.ok("wrapup", "--force"))
        self.assertEqual(self.told("a"), [])

    def test_working_pane_gets_it_without_a_wait(self):
        self.spawn("a")
        self.assertIn("a: asked", self.ok("wrapup"))
        self.assertEqual(len(self.told("a")), 1)
        self.assertNotIn("--wait", self.calls("agent", "prompt")[-1])

    def test_working_pane_with_a_draft_is_skipped(self):
        self.spawn("a")
        self.change_pane("a", draft="typing while it works")
        self.assertIn("unsent text", self.ok("wrapup"))

    def test_hint_lists_exactly_the_panes_asked(self):
        self.settled("a", "b", "c")
        self.set_status("b", "blocked")
        self.close_pane_outside("c")
        self.assertIn("for each of: a\n", self.ok("wrapup"))

    def test_moved_pane_is_not_called_gone(self):
        self.settled("a")
        new = self.move_pane("a")
        self.assertIn("a: asked", self.ok("wrapup", "a"))
        self.assertEqual(self.entry("a")["pane"], new)
        self.assertEqual(len(self.told("a")), 1)


if __name__ == "__main__":
    unittest.main()
