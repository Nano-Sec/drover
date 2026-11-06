#!/usr/bin/env python3
"""A stand-in for the herdr CLI, so the helper can run with no terminal and no Claude.

State lives in the JSON file named by FAKE_HERDR_STATE. Responses copy real herdr 0.8.0
output, and tests/fixtures/herdr holds the real samples they are checked against. Panes sit
in a split tree per tab, which reproduces real pane sizes. Flags this file does not know exit
with status 2, as real herdr does, so a typo in the helper fails a test.
"""
import fcntl, json, os, re, sys

SIDEBAR = 26  # columns herdr keeps for its sidebar
TITLE = 1     # rows herdr keeps above the panes
SETTLED = ["idle", "done", "blocked"]
RULE = "\x1b[38;2;136;136;136m" + "─" * 40 + "\x1b[0m"
IDLE_SCREEN = f"⏺ finished\n\n{RULE}\n❯ \n{RULE}\n  auto mode on\n"


class Stop(Exception):
    def __init__(self, code, out="", err=""):
        self.code, self.out, self.err = code, out, err


def ok(kind, command, **result):
    return json.dumps({"id": f"cli:{command}", "result": {**result, "type": kind}})


def fail(command, code, message):
    raise Stop(1, err=json.dumps({"error": {"code": code, "message": message}, "id": f"cli:{command}"}) + "\n")


def parse(args, values=(), repeated=(), switches=()):
    """Return (positional, flags). Everything after -- stays in flags['--']."""
    pos, flags = [], {"--": []}
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            flags["--"] = args[i + 1:]
            break
        if a in values or a in repeated:
            i += 1
            if i >= len(args):
                raise Stop(2, err=f"error: {a} needs a value\n")
            if a in repeated:
                flags.setdefault(a, []).append(args[i])
            else:
                flags[a] = args[i]
        elif a in switches:
            flags[a] = True
        elif a.startswith("--"):
            raise Stop(2, err=f"error: unexpected argument {a}\n")
        else:
            pos.append(a)
        i += 1
    return pos, flags


def leaves(node):
    if "pane" in node:
        return [node["pane"]]
    return leaves(node["a"]) + leaves(node["b"])


def lay_out(node, x, y, w, h, out):
    if "pane" in node:
        out.append({"focused": False, "pane_id": node["pane"], "rect": {"height": h, "width": w, "x": x, "y": y}})
    elif node["dir"] == "right":
        first = int(w * node["ratio"] + 0.5)
        lay_out(node["a"], x, y, first, h, out)
        lay_out(node["b"], x + first, y, w - first, h, out)
    else:
        first = int(h * node["ratio"] + 0.5)
        lay_out(node["a"], x, y, w, first, out)
        lay_out(node["b"], x, y + first, w, h - first, out)
    return out


def area(state):
    return {"height": state["window"][1] - TITLE, "width": state["window"][0] - SIDEBAR, "x": SIDEBAR, "y": TITLE}


def split_leaf(node, pane, new, direction):
    if node.get("pane") == pane:
        return {"dir": direction, "ratio": 0.5, "a": {"pane": pane}, "b": {"pane": new}}
    if "pane" not in node:
        node["a"] = split_leaf(node["a"], pane, new, direction)
        node["b"] = split_leaf(node["b"], pane, new, direction)
    return node


def drop_leaf(node, pane):
    if node.get("pane") == pane:
        return None
    if "pane" in node:
        return node
    a, b = drop_leaf(node["a"], pane), drop_leaf(node["b"], pane)
    if a is None:
        return b
    if b is None:
        return a
    node["a"], node["b"] = a, b
    return node


def move_border(node, pane, amount):
    """Shrink the pane by moving the nearest border below it up. Returns True when done."""
    if "pane" in node:
        return False
    if move_border(node["a"], pane, amount) or move_border(node["b"], pane, amount):
        return True
    if node["dir"] == "down" and pane in leaves(node["a"]):
        node["ratio"] = max(0.1, node["ratio"] - amount)
        return True
    return False


def pane_info(state, pid):
    p = state["panes"][pid]
    return {"agent_status": "unknown", "cwd": p["cwd"], "focused": False, "foreground_cwd": p["cwd"], "pane_id": pid,
            "revision": 0, "tab_id": p["tab"], "terminal_id": "term_" + pid, "workspace_id": pid.split(":")[0]}


def new_pane(state, tab, cwd, env):
    pid = f"{state['workspace']}:p{state['next_pane']:X}"
    state["next_pane"] += 1
    state["panes"][pid] = {"tab": tab, "cwd": cwd, "env": env, "agent": None, "prompts": [], "keys": [],
                           "draft": "", "screen": None, "steps": [], "busy": False}
    return pid


