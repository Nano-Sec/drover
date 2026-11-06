"""Shared pieces of the drover benchmark: a safe herdr session, and reading usage from transcripts.

Run everything here with HERD_CHILD unset. Nothing in this folder touches the default herdr session.
"""
import ast, glob, json, os, re, shutil, subprocess, sys, tempfile, time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BENCH = os.path.join(REPO, "bench")
RESULTS = os.path.join(BENCH, "results")
HELPER = os.path.join(REPO, "skills", "drover", "drover")
WORK_ROOT = os.path.expanduser("~/Documents/claude_workspace/drover_bench_work")  # plain, so Claude trusts it
PROJECTS = os.path.expanduser("~/.claude/projects")

# Live prices from platform.claude.com/docs/en/about-claude/pricing, dollars per million tokens.
SONNET = {"input": 2.0, "write_5m": 2.5, "write_1h": 4.0, "read": 0.10, "output": 10.0}
HAIKU = {"input": 0.10, "write_5m": 0.125, "write_1h": 0.20, "read": 0.01, "output": 0.50}


def price_of(model):
    return HAIKU if "haiku" in (model or "") else SONNET


def scrub_env():
    """Drop every variable that would turn transcripts off or point at the user's session."""
    for k in list(os.environ):
        if k.startswith(("HERDR_", "HERD_", "DROVER_", "CLAUDE")):
            del os.environ[k]


def box(name, state_dir=None, cols=240, rows=70):
    """An isolated named herdr session with sound off. The caller must stop() it."""
    if name == "default":
        raise ValueError("refusing the default session")
    scrub_env()
    sys.path.insert(0, REPO)
    from tests.live_box import Box
    os.makedirs(WORK_ROOT, exist_ok=True)
    extra = {"DROVER_STATE_DIR": state_dir} if state_dir else None
    return Box(HELPER, name=name, cols=cols, rows=rows, cwd=WORK_ROOT, extra_env=extra)


def project_dir(cwd):
    return os.path.join(PROJECTS, re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))


def lines(path):
    with open(path, errors="replace") as f:
        for line in f:
            try:
                yield json.loads(line)
            except ValueError:
                continue


def messages(path):
    """One row per API response in a transcript. A response spans several lines, one per
    content block, all carrying the same id, so summing lines would count it several times."""
    seen = {}
    for d in lines(path):
        m = d.get("message") if d.get("type") == "assistant" else None
        if not m or not m.get("usage") or m.get("model") == "<synthetic>":
            continue
        u = m["usage"]
        cc = u.get("cache_creation") or {}
        total_write = u.get("cache_creation_input_tokens", 0)
        w1 = cc.get("ephemeral_1h_input_tokens", 0)
        w5 = cc.get("ephemeral_5m_input_tokens", total_write - w1)
        seen[m.get("id") or d.get("uuid")] = {
            "ts": d.get("timestamp"), "model": m.get("model"),
            "input": u.get("input_tokens", 0), "read": u.get("cache_read_input_tokens", 0),
            "write_5m": w5, "write_1h": w1, "output": u.get("output_tokens", 0),
        }
    return list(seen.values())


def cost(row):
    p = price_of(row.get("model"))
    return sum(row[k] * p[k] for k in ("input", "read", "write_5m", "write_1h", "output")) / 1e6


def add(rows):
    out = {k: 0 for k in ("input", "read", "write_5m", "write_1h", "output")}
    for r in rows:
        for k in out:
            out[k] += r[k]
    out["turns"] = len(rows)
    out["cost"] = round(sum(cost(r) for r in rows), 5)
    out["all_tokens"] = sum(out[k] for k in ("input", "read", "write_5m", "write_1h", "output"))
    return out


def prompt_size(row):
    """Everything the model read for this response, whatever the cache did with it."""
    return row["input"] + row["read"] + row["write_5m"] + row["write_1h"]


def transcripts(cwd):
    """Every session in this folder, and every native subagent of each.
    Returns (top level session paths, subagent paths)."""
    d = project_dir(cwd)
    return sorted(glob.glob(os.path.join(d, "*.jsonl"))), sorted(glob.glob(os.path.join(d, "*", "subagents", "**", "*.jsonl"), recursive=True))


def request_shape(path):
    """The system blocks and tools of the first main request, parsed from the transcript."""
    for d in lines(path):
        if d.get("type") == "api-request-shape":
            s = d["shape"]
            return s if isinstance(s, dict) else json.loads(s)
    return None


def first_user_blocks(path):
    for d in lines(path):
        if d.get("type") == "api-request-blob":
            m = d["message"]
            m = m if isinstance(m, dict) else json.loads(m)
            if m.get("role") == "user":
                return m["content"] if isinstance(m["content"], list) else [{"type": "text", "text": m["content"]}]
    return []
