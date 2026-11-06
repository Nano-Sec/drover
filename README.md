# herd

Run Claude Code subagents as real, visible sessions in [herdr](https://herdr.dev) panes, so you can watch each one work and type to it directly.

<!-- Demo GIF goes here: ![herd demo](docs/demo.gif) -->
*Demo GIF coming soon.*

## What it is

Claude Code's built-in subagents run out of sight. You give a task, and you get back a summary. If one goes the wrong way, you find out at the end.

herd replaces that with panes you can see. It is a Claude Code skill plus a small Python helper. When you ask your Claude session (the primary) for subagents, it opens each one as a full interactive Claude session in its own herdr pane. The primary writes the brief, waits, and relays the result. While that happens you can read any pane, type into it, or tell the primary to steer it.

herd works for any task Claude can do, such as code changes, reviews, research, or writing.

It is for developers who already use Claude Code, want a few agents running at once, and want to stay involved while they run.

## Requirements

- [herdr](https://herdr.dev) 0.8.0 or newer, with its Claude integration: `herdr integration install claude`
- Claude Code, run from inside a herdr pane
- Python 3.9 or newer as `python3`. There are no other dependencies.
- git, for worktrees

**Tested on:** herdr 0.8.0, Claude Code 2.1.319, macOS. Other versions and Linux may work, but have not been tested.

herd depends on Claude Code's transcript format and screen layout, which are not stable APIs. A Claude Code update can break it. See [Known limits](#known-limits).

## Install

Use one of these two methods, not both, or Claude will see two herd skills.

### As a Claude Code plugin

```bash
claude plugin marketplace add Nano-Sec/herd
claude plugin install herd@herd
```

Restart Claude Code afterwards. The skill is listed as `herd:herd`, and `/herd` also works unless something else uses that name.

To update, which does not happen automatically by default for third-party marketplaces:

```bash
claude plugin marketplace update herd
claude plugin update herd@herd
```

### With the install script

```bash
git clone https://github.com/Nano-Sec/herd
cd herd
./install.sh
```

This copies the skill to `~/.claude/skills/herd`, or under `CLAUDE_CONFIG_DIR` if you set it. Run it again after a `git pull` to update, and run `./install.sh --uninstall` to remove it. It never edits your `CLAUDE.md`.

### Check your setup

In a Claude session inside herdr, ask Claude to run `herd doctor`. You can also run it yourself from a herdr pane:

```bash
~/.claude/skills/herd/herd doctor                           # script install
~/.claude/plugins/cache/herd/herd/<version>/skills/herd/herd doctor  # plugin install
```

See [herd doctor](#herd-doctor) for what it checks.

### Optional: a stronger automatic trigger

The skill's description tells Claude to use herd whenever you ask for subagents or delegation, and that is usually enough. A description is still only a hint. For a firmer rule, add this line to your `~/.claude/CLAUDE.md`:

```text
When I ask for subagents or parallel agents and HERDR_ENV=1, use the herd skill so they run in visible herdr panes instead of the built-in Agent tool. This does not apply inside a herd pane (HERD_CHILD=1).
```

Outside herdr, herd stays out of the way and Claude uses its built-in Agent tool.

## Quick example

Start herdr, open Claude Code in a pane, and ask in plain language:

```text
Use two subagents with worktrees: one to find why the login test is flaky,
and one to add pagination to the orders API.
```

What happens next:

1. Claude runs `herd spawn` twice. Two panes open beside yours, each on its own branch, and focus stays where it was.
2. Both subagents work while your primary session stays free. You can click into a pane to watch or type.
3. You can also steer through the primary: "tell the pagination agent to use cursors, not offsets."
4. When a subagent finishes, the primary tells you what it reported.
5. The primary closes finished panes. Unmerged work is always kept, and merging is up to you.

When you are stopping for the day, say so. Claude runs `herd wrapup`, and each subagent commits its work and writes a handoff.

## Commands

Claude normally runs these for you, so you rarely need to type them. They do all work by hand in a herdr pane. `herd` is not added to your PATH, so use the full helper path shown in [Check your setup](#check-your-setup).

| Command | What it does |
| --- | --- |
| `herd spawn <name> "<brief>"` | Start a subagent. Options: `--model`, `--mode`, `--cwd`, `--tab "<label>"`, `--label "<text>"`, `--worktree [branch]`. |
| `herd send <name> "<message>"` | Send a message to a subagent, even mid-task. Refused while the pane waits on a prompt, even with `--force`. Also refused if the pane holds unsent text or its input box cannot be found, unless you pass `--force`. |
| `herd wait <name>` | Block until it settles, then print its final message or the prompt it is stuck on. |
| `herd result <name>` | Print the same output without waiting. |
| `herd status` | Show the window size, how many subagents fit per tab, and each subagent's state. |
| `herd rename <name> "<label>"` | Rename the tab holding a subagent. Refused in the primary's tab. |
| `herd rename <name> --pane "<label>"` | Relabel a subagent's pane, in any tab. |
| `herd wrapup [names...]` | Ask subagents to commit and write a handoff. Defaults to all of them. |
| `herd close <name>` or `--all` | Close panes. Skips working or blocked panes unless you pass `--force`. |
| `herd resume [--from <pane-id>]` | After a restart, reconcile state and list the waits to start again. |
| `herd doctor` | Check your setup. |

Pass `-` as the brief or message to read it from stdin.

### Pane labels

Each pane gets a label, which is the agent's name unless spawn is given `--label`. The primary is told to write short labels naming the work. herdr shows the label on the pane's border.

We suggest turning on agent labels too, so panes without a label, such as the primary, also show who is in them. In herdr's `config.toml`:

```toml
[ui]
show_agent_labels_on_pane_borders = true
```

herd's own labels show with this on or off, as long as herdr's pane borders are on, which is the default.

### herd doctor

`herd doctor` prints PASS, WARN, FAIL, or SKIP for each check, with a fix for each failure or warning. It exits with an error if anything failed. A warning does not count as a failure.

| Check | What it looks at |
| --- | --- |
| python | Python is 3.9 or newer. |
| herdr | herdr is on your PATH and new enough. |
| claude integration | herdr's Claude integration is installed and current. |
| claude | `claude` is on your PATH. |
| inside herdr | You are in a herdr pane and the server answers. |
| transcript location | Claude's transcript folder exists. |
| transcript format | herd can still read a recent transcript. Skipped if there are no finished transcripts yet. |
| auto mode | A test pane really starts in auto mode. If auto mode is unavailable this is a warning, because herd still works: spawn says so and runs subagents in manual mode. |
| input box | herd can still read Claude's input box in that test pane. |

The last two open a throwaway Claude pane and close it again. They send no prompt, so they use no tokens. They are skipped if the herdr, claude, or inside herdr check failed, inside a subagent pane, or if Claude is held at a trust prompt in that folder.

You can run `herd doctor` outside herdr too, to check what is installed. The inside herdr check fails there, so it exits with an error.

If you set `CLAUDE_CONFIG_DIR`, set `HERD_PROJECTS_DIR` to Claude's projects folder so herd can find transcripts. Set `HERD_STATE_DIR` to keep herd's records, worktrees, and handoffs somewhere other than `~/.claude/herd`.

## Permissions and trust

**Panes default to auto mode.** Each subagent starts with `--permission-mode auto`, so it works without stopping for routine approvals. Claude's auto mode decides what is allowed, not herd. You are starting agents that act on their own in the folder you give them, so spawn them where you would be comfortable running Claude that way. Use `--mode manual` to get approval prompts instead. `--mode` also accepts `acceptEdits` and `plan`.

If auto mode is not available to you, for example because of your plan or a setting, herd warns you and the pane runs in manual mode, or whichever mode Claude started it in. That pane then stops at approval prompts for you to answer.

**herd never accepts a trust dialog.** Claude asks once for each git root it does not trust yet. When a new pane hits that prompt, herd holds the brief and tells you which pane needs you. Only you can answer it. herd does not send keys to the dialog or edit `~/.claude.json`. Once you accept, herd delivers the brief. If you decline, the subagent is reported as gone.

**herd does not approve prompts for you.** If a subagent stops at a permission prompt, it shows as blocked, and the primary tells you what it is asking. You answer in that pane. `herd send` is refused while a pane is blocked, even with `--force`, because its Enter would answer the prompt.

## Worktrees and handoffs

Subagents share a folder unless you say otherwise. If two might edit the same repo, give each one a worktree with `--worktree`, or just ask for worktrees.

- The default branch is `herd/<name>`, and the checkout lives at `~/.claude/herd/worktrees/<repo>/<name>`.
- A worktree starts from the last commit, so uncommitted changes and ignored files such as `.env` are not in it.
- Subagents commit there. They are told not to merge or push.
- `herd close` removes a worktree, and the branch if herd created it, only if nothing would be lost. Uncommitted changes, ignored files, or commits not on the base branch all keep it, and `--force` does not change that.
- Spawning the same name with `--worktree` reattaches to kept work.

`herd wrapup` asks each subagent to commit to its branch and write a handoff to `~/.claude/herd/handoffs/<name>.md`, with its status, decisions, next steps, and open questions. The file sits outside the repo, so it stays out of pull requests and survives worktree removal. If you spawn that name again later, herd pastes the handoff into the new brief, and the work carries on.

If the primary restarts, its background waits are lost, but the panes keep running. Run `herd resume`, or just tell Claude about it, and it picks them back up.

## When to use herd, and when to use firstmate

[firstmate](https://github.com/kunchenguid/firstmate) solves a related problem, and it can use herdr as a backend too. Its README describes an "agent distro": you clone it and talk to a single agent, the first mate, which spawns autonomous agents in a visible session backend, gives each a clean git worktree, supervises them to completion, and hands you finished PRs, approved local merges, or investigation reports.

| | herd | firstmate |
| --- | --- | --- |
| Best for | Attended work you steer as it goes | Delivering many tasks with less supervision |
| Scale | Up to a few agents | A crew of agents across projects, with optional secondmates on this machine or over SSH |
| Where you work | Your existing Claude session, in the repo you are already in | A session launched inside the firstmate checkout |
| Kinds of task | Anything you would ask Claude | Ship tasks that deliver changes, and scout tasks that produce reports |
| Output | Whatever you asked for, relayed to you | PRs, local merges, or reports |
| Agents | Claude Code in herdr | Several harnesses, such as Claude Code, Codex, and Pi, across tmux, herdr, and other backends |
| Setup | One skill | Clone the repo, sign in to the GitHub CLI, and launch a supported harness inside it |

Use herd if you want to stay in one session and work alongside a few agents, stepping in as they go. Use firstmate if you want to hand off a stream of tasks across repos and get finished results back, without watching each one.

## Known limits

- **Unstable interfaces.** herd reads Claude's transcript files to get final messages and spot background jobs, and it reads the pane's screen to detect unsent text and the permission mode. Neither is a stable API. Run `herd doctor` after a Claude Code update if something looks wrong.
- **Claude Code only.** Subagents are always Claude sessions.
- **Inside herdr only.** Apart from `herd doctor`, herd does nothing outside a herdr pane.
- **Limited panes per tab.** Between 1 and 8 fit, depending on window size. Past that, herd opens more tabs.
- **Token cost.** Each pane is a full session with its own context and tokens. Idle panes get costlier to resume once the prompt cache expires, so close them when done.
- **No nesting.** A subagent cannot spawn its own subagents.
- **Context is not inherited.** Subagents do not see your conversation, only the brief. A pane loads `CLAUDE.md` from its own folder and parents, and herd pastes in the primary's files if the pane starts elsewhere, up to 20,000 characters each. The primary's memory is not passed to panes, so anything needed from it must go in the brief.
- **Paused panes.** `wait` treats an idle pane with background jobs still running as paused, and holds for up to 30 minutes per pause before reporting anyway.
- **Stashes do not count as unsaved.** `herd close` can remove a worktree whose only unsaved work is a `git stash`. The stash stays in the repo's stash list.
- **Ignored files always keep a worktree.** Anything ignored, such as `node_modules`, keeps the worktree on close, even if all the work is merged. Delete those files, then run `herd close` again.
- **Reused branches are kept.** herd only deletes branches it created. A branch that already existed is never deleted, and while it has commits not on the base branch, its worktree stays too.
- **Pane labels cannot start with a dash.** herdr would read one as an option.
- **Pane records are per primary.** State in `~/.claude/herd` is keyed by the primary's pane. After a restart in a different pane, use `herd resume --from <pane-id>`.

## License

MIT. See [LICENSE](LICENSE).