def agent_view(pid, pane):
    a = dict(pane["agent"])
    a.update(pane_id=pid, tab_id=pane["tab"], workspace_id=pid.split(":")[0], agent="claude", focused=False,
             interactive_ready=True, revision=1, state_change_seq=1, terminal_id="term_" + pid)
    a.setdefault("cwd", pane["cwd"])
    a.setdefault("foreground_cwd", a["cwd"])
    return a


def find_agent(state, target, command):
    for pid, p in state["panes"].items():
        if p["agent"] and (pid == target or p["agent"].get("name") == target):
            return pid, p
    fail(command, "agent_not_found", f"agent target {target} not found")


def set_session(agent, value):
    agent["agent_session"] = {"agent": "claude", "kind": "id", "source": "herdr:claude", "value": value}


def close_pane(state, pid):
    tab = state["tabs"][state["panes"][pid]["tab"]]
    tab["root"] = drop_leaf(tab["root"], pid)
    if tab["root"] is None:
        del state["tabs"][state["panes"][pid]["tab"]]
    del state["panes"][pid]


def apply_step(state, pid, step):
    """One scripted change, used up by the next agent wait on this pane."""
    for path, line in step.get("append", []):
        with open(path, "a") as f:
            f.write(line + "\n")
    if step.get("gone"):
        close_pane(state, pid)
    elif "status" in step:
        state["panes"][pid]["agent"]["agent_status"] = step["status"]
    return step


def agent_cmd(state, verb, args):
    command = f"agent:{verb}"
    if verb == "list":
        agents = [agent_view(pid, p) for pid, p in state["panes"].items() if p["agent"]]
        return ok("agent_list", command, agents=agents)
    if verb == "get":
        pid, p = find_agent(state, args[0], command)
        delayed = p["agent"].pop("session_after_gets", None)
        if delayed:
            delayed["gets"] -= 1
            if delayed["gets"] <= 0:
                set_session(p["agent"], delayed["value"])
            else:
                p["agent"]["session_after_gets"] = delayed
        view = agent_view(pid, p)
        view.pop("session_after_gets", None)
        return ok("agent_info", command, agent=view)
    if verb == "start":
        pos, flags = parse(args, values=["--kind", "--pane", "--timeout"])
        name, pid = pos[0], flags["--pane"]
        behaviour = state["start"].get(name, "ok")
        state["start_argv"][name] = flags["--"]
        if behaviour == "fail":
            fail(command, "agent_start_failed", "agent did not become ready")
        pane = state["panes"].get(pid)
        if pane is None:
            fail(command, "pane_not_found", f"pane {pid} not found")
        pane["agent"] = {"name": name, "agent_status": "idle"}
        state["sessions"] += 1
        session = f"session-{state['sessions']}"
        if behaviour == "held":
            pane["agent"]["agent_status"] = "blocked"
            pane["agent"]["held_session"] = session
        elif behaviour == "slow":
            pane["agent"]["session_after_gets"] = {"gets": 2, "value": session}
        else:
            set_session(pane["agent"], session)
        view = agent_view(pid, pane)
        view.pop("session_after_gets", None)
        return ok("agent_started", command, agent=view, argv=["claude", *flags["--"]])
    if verb == "prompt":
        pos, flags = parse(args, values=["--timeout"], repeated=["--until"], switches=["--wait"])
        pid, p = find_agent(state, pos[0], command)
        if pid in state["prompt_fail"]:
            fail(command, "agent_prompt_stalled", "no lifecycle change")
        text = pos[1]
        if p["agent"]["agent_status"] == "blocked":
            # Real herdr writes the text and Enter, and Enter picks the highlighted option.
            p["answered"] = text
            p["agent"]["agent_status"] = "working"
            return ok("agent_prompted", command, agent=agent_view(pid, p))
        p["prompts"].append(p["draft"] + text)  # a prompt sent on a draft merges with it
        p["draft"] = ""
        p["agent"]["agent_status"] = "working"
        return ok("agent_prompted", command, agent=agent_view(pid, p))
    if verb == "wait":
        pos, flags = parse(args, values=["--timeout"], repeated=["--until"])
        pid, p = find_agent(state, pos[0], command)
        until = flags.get("--until", SETTLED)
        if p["steps"]:
            step = apply_step(state, pid, p["steps"].pop(0))
            if step.get("gone"):
                fail(command, "agent_not_found", f"agent target {pid} not found")
        elif p["agent"]["agent_status"] == "working" and "working" not in until and not p["busy"]:
            p["agent"]["agent_status"] = "idle"
        if p["agent"]["agent_status"] not in until:
            fail(command, "timeout", "timed out waiting for agent status")
        return ok("agent_info", command, agent=agent_view(pid, p))
    if verb == "read":
        pos, flags = parse(args, values=["--source", "--format", "--lines"])
        pid, p = find_agent(state, pos[0], command)
        screen = p["screen"] or IDLE_SCREEN
        if p["draft"]:
            head, sep, tail = screen.rpartition("❯ ")
            screen = head + sep + p["draft"] + tail
        if flags.get("--format") != "ansi":
            screen = re.sub(r"\x1b\[[0-9;:]*m", "", screen)
        raise Stop(0, out=screen)
    if verb == "send-keys":
        pid, p = find_agent(state, args[0], command)
        p["keys"].append(args[1:])
        if "ctrl+u" in args[1:] and not p.get("stuck_draft"):
            p["draft"] = ""
        return ok("ok", command)
    raise Stop(2, err=f"error: unknown agent command {verb}\n")


