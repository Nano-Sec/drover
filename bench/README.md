# Drover benchmark

Status: Part 1 and Part 2 are done. Do not base guidance on the pilot numbers below, use the measured Part 2 section.

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

## Part 2: drover panes vs native subagents (measured)

Arms: A = native Agent tool subagent, B = drover pane with default flags, C = drover pane with trimmed flags
(`--tools Bash,Read,Edit,Write,Glob,Grep,ToolSearch,WebFetch,WebSearch --strict-mcp-config`). Primary is an interactive
sonnet session in auto mode in every arm. 5 tasks, **2 repeats per cell (30 runs)**, cut from 3 before launch to fit the budget. All 30 ran.
Total about 16.8M tokens counting cache reads and 3.8M of earlier work, about 1M past the 15.8M cap, because the last runs were already in flight.
Raw rows: `results/part2.jsonl`, log `results/part2_run.log`, outputs `results/outputs/part2/`.
Tokens include cache reads. With n=2 the ranges are just the two values, so only gaps far larger than the ranges are claimed.

Median tokens [min-max] / median cost USD / quality (mean score, all runs):

| task | A native | B drover default | C drover trimmed |
|---|---|---|---|
| t1 lookup | 296k [281-312] / 0.133 / 1.0 | 510k [508-512] / 0.197 / 1.0 | 392k [392-393] / 0.156 / 1.0 |
| t2 review | 237k [221-253] / 0.134 / 1.0 | 473k [473-473] / 0.203 / 1.0 | 384k [384-384] / 0.163 / 1.0 |
| t3 fix | 285k [285-286] / 0.145 / 1.0 | 472k [472-472] / 0.205 / 1.0 | 396k [384-408] / 0.173 / 1.0 |
| t4 parallel x3 | 549k [528-571] / 0.271 / 1.0 | 839k [815-862] / 0.377 / 1.0 | 530k [501-558] / 0.233 / 1.0 |
| t5 rule | 255k [254-256] / 0.162 / 1.0 | 475k [474-477] / 0.213 / 1.0 | 395k [388-401] / 0.176 / 1.0 |

Primary vs subagent tokens (medians per cell, summed share): primary is 57% of tokens in A, 67% in B, 88% in C. In C the
subagent pane costs only about 32k to 98k tokens, but the primary still costs 350k+ on single-task runs (8 turns of a roughly
39k-token interactive prompt) against about 160k in A.

Checks: every run used only claude-sonnet-5-5; every run finished; A always used the Agent tool (n_native 1, or 3 on T4) and
no panes; B and C always used drover panes (1, or 3 on T4) and no native agents; T5 subagents saw the rule in all 6 runs.
Quality was 1.0 in all 30 runs, so quality does not separate the arms (the tasks are easy ceiling tasks).

Conclusions:
- Native subagents were cheaper than default drover panes on every task, by roughly 1.5x to 2x in tokens and 1.3x to 1.5x in
  cost. The gaps exceed the spread. Wall time was also shorter (14 to 24 s vs 28 to 43 s).
- Trimmed flags recover part of the gap: C is below B on every task. C is still above A on the four single-pane-or-small tasks
  (about 1.3x to 1.6x tokens, 1.1x to 1.2x cost). On T4 (3 parallel subagents) C is about equal to A in tokens (530k vs 549k)
  and below it in cost (0.233 vs 0.271); token ranges overlap and cost ranges do not (0.227-0.239 vs 0.266-0.276), but with n=2 this is at most a small cost edge, not an established win.
- No quality difference was measurable. Drover's benefit here is visibility and user control, not token savings.

Limits: 2 repeats; easy tasks; 3 runs in parallel shared rate limits and cache, which may affect wall time; auto-mode
classifier calls may be missing from transcripts (unchecked); a drover capability test of Arm C on harder work was not done;
one sonnet native subagent first prompt was about 28k tokens (single sample type, not the 3.5k quoted for small Haiku ones).
