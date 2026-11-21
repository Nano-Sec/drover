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


if __name__ == "__main__":
    unittest.main()
