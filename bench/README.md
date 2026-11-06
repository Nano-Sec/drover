# Drover benchmark

Status: Part 1 is done. Part 2 is built and piloted, but the measured runs have not started, so there is no comparison result yet. Do not base guidance on the pilot numbers below.

## Files

- `lib.py`: isolated herdr session, usage from transcripts, prices.
- `part1_startup.py`: first-turn cost per launch flag set, in real interactive panes.
- `run_part2.py`: the three arms. `score.py`: objective scoring. `check_scorers.py`: run this first.
- `tasks/`: sample projects, task text, and hidden tests.
- `results/`: raw rows. Pane screens were removed, because they held local paths.

Run with `env -u HERD_CHILD python3 bench/...`.

## Prices

Sonnet 5.5, dollars per million tokens, from the live pricing page on 2026-11-07: input 2, 5m cache write 2.50, 1h cache write 4, cache read 0.10, output 10. Claude Code's own `cost-state` record for one session matched these rates exactly.

## Part 1: first turn of a real interactive pane, sonnet

One run per flag set and cache state, except that the haiku sweep repeated the baseline (39,538 and 39,559). Cold is a new folder, warm is a second session in the same folder straight after.

| Launch flags | Prompt tokens | Cold cost | Warm cost | Session id | Slash commands |
|---|---|---|---|---|---|
| default | 38,809 | $0.056 | $0.049 | yes | yes |
| `--disallowedTools Artifact` | 26,048 | $0.055 | $0.048 | yes | yes |
| `--disallowedTools` Artifact, SendFeedback, ReportFindings, ScheduleWakeup, ListAgents | 21,171 | $0.085 | $0.047 | yes | yes |
| `--strict-mcp-config` | 37,126 | $0.050 | $0.042 | yes | yes |
| `--disable-slash-commands` | 35,451 | $0.142 | $0.024 | yes | no |
| auto memory off, via `--settings` | 38,097 | $0.054 | $0.049 | yes | yes |
| `--tools` six tools | 13,283 | $0.053 | $0.011 | yes | yes |
| `--tools` six tools, `--strict-mcp-config` | 10,121 | $0.015 | $0.008 | yes | yes |
| same, plus ToolSearch, WebFetch, WebSearch (Arm C) | 9,438 | $0.016 | $0.009 | yes | yes |
| `--setting-sources project,local` | 35,439 | $0.043 | $0.035 | NO | yes |
| `--safe-mode` | 32,272 | $0.026 | $0.026 | NO | yes |
| `--bare` | none | none | none | NO | yes |

Six tools means Bash, Read, Edit, Write, Glob, Grep.

- Tokens and cost are different questions. About 25,000 tokens of the default prompt are cache reads even in a new folder, at $0.10 per million. Most of the cost is about 12,000 to 14,000 tokens written per session at the 1h rate: the skills listing, the deferred tool list, and MCP notes.
- So removing the Artifact tool cuts 12,800 tokens, about a third, but only about 2 percent of first-turn cost.
- A changed tool list can lose the shared cache. Some cold runs read nothing and cost more than the default, such as `--disable-slash-commands` at $0.142.
- `--tools` alone leaves the 8 MCP tools loaded up front, because there is no ToolSearch to defer them. It needs `--strict-mcp-config`.
- `/context` is not a reliable breakdown here: it estimated 28,400 tokens for a 39,500 token request.
- The brief wrapper costs about 135 to 155 tokens.
- `--setting-sources project,local` and `--safe-mode` drop the user-settings hook. herdr still showed status, but gave no session id, which drover needs for transcripts and which it treats as a held startup prompt. Do not use them for panes.
- `--bare` starts, then answers "Not logged in" on this OAuth account.
- Print mode is not a stand-in: a parallel study measured about 20,000 tokens for the default there, and no saving from `--strict-mcp-config`.

What an Arm C pane cannot do: use Agent, Skill, AskUserQuestion, Artifact, Monitor, TaskStop, ScheduleWakeup, cron or worktree tools, or any MCP server. It keeps Bash, file tools, web tools through ToolSearch, typed slash commands, and CLAUDE.md. Only the tool lists and the slash probe were checked, and only on trivial tasks.

## Part 2 pilots

Single runs on a trivial sample, kept only to size the budget. `pilot1.jsonl` rows for B and C are invalid: the primary blocked on a harness fault, since fixed. Arm A was not piloted on the parallel task.

| Run | Tokens | Cost | Primary turns | Primary tokens | Subagent first prompt |
|---|---|---|---|---|---|
| T1 lookup, A | 282,182 | $0.182 | 4 | 160,392 | 27,993 |
| T1 lookup, B | 509,164 | $0.197 | 8 | 350,123 | 39,195 |
| T1 lookup, C | 392,639 | $0.156 | 8 | 351,245 | 9,545 |
| T4 parallel, B | 949,151 | $0.393 | 12 | 549,104 | about 39,100 |
| T4 parallel, C | 549,862 | $0.244 | 10 | 456,646 | about 9,500 |
