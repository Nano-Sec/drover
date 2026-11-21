"""Pinned panes: spawn --keep, the keep command, and what honors a pin."""
import unittest

from tests.harness import DroverCase, assistant_line


class Pin(DroverCase):
    def test_spawn_keep_stores_a_pin(self):
        self.spawn("a", "--keep")
        self.assertTrue(self.entry("a")["pinned"])
        self.assertNotIn("kept", self.entry("a"))

    def test_spawn_without_keep_is_not_pinned(self):
        self.spawn("a")
        self.assertNotIn("pinned", self.entry("a"))

    def test_run_keep_still_leaves_the_pane_open_and_pins_it(self):
        self.write(f"{self.projects}/-sandbox/session-1.jsonl", assistant_line("DONE") + "\n")
        out = self.ok("run", "a", "Do the task.", "--keep")
        self.assertIn("a: left open (--keep)", out)
        self.assertTrue(self.entry("a")["pinned"])
        self.assertIn("w1:p2", self.fake()["panes"])

    def test_keep_pins_and_off_unpins(self):
        self.spawn("a")
        self.spawn("b")
        out = self.ok("keep", "a", "b")
        self.assertIn("a: pinned", out)
        self.assertTrue(self.entry("a")["pinned"] and self.entry("b")["pinned"])
        self.assertIn("a: unpinned", self.ok("keep", "--off", "a"))
        self.assertNotIn("pinned", self.entry("a"))
        self.assertTrue(self.entry("b")["pinned"])

    def test_keep_refuses_unknown_names_and_changes_nothing(self):
        self.spawn("a")
        out = self.refused("keep", "a", "nope")
        self.assertIn("no subagent named nope", out)
        self.assertNotIn("pinned", self.entry("a"))

    def test_keep_refuses_a_gone_pane(self):
        self.spawn("a")
        self.close_pane_outside("a")
        self.assertIn("a is gone", self.refused("keep", "a"))
        self.assertNotIn("pinned", self.entry("a"))

    def test_wait_close_skips_a_pinned_pane(self):
        self.spawn("a")
        self.spawn("b")
        self.ok("keep", "a")
        out = self.ok("wait", "a", "b", "--close")
        self.assertIn("a: left open (pinned)", out)
        self.assertIn("b: closed", out)
        self.assertEqual(list(self.reg()), ["a"])
        self.assertIn(self.entry("a")["pane"], self.fake()["panes"])

    def test_single_wait_close_skips_a_pinned_pane(self):
        self.spawn("a", "--keep")
        out = self.ok("wait", "a", "--close")
        self.assertIn("a: left open (pinned)", out)
        self.assertIn("a", self.reg())

    def test_close_all_skips_pinned_panes(self):
        self.spawn("a")
        self.spawn("b")
        self.ok("keep", "a")
        out = self.ok("close", "--all", "--force")
        self.assertIn("a: left open (pinned)", out)
        self.assertIn("b: closed", out)
        self.assertEqual(list(self.reg()), ["a"])

    def test_explicit_close_still_closes_a_pinned_pane(self):
        self.spawn("a", "--keep")
        pane = self.entry("a")["pane"]
        self.assertIn("a: closed", self.ok("close", "a", "--force"))
        self.assertNotIn(pane, self.fake()["panes"])
        self.assertEqual(self.reg(), {})

    def test_wrapup_is_unaffected_by_a_pin(self):
        self.spawn("a", "--keep")
        self.ok("wait", "a")
        out = self.ok("wrapup", "a")
        self.assertNotIn("pinned", out)

    def test_status_marks_a_pinned_pane(self):
        self.spawn("a", "--keep")
        self.spawn("b")
        lines = {l.split()[0]: l for l in self.ok("status").splitlines()[1:]}
        self.assertTrue(lines["a"].endswith("pinned"))
        self.assertNotIn("pinned", lines["b"])

    def test_resume_shows_a_pinned_pane(self):
        self.spawn("a", "--keep")
        self.assertIn("pinned: wait --close and close --all leave it open", self.ok("resume"))


if __name__ == "__main__":
    unittest.main()
