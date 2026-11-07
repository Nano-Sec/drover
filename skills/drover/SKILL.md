---
name: drover
description: Run subagents as visible Claude sessions in herdr panes, so the user can watch and message each one. Native Agent tool subagents are the default and are cheaper and faster, so use this only when the user asks for panes, visible agents, or drover (or invokes /drover), wants to watch or message an agent as it works, or when long work needs worktrees, handoffs, or resume. Do not use it for ordinary requests for subagents or parallel agents. Its first step checks whether the session is inside herdr (HERDR_ENV=1) and falls back to the Agent tool if not. Not for use inside a drover pane (DROVER_CHILD=1).
---

# Drover

You are the primary. Each subagent is a full interactive Claude session in its own herdr pane, which the user can watch and type into. You brief, steer, and collect.

Run everything through the helper:

```bash
H="${CLAUDE_SKILL_DIR}/drover"
$H run <name> "<brief>" [spawn options] [--keep] [--timeout ms]  # spawn, wait, print the result, close: one pane, one command
$H spawn <name> "<brief>" [--model sonnet] [--effort low|medium|high|xhigh|max] [--preset scout|build] [--tools lean] [--mode manual] [--cwd <path>] [--tab "<label>"] [--label "<text>"] [--worktree [branch]]
$H send <name> "<message>"     # steer a subagent, works mid-task
$H wrapup [names...] [--force] # ask subagents to commit and write a handoff, default all
$H wait <name> [name...] [--close] # blocks until all settle, or one is blocked, then prints each result or prompt
$H result <name>               # same output, without waiting
$H status                      # window size, subagents per tab, and each subagent's state
$H rename <name> "<label>"     # rename the tab holding that subagent, refused in the primary tab
$H rename <name> --pane "<label>" # relabel its pane, which also works in the primary tab
$H close <name> | --all        # skips working or blocked panes unless --force, never deletes unmerged work
$H resume [--from <pane-id>]   # after a restart: reconcile state and list the waits to start
$H doctor                      # check the setup and say how to fix what fails, works outside herdr too
```

The helper sits next to this file. Shell variables may not carry over between Bash calls, so set `H` in each command.

Pass `-` as the brief or message to read it from stdin, which is best for multi-line text. Put `--worktree` after the brief, since it takes an optional branch. `--preset scout` is haiku with low effort and `--preset build` is sonnet with medium effort, and an explicit `--model` or `--effort` overrides it. `--tools lean` is opt-in only: it starts the pane with just Bash, Read, Edit, Write, Glob, Grep, ToolSearch, WebFetch, WebSearch and no MCP servers. Such a pane cannot use Agent, Skill, AskUserQuestion, Artifact, Monitor, TaskStop, ScheduleWakeup, cron or worktree tools, or any MCP server, so use it only for plain file, shell, and web work. Give `rename` a tab label or `--pane`, not both.

## Workflow

1. **No separate check.** The helper refuses in the two cases that matter. If it says `not running inside herdr`, use the Agent tool instead. If it says this pane is a drover subagent, do the work yourself.
2. **Brief fully.** Subagents do not see this conversation. Include the goal, paths, constraints, and what to report.
3. **One pane:** a single Bash call with `run_in_background: true` running `$H run <name> "<brief>"`. It spawns, waits, prints the result, and closes the pane. **Several panes:** spawn each (they take turns on a lock), then one background call `$H wait a b c --close`. Then end your turn: you are woken when it finishes, so never poll, never run `wait` in the foreground, and never loop on `status`. If a pane is blocked, `wait` returns early with its prompt and the names still running.
4. **Relay.** The output already contains the final message. Summarize it for the user, and do not read the full transcript or pane unless something looks wrong.
5. **Steer** when the user asks, with `$H send`. If the subagent had settled, start a new background `wait`. If a wait is still running, leave it. `wait` tracks state, not individual prompts, so after several sends check the message answers everything. An idle pane with background jobs still running counts as paused, so `wait` keeps holding, for up to 30 minutes per pause.
6. **Closing** is built into `run` and `wait --close`, because idle panes get costlier to resume once the prompt cache expires. Pass `--keep` to `run`, or leave off `--close`, if the user asked to keep a pane or has been talking to it. Only panes that settled normally are closed: blocked, held, timed out, and paused ones stay open and are reported. Transcripts survive closing.

## Stopping for now

When the user says they are stopping for now, hand off before closing anything:

1. Run `$H wrapup`, or name specific subagents. Each pane is told to commit to its task branch (never pushing, never on main), write a handoff to `~/.claude/drover/handoffs/<name>.md` (wrapup prints the path), and report its branch, worktree path, and handoff path. Working panes get the message too. The file sits outside the repo so it stays out of PRs and survives worktree removal.
2. Read the output. Gone, blocked, unsent-text, and no-input-box panes are skipped and listed. Tell the user about each. For unsent text, ask the user first. `--force` discards the draft before sending, because a message sent on top of a draft is read as pasted text and ignored. For a missing input box, `--force` sends anyway, so use it only if the user says so. `--force` never reaches a blocked pane: once its prompt is answered, run wrapup for it again.
3. Start one background `$H wait <names>` for the panes that were asked.
4. As each wait finishes, relay the branch, worktree path, and handoff path to the user.
5. Before closing a pane, run `test -f ~/.claude/drover/handoffs/<name>.md`. Wrapup moves any older handoff to `<name>.md.prev`, so the file existing means this wrapup wrote it. If missing, do not close that pane: say so, and see `$H result <name>`.

## Handling states

