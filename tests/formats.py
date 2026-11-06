"""What the helper needs from Claude's and herdr's output, as checks that name what broke.

The format tests run these on the fixtures, and the live tests run them on real output, so a
change in either program fails with a message saying which assumption stopped holding.
"""
import json, re

ANSI = re.compile(r"\x1b\[[0-9;:]*m")
AGENT_KEYS = ("pane_id", "tab_id", "agent_status", "cwd", "foreground_cwd", "name")
STATES = ("idle", "working", "blocked", "done", "unknown")


def transcript_problems(text):
    """Problems with a Claude transcript, as read by last_message and pending_jobs."""
    problems, said = [], False
    for n, line in enumerate(text.splitlines(), 1):
        try:
            d = json.loads(line)
        except ValueError:
            problems.append(f"transcript line {n} is not JSON")
            continue
        if "<task-notification>" in line and not re.search(r"tool-use-id>([^<\\]+)", line):
            problems.append(f"transcript line {n}: task notification has no <tool-use-id>")
        if d.get("type") != "assistant":
            continue
        if "isSidechain" not in d:
            problems.append(f"transcript line {n}: assistant line has no isSidechain")
        content = d.get("message", {}).get("content")
        if not isinstance(content, list):
            problems.append(f"transcript line {n}: assistant message.content is not a list")
            continue
        for block in content:
            if block.get("type") == "text":
                said = said or "text" in block
            elif block.get("type") == "tool_use" and not ("id" in block and isinstance(block.get("input"), dict)):
                problems.append(f"transcript line {n}: tool_use block lacks id or input")
    if not said:
        problems.append("transcript has no assistant text block")
    return problems


def screen_problems(text):
    """Problems with an idle Claude screen, as read by has_draft."""
    tail = [ANSI.sub("", line) for line in text.splitlines()[-10:]]
    if not any(line.lstrip().startswith("❯") for line in tail):
        return ["no input line starting with ❯ in the last 10 screen lines"]
    return []


def agent_problems(agent, session=True):
    """Problems with one agent record from herdr agent list, get or start."""
    problems = [f"agent record has no {k}" for k in AGENT_KEYS if k not in agent]
    if agent.get("agent_status") not in STATES:
        problems.append(f"unknown agent_status {agent.get('agent_status')!r}")
    if session and "value" not in (agent.get("agent_session") or {}):
        problems.append("agent record has no agent_session.value")
    return problems


def layout_problems(layout):
    """Problems with the layout from herdr pane layout."""
    problems = [f"layout area has no {k}" for k in ("width", "height") if k not in layout.get("area", {})]
    for pane in layout.get("panes", []):
        if "pane_id" not in pane:
            problems.append("layout pane has no pane_id")
        problems += [f"layout rect has no {k}" for k in ("x", "y", "width", "height") if k not in pane.get("rect", {})]
    if not layout.get("panes"):
        problems.append("layout has no panes")
    return problems
