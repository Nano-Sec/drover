"""Saved reports: close keeps the last message under results/, and result reads it back."""
import os
import unittest

from tests.harness import DroverCase, assistant_line


class SavedResults(DroverCase):
    def path(self, name="a"):
        return os.path.join(self.state_dir, "results", name + ".md")

    def read(self, path):
        with open(path) as f:
            return f.read()

    def test_close_saves_the_last_message(self):
        self.spawn("a")
        self.say("a", assistant_line("FINAL WORDS"))
        self.set_status("a", "idle")
        out = self.ok("close", "a")
        self.assertIn(f"a: closed, report saved to {self.path()}", out)
        self.assertIn("FINAL WORDS", self.read(self.path()))
        self.assertEqual(self.reg(), {})

    def test_result_reads_the_saved_report_after_close(self):
        self.spawn("a")
        self.say("a", assistant_line("FINAL WORDS"))
        self.set_status("a", "idle")
        self.ok("close", "a")
        out = self.ok("result", "a")
        self.assertIn("a: closed", out)
        self.assertIn(self.path(), out)
        self.assertIn("FINAL WORDS", out)

    def test_wait_close_saves_too(self):
        self.spawn("a")
        self.say("a", assistant_line("WAITED"))
        self.set_status("a", "idle")
        out = self.ok("wait", "a", "--close")
        self.assertIn("report saved to", out)
        self.assertIn("WAITED", self.read(self.path()))

    def test_no_message_skips_the_file_and_still_closes(self):
        self.spawn("a")
        self.set_status("a", "idle")
        out = self.ok("close", "a")
        self.assertIn("a: closed", out)
        self.assertNotIn("report saved", out)
        self.assertFalse(os.path.exists(self.path()))
        self.assertEqual(self.reg(), {})

    def test_unknown_name_keeps_the_error(self):
        self.assertIn("no subagent named zz", self.refused("result", "zz"))

    def test_older_report_moves_to_prev(self):
        self.spawn("a")
        self.say("a", assistant_line("FIRST"))
        self.set_status("a", "idle")
        self.ok("close", "a")
        self.spawn("a")
        self.say("a", assistant_line("SECOND"))
        self.set_status("a", "idle")
        self.ok("close", "a")
        self.assertIn("SECOND", self.read(self.path()))
        self.assertIn("FIRST", self.read(self.path() + ".prev"))

    def test_state_dir_is_honored(self):
        self.spawn("a")
        self.say("a", assistant_line("HERE"))
        self.set_status("a", "idle")
        self.ok("close", "a")
        self.assertTrue(self.path().startswith(self.state_dir))
        self.assertTrue(os.path.exists(self.path()))

    def settle(self, text, name="a", *args):
        self.spawn(name, *args)
        self.say(name, assistant_line(text))
        self.set_status(name, "idle")

    def test_wait_saves_the_report_while_the_pane_stays_open(self):
        self.settle("OPEN REPORT", "a", "--keep")
        self.ok("wait", "a")
        self.assertIn("OPEN REPORT", self.read(self.path()))
        self.assertIn("a", self.reg())

    def test_close_does_not_rotate_an_unchanged_report(self):
        self.settle("SAME TEXT")
        self.ok("wait", "a")
        self.ok("close", "a")
        self.assertIn("SAME TEXT", self.read(self.path()))
        self.assertFalse(os.path.exists(self.path() + ".prev"))

    def test_long_report_is_cut_with_a_pointer(self):
        text = "\n".join(f"line {i:03d} " + "x" * 40 for i in range(100))
        self.settle(text)
        out = self.ok("wait", "a")
        self.assertIn("--- final message ---", out)
        self.assertIn("line 000", out)
        self.assertNotIn("line 099", out)
        self.assertIn("--- cut: showing", out)
        self.assertIn(self.path(), out)
        self.assertEqual(self.read(self.path()), text + "\n")

    def test_full_prints_everything_and_so_does_result(self):
        text = "\n".join(f"line {i:03d} " + "x" * 40 for i in range(100))
        self.settle(text)
        self.assertIn("line 099", self.ok("wait", "a", "--full"))
        self.assertNotIn("--- cut", self.ok("wait", "a", "--full"))
        self.assertIn("line 099", self.ok("result", "a"))

    def test_short_report_has_no_cut_line(self):
        self.settle("SHORT")
        self.assertNotIn("--- cut", self.ok("wait", "a"))

    def test_long_report_without_newlines_is_cut(self):
        self.spawn("b", "--keep")
        self.say("b", assistant_line("y" * 3000))
        self.set_status("b", "idle")
        self.assertIn("--- cut", self.ok("wait", "b"))


if __name__ == "__main__":
    unittest.main()
