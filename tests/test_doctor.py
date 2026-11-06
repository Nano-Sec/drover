"""doctor: what each result means, and that only real failures fail it."""
import os, unittest

from tests.harness import HerdCase, PRIMARY


class Doctor(HerdCase):
    def setUp(self):
        super().setUp()
        claude = self.write(os.path.join(self.root, "bin", "claude"), "#!/bin/sh\necho 2.1.319\n")
        os.chmod(claude, 0o755)

    def start(self, behaviour):
        self.change(lambda s: s["start"].update({"*": behaviour}))

    def test_all_good(self):
        out = self.ok("doctor")
        self.assertIn("PASS auto mode: a test pane started in auto mode", out)
        self.assertIn("PASS input box", out)
        self.assertTrue(out.rstrip().endswith("herd is ready"), out)
        self.assertNotIn("fix:", out)

    def test_test_pane_is_closed(self):
        self.ok("doctor")
        self.assertEqual(list(self.fake()["panes"]), [PRIMARY])
        self.assertEqual(self.calls("agent", "prompt"), [])

    def test_auto_refused_is_a_warning(self):
        self.start("no_auto")
        out = self.ok("doctor")
        self.assertIn("WARN auto mode: a test pane started in manual mode", out)
        self.assertIn("fix: check your Claude version", out)
        self.assertIn("it stops at approval prompts", out)
        self.assertIn("PASS input box", out)
        self.assertIn("herd is ready, with 1 warning(s)", out)

    def test_auto_refused_in_unknown_words_is_a_warning(self):
        self.start("no_auto_quiet")
        self.assertIn("WARN auto mode", self.ok("doctor"))

    def test_started_in_another_mode_is_a_warning(self):
        self.start("manual_footer")
        out = self.ok("doctor")
        self.assertIn("WARN auto mode: a test pane started in manual mode", out)
        self.assertIn("disableAutoMode", out)

    def test_warning_does_not_name_the_test_pane(self):
        self.start("no_auto")
        self.assertNotIn("herd-doctor", self.ok("doctor"))

    def test_claude_that_never_starts_fails(self):
        self.start("fail")
        out = self.refused("doctor")
        self.assertIn("FAIL auto mode: claude did not start", out)
        self.assertIn("SKIP input box", out)
        self.assertIn("1 of 9 checks failed", out)
        self.assertEqual(list(self.fake()["panes"]), [PRIMARY])

    def test_unreadable_footer_fails(self):
        self.start("no_footer")
        self.assertIn("FAIL auto mode: could not find the permission mode", self.refused("doctor"))

    def test_held_at_trust_prompt_skips_both(self):
        self.start("held")
        out = self.ok("doctor")
        self.assertIn("SKIP auto mode", out)
        self.assertIn("SKIP input box", out)

    def test_missing_input_box_still_fails(self):
        self.start("no_box")
        self.assertIn("FAIL input box: could not find the input box", self.refused("doctor"))

    def test_herdr_below_the_oldest_tested_version_fails(self):
        self.change(lambda s: s.update(version="0.7.9"))
        out = self.refused("doctor")
        self.assertIn("FAIL herdr: 0.7.9, the oldest tested version is 0.8.0", out)

    def test_newer_herdr_passes(self):
        self.change(lambda s: s.update(version="0.9.1"))
        self.assertIn("PASS herdr: 0.9.1, the oldest tested version is 0.8.0", self.ok("doctor"))

    def test_stale_integration_fails(self):
        self.change(lambda s: s.update(integration="outdated"))
        self.assertIn("FAIL claude integration: outdated", self.refused("doctor"))

    def test_subagent_pane_skips_the_probe(self):
        out = self.ok("doctor", env={"HERD_CHILD": "1"})
        self.assertIn("SKIP auto mode: a herd subagent cannot open panes", out)
        self.assertEqual(self.calls("pane", "split"), [])


if __name__ == "__main__":
    unittest.main()
