"""What spawn pastes into a brief: handoffs and CLAUDE.md files from outside the pane's folder."""
import os, unittest

from tests.harness import HerdCase


class Handoff(HerdCase):
    def handoff(self, name):
        return os.path.join(self.state_dir, "handoffs", name + ".md")

    def test_is_pasted_ahead_of_the_task(self):
        path = self.write(self.handoff("a"), "The code word is MANGOSTEEN.\n")
        out = self.spawn("a", brief="Use the code word.")
        brief = self.brief("a")
        self.assertIn(f"also saved at {path}", brief)
        self.assertLess(brief.index("MANGOSTEEN"), brief.index("Use the code word."))
        self.assertIn(f"handoff: brief points to {path}", out)

    def test_no_file_no_note(self):
        out = self.spawn("a")
        self.assertNotIn("handoff", out)
        self.assertNotIn("earlier work", self.brief("a"))

    def test_only_the_same_name_gets_it(self):
        self.write(self.handoff("other"), "NOT FOR YOU\n")
        self.spawn("a")
        self.assertNotIn("NOT FOR YOU", self.brief("a"))

    def test_reaches_a_worktree_subagent(self):
        repo = self.repo()
        self.write(self.handoff("a"), "MANGOSTEEN\n")
        out = self.spawn("a", "--cwd", repo, "--worktree")
        self.assertIn("MANGOSTEEN", self.brief("a"))
        self.assertIn("handoff:", out)

    def test_long_file_is_cut_and_says_where_the_rest_is(self):
        path = self.write(self.handoff("a"), "x" * 20500)
        self.spawn("a")
        brief = self.brief("a")
        self.assertIn("x" * 20000 + f"\n\n(cut off here, the rest is in {path})", brief)
        self.assertNotIn("x" * 20001, brief)

    def test_file_at_the_limit_is_whole(self):
        self.write(self.handoff("a"), "x" * 20000)
        self.spawn("a")
        self.assertNotIn("cut off here", self.brief("a"))


class ProjectContext(HerdCase):
    def setUp(self):
        super().setUp()
        self.project = self.mkdir("home", "project")
        self.inner = self.mkdir("home", "project", "app")
        self.outside = self.mkdir("home", "outside")
        self.top = self.write(os.path.join(self.project, "CLAUDE.md"), "TOP RULES\n")
        self.low = self.write(os.path.join(self.inner, "CLAUDE.md"), "APP RULES\n")

    def from_inner(self, name, *args):
        return self.ok("spawn", name, "Do the task.", *args, cwd=self.inner)

    def test_pane_outside_gets_every_file_around_the_primary(self):
        self.from_inner("a", "--cwd", self.outside)
        brief = self.brief("a")
        self.assertIn(f"Project context from {self.top}", brief)
        self.assertIn(f"Project context from {self.low}", brief)
        self.assertIn("TOP RULES", brief)
        self.assertIn("APP RULES", brief)

    def test_pane_in_the_same_folder_gets_nothing(self):
        self.from_inner("a")
        self.assertNotIn("Project context", self.brief("a"))

    def test_pane_in_a_subfolder_gets_nothing(self):
        self.from_inner("a", "--cwd", self.mkdir("home", "project", "app", "sub"))
        self.assertNotIn("Project context", self.brief("a"))

    def test_pane_in_a_sibling_gets_only_what_it_cannot_load(self):
        self.from_inner("a", "--cwd", self.mkdir("home", "project", "lib"))
        brief = self.brief("a")
        self.assertIn("APP RULES", brief)
        self.assertNotIn("TOP RULES", brief)

    def test_similar_folder_name_is_not_a_parent(self):
        self.from_inner("a", "--cwd", self.mkdir("home", "project", "app-two"))
        self.assertIn("APP RULES", self.brief("a"))

    def test_worktree_counts_as_outside(self):
        repo = self.repo()
        self.write(os.path.join(repo, "CLAUDE.md"), "REPO RULES\n")
        self.git(repo, "add", ".")
        self.git(repo, "commit", "-qm", "rules")
        self.ok("spawn", "a", "Do the task.", "--worktree", cwd=repo)
        self.assertIn("REPO RULES", self.brief("a"))

    def test_search_stops_at_home(self):
        self.write(os.path.join(self.home, "CLAUDE.md"), "HOME RULES\n")
        self.from_inner("a", "--cwd", self.outside)
        self.assertNotIn("HOME RULES", self.brief("a"))

    def test_long_file_is_cut(self):
        self.write(self.low, "y" * 20500)
        self.from_inner("a", "--cwd", self.outside)
        self.assertIn(f"(cut off here, the rest is in {self.low})", self.brief("a"))

    def test_context_comes_before_the_task_and_the_handoff(self):
        self.write(os.path.join(self.state_dir, "handoffs", "a.md"), "HANDOFF TEXT\n")
        self.from_inner("a", "--cwd", self.outside)
        brief = self.brief("a")
        self.assertLess(brief.index("APP RULES"), brief.index("HANDOFF TEXT"))
        self.assertLess(brief.index("HANDOFF TEXT"), brief.index("Do the task."))


if __name__ == "__main__":
    unittest.main()
