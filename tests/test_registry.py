"""Spawn, send, close, rename and status, and how the registry tracks them."""
import json, os, subprocess, unittest

from tests.harness import HELPER, HerdCase, PRIMARY, assistant_line


class Sandbox(HerdCase):
    def test_refuses_to_run_outside_herdr(self):
        env = {k: v for k, v in self.env.items() if not k.startswith("HERDR_")}
        p = subprocess.run([HELPER, "status"], env=env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 1)
        self.assertIn("not running inside herdr", p.stderr)

    def test_state_and_projects_folders_can_be_redirected(self):
        self.spawn("a")
        self.say("a", assistant_line("from the redirected folder"))
        self.assertTrue(os.path.isfile(self.reg_file()))
        self.assertIn("from the redirected folder", self.ok("wait", "a"))
        self.assertFalse(os.path.exists(os.path.join(self.home, ".claude")))


    def test_transcripts_are_read_from_claude_config_dir(self):
        self.spawn("a")
        config = self.mkdir("home", "config")
        path = self.write(os.path.join(config, "projects", "-sandbox", "session-1.jsonl"),
                          assistant_line("from the config folder") + "\n")
        self.assertTrue(os.path.isfile(path))
        env = {"HERD_PROJECTS_DIR": "", "CLAUDE_CONFIG_DIR": config}
        self.assertIn("from the config folder", self.ok("wait", "a", env=env))


class Spawn(HerdCase):
    def test_records_the_subagent(self):
        out = self.spawn("alpha", "--model", "haiku", "--mode", "manual")
        e = self.entry("alpha")
        self.assertEqual(e["pane"], "w1:p2")
        self.assertEqual(e["session"], "session-1")
        self.assertEqual((e["cwd"], e["mode"], e["model"], e["group"]), (self.work, "manual", "haiku", None))
        self.assertIn("alpha started in w1:p2, the primary tab (manual, haiku), session session-1", out)

    def test_registry_file_is_named_after_the_pane(self):
        self.spawn("alpha")
        self.assertEqual(sorted(f for f in os.listdir(self.state_dir) if f.endswith(".json")), ["w1_p1.json"])

    def test_passes_claude_its_arguments(self):
        self.spawn("alpha", "--model", "haiku")
        self.assertEqual(self.fake()["start_argv"]["alpha"], ["--permission-mode", "auto", "-n", "alpha", "--model", "haiku"])
        self.spawn("beta")
        self.assertEqual(self.fake()["start_argv"]["beta"], ["--permission-mode", "auto", "-n", "beta"])

    def test_brief_says_who_it_is_and_what_to_do(self):
        self.spawn("alpha", brief="Audit the login flow.")
        brief = self.brief("alpha")
        self.assertIn("You are a subagent named alpha", brief)
        self.assertTrue(brief.endswith("Task:\nAudit the login flow."), brief)

    def test_brief_from_stdin(self):
        self.ok("spawn", "alpha", "-", stdin="line one\nline two\n")
        self.assertIn("line one\nline two", self.brief("alpha"))

    def test_pane_is_labelled(self):
        self.assertNotIn("could not label", self.spawn("alpha"))
        self.assertEqual(self.pane("alpha")["label"], "alpha")
        self.assertEqual(self.entry("alpha")["label"], "alpha")

    def test_cwd_is_used(self):
        other = self.mkdir("home", "other")
        self.spawn("alpha", "--cwd", other)
        self.assertEqual(self.pane("alpha")["cwd"], other)

    def test_bad_input_is_refused_before_any_pane_opens(self):
        for name, brief, why in [("Bad", "x", "name must match"), ("9a", "x", "name must match"), ("a" * 33, "x", "name must match"),
                                 ("fine", "   ", "empty brief")]:
            self.assertIn(why, self.refused("spawn", name, brief))
        self.assertEqual(self.calls("pane", "split"), [])

    def test_refused_inside_a_subagent(self):
        self.assertIn("cannot spawn more", self.refused("spawn", "a", "x", env={"HERD_CHILD": "1"}))

    def test_name_already_running(self):
        self.spawn("alpha")
        self.assertIn("already running", self.refused("spawn", "alpha", "x"))

    def test_name_used_by_another_live_agent(self):
        self.change(lambda s: s["panes"]["w1:p1"]["agent"].update(name="alpha"))
        self.assertIn("another live agent", self.refused("spawn", "alpha", "x"))

    def test_gone_name_can_be_reused(self):
        self.spawn("alpha")
        self.close_pane_outside("alpha")
        self.spawn("alpha")
        self.assertEqual(self.entry("alpha")["pane"], "w1:p3")

    def test_claude_that_never_starts_closes_its_pane(self):
        self.change(lambda s: s["start"].update(alpha="fail"))
        self.assertIn("could not start claude in w1:p2, pane closed", self.refused("spawn", "alpha", "x"))
        modes = [c[c.index("--permission-mode") + 1] for c in self.calls("agent", "start")]
        self.assertEqual(modes, ["auto"] * 5 + ["manual"] * 2)
        self.assertNotIn("w1:p2", self.fake()["panes"])
        self.assertEqual(self.reg(), {})

    def test_other_modes_have_no_fallback(self):
        self.change(lambda s: s["start"].update(alpha="fail"))
        self.refused("spawn", "alpha", "x", "--mode", "plan")
        self.assertEqual(len(self.calls("agent", "start")), 5)

    def test_session_that_appears_just_after_start(self):
        self.change(lambda s: s["start"].update(alpha="slow"))
        out = self.spawn("alpha")
        self.assertIn("session session-1", out)
        self.assertNotIn("pending", self.entry("alpha"))
        self.assertEqual(len(self.pane("alpha")["prompts"]), 1)