- **blocked:** the `run` or `wait` output shows the prompt, and the pane stays open. Tell the user which pane needs them and what it is asking. Do not approve on their behalf. `send` is refused while a pane is blocked, even with `--force`, because its Enter would answer the prompt, so the user responds in that pane. Once they have, start a new background `wait`.
- **held at the trust prompt:** spawn says so and shows `session pending`. Claude asks once per git root it does not trust yet. Tell the user which pane needs them. Never answer it, send keys to it, or edit `~/.claude.json`. Start the usual background `wait` anyway: drover stored the brief, and `wait` delivers it once the user accepts, then waits for the result. `send` is refused until then. If the user declines, the wait reports gone.
- **gone:** the pane or agent exited. Report it, with the last message if there is one.
- **send refused for unsent text:** the user is probably typing in that pane. Tell them, and only use `--force` if they say so. It discards their text.
- **send refused because the input box cannot be found:** the pane may show a dialog or hold unsent text. Tell the user, and use `--force` only if they say so. It sends on top of whatever is there.
- **spawn fails, or no transcript was found:** run `$H doctor` and tell the user what it reports.

## Defaults

- **Permissions:** auto mode. Use `--mode manual` only if the user asks for approval prompts or the task is risky. If auto mode is unavailable, spawn warns and the pane runs in manual mode. Tell the user, and expect blocked states at approval prompts.
- **Model:** the user's default. For simple work use `--preset scout` or `--preset build`.
- **Project context:** a pane loads `CLAUDE.md` from its own folder and parents. If it starts outside the primary's folder, as every worktree does, spawn pastes the primary's project `CLAUDE.md` files into the brief (20,000 characters each). Memory is not passed on, so put anything needed from it in the brief.
- **Parallel edits:** subagents share a directory unless told otherwise. If two may edit the same repo, pass `--worktree` to each.
- **Panes or tabs:** if the user asks for panes, use the primary's tab, which is what you get without `--tab`. If they ask for tabs, pass `--tab "<label>"`. Otherwise panes suit work the user will watch or steer, and tabs suit long or unattended work. Tab labels name the work (`Auth audit`, never `drover`), and agents sharing a label share a tab. Anything over a tab's capacity overflows to a new tab.
- **Pane labels:** pass `--label "<text>"` with a short label naming the work, as for tabs, such as `Login flake`. The default is the agent's name. Change it with `$H rename <name> --pane`. It cannot start with a dash.
- **Limits:** a tab holds 1 to 8 subagents depending on window size, checked at each spawn (`$H status` shows it). Past that, a group opens a numbered tab (`Auth audit 2`), and a subagent without `--tab` gets its own. Focus stays on the primary, and drover never renames its tab.
- **Locations:** `DROVER_STATE_DIR` replaces `~/.claude/drover`, so registries, worktrees, and handoffs all move, and the paths in this file move with them. `DROVER_PROJECTS_DIR` replaces `~/.claude/projects`, where drover reads transcripts. Set it if Claude keeps its files elsewhere.

## Worktrees

`--worktree` gives a subagent its own checkout, so parallel subagents on one repo cannot collide. The base repo is `--cwd`, or the current directory. Spawn fails before opening a pane if that is not a git repo. The default branch is `drover/<name>`, and the worktree lives at `~/.claude/drover/worktrees/<repo>/<name>`. It starts from the base repo's last commit, so uncommitted changes and ignored files such as `.env` are not in it. The subagent is told to commit there and not to merge or push. Merging is yours or the user's.

- **Reattaching:** if the branch exists or a closed subagent left a worktree, spawn reuses it and prints `reattached`. Use the same name with `--worktree` to carry on kept work. Spawn refuses if a live agent is in that worktree, if the branch is checked out in the main working copy, or if the name has a worktree on record and you pass another branch or omit `--worktree`.
- **Closing:** `close` always closes the pane, then removes the worktree and the branch only if nothing would be lost. Uncommitted changes, ignored files, commits not on the base branch, or a failed check all keep the worktree and branch, and it prints where they are. `--force` does not change this. It only overrides the working or blocked check. drover only deletes branches it created, so a branch that already existed always stays. A `git stash` does not count as unsaved, so have subagents commit instead.
- **Kept work:** the entry stays in `status` as `kept`. Tell the user the branch and path. After the work is merged, run `close` again to clean up. Discard unmerged work only if the user asks: `git -C <repo> worktree remove --force <path>`, then `git -C <repo> branch -D <branch>`, then `close`.

## Handoffs

If `~/.claude/drover/handoffs/<name>.md` exists, spawn pastes it into the brief, up to 20,000 characters, and prints `handoff:`. Reuse the same name to continue earlier work. If a longer handoff was cut off, the subagent reads the rest from that file, which may show a permission prompt under `blockReadsOutsideWorkingDirectories`. That is an ordinary **blocked** state.

## After a restart

Background waits die with the primary session. If you restart in a herdr pane, or the user mentions subagents you have no record of, run `$H resume` before anything else.

- It reports each subagent as running, settled, blocked, gone, or kept, and follows panes that moved to another workspace.
- It prints the `wait` commands to start with Bash `run_in_background: true`, and the `result` commands to read now.
- Gone and kept entries stay listed until you `close` them, and `result` still gives a gone subagent's last message.
- Registries are per primary pane. If this pane has none, `resume` lists the others. Confirm with the user which is yours, then run `$H resume --from <pane-id>`. It refuses a pane with a live agent unless `--force`, which is right only if that agent is not their primary.

Spawn only what the task needs: each pane is a full session and costs more than a native subagent.
