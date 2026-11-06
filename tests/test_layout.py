"""Capacity and pane placement. The expected sizes in fixtures/herdr/layouts.json are what
real herdr produced for the same spawns, at the window sizes the helper was tuned on."""
import json, os, unittest

from tests.fake_herdr import area, lay_out
from tests.harness import FIXTURES, HOME_TAB, DroverCase, PRIMARY


def rects(case, pane=PRIMARY):
    state = case.fake()
    tab = state["panes"][pane]["tab"]
    a = area(state)
    panes = lay_out(state["tabs"][tab]["root"], a["x"], a["y"], a["width"], a["height"], [])
    return {p["pane_id"]: [p["rect"][k] for k in ("x", "y", "width", "height")] for p in panes}


class LayoutCase(DroverCase):
    def set_window(self, cols, rows):
        self.change(lambda s: s.update(window=[cols, rows]))


class RealLayouts(LayoutCase):
    def replay(self, cols, rows):
        with open(os.path.join(FIXTURES, "herdr", "layouts.json")) as f:
            sample = next(c for c in json.load(f) if c["window"] == [cols, rows])
        self.set_window(cols, rows)
        self.assertEqual(self.ok("status").splitlines()[0], sample["status"])
        for i, step in enumerate(sample["steps"]):
            self.assertIn(step["where"], self.spawn(f"s{i}").splitlines()[0])
            self.assertEqual(rects(self), step["panes"], f"after spawn {i}")

    def test_large_window(self):
        self.replay(270, 70)

    def test_medium_window(self):
        self.replay(162, 44)

    def test_wide_short_window(self):
        self.replay(292, 50)

    def test_narrow_short_window(self):
        self.replay(100, 30)

    def test_narrow_tall_window(self):
        self.replay(100, 62)


class Capacity(LayoutCase):
    def limit(self, cols, rows):
        self.set_window(cols, rows)
        return self.ok("status").splitlines()[0]

    def test_capacity_by_window(self):
        for cols, rows, expected in [(270, 70, "window 244x69, 8 subagents per tab"),
                                     (162, 44, "window 136x43, 3 subagents per tab"),
                                     (292, 50, "window 266x49, 6 subagents per tab"),
                                     (100, 30, "window 74x29, 1 subagents per tab"),
                                     (100, 62, "window 74x61, 2 subagents per tab"),
                                     (60, 10, "window 34x9, 1 subagents per tab")]:
            self.assertEqual(self.limit(cols, rows), expected)

    def test_capacity_is_checked_at_each_spawn(self):
        self.set_window(100, 30)
        self.spawn("a")
        self.assertIn("tab 'b'", self.spawn("b"))
        self.set_window(270, 70)
        self.assertIn("the primary tab", self.spawn("c"))


class Placement(LayoutCase):
    window = (162, 44)

    def tab_label(self, name):
        state = self.fake()
        return state["tabs"][state["panes"][self.entry(name)["pane"]]["tab"]]["label"]

    def test_labelled_group_shares_a_tab_then_numbers_the_next(self):
        for i in range(4):
            self.spawn(f"g{i}", "--tab", "Auth audit")
        self.assertEqual([self.tab_label(f"g{i}") for i in range(4)], ["Auth audit"] * 3 + ["Auth audit 2"])
        self.assertEqual(self.entry("g3")["group"], "Auth audit")

    def test_group_never_uses_the_primary_tab(self):
        self.spawn("plain")
        self.spawn("g", "--tab", "Docs")
        self.assertEqual(self.tab_label("plain"), "main")
        self.assertEqual(self.tab_label("g"), "Docs")

    def test_overflow_gets_a_tab_named_after_the_agent(self):
        for i in range(3):
            self.spawn(f"s{i}")
        self.assertIn("tab 'over'", self.spawn("over"))
        self.assertEqual(self.tab_label("over"), "over")

    def test_gone_subagents_free_their_place(self):
        for i in range(3):
            self.spawn(f"s{i}")
        self.close_pane_outside("s1")
        self.assertIn("the primary tab", self.spawn("next"))

    def test_focus_stays_on_the_primary_and_its_tab_keeps_its_name(self):
        self.spawn("a")
        self.spawn("b", "--tab", "Docs")
        self.assertTrue(all(p.get("no_focus", True) for p in self.fake()["panes"].values()))
        self.assertEqual(self.calls("tab", "rename"), [])
        self.assertEqual(self.fake()["tabs"][HOME_TAB]["label"], "main")

    def test_new_panes_are_marked_as_subagents(self):
        self.spawn("a")
        self.spawn("b", "--tab", "Docs")
        self.assertEqual(self.pane("a")["env"], ["DROVER_CHILD=1"])
        self.assertEqual(self.pane("b")["env"], ["DROVER_CHILD=1"])


if __name__ == "__main__":
    unittest.main()