def pane_cmd(state, verb, args):
    command = f"pane:{verb}"
    if verb == "layout":
        _, flags = parse(args, values=["--pane"])
        pid = flags["--pane"]
        if pid not in state["panes"]:
            fail(command, "pane_not_found", "pane not found")
        tab = state["panes"][pid]["tab"]
        a = area(state)
        panes = lay_out(state["tabs"][tab]["root"], a["x"], a["y"], a["width"], a["height"], [])
        return ok("pane_layout", command, layout={"area": a, "panes": panes, "splits": [], "tab_id": tab,
                                                  "workspace_id": pid.split(":")[0], "zoomed": False})
    if verb == "split":
        _, flags = parse(args, values=["--pane", "--direction", "--cwd"], repeated=["--env"], switches=["--no-focus"])
        target = flags["--pane"]
        if target not in state["panes"]:
            fail(command, "pane_not_found", f"pane {target} not found")
        tab = state["panes"][target]["tab"]
        pid = new_pane(state, tab, flags["--cwd"], flags.get("--env", []))
        state["panes"][pid]["no_focus"] = flags.get("--no-focus", False)
        state["tabs"][tab]["root"] = split_leaf(state["tabs"][tab]["root"], target, pid, flags["--direction"])
        return ok("pane_info", command, pane=pane_info(state, pid))
    if verb == "resize":
        _, flags = parse(args, values=["--pane", "--direction", "--amount"])
        pid = flags["--pane"]
        if flags["--direction"] != "up":
            raise Stop(2, err="error: the fake only models resizing up\n")
        move_border(state["tabs"][state["panes"][pid]["tab"]]["root"], pid, float(flags["--amount"]))
        return ok("pane_resize", command, resize={"changed": True, "pane_id": pid})
    if verb == "close":
        pid = args[0]
        if pid not in state["panes"]:
            fail(command, "pane_not_found", f"pane {pid} not found")
        if pid not in state["close_stuck"]:
            close_pane(state, pid)
        return ok("ok", command)
    raise Stop(2, err=f"error: unknown pane command {verb}\n")


def tab_cmd(state, verb, args):
    command = f"tab:{verb}"
    if verb == "create":
        _, flags = parse(args, values=["--workspace", "--cwd", "--label"], repeated=["--env"], switches=["--no-focus"])
        tab = f"{flags['--workspace']}:t{state['next_tab']}"
        state["next_tab"] += 1
        pid = new_pane(state, tab, flags["--cwd"], flags.get("--env", []))
        state["panes"][pid]["no_focus"] = flags.get("--no-focus", False)
        state["tabs"][tab] = {"label": flags["--label"], "root": {"pane": pid}}
        return ok("tab_created", command, tab={"label": flags["--label"], "tab_id": tab, "pane_count": 1},
                  root_pane=pane_info(state, pid))
    if verb == "rename":
        tab, label = args
        if tab not in state["tabs"]:
            fail(command, "tab_not_found", f"tab {tab} not found")
        state["tabs"][tab]["label"] = label
        return ok("tab_info", command, tab={"label": label, "tab_id": tab})
    raise Stop(2, err=f"error: unknown tab command {verb}\n")


def run(state, argv):
    if len(argv) < 2:
        raise Stop(2, err="error: missing command\n")
    group = {"agent": agent_cmd, "pane": pane_cmd, "tab": tab_cmd}.get(argv[0])
    if not group:
        raise Stop(2, err=f"error: unknown command {argv[0]}\n")
    return group(state, argv[1], argv[2:])


def main():
    path = os.environ["FAKE_HERDR_STATE"]
    with open(path + ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with open(path) as f:
            state = json.load(f)
        argv = sys.argv[1:]
        state["calls"].append(argv)
        try:
            result = Stop(0, out=run(state, argv) + "\n")
        except Stop as stop:
            result = stop
        with open(path, "w") as f:
            json.dump(state, f)
    sys.stdout.write(result.out)
    sys.stderr.write(result.err)
    sys.exit(result.code)


if __name__ == "__main__":
    main()
