# drover

Run Claude Code subagents as real, visible sessions in [herdr](https://herdr.dev) panes, so you can watch each one work and type to it directly.

<!-- Demo GIF goes here: ![drover demo](docs/demo.gif) -->
*Demo GIF coming soon.*

## What it is

Claude Code's built-in subagents run out of sight. You give a task, and you get back a summary. If one goes the wrong way, you find out at the end.

drover gives you visibility and control instead: panes you can see and type into. It does not save tokens or time, and it costs more than built-in subagents (see [What it costs](#what-it-costs)). It is a Claude Code skill plus a small Python helper. When you ask your Claude session (the primary) for subagents, it opens each one as a full interactive Claude session in its own herdr pane. The primary writes the brief, waits, and relays the result. While that happens you can read any pane, type into it, or tell the primary to steer it.

drover works for any task Claude can do, such as code changes, reviews, research, or writing.

It is for developers who already use Claude Code, want a few agents running at once, and want to stay involved while they run.

## What it costs

drover is for visibility and control. It is not cheaper or faster than the built-in Agent tool. In the [benchmark](bench/README.md), with the same tasks and the same sonnet primary, default drover panes used about 1.5x to 2x the tokens of native subagents and 1.3x to 1.5x the cost, and were slower (28 to 43 s against 14 to 24 s). Each pane is a full session with its own startup prompt, and the primary spends extra turns on spawn, wait, and close. Quality was the same in every run, but the tasks were easy, so quality is untested on hard work. That benchmark had two repeats per cell.

The `run` command and multi-pane `wait` cut the primary's turns. A re-measure with one run per task (not conclusive) gave, on a one-pane lookup, 7 primary turns against 8, about 8 percent fewer tokens, and the same cost ($0.196). On three parallel panes it gave 7 turns against 10 or 11, 20 percent fewer tokens, and 8 percent lower cost ($0.345 against $0.377). That is still above native subagents, at about 1.6x tokens and 1.5x cost on the lookup and 1.2x tokens and 1.3x cost on the three-pane task. `--tools lean` cuts a pane's first prompt to a quarter in a trivial test, but removes tools, so it is opt-in.

**Use panes** when you want to watch an agent, message it mid-task, or answer its prompts, and for long work that needs worktrees, handoffs, or resume after a restart. **Use native subagents** for everything else, such as quick lookups, reviews, and parallel edits you do not need to watch. They are cheaper and faster, and that is Claude's default.

## Requirements

- [herdr](https://herdr.dev) 0.8.0 or newer (the oldest tested version), with its Claude integration: `herdr integration install claude`
- Claude Code, run from inside a herdr pane
- Python 3.9 or newer as `python3`. There are no other dependencies.
- git, for worktrees

**Tested on:** herdr 0.8.0, Claude Code 2.1.319, macOS. Other versions and Linux may work, but have not been tested.

drover depends on Claude Code's transcript format and screen layout, which are not stable APIs. A Claude Code update can break it. See [Known limits](#known-limits).

## Install

Use one of these two methods, not both, or Claude will see two drover skills.

### As a Claude Code plugin

```bash
claude plugin marketplace add Nano-Sec/drover
claude plugin install drover@drover
```

Restart Claude Code afterwards. The skill is listed as `drover:drover`, and `/drover` also works unless something else uses that name.

To update, which does not happen automatically by default for third-party marketplaces:

```bash
claude plugin marketplace update drover
claude plugin update drover@drover
```

### With the install script

```bash
git clone https://github.com/Nano-Sec/drover
cd drover
./install.sh
```

This copies the skill to `~/.claude/skills/drover`, or under `CLAUDE_CONFIG_DIR` if you set it. Run it again after a `git pull` to update, and run `./install.sh --uninstall` to remove it. It never edits your `CLAUDE.md`.

### Check your setup

In a Claude session inside herdr, ask Claude to run `drover doctor`. You can also run it yourself from a herdr pane:

```bash
~/.claude/skills/drover/drover doctor                           # script install
~/.claude/plugins/cache/drover/drover/<version>/skills/drover/drover doctor  # plugin install
```

See [drover doctor](#drover-doctor) for what it checks.

### Optional: a stronger automatic trigger

Claude uses built-in subagents by default. The skill's description tells it to use drover when you ask for panes, visible agents, or drover by name, and that is usually enough. A description is still only a hint. For a firmer rule, add this line to your `~/.claude/CLAUDE.md`:

```text
When I ask for subagents or parallel agents and HERDR_ENV=1, use the drover skill so they run in visible herdr panes instead of the built-in Agent tool. This does not apply inside a drover pane (DROVER_CHILD=1).
```

That line sends every subagent request to panes, so drop it if you want drover only when you ask for it. Outside herdr, drover stays out of the way and Claude uses its built-in Agent tool.

## Quick example

Start herdr, open Claude Code in a pane, and ask in plain language:

```text
Use two drover panes with worktrees: one to find why the login test is flaky,
and one to add pagination to the orders API.
```

What happens next:

1. Claude runs `drover spawn` twice. Two panes open beside yours, each on its own branch, and focus stays where it was.
2. Both subagents work while your primary session stays free. You can click into a pane to watch or type.
3. You can also steer through the primary: "tell the pagination agent to use cursors, not offsets."
4. When a subagent finishes, the primary tells you what it reported.
5. The primary closes finished panes. Unmerged work is always kept, and merging is up to you.

When you are stopping for the day, say so. Claude runs `drover wrapup`, and each subagent commits its work and writes a handoff.

## Commands

Claude normally runs these for you, so you rarely need to type them. They do all work by hand in a herdr pane. `drover` is not added to your PATH, so use the full helper path shown in [Check your setup](#check-your-setup).

| Command | What it does |
| --- | --- |
| `drover run <name> "<brief>"` | Spawn, wait, print the result, and close the pane, in one command. Takes every spawn option, plus `--keep` to skip the close and `--timeout`. A blocked, held, or timed out pane stays open and is reported. |
| `drover spawn <name> "<brief>"` | Start a subagent. Options: `--model`, `--effort low\|medium\|high\|xhigh\|max`, `--preset scout\|build`, `--tools lean`, `--mode`, `--cwd`, `--tab "<label>"`, `--label "<text>"`, `--worktree [branch]`. |
| `drover send <name> "<message>"` | Send a message to a subagent, even mid-task. Refused while the pane waits on a prompt, even with `--force`. Also refused if the pane holds unsent text or its input box cannot be found, unless you pass `--force`. |
| `drover wait <name> [name...]` | Block until the panes settle, then print each final message or the prompt it is stuck on. With several names it returns early if one is blocked, naming the panes still running. `--close` closes the ones that settled normally. |
| `drover result <name>` | Print the same output without waiting. |
| `drover status` | Show the window size, how many subagents fit per tab, and each subagent's state. |
| `drover rename <name> "<label>"` | Rename the tab holding a subagent. Refused in the primary's tab. |
| `drover rename <name> --pane "<label>"` | Relabel a subagent's pane, in any tab. |
| `drover wrapup [names...]` | Ask subagents to commit and write a handoff. Defaults to all of them. |
| `drover close <name>` or `--all` | Close panes. Skips working or blocked panes unless you pass `--force`. |
| `drover resume [--from <pane-id>]` | After a restart, reconcile state and list the waits to start again. |
| `drover doctor` | Check your setup. |

Pass `-` as the brief or message to read it from stdin.

`--preset scout` is haiku with low effort and `--preset build` is sonnet with medium effort. An explicit `--model` or `--effort` overrides the preset. `--tools lean` is opt-in and never the default. It starts the pane with only Bash, Read, Edit, Write, Glob, Grep, ToolSearch, WebFetch, and WebSearch, and no MCP servers, which cuts the pane's first prompt to about a quarter. Such a pane cannot use Agent, Skill, AskUserQuestion, Artifact, Monitor, TaskStop, ScheduleWakeup, cron or worktree tools, or any MCP server. It keeps typed slash commands and `CLAUDE.md`. This was only checked on trivial tasks.

### Pane labels

Each pane gets a label, which is the agent's name unless spawn is given `--label`. The primary is told to write short labels naming the work. herdr shows the label on the pane's border.

We suggest turning on agent labels too, so panes without a label, such as the primary, also show who is in them. In herdr's `config.toml`:

```toml
[ui]
show_agent_labels_on_pane_borders = true
```

drover's own labels show with this on or off, as long as herdr's pane borders are on, which is the default.

### drover doctor

`drover doctor` prints PASS, WARN, FAIL, or SKIP for each check, with a fix for each failure or warning. It exits with an error if anything failed. A warning does not count as a failure.

| Check | What it looks at |
| --- | --- |
| python | Python is 3.9 or newer. |
| herdr | herdr is on your PATH and new enough. |
| claude integration | herdr's Claude integration is installed and current. |
| claude | `claude` is on your PATH. |
| inside herdr | You are in a herdr pane and the server answers. |
| transcript location | Claude's transcript folder exists. |
| transcript format | drover can still read a recent transcript. Skipped if there are no finished transcripts yet. |
| auto mode | A test pane really starts in auto mode. If auto mode is unavailable this is a warning, because drover still works: spawn says so and runs subagents in manual mode. |
| input box | drover can still read Claude's input box in that test pane. |

The last two open a throwaway Claude pane and close it again. They send no prompt, so they use no tokens. They are skipped if the herdr, claude, or inside herdr check failed, inside a subagent pane, or if Claude is held at a trust prompt in that folder.

You can run `drover doctor` outside herdr too, to check what is installed. The inside herdr check fails there, so it exits with an error.

drover finds transcripts under `CLAUDE_CONFIG_DIR` if you set it, and `DROVER_PROJECTS_DIR` overrides that. Set `DROVER_STATE_DIR` to keep drover's records, worktrees, and handoffs somewhere other than `~/.claude/drover`.

## Permissions and trust

**Panes default to auto mode.** Each subagent starts with `--permission-mode auto`, so it works without stopping for routine approvals. Claude's auto mode decides what is allowed, not drover. You are starting agents that act on their own in the folder you give them, so spawn them where you would be comfortable running Claude that way. Use `--mode manual` to get approval prompts instead. `--mode` also accepts `acceptEdits` and `plan`.

If auto mode is not available to you, for example because of your plan or a setting, drover warns you and the pane runs in manual mode, or whichever mode Claude started it in. That pane then stops at approval prompts for you to answer.

**drover never accepts a trust dialog.** Claude asks once for each git root it does not trust yet. When a new pane hits that prompt, drover holds the brief and tells you which pane needs you. Only you can answer it. drover does not send keys to the dialog or edit `~/.claude.json`. Once you accept, drover delivers the brief. If you decline, the subagent is reported as gone.

**drover does not approve prompts for you.** If a subagent stops at a permission prompt, it shows as blocked, and the primary tells you what it is asking. You answer in that pane. `drover send` is refused while a pane is blocked, even with `--force`, because its Enter would answer the prompt.

## Worktrees and handoffs

Subagents share a folder unless you say otherwise. If two might edit the same repo, give each one a worktree with `--worktree`, or just ask for worktrees.

- The default branch is `drover/<name>`, and the checkout lives at `~/.claude/drover/worktrees/<repo>/<name>`.
- A worktree starts from the last commit, so uncommitted changes and ignored files such as `.env` are not in it.
- Subagents commit there. They are told not to merge or push.
- `drover close` removes a worktree, and the branch if drover created it, only if nothing would be lost. Uncommitted changes, ignored files, or commits not on the base branch all keep it, and `--force` does not change that.
- Spawning the same name with `--worktree` reattaches to kept work.

`drover wrapup` asks each subagent to commit to its branch and write a handoff to `~/.claude/drover/handoffs/<name>.md`, with its status, decisions, next steps, and open questions. The file sits outside the repo, so it stays out of pull requests and survives worktree removal. If you spawn that name again later, drover pastes the handoff into the new brief, and the work carries on.

If the primary restarts, its background waits are lost, but the panes keep running. Run `drover resume`, or just tell Claude about it, and it picks them back up.

## When to use drover, and when to use firstmate

[firstmate](https://github.com/kunchenguid/firstmate) solves a related problem, and it can use herdr as a backend too. Its README describes an "agent distro": you clone it and talk to a single agent, the first mate, which spawns autonomous agents in a visible session backend, gives each a clean git worktree, supervises them to completion, and hands you finished PRs, approved local merges, or investigation reports.

| | drover | firstmate |
| --- | --- | --- |
| Best for | Attended work you steer as it goes | Delivering many tasks with less supervision |
| Scale | Up to a few agents | A crew of agents across projects, with optional secondmates on this machine or over SSH |
| Where you work | Your existing Claude session, in the repo you are already in | A session launched inside the firstmate checkout |
| Kinds of task | Anything you would ask Claude | Ship tasks that deliver changes, and scout tasks that produce reports |
| Output | Whatever you asked for, relayed to you | PRs, local merges, or reports |
| Agents | Claude Code in herdr | Several harnesses, such as Claude Code, Codex, and Pi, across tmux, herdr, and other backends |
| Setup | One skill | Clone the repo, sign in to the GitHub CLI, and launch a supported harness inside it |

Use drover if you want to stay in one session and work alongside a few agents, stepping in as they go. Use firstmate if you want to hand off a stream of tasks across repos and get finished results back, without watching each one.

## Known limits

- **Unstable interfaces.** drover reads Claude's transcript files to get final messages and spot background jobs, and it reads the pane's screen to detect unsent text and the permission mode. Neither is a stable API. Run `drover doctor` after a Claude Code update if something looks wrong.
- **Claude Code only.** Subagents are always Claude sessions.
- **Inside herdr only.** Apart from `drover doctor`, drover does nothing outside a herdr pane.
- **Limited panes per tab.** Between 1 and 8 fit, depending on window size. Past that, drover opens more tabs.
- **Token cost.** Each pane is a full session with its own context and tokens, see [What it costs](#what-it-costs). Idle panes get costlier to resume once the prompt cache expires, so close them when done.
- **No nesting.** A subagent cannot spawn its own subagents.
- **Context is not inherited.** Subagents do not see your conversation, only the brief. A pane loads `CLAUDE.md` from its own folder and parents, and drover pastes in the primary's files if the pane starts elsewhere, up to 20,000 characters each. The primary's memory is not passed to panes, so anything needed from it must go in the brief.
- **Paused panes.** `wait` treats an idle pane with background jobs still running as paused, and holds for up to 30 minutes per pause before reporting anyway.
- **Some background jobs are invisible or slow to clear.** A job started with a plain shell `&` leaves no trace in the transcript, so `wait` can return while it runs. A background Agent job stopped with TaskStop, or a job killed by a restart, may count as running until the 30 minute limit passes.
- **Failed reattach.** If `spawn` fails while reattaching a branch that holds commits, the worktree stays on disk without a record. Nothing is lost, and the next spawn with `--worktree` finds it.
- **Stashes do not count as unsaved.** `drover close` can remove a worktree whose only unsaved work is a `git stash`. The stash stays in the repo's stash list.
- **Ignored files always keep a worktree.** Anything ignored, such as `node_modules`, keeps the worktree on close, even if all the work is merged. Delete those files, then run `drover close` again.
- **Reused branches are kept.** drover only deletes branches it created. A branch that already existed is never deleted, and while it has commits not on the base branch, its worktree stays too.
- **Pane labels cannot start with a dash.** herdr would read one as an option.
- **Pane records are per primary.** State in `~/.claude/drover` is keyed by the primary's pane. After a restart in a different pane, use `drover resume --from <pane-id>`.

## License

MIT. See [LICENSE](LICENSE).
