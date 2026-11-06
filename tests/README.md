# Tests

## Fast tests

Run these from the repo root:

```bash
python3 -m unittest
```

These need Python 3.9 or later and git, and nothing else: no herdr, no Claude, no tokens, no secrets. Each test runs the real helper against `fake_herdr.py` in its own sandbox, with `HOME`, `DROVER_STATE_DIR` and `DROVER_PROJECTS_DIR` all pointing into a temp folder, so nothing touches your `~/.claude`. Set `DROVER_BIN` to test another copy of the helper.

A test marked `expectedFailure` records a known helper bug. When the bug is fixed the test reports an unexpected success: remove the marker.

## Format fixtures

`fixtures/` holds real output from Claude Code and herdr, with paths and ids replaced, except the screens named `synthetic_`. `test_formats.py` runs them through the helper, and `formats.py` lists what the helper assumes about each format. `fixtures/herdr/layouts.json` holds the pane sizes real herdr produced at five window sizes, and `test_layout.py` replays those spawns. When a format changes, recapture the sample and fix whatever fails.

## Live tests

```bash
DROVER_LIVE=1 python3 -m unittest tests.test_live
DROVER_LIVE=1 DROVER_TEST_TRUSTED_REPO=/path/to/repo python3 -m unittest tests.test_live
```

These use real herdr and real Claude on haiku, so they spend tokens. They run in a throwaway herdr session with sound off and the registry in a temp folder, and they drop every `HERDR_`, `DROVER_` and `CLAUDE` variable. The same `formats.py` checks run on real output, so a format change fails here first.

Claude must already trust the folder it starts in. The tests never answer the trust prompt: plain tests skip if Claude stops at it. Worktree tests need `DROVER_TEST_TRUSTED_REPO`, a git repo you have already trusted, and skip without it. They add temporary `drover/live-wt<pid>` branches and worktrees during the test, and remove them.