class AutoMode(HerdCase):
    def modes(self):
        return [c[c.index("--permission-mode") + 1] for c in self.calls("agent", "start")]

    def test_confirmed_from_the_first_look_at_the_footer(self):
        self.assertNotIn("warning", self.spawn("alpha"))
        self.assertEqual(self.entry("alpha")["mode"], "auto")
        self.assertEqual(len(self.calls("agent", "read")), 1)  # no retries while the footer draws

    def test_refused_auto_falls_back_at_once(self):
        self.change(lambda s: s["start"].update(alpha="no_auto"))
        out = self.spawn("alpha")
        self.assertEqual(self.modes(), ["auto", "manual"])
        self.assertIn("could not start in auto mode", out)
        self.assertIn("it stops at approval prompts", out)
        self.assertEqual(self.entry("alpha")["mode"], "manual")

    def test_refusal_in_unknown_words_falls_back_after_the_retries(self):
        self.change(lambda s: s["start"].update(alpha="no_auto_quiet"))
        self.assertIn("could not start in auto mode", self.spawn("alpha"))
        self.assertEqual(self.modes(), ["auto"] * 5 + ["manual"])
        self.assertEqual(self.entry("alpha")["mode"], "manual")

    def test_claude_that_starts_in_another_mode_is_reported(self):
        self.change(lambda s: s["start"].update(alpha="manual_footer"))
        self.assertIn("auto mode is not available for alpha", self.spawn("alpha"))
        self.assertEqual(self.entry("alpha")["mode"], "manual")


class HeldAtStartup(HerdCase):
    """Claude reports no session while the folder trust prompt is up."""

    def setUp(self):
        super().setUp()
        self.change(lambda s: s["start"].update(held="held"))
        self.out = self.spawn("held", brief="Reply with PINEAPPLE.")

    def accept(self, name="held"):
        pid = self.entry(name)["pane"]

        def go(state):
            a = state["panes"][pid]["agent"]
            a["agent_status"] = "idle"
            a["agent_session"] = {"agent": "claude", "kind": "id", "source": "herdr:claude", "value": a["held_session"]}
        self.change(go)

    def test_brief_is_stored_not_sent(self):
        e = self.entry("held")
        self.assertIsNone(e["session"])
        self.assertIn("PINEAPPLE", e["pending"])
        self.assertEqual(self.pane("held")["prompts"], [])
        self.assertIn("session pending", self.out)
        self.assertIn("Only the user should answer it", self.out)

    def test_no_key_ever_reaches_the_prompt(self):
        self.herd("send", "held", "hello")
        self.ok("wait", "held", "--timeout", "3000")
        self.ok("status")
        self.ok("resume")
        self.assertEqual(self.pane("held")["keys"], [])
        self.assertEqual(self.calls("agent", "send-keys"), [])
        self.assertNotIn("answered", self.pane("held"))

    def test_send_is_refused(self):
        self.assertIn("startup prompt", self.refused("send", "held", "hello"))

    def test_timed_wait_shows_the_prompt_and_keeps_the_brief(self):
        self.change_pane("held", screen="Quick safety check\n Yes, I trust this folder\n")
        out = self.ok("wait", "held", "--timeout", "3000")
        self.assertIn("trust this folder", out)
        self.assertIn("PINEAPPLE", self.entry("held")["pending"])

    def test_wait_delivers_the_brief_once_accepted(self):
        self.accept()
        self.ok("wait", "held", "--timeout", "3000")
        self.assertIn("PINEAPPLE", self.brief("held"))
        self.assertNotIn("pending", self.entry("held"))
        self.assertEqual(self.entry("held")["session"], "session-1")

    def test_declined_prompt_reports_gone(self):
        self.close_pane_outside("held")
        self.assertIn("held: gone", self.ok("wait", "held", "--timeout", "3000"))

    def test_status_and_resume_show_it(self):
        self.assertRegex(self.ok("status"), r"held\s+blocked")
        out = self.ok("resume")
        self.assertIn("brief not delivered", out)
        self.assertIn("wait held", out)


