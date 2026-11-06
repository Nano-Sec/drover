#!/usr/bin/env python3
"""Part 1: what makes up a pane's first turn, and which real launch flags cut it.

Starts Claude in a pane of an isolated herdr session, once per flag set, sends a drover-style
brief with a trivial task, and reads real usage and the real request from the transcript.
Usage: env -u HERD_CHILD python3 bench/part1_startup.py <haiku|sonnet> [config names...]
"""
import json, os, re, shutil, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

TASK = "Reply with exactly the word ok, and use no tools."
# Same text as BRIEF in the helper.
BRIEF = ("You are a subagent named probe, running in your own herdr pane. A primary Claude session delegated this "
         "task to you, and the user can watch and message you here directly. Treat messages in this pane as coming "
         "from the user or the primary.\n\nRules: do the task yourself and do not start further subagents or panes. "
         "The primary reads only your final message, so end with a complete, self-contained report of what you did "
         "and found, including file paths.\n\nTask:\n" + TASK)
TRIM = "Artifact,SendFeedback,ReportFindings,ScheduleWakeup,ListAgents"
SIX = "Bash,Read,Edit,Write,Glob,Grep"
CONFIGS = {
    "base": [],
    "base_repeat": [],
    "plain_prompt": [],  # the same launch, without the brief wrapper
    "no_mcp": ["--strict-mcp-config"],
    "no_skills": ["--disable-slash-commands"],
    "no_artifact": ["--disallowedTools", "Artifact"],
    "trim_tools": ["--disallowedTools", TRIM],
    "core_tools": ["--tools", "Bash,Read,Edit,Write"],
    "no_automemory": ["--settings", '{"autoMemoryEnabled":false}'],
    "project_settings_only": ["--setting-sources", "project,local"],
    "exclude_dynamic": ["--exclude-dynamic-system-prompt-sections"],
    "safe_mode": ["--safe-mode"],
    "bare": ["--bare"],
    "trim_no_mcp_no_skills": ["--disallowedTools", TRIM, "--strict-mcp-config", "--disable-slash-commands"],
    "core_no_mcp_no_skills": ["--tools", "Bash,Read,Edit,Write", "--strict-mcp-config", "--disable-slash-commands"],
    "tools6": ["--tools", SIX],
    "tools6_no_mcp": ["--tools", SIX, "--strict-mcp-config"],
    "tools6_no_mcp_no_slash": ["--tools", SIX, "--strict-mcp-config", "--disable-slash-commands"],
    "tools6_search_no_mcp": ["--tools", SIX + ",ToolSearch,WebFetch,WebSearch", "--strict-mcp-config"],
    "tiny_system_prompt": ["--system-prompt", "You are a coding agent.", "--tools", "Bash,Read,Edit,Write",
                           "--strict-mcp-config", "--disable-slash-commands"],
}


def sections(path):
    """Characters in each part of the real first request, measured, not estimated."""
    s = lib.request_shape(path)
    if not s:
        return None
    tools = {t.get("name"): len(json.dumps(t)) for t in s.get("tools", [])}
    out = {"system_chars": sum(len(b.get("text", "")) for b in s.get("system", [])), "tool_chars": tools}
    late = ""
    user = 0
    for d in lib.lines(path):
        if d.get("type") == "api-request-blob":
            m = d["message"]
            c = m.get("content")
            text = c if isinstance(c, str) else "".join(b.get("text", "") for b in c)
            if m.get("role") == "system":
                late += text
            else:
                user += len(text)
    marks = [("env", "# Environment"), ("deferred_tools", "The following tools just became available"),
             ("mcp_instructions", "# MCP Server Instructions"), ("skills", "The following skills are available")]
    found = sorted((late.find(t), n) for n, t in marks if t in late)
    parts = {}
    for i, (pos, n) in enumerate(found):
        parts[n] = (found[i + 1][0] if i + 1 < len(found) else len(late)) - pos
    out["late_system_chars"] = parts
    out["user_chars"] = user
    return out


def run(b, model, name, flags, heat="cold"):
    """cold makes a fresh folder. warm reuses it at once, the way a second pane in one folder would."""
    cwd = os.path.join(lib.WORK_ROOT, f"p1_{model}_{name}")
    if heat == "cold":
        shutil.rmtree(cwd, ignore_errors=True)
        os.makedirs(cwd)
    before = set(lib.transcripts(cwd)[0])
    agent = "p" + re.sub(r"[^a-z0-9]", "", name)[:20]
    tab = b.j("tab", "create", "--workspace", b.workspace, "--cwd", cwd, "--label", name[:16])
    pane = tab["root_pane"]["pane_id"]
    time.sleep(2)
    row = {"config": name, "model": model, "flags": flags, "heat": heat}
    r = b.run("agent", "start", agent, "--kind", "claude", "--pane", pane, "--timeout", "45000", "--",
              "--permission-mode", "auto", "-n", agent, "--model", model, *flags)
    row["started"] = r.returncode == 0
    if r.returncode != 0:
        row["start_error"] = (r.stderr or r.stdout)[:300]
        row["screen"] = b.run("pane", "read", pane, "--source", "recent-unwrapped", "--lines", "15").stdout[-500:]
    else:
        ag = json.loads(r.stdout)["result"]["agent"]
        row["session_reported"] = bool((ag.get("agent_session") or {}).get("value"))
        time.sleep(2)
        text = TASK if name == "plain_prompt" else BRIEF
        r = b.run("agent", "prompt", agent, text, "--wait", "--timeout", "90000")
        row["prompt_rc"] = r.returncode
        time.sleep(3)
        row["screen"] = b.run("agent", "read", agent, "--source", "visible").stdout[-1500:]
        late = b.run("agent", "get", agent)
        row["session_reported_later"] = bool((json.loads(late.stdout)["result"]["agent"].get("agent_session") or {}).get("value")) if late.returncode == 0 else None
        row["status_after"] = json.loads(late.stdout)["result"]["agent"].get("agent_status") if late.returncode == 0 else None
        top = [t for t in lib.transcripts(cwd)[0] if t not in before]
        row["transcripts"] = len(top)
        if top:
            ms = lib.messages(top[0])
            if ms:
                row["first_turn"] = ms[0]
                row["prompt_tokens"] = lib.prompt_size(ms[0])
                row["cost"] = round(lib.cost(ms[0]), 5)
            row["sections"] = sections(top[0])
        if heat == "warm":  # do slash commands still work if a person types one in the pane?
            b.run("agent", "prompt", agent, "/context", "--wait", "--timeout", "30000")
            time.sleep(3)
            row["slash_context_works"] = "Estimated usage" in b.run("agent", "read", agent, "--source", "recent-unwrapped", "--lines", "60").stdout
    b.run("pane", "close", pane)
    print(json.dumps({k: row.get(k) for k in ("config", "heat", "started", "session_reported", "session_reported_later", "status_after", "prompt_tokens", "cost", "slash_context_works")}), flush=True)
    return row


def main():
    model = sys.argv[1]
    names = sys.argv[2:] or list(CONFIGS)
    out = os.path.join(lib.RESULTS, f"part1_{model}.jsonl")
    b = lib.box(f"droverbenchp1{os.getpid()}")
    try:
        with open(out, "a") as f:
            for n in names:
                for heat in ("cold", "warm"):
                    row = run(b, model, n, CONFIGS[n], heat)
                    f.write(json.dumps(row) + "\n")
                    f.flush()
    finally:
        b.stop()


if __name__ == "__main__":
    main()
