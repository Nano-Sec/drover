"""Worktree creation, reattaching, and the rules for keeping or removing work on close."""
import os, shutil, unittest

from tests.harness import HerdCase


class WorktreeCase(HerdCase):
    def setUp(self):
        super().setUp()
        self.base = self.repo()

    def wt(self, name, *args):
        return self.spawn(name, "--cwd", self.base, "--worktree", *args)

    def settled(self, name, *args):
        out = self.wt(name, *args)
        self.ok("wait", name)
        return out

    def path(self, name):
        return self.wt_path(self.base, name)


class Create(WorktreeCase):
    def test_new_worktree_and_branch(self):
        out = self.wt("a")
        path = self.path("a")
        self.assertTrue(os.path.isfile(os.path.join(path, "a.txt")))
        self.assertTrue(self.has_branch(self.base, "herd/a"))
        self.assertIn("worktree created: branch herd/a", out)
        self.assertEqual(self.pane("a")["cwd"], path)
        e = self.entry("a")
        self.assertEqual(e["cwd"], path)
        self.assertEqual(e["worktree"], {"path": path, "branch": "herd/a", "base_repo": self.base,
                                         "base_ref": "refs/heads/main", "created_branch": True})

    def test_custom_branch(self):
        self.wt("a", "feature/x")
        self.assertTrue(self.has_branch(self.base, "feature/x"))
        self.assertEqual(self.entry("a")["worktree"]["branch"], "feature/x")

    def test_brief_explains_the_worktree(self):
        self.wt("a")
        brief = self.brief("a")
        self.assertIn(f"own git worktree at {self.path('a')}, on branch herd/a", brief)
        self.assertNotIn("already holds earlier work", brief)

    def test_status_shows_the_branch(self):
        self.wt("a")
        self.assertIn("[herd/a]", self.ok("status"))

    def test_two_subagents_on_one_repo(self):
        self.wt("a")
        self.wt("b")
        self.assertNotEqual(self.entry("a")["cwd"], self.entry("b")["cwd"])

    def test_starts_from_the_last_commit_without_uncommitted_files(self):
        self.write(os.path.join(self.base, "dirty.txt"), "x")
        self.wt("a")
        self.assertFalse(os.path.exists(os.path.join(self.path("a"), "dirty.txt")))

    def test_detached_base_is_recorded_by_commit(self):
        commit = self.git(self.base, "rev-parse", "HEAD")
        self.git(self.base, "checkout", "-q", "--detach")
        self.wt("a")
        self.assertEqual(self.entry("a")["worktree"]["base_ref"], commit)


class RefusedBeforeAnyPane(WorktreeCase):
    def check(self, why, *args):
        self.assertIn(why, self.refused("spawn", "a", "x", *args))
        self.assertEqual(self.calls("pane", "split"), [])
        self.assertEqual(self.reg(), {})

    def test_not_a_git_repo(self):
        self.check("not in one", "--cwd", self.mkdir("home", "plain"), "--worktree")

    def test_repo_with_no_commits(self):
        empty = self.mkdir("home", "empty")
        self.git(empty, "init", "-q")
        self.check("no commits yet", "--cwd", empty, "--worktree")

    def test_bad_branch_name(self):
        self.check("not a valid branch name", "--cwd", self.base, "--worktree", "bad..name")

    def test_branch_in_the_main_copy(self):
        self.check("main working copy", "--cwd", self.base, "--worktree", "main")
        self.assertEqual(self.git(self.base, "worktree", "list").count("\n"), 0)

    def test_path_already_taken(self):
        self.write(os.path.join(self.path("a"), "x"), "y")
        self.check("already exists", "--cwd", self.base, "--worktree")


class FailedSpawn(WorktreeCase):
    def test_fresh_worktree_is_removed_again(self):
        self.change(lambda s: s["start"].update(a="fail"))
        self.refused("spawn", "a", "x", "--cwd", self.base, "--worktree")
        self.assertFalse(os.path.exists(self.path("a")))
        self.assertFalse(self.has_branch(self.base, "herd/a"))
        self.assertEqual(self.reg(), {})

    def test_reattached_worktree_survives(self):
        self.settled("a")
        self.write(os.path.join(self.path("a"), "wip.txt"), "x")
        self.ok("close", "a")
        self.change(lambda s: s["start"].update(a="fail"))
        self.refused("spawn", "a", "x", "--cwd", self.base, "--worktree")
        self.assertTrue(os.path.isfile(os.path.join(self.path("a"), "wip.txt")))