class Send(HerdCase):
    def setUp(self):
        super().setUp()
        self.spawn("a")
        self.ok("wait", "a")

    def test_settled_pane_waits_for_the_prompt_to_land(self):
        self.ok("send", "a", "next task")
        self.assertEqual(self.pane("a")["prompts"][-1], "next task")
        call = self.calls("agent", "prompt")[-1]
        self.assertIn("--wait", call)
        self.assertEqual(call.count("--until"), 4)

    def test_busy_pane_is_not_waited_on(self):
        self.set_status("a", "working")
        self.ok("send", "a", "also this")
        self.assertEqual(self.pane("a")["prompts"][-1], "also this")
        self.assertNotIn("--wait", self.calls("agent", "prompt")[-1])

    def test_message_from_stdin(self):
        self.ok("send", "a", "-", stdin="from stdin")
        self.assertEqual(self.pane("a")["prompts"][-1], "from stdin")

    def test_unknown_name(self):
        self.assertIn("no subagent named nope. Known: a", self.refused("send", "nope", "hi"))

    def test_unsent_text_refuses(self):
        self.change_pane("a", draft="half typed")
        self.assertIn("unsent text", self.refused("send", "a", "hi"))
        self.assertEqual(len(self.pane("a")["prompts"]), 1)
        self.assertEqual(self.pane("a")["draft"], "half typed")

    def test_force_discards_the_draft_first(self):
        self.change_pane("a", draft="half typed")
        self.ok("send", "a", "hi", "--force")
        self.assertEqual(self.pane("a")["prompts"][-1], "hi")

    def test_force_gives_up_on_a_draft_that_will_not_clear(self):
        self.change_pane("a", draft="stuck", stuck_draft=True)
        self.assertIn("could not clear", self.refused("send", "a", "hi", "--force"))
        self.assertEqual(len(self.pane("a")["prompts"]), 1)

    def test_blocked_pane_is_not_answered(self):
        """The Enter in a prompt picks the highlighted option, so a send would approve it.
        Confirmed against real Claude: the command ran."""
        self.set_status("a", "blocked")
        self.assertIn("waiting on a prompt", self.refused("send", "a", "hello"))
        self.assertNotIn("answered", self.pane("a"))

    def test_force_does_not_answer_a_blocked_pane(self):
        self.set_status("a", "blocked")
        self.change_pane("a", draft="half typed")
        self.assertIn("waiting on a prompt", self.refused("send", "a", "hello", "--force"))
        self.assertNotIn("answered", self.pane("a"))
        self.assertEqual(self.pane("a")["keys"], [])
        self.assertEqual(self.pane("a")["draft"], "half typed")


class Close(HerdCase):
    def test_settled_pane_closes(self):
        self.spawn("a")
        self.ok("wait", "a")
        pane = self.entry("a")["pane"]
        self.assertIn("a: closed", self.ok("close", "a"))
        self.assertNotIn(pane, self.fake()["panes"])
        self.assertEqual(self.reg(), {})

    def test_working_and_blocked_are_skipped_unless_forced(self):
        self.spawn("w")
        self.spawn("b")
        self.set_status("b", "blocked")
        out = self.ok("close", "w", "b")
        self.assertIn("w: still working, skipped", out)
        self.assertIn("b: still blocked, skipped", out)
        self.assertEqual(sorted(self.reg()), ["b", "w"])
        self.ok("close", "w", "b", "--force")
        self.assertEqual(self.reg(), {})

    def test_all(self):
        self.spawn("a")
        self.spawn("b")
        self.ok("close", "--all", "--force")
        self.assertEqual(self.reg(), {})
        self.assertEqual(list(self.fake()["panes"]), [PRIMARY])

    def test_gone_entry_clears(self):
        self.spawn("a")
        self.close_pane_outside("a")
        self.assertIn("a: closed", self.ok("close", "a"))
        self.assertEqual(self.reg(), {})

    def test_needs_names(self):
        self.assertIn("give names or --all", self.refused("close"))

    def test_unknown_name_stops_everything(self):
        self.spawn("a")
        self.ok("wait", "a")
        self.refused("close", "a", "nope")
        self.assertIn("a", self.reg())
        self.assertEqual(self.calls("pane", "close"), [])


class Tracking(HerdCase):
    def test_moved_pane_is_followed_by_session(self):
        self.spawn("a")
        new = self.move_pane("a")
        self.ok("status")
        self.assertEqual(self.entry("a")["pane"], new)

    def test_lost_session_falls_back_to_name_and_cwd(self):
        self.spawn("a")
        reg = self.reg()
        reg["a"]["session"] = None
        self.save_reg(reg)
        new = self.move_pane("a")
        self.ok("status")
        self.assertEqual(self.reg()["a"]["pane"], new)
        self.assertEqual(self.reg()["a"]["session"], "session-1")

    def test_session_change_is_picked_up(self):
        self.spawn("a")
        pid = self.entry("a")["pane"]
        self.change(lambda s: s["panes"][pid]["agent"]["agent_session"].update(value="session-new"))
        self.ok("status")
        self.assertEqual(self.entry("a")["session"], "session-new")

    def test_damaged_registry_counts_as_empty(self):
        self.write(self.reg_file(), "{not json")
        self.assertIn("no subagents", self.ok("status"))

    def test_saving_leaves_no_temporary_files(self):
        self.spawn("a")
        self.assertEqual([f for f in os.listdir(self.state_dir) if f.endswith(".tmp")], [])
        with open(self.reg_file()) as f:
            self.assertIn("a", json.load(f))


class Status(HerdCase):
    def test_lists_state_of_each_subagent(self):
        self.spawn("a")
        self.spawn("b")
        self.close_pane_outside("b")
        out = self.ok("status")
        self.assertIn("window 174x59, 4 subagents per tab", out)
        self.assertRegex(out, r"a\s+working\s+w1:p2")
        self.assertRegex(out, r"b\s+gone\s+w1:p3")

    def test_nothing_on_record(self):
        self.assertIn("no subagents", self.ok("status"))


class Rename(HerdCase):
    def test_renames_the_tab_and_every_subagent_in_it(self):
        self.spawn("a", "--tab", "Old")
        self.spawn("b", "--tab", "Old")
        self.assertIn("tab renamed to New", self.ok("rename", "a", "New"))
        tab = self.pane("a")["tab"]
        self.assertEqual(self.fake()["tabs"][tab]["label"], "New")
        self.assertEqual((self.entry("a")["group"], self.entry("b")["group"]), ("New", "New"))

    def test_renamed_group_keeps_filling_the_same_tab(self):
        self.spawn("a", "--tab", "Old")
        self.ok("rename", "a", "New")
        self.spawn("b", "--tab", "New")
        self.assertEqual(self.pane("a")["tab"], self.pane("b")["tab"])

    def test_primary_tab_is_refused(self):
        self.spawn("a")
        self.assertIn("does not rename", self.refused("rename", "a", "New"))
        self.assertEqual(self.calls("tab", "rename"), [])

    def test_gone_subagent(self):
        self.spawn("a", "--tab", "Old")
        self.close_pane_outside("a")
        self.assertIn("a is gone", self.refused("rename", "a", "New"))


if __name__ == "__main__":
    unittest.main()