class CloseKeeps(WorktreeCase):
    def test_clean_worktree_is_removed_with_its_branch(self):
        self.settled("a")
        self.assertIn("a: closed, worktree removed", self.ok("close", "a"))
        self.assertFalse(os.path.exists(self.path("a")))
        self.assertFalse(self.has_branch(self.base, "herd/a"))
        self.assertNotIn("herd/a", self.git(self.base, "worktree", "list"))
        self.assertEqual(self.reg(), {})

    def test_empty_repo_folder_is_tidied(self):
        self.settled("a")
        self.ok("close", "a")
        self.assertFalse(os.path.exists(os.path.dirname(self.path("a"))))

    def test_other_worktrees_of_the_repo_stay(self):
        self.settled("a")
        self.settled("b")
        self.ok("close", "a")
        self.assertTrue(os.path.isdir(self.path("b")))

    def assert_kept(self, name, why, *args):
        out = self.ok("close", name, *args)
        self.assertIn(why, out)
        self.assertIn("work kept", out)
        self.assertTrue(os.path.isdir(self.path(name)))
        self.assertTrue(self.reg()[name]["kept"])
        return out

    def test_uncommitted_file(self):
        self.settled("a")
        self.write(os.path.join(self.path("a"), "new.txt"), "x")
        self.assert_kept("a", "1 uncommitted changes")
        self.assertTrue(self.has_branch(self.base, "herd/a"))

    def test_changed_tracked_file(self):
        self.settled("a")
        self.write(os.path.join(self.path("a"), "a.txt"), "changed")
        self.assert_kept("a", "1 uncommitted changes")

    def test_ignored_file(self):
        self.settled("a")
        self.write(os.path.join(self.path("a"), "notes.log"), "x")
        self.assert_kept("a", "1 ignored files")

    def test_commits_not_on_the_base_branch(self):
        self.settled("a")
        self.commit_file(self.path("a"))
        self.assert_kept("a", "1 commits not on main")

    def test_force_changes_nothing_about_this(self):
        self.settled("a")
        self.commit_file(self.path("a"))
        self.write(os.path.join(self.path("a"), "new.txt"), "x")
        self.set_status("a", "working")
        self.assert_kept("a", "1 commits not on main", "--force")
        self.assertTrue(os.path.isfile(os.path.join(self.path("a"), "new.txt")))

    def test_commits_on_a_detached_head(self):
        self.settled("a")
        self.git(self.path("a"), "checkout", "-q", "--detach")
        self.commit_file(self.path("a"))
        self.assert_kept("a", "commits not on main")

    def test_commits_on_another_branch_it_switched_to(self):
        self.settled("a")
        self.git(self.path("a"), "checkout", "-q", "-b", "elsewhere")
        self.commit_file(self.path("a"))
        self.assert_kept("a", "commits not on main")

    def test_failed_check_keeps_the_work(self):
        self.settled("a")
        reg = self.reg()
        reg["a"]["worktree"]["base_ref"] = "refs/heads/nonexistent"
        self.save_reg(reg)
        self.assert_kept("a", "cannot compare it with nonexistent")

    def test_folder_deleted_but_branch_has_commits(self):
        self.settled("a")
        self.commit_file(self.path("a"))
        shutil.rmtree(self.path("a"))
        out = self.ok("close", "a")
        self.assertIn("1 commits not on main", out)
        self.assertTrue(self.has_branch(self.base, "herd/a"))

    def test_branch_that_existed_before_is_not_deleted(self):
        self.git(self.base, "branch", "herd/a")
        self.settled("a")
        self.ok("close", "a")
        self.assertFalse(os.path.exists(self.path("a")))
        self.assertTrue(self.has_branch(self.base, "herd/a"))

    def test_pane_that_will_not_close_leaves_the_worktree_alone(self):
        self.settled("a")
        pane = self.entry("a")["pane"]
        self.change(lambda s: s["close_stuck"].append(pane))
        self.assertIn("pane did not close, worktree left alone", self.ok("close", "a"))
        self.assertTrue(os.path.isdir(self.path("a")))

    def test_working_pane_is_skipped_before_anything_is_judged(self):
        self.wt("a")
        self.assertIn("still working, skipped", self.ok("close", "a"))
        self.assertTrue(os.path.isdir(self.path("a")))


class KeptWork(WorktreeCase):
    def setUp(self):
        super().setUp()
        self.settled("a")
        self.commit_file(self.path("a"))
        self.ok("close", "a")

    def test_status_shows_kept(self):
        self.assertRegex(self.ok("status"), r"a\s+kept")

    def test_result_says_it_was_kept(self):
        self.assertIn("closed, worktree kept", self.ok("result", "a"))

    def test_close_again_after_merge_cleans_up(self):
        self.git(self.base, "merge", "-q", "--ff-only", "herd/a")
        self.assertIn("a: closed, worktree removed", self.ok("close", "a"))
        self.assertFalse(os.path.exists(self.path("a")))
        self.assertFalse(self.has_branch(self.base, "herd/a"))
        self.assertEqual(self.reg(), {})

    def test_close_again_before_merge_keeps_it(self):
        self.assertIn("work kept", self.ok("close", "a"))
        self.assertTrue(os.path.isdir(self.path("a")))

    def test_close_does_not_touch_any_pane_again(self):
        before = len(self.calls("pane", "close"))
        self.ok("close", "a")
        self.assertEqual(len(self.calls("pane", "close")), before)

    def test_entry_clears_after_a_manual_discard(self):
        self.git(self.base, "worktree", "remove", "--force", self.path("a"))
        self.git(self.base, "branch", "-D", "herd/a")
        self.ok("close", "a")
        self.assertEqual(self.reg(), {})

    def test_name_needs_worktree_flag(self):
        self.assertIn("Pass --worktree", self.refused("spawn", "a", "x", "--cwd", self.base))

    def test_name_refuses_a_different_branch(self):
        self.assertIn("on record", self.refused("spawn", "a", "x", "--worktree", "other", "--cwd", self.base))


class Reattach(WorktreeCase):
    def test_existing_branch_gets_a_new_worktree(self):
        self.git(self.base, "branch", "herd/a")
        seed = os.path.join(self.root, "seed")
        self.git(self.base, "worktree", "add", "-q", seed, "herd/a")
        self.commit_file(seed, "earlier.txt")
        self.git(self.base, "worktree", "remove", seed)
        out = self.wt("a")
        self.assertIn("reattached existing branch in a new worktree", out)
        self.assertIn("it holds: 1 commits not on main", out)
        self.assertTrue(os.path.isfile(os.path.join(self.path("a"), "earlier.txt")))
        self.assertIn("already holds earlier work", self.brief("a"))
        self.assertFalse(self.entry("a")["worktree"]["created_branch"])

    def test_kept_worktree_is_reused(self):
        self.settled("a")
        self.write(os.path.join(self.path("a"), "wip.txt"), "x")
        self.ok("close", "a")
        out = self.wt("a")
        self.assertIn("reattached to existing worktree", out)
        self.assertIn("it holds: 1 uncommitted changes", out)
        e = self.entry("a")
        self.assertEqual(e["cwd"], self.path("a"))
        self.assertNotIn("kept", e)

    def test_reattached_worktree_keeps_its_original_facts(self):
        self.settled("a")
        self.commit_file(self.path("a"))
        self.ok("close", "a")
        self.git(self.base, "checkout", "-q", "-b", "later")
        self.spawn("a", "--worktree", brief="Carry on.")
        w = self.entry("a")["worktree"]
        self.assertEqual((w["base_ref"], w["created_branch"], w["base_repo"]), ("refs/heads/main", True, self.base))

    def test_worktree_on_another_branch_is_followed(self):
        self.settled("a")
        self.git(self.path("a"), "checkout", "-q", "-b", "elsewhere")
        self.commit_file(self.path("a"))
        self.ok("close", "a")
        self.assertIn("reattached to existing worktree", self.wt("a"))
        self.assertEqual(self.entry("a")["cwd"], self.path("a"))

    def test_unrecorded_worktree_is_found_by_branch(self):
        self.settled("a")
        self.write(os.path.join(self.path("a"), "wip.txt"), "x")
        self.ok("close", "a")
        reg = self.reg()
        del reg["a"]
        self.save_reg(reg)
        out = self.spawn("b", "--cwd", self.base, "--worktree", "herd/a")
        self.assertIn("reattached to existing worktree", out)
        self.assertEqual(self.entry("b")["cwd"], self.path("a"))

    def test_refused_while_a_live_agent_is_there(self):
        self.wt("a")
        self.assertIn("live agent", self.refused("spawn", "b", "x", "--cwd", self.base, "--worktree", "herd/a"))
        self.assertNotIn("b", self.reg())

    def test_refused_while_a_live_agent_is_below_it(self):
        self.wt("a")
        pid = self.entry("a")["pane"]
        sub = self.mkdir(os.path.relpath(self.path("a"), self.root), "sub")
        self.change(lambda s: s["panes"][pid]["agent"].update(cwd=self.work, foreground_cwd=sub))
        self.assertIn("live agent", self.refused("spawn", "b", "x", "--cwd", self.base, "--worktree", "herd/a"))

    def test_worktree_deleted_by_hand_is_replaced(self):
        self.settled("a")
        self.commit_file(self.path("a"))
        self.ok("close", "a")
        shutil.rmtree(self.path("a"))
        self.assertIn("reattached existing branch in a new worktree", self.wt("a"))
        self.assertTrue(os.path.isfile(os.path.join(self.path("a"), "work.txt")))


if __name__ == "__main__":
    unittest.main()
